#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the candidate's actual command closure against bounded child processes."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).with_name('build_rpmh_candidate.py')
spec = importlib.util.spec_from_file_location('candidate', SOURCE)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
tree = ast.parse(SOURCE.read_text())
build = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'build')
run = next(node for node in build.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
compiled = compile(ast.Module(body=[run], type_ignores=[]), str(SOURCE), 'exec')


class ProbeRuntimeTests(unittest.TestCase):
    def exercise(self, program, *, timeout=3, maximum=65536, error=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = {'commands': []}
            namespace = dict(candidate.__dict__)
            namespace.update(record=record, work=root, env=dict(os.environ), check_cancelled=lambda: None)
            exec(compiled, namespace)
            if error is None:
                namespace['run']('probe', [sys.executable, '-c', program], timeout=timeout, max_log_bytes=maximum)
            else:
                with self.assertRaises(error):
                    namespace['run']('probe', [sys.executable, '-c', program], timeout=timeout, max_log_bytes=maximum)
            row = record['commands'][0]
            self.assertTrue(row['child_reaped'])
            self.assertEqual(row['timeout_seconds'], timeout)
            self.assertEqual(row['log_limit_bytes'], maximum)
            self.assertEqual(row['log'], candidate.identity(root / 'probe.log'))
            self.assertFalse(Path('/proc', str(row['pid'])).exists())
            return row, (root / 'probe.log').read_bytes()

    def test_success_retains_exact_version_output(self):
        row, raw = self.exercise('print("Debian clang version 19.1.7 (3+b1)")')
        self.assertEqual(row['exit_code'], 0)
        self.assertEqual(raw, b'Debian clang version 19.1.7 (3+b1)\n')

    def test_timeout_retains_diagnostics_and_reaps(self):
        row, raw = self.exercise('import time;print("probe-started",flush=True);time.sleep(10)',
                                 timeout=.2, error=subprocess.TimeoutExpired)
        self.assertEqual(raw, b'probe-started\n')
        self.assertIn('TimeoutExpired', row['error'])
        self.assertNotEqual(row['exit_code'], 0)

    def test_nonzero_is_not_unknown_success(self):
        row, raw = self.exercise('import sys;print("version failed",flush=True);sys.exit(23)', error=ValueError)
        self.assertEqual(row['exit_code'], 23)
        self.assertEqual(raw, b'version failed\n')

    def test_output_limit_is_bounded_failure(self):
        row, raw = self.exercise('import os;os.write(1,b"x"*8192)', maximum=32, error=ValueError)
        self.assertEqual(raw, b'x' * 32)
        self.assertIn('bounded diagnostic log', row['error'])


if __name__ == '__main__':
    unittest.main()
