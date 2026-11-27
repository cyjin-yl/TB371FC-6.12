#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Receipt negatives and real owned-process cleanup; no VM boots."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r7_vm', HERE / 'run_rpmh_generic_vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)
REPO = Path(os.environ.get('TB371FC_R7_TEST_REPO', HERE.parents[3]))


class Identities(unittest.TestCase):
    def test_plain_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plain'
            path.write_bytes(b'actual payload')
            expected = vm.identity(path)
            self.assertEqual(expected['bytes'], 14)
            vm.pinned(path, expected)
            link = path.with_name('alias')
            link.symlink_to(path)
            with self.assertRaises(OSError):
                vm.identity(link)
            path.write_bytes(b'different data')
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                vm.pinned(path, expected)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            json.loads('{"passed": false, "passed": true}', object_pairs_hook=vm.unique_object)


class CommandContract(unittest.TestCase):
    def test_maintenance_substitution_rejected_before_mutable_label_boot(self):
        maintenance = {'bytes': 22, 'sha256': 'e' * 64}
        production = {'bytes': 33, 'sha256': 'f' * 64}
        construction = {'archive_module_checks': {
            'maintenance': {'passed': True, 'kernel_release': vm.RELEASE, 'image': maintenance},
            'production': {'passed': True, 'kernel_release': vm.RELEASE, 'image': production}},
            'initrd': {**production, 'path': '/work/production.img'}}
        vm.validate_archive_binding(construction, 'label', maintenance)
        vm.validate_archive_binding(construction, 'verify', production)
        with self.assertRaisesRegex(ValueError, 'phase archive differs from construction: maintenance'):
            vm.validate_archive_binding(construction, 'label', production)
        with self.assertRaisesRegex(ValueError, 'phase archive differs from construction: production'):
            vm.validate_archive_binding(construction, 'verify', maintenance)

    def test_exact_generic_machine_and_resources(self):
        command = vm.expected_command(Path('/work/fedora-r7-system-test'), 'verify', 'a' * 64)
        for key, expected in (('-machine', 'virt'), ('-cpu', 'cortex-a72'), ('-smp', '2'),
                              ('-m', '2048'), ('-nic', 'none'), ('-monitor', 'none')):
            self.assertEqual(command[command.index(key) + 1], expected)
        for forbidden in ('-dtb', '-fsdev', '-virtfs', '-netdev', '-snapshot'):
            self.assertNotIn(forbidden, command)

    def test_label_only_permissive_and_production_unchanged(self):
        work = Path('/work/fedora-r7-system-test')
        label = vm.expected_command(work, 'label', 'a' * 64)
        verify = vm.expected_command(work, 'verify', 'a' * 64)
        label_args = label[label.index('-append') + 1].split()
        verify_args = verify[verify.index('-append') + 1].split()
        self.assertIn('enforcing=0', label_args)
        self.assertNotIn('rdinit=/init.tmpfs', label_args)
        for token in ('enforcing=1', 'rdinit=/init.tmpfs', 'rd.tb371fc.tmpfs-root=1',
                      'rd.tb371fc.early-selinux=1', 'module.sig_enforce=1'):
            self.assertIn(token, verify_args)
        self.assertIn('-maintenance.img', label[label.index('-initrd') + 1])
        self.assertNotIn('-maintenance.img', verify[verify.index('-initrd') + 1])


