#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Paused-gate regression fixtures; these tests do not execute a guest VM."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import launch_second_stage as launch
from test_boot_formats import Tree, image


BOOTARGS = "console=ttyMSM0,115200n8 module.sig_enforce=1 root=/dev/sda ro"


def final_dtb(start, size):
    return (Tree().begin("").prop("compatible", b"lenovo,tb371fc\0qcom,sm8250\0")
            .prop("#address-cells", struct.pack(">I", 2))
            .prop("#size-cells", struct.pack(">I", 2))
            .begin("chosen").prop("bootargs", BOOTARGS.encode() + b"\0")
            .prop("linux,initrd-start", struct.pack(">Q", start))
            .prop("linux,initrd-end", struct.pack(">Q", start + size))
            .end().end().finish())


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fixture-qemu", timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakeQMP:
    def __init__(self, process, inputs, out, *, corrupt_kernel=False,
                 duplicate_kernel=False, missing_initrd=False, dump_error=False,
                 panic=False, exit_after_gate=False):
        self.process, self.out = process, out
        self.messages, self.commands = [], []
        self.closed = False
        self.dump_error, self.panic = dump_error, panic
        self.exit_after_gate, self.status_queries = exit_after_gate, 0
        base = inputs["kernel_load_base"]
        kernel_start = base + 2 * launch.MIB
        initrd_start = base + 128 * launch.MIB
        dtb_start = (initrd_start + len(inputs["raw"]["initrd"]) + 2 * launch.MIB - 1) & ~(2 * launch.MIB - 1)
        loaded_kernel = bytearray(inputs["raw"]["kernel"])
        if corrupt_kernel:
            # Preserve the entire header: a header-only verifier would pass.
            loaded_kernel[70] ^= 0xff
        self.payloads = {kernel_start: bytes(loaded_kernel),
                         initrd_start: inputs["raw"]["initrd"],
                         dtb_start: final_dtb(initrd_start, len(inputs["raw"]["initrd"]))}
        self.roms = [
            {"start": base, "size": 48, "name": "bootloader"},
            {"start": kernel_start, "size": len(loaded_kernel), "name": str(inputs["paths"]["kernel"])},
            {"start": initrd_start, "size": len(self.payloads[initrd_start]), "name": str(inputs["paths"]["initrd"])},
            {"start": dtb_start, "size": len(self.payloads[dtb_start]), "name": "dtb"},
        ]
        if duplicate_kernel:
            self.roms.append(dict(self.roms[1]))
        if missing_initrd:
            self.roms.pop(2)

    def command(self, name, arguments=None, timeout=15):
        self.commands.append((name, arguments))
        if name == "query-version":
            return {"qemu": {"major": 10, "minor": 0, "micro": 0}, "package": "fixture"}
        if name == "query-status":
            self.status_queries += 1
            if self.exit_after_gate and self.status_queries == 2:
                self.process.returncode = 17
            return {"running": False, "status": "prelaunch"}
        if name == "query-cpus-fast":
            return [{"cpu-index": index} for index in range(8)]
        if name == "human-monitor-command":
            return "\n".join('addr={start:x} size=0x{size:x} mem=ram name="{name}"'.format(**r)
                              for r in self.roms) + "\n"
        if name == "pmemsave":
            if self.dump_error:
                raise ValueError("fixture QMP memory failure")
            Path(arguments["filename"]).write_bytes(self.payloads[arguments["val"]])
            return {}
        if name == "cont":
            text = "Linux version 6.12.114-fixture\n"
            if self.panic:
                text += "Kernel panic - not syncing: fixture failure\nCall trace:\n"
            (self.out / "serial.log").write_text(text)
            self.process.returncode = 0
            return {}
        if name == "quit":
            self.process.returncode = 0
            return {}
        raise AssertionError("unexpected fixture command: " + name)

    def receive(self, timeout):
        return None

    def close(self):
        self.closed = True


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        raw = {"kernel": image(stored=80, effective=4 * launch.MIB),
               "initrd": b"fixture-raw-initrd", "dtb": b"fixture-input-dtb",
               "config": b'CONFIG_CMDLINE_FROM_BOOTLOADER=y\n',
               "certificate": b"fixture-public-cert"}
        paths = {}
        for name in ("qemu", "kernel", "initrd", "dtb", "config", "certificate", "rootfs"):
            paths[name] = self.root / name
            paths[name].write_bytes(raw.get(name, b"fixture"))
        self.inputs = {"paths": paths, "raw": raw, "release": "6.12.114-fixture",
                       "bootargs": BOOTARGS, "kernel_load_base": 0xa0000000,
                       "identities": {name: launch.identity(path.read_bytes()) for name, path in paths.items()}}
        self.out = self.root / "new-output"
        self.process = FakeProcess()
        self.qmp = None
        self.validator_calls = []

    def tearDown(self):
        self.temp.cleanup()

    def run_fixture(self, *, run_seconds=0, unchanged=None, reject_layout=False, **options):
        def qmp_factory(path, process, timeout):
            self.qmp = FakeQMP(process, self.inputs, self.out, **options)
            return self.qmp

        def validator(*args):
            self.validator_calls.append(args)
            if reject_layout:
                raise ValueError("fixture known-reservation collision")
            return {"status": "simulated_layout_valid", "physical_boot_verified": False}

        return launch.run_prepared(self.inputs, self.out, run_seconds,
                                   process_factory=lambda *args, **kwargs: self.process,
                                   qmp_factory=qmp_factory,
                                   unchanged=unchanged or (lambda inputs: None), validator=validator)

    def assert_never_continued(self, result):
        self.assertFalse(result["cont_issued"])
        self.assertNotIn("cont", [name for name, args in self.qmp.commands])
        self.assertTrue(result["cleanup"]["child_reaped"])
        self.assertTrue(self.qmp.closed)

    def test_command_consumes_explicit_loader_dtb_and_snapshot_root(self):
        command = launch.make_command(self.inputs, self.out, Path("/tmp/fixture/qmp.sock"))
        self.assertEqual(command[command.index("-M") + 1], "tb371fc,kernel-load-base=0xa0000000")
        self.assertEqual(command[command.index("-dtb") + 1], str(self.inputs["paths"]["dtb"]))
        self.assertIn("-S", command)
        self.assertIn("snapshot=on", command[command.index("-drive") + 1])
        self.assertEqual(command[command.index("-nic") + 1], "none")

    def test_paused_success_checks_full_bytes_without_guest_boot_claim(self):
        result = self.run_fixture()
        self.assertEqual(result["exit_code"], 0, result["controller_errors"])
        self.assertTrue(result["layout_gate_passed"])
        self.assert_never_continued(result)
        observed = self.validator_calls[0][-1]
        self.assertEqual(observed["ram"], launch.BOARD_RAM)
        self.assertEqual(observed["kernel_address"], 0xa0200000)
        self.assertEqual(observed["loader_reserved"], [{"start": 0xa0000000, "size": 48}])
        self.assertFalse(result["userspace_verified"])
        self.assertFalse(result["physical_boot_verified"])
        self.assertEqual(result["owner_native_linux_passes_added"], 0)

    def test_failed_layout_never_continues(self):
        result = self.run_fixture(run_seconds=1, reject_layout=True)
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["layout_gate_passed"])
        self.assert_never_continued(result)

    def test_paused_layout_does_not_hide_late_nonzero_qemu_exit(self):
        result = self.run_fixture(exit_after_gate=True)
        self.assertTrue(result["layout_gate_passed"])
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["cleanup"]["qemu_returncode"], 17)
        self.assertIn("did not exit normally", " ".join(result["controller_errors"]))
        self.assert_never_continued(result)

    def test_qmp_memory_failure_never_continues(self):
        result = self.run_fixture(run_seconds=1, dump_error=True)
        self.assertEqual(result["exit_code"], 1)
        self.assert_never_continued(result)

    def test_identical_header_with_corrupt_image_tail_never_continues(self):
        result = self.run_fixture(run_seconds=1, corrupt_kernel=True)
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("complete loaded Image", " ".join(result["controller_errors"]))
        self.assertEqual(self.validator_calls, [])
        self.assert_never_continued(result)

    def test_ambiguous_or_missing_rom_never_continues(self):
        for key in ("duplicate_kernel", "missing_initrd"):
            with self.subTest(key=key):
                self.out = self.root / key
                self.process = FakeProcess()
                result = self.run_fixture(run_seconds=1, **{key: True})
                self.assertEqual(result["exit_code"], 1)
                self.assert_never_continued(result)

    def test_input_change_after_paused_checks_never_continues(self):
        calls = []

        def unchanged(_):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("fixture changed root identity")

        result = self.run_fixture(run_seconds=1, unchanged=unchanged)
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(len(self.validator_calls), 1)
        self.assert_never_continued(result)

    def test_optional_execution_preserves_panic_even_with_zero_qemu_exit(self):
        result = self.run_fixture(run_seconds=1, panic=True)
        self.assertTrue(result["layout_gate_passed"])
        self.assertTrue(result["cont_issued"])
        self.assertEqual([name for name, args in self.qmp.commands].count("cont"), 1)
        self.assertEqual(result["cleanup"]["qemu_returncode"], 0)
        self.assertEqual(result["exit_code"], 3)
        self.assertTrue(result["runtime_observation"]["fatal_detected"])
        self.assertFalse(result["boot_completed_verified"])
        self.assertFalse(result["userspace_verified"])

    def test_fresh_output_refusal_survives_optimized_python(self):
        self.out.mkdir()
        marker = self.out / "result.json"
        marker.write_text("original evidence")
        code = """import sys
from pathlib import Path
import launch_second_stage as launch
try:
    launch.run_prepared({}, Path(sys.argv[1]))
except FileExistsError:
    raise SystemExit(0)
raise SystemExit(1)
"""
        child = subprocess.run([sys.executable, "-O", "-c", code, str(self.out)],
                               cwd=Path(launch.__file__).parent, capture_output=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        self.assertEqual(marker.read_text(), "original evidence")

    def test_malformed_physical_rom_lines_are_rejected(self):
        for text in ('addr=xyz size=0x8 mem=ram name="x"',
                     'addr=ffffffffffffffff size=0x2 mem=ram name="x"',
                     'addr=80000000 size=0x0 mem=ram name="x"'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                launch.parse_roms(text)


if __name__ == "__main__":
    unittest.main()
