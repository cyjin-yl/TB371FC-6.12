#!/usr/bin/env python3
"""Offline evidence-integrity, parser-boundary and privacy regression checks."""
import base64
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/research/2026-11-23/evidence"


def module(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts/research" / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


COLLECT = module("collect_android_hardware")
TRACE = module("capture_android_trace")
HID = module("hid_report")
DISPLAY = module("display_decode")
STOCK = json.loads((EVIDENCE / "android-stock.json").read_text())
PANEL = "/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video"
TIMING = PANEL + "/qcom,mdss-dsi-display-timings/timing@0"


@contextmanager
def fake_tracefs(*, trace_error=None, after_error=None):
    """A filesystem fixture, with no access to live tracing or hardware."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "instances").mkdir()
        clock = [100.0]
        observed = {"sample_phases": [], "disabled_before_remove": False}
        original_mkdir, original_rmdir = Path.mkdir, Path.rmdir
        instance_path = [None]
        state = {"tracing_on": "0", "current_tracer": "nop", "buffer_size_kb": "4096"}

        def mkdir(path, *args, **kwargs):
            value = original_mkdir(path, *args, **kwargs)
            if path.parent == root / "instances" and instance_path[0] is None:
                instance_path[0] = path
                files = {"tracing_on": "0", "current_tracer": "nop", "buffer_size_kb": "128",
                         "trace_clock": "local [mono]", "trace": "",
                         "events/power/cpu_frequency/enable": "0",
                         "per_cpu/cpu0/stats": "overrun: 0\ncommit overrun: 0\ndropped events: 0\n"}
                for relative, contents in files.items():
                    target = path / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(contents)
            return value

        def rmdir(path, *args, **kwargs):
            if path == instance_path[0]:
                observed["disabled_before_remove"] = (
                    (path / "tracing_on").read_text() == "0"
                    and (path / "events/power/cpu_frequency/enable").read_text() == "0")
                shutil.rmtree(path)
            else:
                original_rmdir(path, *args, **kwargs)

        def read(path, limit=8 * 1024 * 1024):
            path = Path(path)
            if str(path) == "/proc/sys/kernel/osrelease":
                return "fixture-kernel"
            if path.name == "trace":
                if trace_error:
                    raise trace_error("PRIVATE_ERROR_PAYLOAD")
                return "fixture-1 [000] d..2 100.1: cpu_frequency: state=691200 cpu_id=0"
            return path.read_text().strip()

        def sample(phase):
            # Simulate all nine reads taking their full timeout. They must
            # happen with tracing disabled and not extend observed_seconds.
            assert (instance_path[0] / "tracing_on").read_text() == "0"
            observed["sample_phases"].append(phase)
            clock[0] += 6.75
            return {"phase": phase, "monotonic_s": clock[0]}

        def sleep(seconds):
            clock[0] += seconds

        with mock.patch.object(TRACE, "ROOT", root), \
             mock.patch.object(TRACE.os, "geteuid", return_value=0), \
             mock.patch.object(Path, "mkdir", mkdir), \
             mock.patch.object(Path, "rmdir", rmdir), \
             mock.patch.object(TRACE, "read", side_effect=read), \
             mock.patch.object(TRACE, "sample_power", side_effect=sample), \
             mock.patch.object(TRACE, "global_state", side_effect=[state, after_error or state]), \
             mock.patch.object(TRACE.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(TRACE.time, "sleep", side_effect=sleep):
            yield observed


class EvidenceTests(unittest.TestCase):
    def test_binary_capture_integrity(self):
        values = [value for props in STOCK["device_tree"]["nodes"].values() for value in props.values()]
        values += [item["descriptor"] for item in STOCK["keyboard_hid"]]
        for value in values:
            raw = base64.b64decode(value["base64"], validate=True)
            self.assertEqual(len(raw), value["size"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), value["sha256"])
            if "be32" in value:
                self.assertEqual(list(struct.unpack(">" + "I" * (len(raw) // 4), raw)), value["be32"])

    def test_real_keyboard_reports(self):
        raw = base64.b64decode(STOCK["keyboard_hid"][0]["descriptor"]["base64"])
        parsed = HID.parse_descriptor(raw)
        self.assertEqual(len(raw), 604)
        self.assertFalse(parsed["warnings"])
        actual = {(row["kind"], row["report_id"]): row["report_bytes_with_id"] for row in parsed["reports"]}
        self.assertEqual(actual, {("input", 3): 29, ("input", 4): 9, ("input", 5): 4,
                                  ("output", 4): 2, ("feature", 2): 2, ("feature", 6): 5})

    def test_hid_rejects_truncation_and_stack_underflow(self):
        for malformed in (b"\x75", b"\xfe\x04", b"\xb4"):
            with self.assertRaises(HID.DescriptorError):
                HID.parse_descriptor(malformed)

    def test_hid_omits_opaque_strings(self):
        secret = b"PRIVATE_IDENTIFIER_SENTINEL"
        raw = b"\xfe" + bytes((len(secret), 0x7F)) + secret
        self.assertNotIn(secret.decode(), json.dumps(HID.parse_descriptor(raw)))

    def test_on_payload_comparison_and_mismatch(self):
        raw = DISPLAY.read_capture(EVIDENCE / "android-stock.json", TIMING, "qcom,mdss-dsi-on-command")
        decoded = DISPLAY.commands(raw)
        self.assertEqual(decoded["command_count"], 88)
        source = REPO / "mainline-port/backports/linux-6.12/panel-novatek-nt36523.c"
        check = DISPLAY.compare_tianma_init(decoded["commands"], source)
        self.assertTrue(check["vendor_payloads_match"])
        self.assertEqual(check["source_vendor_count"], 86)
        changed = copy.deepcopy(decoded["commands"])
        changed[0]["payload_hex"] = "0000"
        self.assertFalse(DISPLAY.compare_tianma_init(changed, source)["vendor_payloads_match"])

    def test_display_truncation_and_wrong_table(self):
        for malformed in (b"\x39", bytes.fromhex("39010000000004ffff")):
            with self.assertRaises(ValueError):
                DISPLAY.commands(malformed)
        with self.assertRaises(ValueError):
            DISPLAY.pps(bytes(127))
        off = DISPLAY.read_capture(EVIDENCE / "android-stock.json", TIMING, "qcom,mdss-dsi-off-command")
        commands = DISPLAY.commands(off)["commands"]
        self.assertEqual([row["wait_ms"] for row in commands], [15, 60])
        with self.assertRaises(ValueError):
            DISPLAY.compare_tianma_init(commands, REPO / "mainline-port/backports/linux-6.12/panel-novatek-nt36523.c")

    def test_collector_excludes_identifiers_and_factory_matrices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel = root / ("sys/firmware/devicetree/base" + PANEL)
            panel.mkdir(parents=True)
            (panel / "qcom,mdss-dsc-slice-per-pkt").write_bytes(struct.pack(">I", 1))
            (panel / "serial-number").write_text("PRIVATE_IDENTIFIER_SENTINEL")
            for name in ("qcom,mac-addr", "bdaddr", "device-id", "unknown-vendor-value"):
                (panel / name).write_text("PRIVATE_IDENTIFIER_SENTINEL")
            factory = root / "sys/firmware/devicetree/base/soc/spi@880000/novatek@0/novatek-mp-criteria-6068@0"
            factory.mkdir(parents=True)
            (factory / "thresholds").write_text("FACTORY_MATRIX_SENTINEL")
            (root / "proc").mkdir()
            (root / "proc/cmdline").write_text("androidboot.serialno=PRIVATE_IDENTIFIER_SENTINEL androidboot.vbmeta.device_state=unlocked")
            result = COLLECT.capture(COLLECT.Reader(temporary))
            encoded = json.dumps(result)
            self.assertNotIn("PRIVATE_IDENTIFIER_SENTINEL", encoded)
            self.assertNotIn("FACTORY_MATRIX_SENTINEL", encoded)
            self.assertEqual(result["boot_arguments"], {"androidboot.vbmeta.device_state": "unlocked"})

    def test_trace_slow_power_reads_do_not_extend_active_window(self):
        with fake_tracefs() as observed:
            result = TRACE.capture(8)
        self.assertTrue(result["capture_succeeded"])
        self.assertEqual(result["observed_seconds"], 8)
        self.assertEqual(observed["sample_phases"], ["before_tracing", "after_tracing"])
        self.assertTrue(observed["disabled_before_remove"])
        self.assertFalse(result["buffer_loss_detected"])

    def test_command_output_failure_and_truncation_are_not_evidence(self):
        cases = ((1, b"PRIVATE_PARTIAL"), (0, b"PRIVATE_OVERSIZE"), (0, b" \n"))
        for returncode, stdout in cases:
            with self.subTest(returncode=returncode, size=len(stdout)):
                reader = COLLECT.Reader("/fixture")
                completed = COLLECT.subprocess.CompletedProcess(["fixture"], returncode, stdout)
                with mock.patch.object(COLLECT.subprocess, "run", return_value=completed):
                    value = COLLECT.command_text(reader, ["fixture"], error_key="fixture", stdout_limit=8)
                self.assertIsNone(value)
                self.assertIn("fixture", reader.errors)
                self.assertNotIn("PRIVATE", json.dumps(reader.errors))
        reader = COLLECT.Reader("/fixture")
        completed = COLLECT.subprocess.CompletedProcess(["fixture"], 0, b"valid\n")
        with mock.patch.object(COLLECT.subprocess, "run", return_value=completed):
            self.assertEqual(COLLECT.command_text(reader, ["fixture"], error_key="fixture", stdout_limit=8), "valid")
        self.assertFalse(reader.errors)

    def test_trace_failure_preserves_cleanup_evidence(self):
        with fake_tracefs(trace_error=TimeoutError) as observed:
            result = TRACE.capture(8)
        self.assertFalse(result["capture_succeeded"])
        self.assertEqual(result["capture_error"], "TimeoutError")
        self.assertTrue(result["instance_removed"])
        self.assertTrue(result["global_settings_unchanged"])
        self.assertTrue(observed["disabled_before_remove"])
        self.assertNotIn("PRIVATE_ERROR_PAYLOAD", json.dumps(result))

    def test_trace_final_global_read_failure_is_unknown(self):
        with fake_tracefs(after_error=TimeoutError("PRIVATE_ERROR_PAYLOAD")):
            result = TRACE.capture(8)
        self.assertFalse(result["capture_succeeded"])
        self.assertIsNone(result["global_settings_unchanged"])
        self.assertTrue(result["instance_removed"])
        self.assertEqual(result["global_after"], {"unavailable": "TimeoutError"})
        self.assertNotIn("PRIVATE_ERROR_PAYLOAD", json.dumps(result))

    def test_trace_discards_process_prefix_and_device_payload(self):
        raw = ("PRIVATE_PROCESS-345 [000] d..2 12.123456: cpu_frequency: state=691200 cpu_id=0\n"
               "PRIVATE_PROCESS-345 [000] d..2 12.123457: cpu_idle: state=4294967295 cpu_id=0\n"
               "PRIVATE_PROCESS-345 [000] d..2 12.123458: device_pm_callback_start: device=PRIVATE_IDENTIFIER_SENTINEL\n")
        result = TRACE.summarize_trace(raw)
        self.assertEqual(result["cpu_frequency_khz"], {"0": [691200]})
        self.assertEqual(result["event_counts"]["device_pm_callback_start"], 1)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_saved_trace_quality_and_cleanup(self):
        good = json.loads((EVIDENCE / "android-trace-summary.json").read_text())
        partial = json.loads((EVIDENCE / "android-trace-idle-partial.json").read_text())
        self.assertIs(good["buffer_loss_detected"], False)
        self.assertIs(partial["buffer_loss_detected"], True)
        for result in (good, partial):
            self.assertTrue(result["global_settings_unchanged"])
            self.assertTrue(result["instance_removed"])
            self.assertFalse(result["cleanup_errors"])
            self.assertEqual(result["summary"]["unparsed_lines"], 0)

    def test_public_evidence_has_no_mac_or_credential_marker(self):
        for path in EVIDENCE.glob("*.json"):
            text = path.read_text()
            self.assertNotRegex(text, r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
            self.assertNotRegex(text, r"-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) .*KEY-----|gh[pousr]_[A-Za-z0-9]{20,}")
        self.assertNotIn("ro.serialno", STOCK["properties"])
        self.assertNotIn("androidboot.serialno", STOCK["boot_arguments"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