class ResultContract(unittest.TestCase):
    def setUp(self):
        self.profile = {'kernel_image_sha256': 'a' * 64}
        self.profile_id = {'bytes': 10, 'sha256': 'b' * 64}
        self.initrd_id = {'bytes': 20, 'sha256': 'c' * 64}
        self.serial_id = {'bytes': 30, 'sha256': 'd' * 64}
        self.replay = {'expected_marker_seen': True, 'marker_exact_line_count': 1,
                       'validation_failure_seen': False, 'kernel_panic_seen': False,
                       'invalid_initramfs_seen': False, 'persistent_result_metadata': None}
        self.result = {'schema_version': 2, 'phase': 'label', 'profile_sha256': 'b' * 64,
            'kernel_image_sha256': 'a' * 64, 'initramfs_sha256': 'c' * 64,
            'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2,
            'qemu_exit_code': 0, 'termination_reason': None, 'passed': True,
            'physical_hardware_tested': False, 'physical_device_passthrough': False,
            'network': False, 'board_dtb_used': False, 'host_filesystem_shared': False,
            'vm_module_sig_enforce_argument': 'module.sig_enforce=1', 'compiled_module_sig_force': False,
            'systemd_debug_logging_for_this_vm_only': True, 'initramfs_role': 'maintenance-label-only',
            'early_selinux_argument': None, 'kernel_rdinit_argument': None, 'audit_printk_observation_argument': None,
            'serial_log_sha256': 'd' * 64, 'serial_log_bytes': 30, **self.replay}

    def validate(self, phase='label'):
        vm.validate_phase_result(self.result, self.replay, phase, self.profile,
                                 self.profile_id, self.initrd_id, self.serial_id)

    def test_coherent_synthetic_label(self):
        self.validate()

    def test_pass_bit_cannot_override_failed_actual_reparse(self):
        self.replay['kernel_panic_seen'] = True
        with self.assertRaisesRegex(ValueError, 'independent frozen acceptance reparse'):
            self.validate()

    def test_wrong_image_or_profile_and_native_claim_fail(self):
        pristine = copy.deepcopy(self.result)
        for key, value in (('kernel_image_sha256', 'e' * 64), ('profile_sha256', 'f' * 64),
                           ('physical_hardware_tested', True), ('termination_reason', 'timeout'),
                           ('passed', 1), ('board_dtb_used', True)):
            self.result = {**pristine, key: value}
            with self.assertRaisesRegex(ValueError, 'binding or scope'):
                self.validate()

    def test_recorded_extraction_error_fails(self):
        self.result['persistent_result_error'] = {'message': 'failed'}
        with self.assertRaisesRegex(ValueError, 'contains an error'):
            self.validate()

    def test_production_needs_actual_persisted_success_and_zero_warnings(self):
        self.result['phase'] = 'verify'
        self.result.update(initramfs_role='production-tmpfs-early-selinux',
                           early_selinux_argument='rd.tb371fc.early-selinux=1',
                           kernel_rdinit_argument='rdinit=/init.tmpfs',
                           audit_printk_observation_argument='rd.tb371fc.audit-printk-unlimited=1')
        metadata = {'qualified': True, 'receipt': {}, 'guest_inode': {}, 'parent_inodes': {},
                    'image_opened_for_write': False, 'image_mounted': False,
                    'filesystem_replayed_or_repaired': False, 'source_image_metadata_unchanged': True}
        self.replay.update(guest_gates_match=True, persistent_result_qualified=True,
                           guest_file_status='pass', observed_warning_counts={'selinux_avc_denial_count': 0},
                           persistent_result_metadata=metadata)
        self.result.update(self.replay)
        self.validate('verify')
        for key, value in (('guest_gates_match', False), ('persistent_result_qualified', False),
                           ('guest_file_status', 'fail'), ('observed_warning_counts', {'audit_lost': 1})):
            original = self.replay[key]
            self.replay[key] = value
            self.result[key] = value
            with self.assertRaisesRegex(ValueError, 'production frozen guest gates'):
                self.validate('verify')
            self.replay[key] = original
            self.result[key] = original


