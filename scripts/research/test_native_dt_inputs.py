# SPDX-License-Identifier: GPL-2.0-only
"""Regression checks for public allowlisting and immutable backup inputs."""
import json
import unittest

from collect_native_dt import (bootconfig_observations,
                               command_line_observations, selection_value)
from inspect_native_dt_backup import inspect_backup, unique_pairs


class BootSelectionTests(unittest.TestCase):
    def test_cmdline_keeps_duplicates_and_drops_private_fields(self):
        data = (b"androidboot.serialno=PRIVATE androidboot.dtb_idx=1 "
                b"androidboot.dtbo_idx=4,7 androidboot.dtb_idx=2 "
                b"androidboot.slot_suffix=_a console=SECRET")
        result = command_line_observations(data)
        self.assertEqual(result["androidboot.dtb_idx"], [
            {"indices": [1], "valid": True}, {"indices": [2], "valid": True}])
        self.assertEqual(result["androidboot.dtbo_idx"], [{"indices": [4, 7], "valid": True}])
        self.assertEqual(result["androidboot.slot_suffix"], [{"slot_suffix": "_a"}])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("SECRET", json.dumps(result))

    def test_bad_selection_does_not_echo_content(self):
        for key, value in (("androidboot.dtb_idx", "2,3"),
                           ("androidboot.dtb_idx", "4294967296"),
                           ("androidboot.dtbo_idx", "-1"),
                           ("androidboot.dtbo_idx", "0,PRIVATE"),
                           ("androidboot.slot_suffix", "PRIVATE")):
            self.assertEqual(selection_value(key, value), {"valid": False})

    def test_flat_bootconfig_and_no_nested_guess(self):
        data = (b'androidboot.dtb_idx = "1"\n'
                b'androidboot.dtbo_idx = "4,7";\n'
                b'androidboot.slot_suffix = "_b"\n'
                b'androidboot.serialno = "PRIVATE"\n'
                b'androidboot {\n dtb_idx = "3"\n}\n')
        result = bootconfig_observations(data)
        self.assertEqual(result["androidboot.dtb_idx"], [{"indices": [1], "valid": True}])
        self.assertEqual(result["androidboot.dtbo_idx"], [{"indices": [4, 7], "valid": True}])
        self.assertEqual(result["androidboot.slot_suffix"], [{"slot_suffix": "_b"}])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_duplicate_json_ref_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"archive_bytes": 1, "archive_bytes": 2}', object_pairs_hook=unique_pairs)

    def test_unfrozen_reference_rejected_before_open(self):
        with self.assertRaises(ValueError):
            inspect_backup("/path-that-must-not-be-opened", {})


if __name__ == "__main__":
    unittest.main()
