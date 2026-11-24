#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline synthetic-firmware tests; contains no vendor firmware or private keys.

Only tests replace the capture trust pin with an in-memory mock. The command
line tool has no unverified-input switch or user-selectable replacement hash.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_gpu_firmware as stage


HASH_BYTES = b"synthetic-hash-not-a-signature!!".ljust(32, b"!")
PAYLOAD = b"test-GPU-payload!"


def zap_fixture(*, complete=False, external_hash=False, extra=(), filesz=None, memsz=None,
                first_payload_offset=0x2000, no_loadable=False):
    """Build minimal independent ELF32 fixtures with Qualcomm program flags."""
    size = len(PAYLOAD) if filesz is None else filesz
    memory = size if memsz is None else memsz
    count = 3 + len(extra)
    header_size = 52 + 32 * count
    headers = [(0, 0, 0, 0, header_size, 0, 0x07000000, 0),
               (0, 0x1000, 0, 0, len(HASH_BYTES), 4096, 0x02200000, 4096),
               (0 if no_loadable else 1, first_payload_offset, 0, 0, size, memory, 0x08000007, 4096)]
    headers.extend(extra)
    ident = b"\x7fELF\x01\x01\x01" + b"\x00" * 9
    elf_header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 40, 1, 0, 52, 0, 0, 52, 32, count, 0, 0, 0)
    table = elf_header + b"".join(struct.pack("<8I", *row) for row in headers)
    if not complete:
        return table if external_hash else table + HASH_BYTES
    total = max(row[1] + row[4] for row in headers if row[4])
    result = bytearray(total)
    result[:len(table)] = table
    result[0x1000:0x1000 + len(HASH_BYTES)] = HASH_BYTES
    result[first_payload_offset:first_payload_offset + size] = PAYLOAD[:size]
    return bytes(result)


class FirmwareStagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tb371fc-gpu-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "extracted-vendor-firmware"
        self.source.mkdir()
        self.output = self.root / "new-stage"
        self.evidence = self.root / "synthetic-capture.json"

    def fixture(self, firmware):
        blobs = {"a650_gmu.bin": b"synthetic-gmu", "a650_sqe.fw": b"synthetic-sqe", **firmware}
        rows = []
        for name, data in blobs.items():
            (self.source / name).write_bytes(data)
            rows.append({"path": "/vendor/firmware/" + name, "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
        capture = {"schema_version": 1, "capture_utc": "2000-01-01T00:00:00+00:00", "firmware": rows}
        content = (json.dumps(capture, sort_keys=True) + "\n").encode()
        self.evidence.write_bytes(content)
        patcher = mock.patch.object(stage, "TRUSTED_CAPTURE_SHA256", hashlib.sha256(content).hexdigest())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_stage(self, mode="mdt", **overrides):
        return stage.stage_firmware(overrides.get("source", self.source),
                                    overrides.get("output", self.output), mode,
                                    overrides.get("evidence", self.evidence))

    def assert_fails_without_output(self, message, mode="mdt", **overrides):
        with self.assertRaisesRegex(stage.FirmwareError, message):
            self.run_stage(mode, **overrides)
        self.assertFalse(self.output.exists())

    def test_complete_elf_needs_no_split_files_and_copies_no_unknowns(self):
        elf = zap_fixture(complete=True)
        self.fixture({"a650_zap.elf": elf})
        (self.source / "signing-private-key.pem").write_text("synthetic unrelated file")
        (self.source / "a650_zap.b77").write_text("unrelated segment")
        (self.source / "a630_sqe.fw").write_text("different GPU file")
        manifest = self.run_stage("elf")
        self.assertEqual(len(manifest["files"]), 3)
        self.assertFalse(manifest["zap_layout"]["split_payload_required"])
        self.assertEqual(manifest["zap_layout"]["required_split_files"], {})
        installed = self.output / "lib/firmware" / stage.ZAP_DESTINATION
        self.assertEqual(installed.read_bytes(), elf)
        names = {path.name for path in self.output.rglob("*") if path.is_file()}
        self.assertEqual(names, {"a650_gmu.bin", "a650_sqe.fw", "a650_zap.mbn",
                                 "gpu-firmware-manifest.json", "SHA256SUMS"})

    def test_packed_mdt_requires_only_nonempty_loadable_b02(self):
        self.fixture({"a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD,
                      "a650_zap.b00": b"unused-header", "a650_zap.b01": HASH_BYTES})
        (self.source / "a650_zap.b00").unlink()
        (self.source / "a650_zap.b01").unlink()
        manifest = self.run_stage()
        self.assertEqual(len(manifest["files"]), 4)
        self.assertEqual(set(manifest["zap_layout"]["required_split_files"]), {"a650_zap.b02"})
        self.assertEqual(manifest["zap_layout"]["metadata_hash_source"], "packed immediately after metadata header")
        self.assertFalse(any(path.name in {"a650_zap.b00", "a650_zap.b01"} for path in self.output.rglob("*")))

    def test_missing_loadable_segment_fails_instead_of_accepting_other_bxx(self):
        self.fixture({"a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD,
                      "a650_zap.b00": b"header", "a650_zap.b01": HASH_BYTES})
        (self.source / "a650_zap.b02").unlink()
        self.assert_fails_without_output("required input missing: a650_zap.b02")

    def test_wrong_segment_length_fails_even_when_capture_hash_matches_it(self):
        self.fixture({"a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD[:-1]})
        self.assert_fails_without_output("segment length does not match ELF")

    def test_same_size_changed_segment_fails_provenance(self):
        self.fixture({"a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD})
        (self.source / "a650_zap.b02").write_bytes(b"x" * len(PAYLOAD))
        self.assert_fails_without_output("does not match the TB371FC capture")

    def test_renamed_foreign_complete_elf_fails_provenance(self):
        elf = zap_fixture(complete=True)
        self.fixture({"a650_zap.elf": elf})
        changed = bytearray(elf)
        changed[-1] ^= 1
        (self.source / "a650_zap.elf").write_bytes(changed)
        self.assert_fails_without_output("does not match the TB371FC capture", "elf")

    def test_incomplete_elf_does_not_fall_back_to_available_mdt(self):
        self.fixture({"a650_zap.elf": zap_fixture(), "a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD})
        self.assert_fails_without_output("not a complete image", "elf")

    def test_unpacked_external_hash_is_required_as_well_as_payload(self):
        self.fixture({"a650_zap.mdt": zap_fixture(external_hash=True),
                      "a650_zap.b01": HASH_BYTES, "a650_zap.b02": PAYLOAD})
        manifest = self.run_stage()
        self.assertEqual(set(manifest["zap_layout"]["required_split_files"]), {"a650_zap.b01", "a650_zap.b02"})
        self.assertEqual(len(manifest["files"]), 5)

    def test_missing_external_hash_fails(self):
        self.fixture({"a650_zap.mdt": zap_fixture(external_hash=True),
                      "a650_zap.b01": HASH_BYTES, "a650_zap.b02": PAYLOAD})
        (self.source / "a650_zap.b01").unlink()
        self.assert_fails_without_output("required input missing: a650_zap.b01")

    def test_zero_file_size_loadable_segment_needs_no_bss_file(self):
        extra = ((1, 0x4000, 0, 0, 0, 4096, 0x08000007, 4096),)
        self.fixture({"a650_zap.mdt": zap_fixture(extra=extra), "a650_zap.b02": PAYLOAD})
        manifest = self.run_stage()
        self.assertEqual(len(manifest["zap_layout"]["loadable_segments"]), 2)
        self.assertEqual(set(manifest["zap_layout"]["required_split_files"]), {"a650_zap.b02"})

    def test_hash_marked_pt_load_is_not_treated_as_payload(self):
        data = bytearray(zap_fixture())
        struct.pack_into("<I", data, 52 + 32, 1)  # Hash phdr p_type = PT_LOAD.
        self.fixture({"a650_zap.mdt": bytes(data), "a650_zap.b02": PAYLOAD})
        manifest = self.run_stage()
        self.assertEqual([row["index"] for row in manifest["zap_layout"]["loadable_segments"]], [2])
        self.assertEqual(set(manifest["zap_layout"]["required_split_files"]), {"a650_zap.b02"})

    def test_zero_memory_size_pt_load_is_not_a_loader_payload(self):
        extra = ((1, 0x4000, 0, 0, 16, 0, 0x08000007, 4096),)
        self.fixture({"a650_zap.mdt": zap_fixture(extra=extra), "a650_zap.b02": PAYLOAD})
        manifest = self.run_stage()
        self.assertEqual([row["index"] for row in manifest["zap_layout"]["loadable_segments"]], [2])
        self.assertEqual(set(manifest["zap_layout"]["required_split_files"]), {"a650_zap.b02"})

    def test_one_external_loadable_segment_makes_all_payload_segments_split(self):
        extra = ((1, 0x4000, 0, 0, 8, 8, 0x08000007, 4096),)
        self.fixture({"a650_zap.mdt": zap_fixture(extra=extra, first_payload_offset=0),
                      "a650_zap.b02": PAYLOAD, "a650_zap.b03": b"payload3"})
        (self.source / "a650_zap.b02").unlink()
        self.assert_fails_without_output("required input missing: a650_zap.b02")

    def test_outside_hash_offset_makes_an_inside_payload_need_b02(self):
        self.fixture({"a650_zap.mdt": zap_fixture(first_payload_offset=0), "a650_zap.b02": PAYLOAD})
        (self.source / "a650_zap.b02").unlink()
        self.assert_fails_without_output("required input missing: a650_zap.b02")

    def test_outside_nonloadable_header_makes_an_inside_payload_need_b02(self):
        extra = ((0, 0x5000, 0, 0, 8, 0, 0, 0),)
        data = bytearray(zap_fixture(extra=extra, first_payload_offset=0))
        struct.pack_into("<I", data, 52 + 32 + 4, 52 + 32 * 4)  # Hash offset is inside.
        self.fixture({"a650_zap.mdt": bytes(data), "a650_zap.b02": PAYLOAD})
        (self.source / "a650_zap.b02").unlink()
        self.assert_fails_without_output("required input missing: a650_zap.b02")

    def test_outside_zero_size_bss_does_not_make_complete_elf_split(self):
        extra = ((1, 0x8000, 0, 0, 0, 4096, 0x08000007, 4096),)
        self.fixture({"a650_zap.elf": zap_fixture(complete=True, extra=extra)})
        manifest = self.run_stage("elf")
        self.assertFalse(manifest["zap_layout"]["split_payload_required"])
        self.assertEqual(manifest["zap_layout"]["required_split_files"], {})

    def test_invalid_program_header_bounds_fail(self):
        broken = bytearray(zap_fixture())
        struct.pack_into("<I", broken, 28, 0xfffffff0)
        self.fixture({"a650_zap.mdt": bytes(broken), "a650_zap.b02": PAYLOAD})
        self.assert_fails_without_output("program-header table")

    def test_loadable_file_size_larger_than_memory_fails(self):
        self.fixture({"a650_zap.mdt": zap_fixture(memsz=4), "a650_zap.b02": PAYLOAD})
        self.assert_fails_without_output("invalid file/memory size")

    def test_no_non_hash_loadable_segment_fails(self):
        self.fixture({"a650_zap.mdt": zap_fixture(no_loadable=True)})
        self.assert_fails_without_output("no non-hash loadable segment")

    def test_source_file_symlink_is_refused_even_with_matching_bytes(self):
        self.fixture({"a650_zap.mdt": zap_fixture(), "a650_zap.b02": PAYLOAD})
        outside = self.root / "outside-payload"
        outside.write_bytes(PAYLOAD)
        (self.source / "a650_zap.b02").unlink()
        (self.source / "a650_zap.b02").symlink_to(outside)
        self.assert_fails_without_output("symlinks refused")

    def test_source_parent_symlink_is_refused(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        link = self.root / "source-link"
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_stage("elf", source=link)
        self.assertFalse(self.output.exists())

    def test_output_parent_symlink_cannot_escape(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "output-parent-link"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_stage("elf", output=link / "stage")
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_output_is_never_overwritten(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_bytes(b"untouched")
        with self.assertRaisesRegex(stage.FirmwareError, "already exists"):
            self.run_stage("elf")
        self.assertEqual(marker.read_bytes(), b"untouched")
        self.assertEqual(list(self.output.iterdir()), [marker])

    def test_dangling_output_symlink_is_still_existing(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        self.output.symlink_to(self.root / "nonexistent")
        with self.assertRaisesRegex(stage.FirmwareError, "already exists"):
            self.run_stage("elf")
        self.assertTrue(self.output.is_symlink())
        self.assertFalse((self.root / "nonexistent").exists())

    def test_parent_traversal_is_refused(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        for field, value in (("source", self.source / ".." / self.source.name),
                             ("output", self.root / ".." / "escape")):
            with self.subTest(field=field):
                self.assert_fails_without_output("parent traversal", "elf", **{field: value})

    def test_special_file_is_rejected_before_read(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        special = self.source / "a650_gmu.bin"
        special.unlink()
        os.mkfifo(special)
        self.assert_fails_without_output("not a regular file", "elf")

    def test_changed_evidence_cannot_authorize_new_firmware(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        self.evidence.write_text(self.evidence.read_text() + " ")
        self.assert_fails_without_output("evidence does not match", "elf")

    def test_evidence_symlink_is_refused(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        link = self.root / "evidence-link.json"
        link.symlink_to(self.evidence)
        self.assert_fails_without_output("symlinks refused", "elf", evidence=link)

    def test_source_and_output_cannot_overlap(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        with self.assertRaisesRegex(stage.FirmwareError, "must not overlap"):
            self.run_stage("elf", output=self.source / "stage")
        self.assertFalse((self.source / "stage").exists())

    def test_output_manifest_and_checksums_are_reproducible(self):
        self.fixture({"a650_zap.elf": zap_fixture(complete=True)})
        first = self.run_stage("elf")
        second_output = self.root / "second-stage"
        second = self.run_stage("elf", output=second_output)
        self.assertEqual(first, second)
        for relative in ("gpu-firmware-manifest.json", "SHA256SUMS"):
            self.assertEqual((self.output / relative).read_bytes(), (second_output / relative).read_bytes())
        for line in (self.output / "SHA256SUMS").read_text().splitlines():
            digest, relative = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), digest)

    def test_live_device_paths_are_not_extracted_input_paths(self):
        for value in ("/vendor/firmware", "/dev/block/device", "/proc/self", "/sys/firmware"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(stage.FirmwareError, "live device/system"):
                    stage.safe_absolute(value)


if __name__ == "__main__":
    unittest.main()