class SourceBinding(unittest.TestCase):
    @unittest.skipUnless((REPO / vm.CONSTRUCTOR).is_file(), 'frozen repository fixture not supplied')
    def test_real_frozen_derivation_and_changed_driver_fail(self):
        previous_umask = os.umask(0o077)
        try:
            with tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                constructor = vm.load_module(REPO / vm.CONSTRUCTOR, 'r7_test_constructor')
                staging = constructor.load_module(REPO / 'scripts/research/rootfs/stage_r5_fedora.py', 'stage_r5_fedora')
                materializer = constructor.load_module(REPO / 'scripts/research/rootfs/materialize_r5_fedora_recipe.py', 'r7_test_materializer')
                constructor.derive_recipe(REPO, work / 'template', work / 'recipe', materializer, staging)
                output = work / 'source-check'
                output.mkdir()
                sources, derived, unused, unused2, driver = vm.prepare_sources(REPO, work, output)
                self.assertEqual(len(derived['derived']), 16)
                self.assertEqual(len(sources), 19)
                self.assertEqual(vm.identity(Path(driver.__file__))['sha256'], vm.DRIVER_SHA)
                with (work / 'recipe/boot_system_vm.py').open('a') as stream:
                    stream.write('\n# altered acceptance\n')
                second = work / 'second-check'
                second.mkdir()
                with self.assertRaisesRegex(ValueError, 'executed recipe differs'):
                    vm.prepare_sources(REPO, work, second)
        finally:
            os.umask(previous_umask)


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux lifecycle tests')
class OwnedProcessLifecycle(unittest.TestCase):
    def harness(self, body):
        prefix = ('import importlib.util, os, signal, subprocess, sys, tempfile\n'
                  'from pathlib import Path\n'
                  'spec = importlib.util.spec_from_file_location("vm", ' + repr(str(HERE / 'run_rpmh_generic_vm.py')) + ')\n'
                  'vm = importlib.util.module_from_spec(spec); spec.loader.exec_module(vm)\n'
                  'vm.enable_subreaper()\n')
        result = subprocess.run([sys.executable, '-B', '-O', '-c', prefix + body],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_normal_child_reaped(self):
        self.harness('with tempfile.TemporaryDirectory() as tmp:\n'
                     '    row = vm.run_owned([sys.executable, "-c", "print(123)"], Path(tmp) / "log", timeout=2)\n'
                     '    vm.require(row["child_reaped"] and row["all_owned_descendants_reaped"] and row["process_group_empty"], "cleanup evidence missing")\n')

    def test_separate_session_orphan_is_killed_and_reaped_then_rejected(self):
        child = 'import subprocess, sys; subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)'
        self.harness('with tempfile.TemporaryDirectory() as tmp:\n'
                     '    row = {}\n'
                     '    try:\n'
                     '        vm.run_owned([sys.executable, "-c", ' + repr(child) + '], Path(tmp) / "log", timeout=2, receipt=row)\n'
                     '        raise RuntimeError("orphan accepted")\n'
                     '    except ValueError as error:\n'
                     '        vm.require("left an owned process" in str(error), "unexpected failure")\n'
                     '    vm.require(row["orphan_descendants_found"] and row["all_owned_descendants_reaped"] and not vm.descendants(), "orphan escaped")\n')

    def test_signal_during_owned_child_is_latched_and_cleans_up(self):
        child = ('import os, signal, sys, time; signal.signal(signal.SIGTERM, lambda a,b: sys.exit(0)); '
                 'os.kill(os.getppid(), signal.SIGTERM); time.sleep(60)')
        self.harness('signal.signal(signal.SIGTERM, vm.on_signal)\n'
                     'with tempfile.TemporaryDirectory() as tmp:\n'
                     '    row = {}\n'
                     '    try:\n'
                     '        vm.run_owned([sys.executable, "-c", ' + repr(child) + '], Path(tmp) / "log", timeout=2, receipt=row)\n'
                     '        raise RuntimeError("signal ignored")\n'
                     '    except InterruptedError:\n'
                     '        pass\n'
                     '    vm.require(row["child_reaped"] and row["all_owned_descendants_reaped"] and not vm.descendants(), "cancel leaked child")\n')


if __name__ == '__main__':
    unittest.main()
