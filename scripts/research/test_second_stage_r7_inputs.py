#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic receipt/ordinary-file tests; no R7 build, signature, or VM runs."""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import launch_second_stage as launch
import prepare_r7_second_stage_inputs as prepare
import second_stage_inputs as r5
import second_stage_r7_inputs as r7
from test_boot_formats import image
from test_second_stage_layout import dt, RAM


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def module_paths():
    repo = Path(os.environ.get('TB371FC_R7_TEST_REPO', str(Path(__file__).resolve().parents[2])))
    raw = (repo / 'docs/research/2026-11-26/evidence/tianma-r6-build/build-result.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'f37fbe20624e7f49bdf09eeda28b536fe4da24f9379143efeac598da5a110cc7':
        raise ValueError('test module-path source differs')
    return sorted(name.split('/6.12.114-tb371fc-research6-tianma-off/', 1)[1]
                  for name in json.loads(raw)['modules'])


class Fixture:
    """Small fabricated payloads model identity binding only, never execution."""
    def __init__(self, root):
        self.root = root
        self.names = module_paths()
        self.certificate = b'fixture-public-certificate-not-an-actual-DER'
        self.kernel = image(stored=80, effective=4 * 1024**2) + self.certificate
        self.config = b'CONFIG_QCOM_CLK_RPMH=y\n'
        self.native, self.candidate = dt(), dt(ram=RAM)
        self.initrd, self.disk = b'fixture-production-initrd', b'fixture-unbooted-root'
        self.patches = {'CONFIG': r7.raw_id(self.config), 'NATIVE_DTB': r7.raw_id(self.native),
                        'STAGE2_DTB': r7.raw_id(self.candidate), 'ROOTFS_BYTES': len(self.disk)}
        self.artifacts = {name: ('fixture-artifact-' + name).encode() for name in r7.ARTIFACTS}
        self.artifacts.update({'Image': self.kernel, 'kernel.config': self.config,
            'board.dtb': self.native, 'kernel.release': (r7.RELEASE + '\n').encode(),
            'signing-cert.der': self.certificate, 'modules.order': ('\n'.join(self.names) + '\n').encode()})
        self.modules = {r7.PREFIX + name: ('fixture-signed-module-' + name).encode() for name in self.names}
        self.build = {'schema_version': 1, 'passed': True, 'kernel_release': r7.RELEASE,
            'recipe': {'sha256': r7.BUILD_RECIPE_SHA}, 'retained_inputs_reverified': True,
            'offline_modules_qualified': True, 'old_objects_copied': False, 'old_private_key_copied': False,
            'runtime_signature_enforcement_verified': False, 'native_hardware_passes_added': 0,
            'module_count': 84, 'modules': {name: r7.raw_id(raw) for name, raw in self.modules.items()},
            'artifacts': {name: r7.raw_id(raw) for name, raw in self.artifacts.items()},
            'inputs': {'signature_verifier': {'sha256': r7.SIGNATURE_VERIFIER_SHA},
                       'abi_verifier': {'sha256': r7.ABI_VERIFIER_SHA}}}
        build = self.build
        build['candidate_config'] = r7.raw_id(self.config)
        build['new_signing_certificate'] = r7.raw_id(self.certificate)
        build['module_metadata'] = {name: {'built': build['artifacts'][name],
            'installed': build['artifacts'][name], 'relationship':
            'Kbuild kernel-prefix and .o-to-.ko transform' if name == 'modules.order' else 'byte-identical'}
            for name in r7.METADATA}
        self.sig = {'schema_version': 1, 'passed': True, 'input_snapshot_stable': True,
            'module_count': 84, 'expected_count': 84, 'runtime_signature_enforcement_verified': False,
            'kernel_keyring_trust_verified': False, 'module_loadability_verified': False,
            'private_key_accessed': False, 'certificate_chain_validation': False,
            'verifier_source': {'sha256': r7.SIGNATURE_VERIFIER_SHA}, 'compressed_modules_not_verified': [],
            'public_certificate': {**r7.raw_id(self.certificate), 'format': 'DER',
                                   'der_sha256': r7.raw_id(self.certificate)['sha256']},
            'modules': [{'path': name[len('modules/'):], **r7.raw_id(raw), 'passed': True,
                         'verified_content_matches': True,
                         'verified_signer_der_sha256': r7.raw_id(self.certificate)['sha256']}
                        for name, raw in self.modules.items()]}
        self.abi = {'schema_version': 1, 'passed': True, 'input_snapshot_stable': True,
            'module_count': 84, 'kernel_release': r7.RELEASE,
            'runtime_signature_enforcement_verified': False, 'runtime_module_loading_verified': False,
            'btf_semantic_type_validation': False, 'module_symvers': build['artifacts']['Module.symvers'],
            'modules': [{'path': name[len(r7.PREFIX):], **r7.raw_id(raw),
                'imported_symbol_crcs_match': True, 'debug_info_stripped': True,
                'vermagic': r7.RELEASE + ' SMP preempt mod_unload modversions aarch64'}
                for name, raw in self.modules.items()]}
        self.source = b'{"fixture":"source inventory, not real kernel source"}\n'
        build.update(offline_signature_result=r7.raw_id(encoded(self.sig)),
                     offline_abi_result=r7.raw_id(encoded(self.abi)), source_inventory=r7.raw_id(self.source))
        self.build_id = r7.raw_id(encoded(build))
        self.launch_ids = {name: r7.raw_id(raw) for name, raw in {'kernel': self.kernel,
            'config': self.config, 'certificate': self.certificate, 'dtb': self.candidate,
            'initrd': self.initrd, 'rootfs': self.disk}.items()}
        self.docs = {}
        def save(name, doc):
            self.docs[name] = doc
            return r7.raw_id(encoded(doc))
        files = {**build['modules'], **{r7.PREFIX + name: build['artifacts'][name] for name in r7.METADATA}}
        report_rows = [{'path': name[len(r7.PREFIX):], **entry, 'mode': 0o644} for name, entry in files.items()]
        report = save('root-module-report.json', {'root_module_tree': {
            **{key: True for key in ('passed', 'input_snapshot_stable', 'module_bytes_verified',
                'kbuild_metadata_verified', 'text_dependency_graph_verified', 'binary_indexes_recorded',
                'native_depmod_provenance_not_verified')},
            **{key: False for key in ('binary_index_semantics_verified', 'rootfs_runtime_ready',
                'physical_hardware_tested', 'rootfs_modified', 'target_code_executed')},
            'kernel_release': r7.RELEASE, 'module_count_expected': 84, 'indexes': [],
            'module_files': [row for row in report_rows if row['path'].endswith('.ko')],
            'kbuild_metadata': [row for row in report_rows if not row['path'].endswith('.ko')]}})
        save('r7-module-contract.json', {'schema_version': 1, 'scope': 'fixture',
            'kernel': {'release': r7.RELEASE, 'module_count': 84}, 'build_result': self.build_id,
            'physical_boot_verified': False,
            'kernel_files': [{'path': name, **entry, 'mode': 0o644} for name, entry in sorted(files.items())]})
        tree = {name[len(r7.PREFIX):]: {**entry, 'mode': 0o644} for name, entry in files.items()}
        firmware = {'lib/firmware/fixture-' + str(n): {**r7.raw_id(str(n).encode()), 'mode': 0o644} for n in range(69)}
        self.closure = sorted(r7.SUPPLIERS)
        stage_id = save('r7-runtime-stage.json', {'complete': True, 'kernel_release': r7.RELEASE,
            'owner_native_linux_passes_added': 0, 'stage_source': {'sha256': r7.CONSTRUCTOR_SHA},
            'build_result': self.build_id, 'root_module_report': {**report, 'mode': 0o600}, 'module_tree': tree,
            'journal_acls': {}, 'firmware_inventory': firmware, 'supplier_closure': self.closure})
        meta = 'usr/share/tb371fc/' + r7.RELEASE + '/'
        mappings = {'Image': 'boot/Image-' + r7.RELEASE,
            'board.dtb': 'boot/dtb-' + r7.RELEASE + '/qcom/sm8250-lenovo-tb371fc.dtb',
            'kernel.config': 'boot/config-' + r7.RELEASE, 'System.map': 'boot/System.map-' + r7.RELEASE,
            **{name: meta + name for name in ('signing-cert.der', 'kernel.btf', 'Module.symvers', 'kernel.release')}}
        runtime_id = save('runtime.json', {'schema_version': 1, 'kernel_release': r7.RELEASE,
            'module_count': 84, 'firmware_file_count': 69, 'physical_tablet_tested': False,
            'firmware_selection_verified': False, 'runtime_files': {
                **{'usr/lib/modules/' + r7.RELEASE + '/' + name: entry['sha256'] for name, entry in tree.items()},
                **{'usr/' + name: entry['sha256'] for name, entry in firmware.items()},
                **{path: build['artifacts'][name]['sha256'] for name, path in mappings.items()},
                **{meta + name: entry['sha256'] for name, entry in {'research7-build.json': self.build_id,
                    'source-manifest.json': build['source_inventory'], 'module-signatures.json': build['offline_signature_result'],
                    'module-abi.json': build['offline_abi_result']}.items()}}})
        derived = {name: {**r7.raw_id(name.encode()), 'mode': 0o644} for name in
                   ('guest_transient_worker.py', 'guest_result_file.py', 'read_vm_result.py')}
        save('recipe/derivation.json', {'schema_version': 1, 'kernel_release': r7.RELEASE,
            'profile': r7.SYSTEM_PROFILE, 'root_label': r7.LABEL, 'derived': derived,
            'frozen_recipe_written': False, 'runtime_acceptance_verified': False})
        profile_id = save('system-profile.json', {'schema_version': 1, 'kernel_release': r7.RELEASE,
            'profile': r7.SYSTEM_PROFILE, 'root_label': r7.LABEL, 'module_count': 84, 'firmware_file_count': 69,
            'runtime_manifest_sha256': runtime_id['sha256'], 'kernel_image_sha256': self.launch_ids['kernel']['sha256'],
            'board_dtb_sha256': self.patches['NATIVE_DTB']['sha256'],
            'kernel_btf_sha256': build['artifacts']['kernel.btf']['sha256'],
            'kernel_btf_size': build['artifacts']['kernel.btf']['bytes'],
            'public_signing_certificate_sha256': self.launch_ids['certificate']['sha256'],
            'staging_receipt_sha256': stage_id['sha256'], 'source_policy_sha256': r7.POLICY_SHA,
            'early_bootstrap_sha256': r7.BOOTSTRAP_SHA, 'early_bootstrap_build_policy_sha256': r7.POLICY_SHA,
            'initramfs_root_type_required': 'tmpfs', 'kernel_rdinit_required': '/init.tmpfs',
            'validation_selinux_context': 'system_u:system_r:sysadm_t:s0',
            'transient_selinux_context': 'system_u:system_r:sysadm_t:s0', 'validation_tasks_max': 128,
            'audit_printk_interval_required': 0, 'journal_acl_check': {}, 'early_selinux_required': True,
            'audit_printk_opt_in_required': True, 'vm_module_signature_enforcement_required': True,
            'configured_module_sig_force': False, 'actual_exported_kernel_policy_sha256_predetermined': False,
            'early_bootstrap_embeds_policy_hash': False,
            **{field: derived[name]['sha256'] for field, name in (
                ('transient_worker_sha256', 'guest_transient_worker.py'),
                ('guest_result_writer_sha256', 'guest_result_file.py'), ('host_result_reader_sha256', 'read_vm_result.py'))}})
        archives = {role: {'passed': True, 'kernel_release': r7.RELEASE,
            'image': r7.raw_id(self.initrd if role == 'production' else b'fixture-maintenance-initrd'),
            'signed_bytes_match_qualified_build': True, 'text_dependency_graph_matches_root': True,
            'required_supplier_closure': self.closure, 'binary_index_semantics_verified': False,
            'module_loading_verified': False, 'signature_enforcement_runtime_verified': False,
            'included_module_count': len(self.closure),
            'modules': {name: build['modules'][r7.PREFIX + name] for name in self.closure}}
            for role in ('production', 'maintenance')}
        save('r7-initrd-modules.json', archives)
        save('r7-construction-result.json', {'schema_version': 1, 'complete': True,
            'kernel_release': r7.RELEASE, 'retained_inputs_reverified': True, 'module_count': 84,
            'constructor': {'sha256': r7.CONSTRUCTOR_SHA}, 'physical_boot_verified': False,
            'userspace_verified': False, 'runtime_signature_enforcement_verified': False,
            'owner_native_linux_passes_added': 0, 'build_result': self.build_id, 'profile': profile_id,
            'rootfs': {'path': '/work/fixture/root.ext4', 'label': r7.LABEL, **r7.raw_id(self.disk)},
            'initrd': {'path': '/work/fixture/initrd', **r7.raw_id(self.initrd)},
            'supplier_closure': self.closure, 'archive_module_checks': archives})
        self.contract = {'schema': r7.CONTRACT_SCHEMA, 'input_profile': r7.INPUT_PROFILE,
            'release': r7.RELEASE, 'build_result': self.build_id,
            'construction_files': {name: r7.raw_id(encoded(doc)) for name, doc in self.docs.items()},
            'launch_files': self.launch_ids, 'dtb_derivation': 'native-memory-reg-only-v1',
            'rootfs_phase': r7.ROOTFS_PHASE}
        self.evidence_logs = {}

    def add_generic_vm(self):
        # These remain synthetic recorded receipts; no driver is executed.
        construction = self.docs['r7-construction-result.json']
        work = Path('/work/fedora-r7-system-fixture')
        construction['rootfs']['path'] = str(work / 'fedora45-research7-rpmh-clock.ext4')
        self.docs['recipe/derivation.json']['derived']['boot_system_vm.py'] = {
            'bytes': 100, 'sha256': r7.GENERIC_VM_DRIVER_SHA, 'mode': 0o644}
        self.contract['construction_files'] = {name: r7.raw_id(encoded(self.docs[name])) for name in r7.CONSTRUCTION_FILES}
        profile_id = self.contract['construction_files']['system-profile.json']
        self.disk = b'V' * len(self.disk)
        self.launch_ids['rootfs'] = r7.raw_id(self.disk)
        guest = {'schema_version': 1, 'status': 'pass', 'phase': 'verify',
            'boot_id': '12345678-1234-1234-1234-123456789012', 'profile_sha256': profile_id['sha256'],
            'result': {'scope': 'synthetic offline fixture; no VM ran'}}
        for name in ('vm-verify-01/guest-result.json', 'r7-generic-vm/reparse-verify/guest-result.json'):
            self.docs[name] = guest
        guest_id = r7.raw_id(encoded(guest))
        persisted = {'qualified': True, 'receipt': {'status': 'pass', 'boot_id': guest['boot_id'],
            'profile_sha256': profile_id['sha256'], 'size': guest_id['bytes'], 'sha256': guest_id['sha256']},
            'guest_inode': {}, 'parent_inodes': [], 'image_opened_for_write': False, 'image_mounted': False,
            'filesystem_replayed_or_repaired': False, 'source_image_metadata_unchanged': True}
        previous = r7.stripped_id(construction['rootfs'])
        rows = []
        for phase in ('label', 'verify'):
            run = 'vm-' + phase + '-01'
            serial = ('fixture synthetic ' + phase + ' log\n').encode()
            driver_log = ('fixture synthetic ' + phase + ' driver\n').encode()
            self.evidence_logs[run + '/serial.log'] = serial
            self.evidence_logs['r7-generic-vm/' + phase + '.driver.log'] = driver_log
            replay = {'expected_marker_seen': True, 'marker_exact_line_count': 1,
                'validation_failure_seen': False, 'kernel_panic_seen': False, 'invalid_initramfs_seen': False}
            if phase == 'verify':
                replay.update(guest_gates_match=True, persistent_result_qualified=True, guest_file_status='pass',
                    observed_warning_counts={'fixture_count': 0}, persistent_result_metadata=persisted,
                    guest_result=guest['result'])
            archive = self.docs['r7-initrd-modules.json']['maintenance' if phase == 'label' else 'production']['image']
            result = {'schema_version': 2, 'phase': phase, 'profile_sha256': profile_id['sha256'],
                'kernel_image_sha256': self.launch_ids['kernel']['sha256'], 'initramfs_sha256': archive['sha256'],
                'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2, 'qemu_exit_code': 0,
                'termination_reason': None, 'passed': True, 'physical_hardware_tested': False,
                'physical_device_passthrough': False, 'network': False, 'board_dtb_used': False,
                'host_filesystem_shared': False, 'vm_module_sig_enforce_argument': 'module.sig_enforce=1',
                'compiled_module_sig_force': False, 'serial_log_sha256': r7.raw_id(serial)['sha256'],
                'serial_log_bytes': len(serial), 'systemd_debug_logging_for_this_vm_only': True,
                'initramfs_role': 'maintenance-label-only' if phase == 'label' else 'production-tmpfs-early-selinux',
                'early_selinux_argument': None if phase == 'label' else 'rd.tb371fc.early-selinux=1',
                'kernel_rdinit_argument': None if phase == 'label' else 'rdinit=/init.tmpfs',
                'audit_printk_observation_argument': None if phase == 'label' else 'rd.tb371fc.audit-printk-unlimited=1', **replay}
            command = r7.generic_command(work, phase, profile_id['sha256'])
            self.docs[run + '/result.json'], self.docs[run + '/command.json'] = result, command
            self.docs['r7-generic-vm/reparse-' + phase + '/inspection.json'] = replay
            after = r7.raw_id(b'L' * len(self.disk)) if phase == 'label' else self.launch_ids['rootfs']
            row = {'phase': phase, 'run': run, 'started_utc': 'fixture-start', 'finished_utc': 'fixture-end',
                'rootfs_before': previous, 'rootfs_after': after, 'result': r7.raw_id(encoded(result)),
                'command': r7.raw_id(encoded(command)), 'serial': r7.raw_id(serial),
                'guest_result': guest_id if phase == 'verify' else None,
                'reparsed_result': r7.raw_id(encoded(replay)),
                'driver_source': r7.stripped_id(self.docs['recipe/derivation.json']['derived']['boot_system_vm.py']),
                'driver_log': r7.raw_id(driver_log), 'exit_code': 0, 'child_reaped': True,
                'process_group_empty': True, 'all_owned_descendants_reaped': True,
                'orphan_descendants_found': [], 'acceptance_reparsed': True}
            rows.append(row); previous = after
        self.docs['r7-generic-vm-result.json'] = {'schema': 'tb371fc-r7-generic-vm-v1',
            'rootfs_phase': r7.GENERIC_VM_PHASE, 'passed': True, 'kernel_release': r7.RELEASE,
            'started_utc': 'fixture-start', 'finished_utc': 'fixture-end',
            'wrapper_source': {'bytes': 100, 'sha256': r7.GENERIC_VM_WRAPPER_SHA},
            'construction_result': self.contract['construction_files']['r7-construction-result.json'],
            'profile': profile_id, 'initial_rootfs': r7.stripped_id(construction['rootfs']),
            'final_rootfs': self.launch_ids['rootfs'], 'tools': r7.GENERIC_VM_TOOLS,
            'source_inputs': {'scripts/research/system-kernel/research7-rpmh-clock/build_rpmh_rootfs.py':
                              {'bytes': 100, 'sha256': r7.CONSTRUCTOR_SHA}},
            'phases': rows, 'inputs_reverified': True, 'generic_virt_acceptance': True,
            'board_model_verified': False, 'physical_boot_verified': False, 'native_userspace_verified': False,
            'owner_native_linux_passes_added': 0, 'error': None}
        self.contract['rootfs_phase'] = r7.GENERIC_VM_PHASE
        self.contract['generic_vm_files'] = {name: r7.raw_id(self.evidence_logs[name] if name in self.evidence_logs
            else encoded(self.docs[name])) for name in r7.GENERIC_VM_FILES}

    def write(self):
        self.kernel_root, self.construction_root = self.root / 'kernel-bundle', self.root / 'construction'
        files = {**self.modules, **{'artifacts/' + name: raw for name, raw in self.artifacts.items()},
            **{r7.PREFIX + name: self.artifacts[name] for name in r7.METADATA},
            'build-result.json': encoded(self.build), 'module-signatures.json': encoded(self.sig),
            'module-abi.json': encoded(self.abi), 'source-inventory.json': self.source}
        for base, values in ((self.kernel_root, files),
                              (self.construction_root, {**{name: encoded(doc) for name, doc in self.docs.items()},
                                                        **self.evidence_logs})):
            for name, raw in values.items():
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                path.chmod(0o644)
        launched = {'kernel': self.kernel, 'config': self.config, 'certificate': self.certificate,
                    'dtb': self.candidate, 'initrd': self.initrd, 'rootfs': self.disk, 'qemu': b'fixture-not-executed'}
        for name, raw in launched.items():
            path = self.root / name
            path.write_bytes(raw)
            path.chmod(0o700 if name == 'qemu' else 0o600)
        self.manifest = {'schema_version': 1, 'input_profile': r7.INPUT_PROFILE, 'release': r7.RELEASE,
            'kernel_bundle': str(self.kernel_root), 'construction_bundle': str(self.construction_root),
            'kernel_load_base': 0xa0000000, 'bootargs': 'console=ttyMSM0 ' + ' '.join(
                key + '=' + value for key, value in r7.REQUIRED_ARGS.items()),
            'files': {name: {'path': str(self.root / name), **r7.raw_id(raw)} for name, raw in launched.items()}}
        self.manifest_path, self.contract_path = self.root / 'manifest.json', self.root / 'contract.json'
        self.manifest_path.write_bytes(encoded(self.manifest))
        self.contract_path.write_bytes(encoded(self.contract))
        self.contract_sha = r7.raw_id(encoded(self.contract))['sha256']


class R7InputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self.temp.name))
        self.patch = mock.patch.multiple(r7, **self.fx.patches)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.fx.write()

    def verify(self):
        return r7.verify_inputs(self.fx.manifest_path, self.fx.contract_path, self.fx.contract_sha)

    def construction(self):
        return r7.validate_construction(self.fx.docs, self.fx.contract['construction_files'],
                                        self.fx.build, self.fx.build_id, self.fx.launch_ids)

    def test_complete_synthetic_bundle_and_scope(self):
        with mock.patch.object(r7, 'read_file', wraps=r7.read_file) as reader:
            inputs = self.verify()
        self.assertEqual(inputs['kernel_bundle_qualification']['kernel_bundle_file_count'], 102)
        self.assertEqual(inputs['evidence_bindings']['rootfs_source'], 'constructed-unbooted-prelabel-v1')
        self.assertFalse(inputs['evidence_bindings']['generic_vm_recorded_acceptance'])
        self.assertFalse(inputs['kernel_bundle_qualification']['module_signatures_reexecuted'])
        self.assertFalse(inputs['kernel_bundle_qualification']['runtime_signature_enforcement_verified'])
        self.assertNotIn('rootfs', inputs['raw'])
        roots = [call for call in reader.call_args_list if Path(call.args[0]) == self.fx.root / 'rootfs']
        self.assertEqual(len(roots), 1)
        self.assertIs(roots[0].kwargs['capture'], False)
        self.assertEqual(inputs['evidence_bindings']['full_rootfs_bytes_hashed'], len(self.fx.disk))
        r7.verify_unchanged(inputs)

    def test_explicit_contract_pin_required_and_mismatch_precedes_bundle_reads(self):
        for pin in (None, '', 'A' * 64, '0' * 64):
            with self.subTest(pin=pin), mock.patch.object(r7, 'read_bundle') as bundle:
                with self.assertRaises(ValueError):
                    r7.verify_inputs(self.fx.manifest_path, self.fx.contract_path, pin)
                bundle.assert_not_called()

    def test_closed_schema_and_no_boolean_lengths(self):
        for which, field, value in (('manifest', 'extra', 1), ('contract', 'extra', 1),
                                     ('manifest', 'schema_version', True), ('contract', 'rootfs_phase', 'verified')):
            target = copy.deepcopy(getattr(self.fx, which))
            target[field] = value
            with self.subTest(which=which, field=field), self.assertRaises(ValueError):
                if which == 'manifest':
                    r7.validate_manifest(target, self.fx.contract)
                else:
                    r7.validate_contract(target)
        contract = copy.deepcopy(self.fx.contract)
        contract['launch_files']['kernel']['bytes'] = True
        with self.assertRaises(ValueError):
            r7.validate_contract(contract)

    def test_security_arguments_are_exact_and_unique(self):
        original = self.fx.manifest['bootargs']
        for bad in (original.replace('enforcing=1', 'enforcing=0'),
                    original.replace(r7.LABEL, 'tb371fc-r5-f45'),
                    original + ' module.sig-enforce=0', original + ' rdinit=/bin/sh',
                    original + ' selinux=0', original + ' security=apparmor', original + ' lsm=capability',
                    original + ' init=/bin/sh', original + ' -- enforcing=0',
                    original + ' mem=2G', original.replace('rdinit=/init.tmpfs', 'rdinit=/init')):
            manifest = copy.deepcopy(self.fx.manifest)
            manifest['bootargs'] = bad
            with self.subTest(args=bad), self.assertRaises(ValueError):
                r7.validate_manifest(manifest, self.fx.contract)

    def test_incomplete_or_wrong_source_build_is_rejected(self):
        for key, value in (('passed', 1), ('retained_inputs_reverified', False),
                           ('offline_modules_qualified', False), ('module_count', 83),
                           ('kernel_release', r5.RELEASE), ('old_private_key_copied', True),
                           ('runtime_signature_enforcement_verified', True)):
            build = copy.deepcopy(self.fx.build); build[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                r7.validate_build(build, self.fx.sig, self.fx.abi)
        build = copy.deepcopy(self.fx.build); build['recipe']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            r7.validate_build(build, self.fx.sig, self.fx.abi)

    def test_signature_abi_and_new_certificate_must_bind_same_84_bytes(self):
        for target, field, value in (('sig', 'sha256', '0' * 64),
                                     ('sig', 'verified_signer_der_sha256', '0' * 64),
                                     ('abi', 'sha256', '0' * 64), ('abi', 'vermagic', r5.RELEASE)):
            sig, abi = copy.deepcopy(self.fx.sig), copy.deepcopy(self.fx.abi)
            (sig if target == 'sig' else abi)['modules'][0][field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                r7.validate_build(self.fx.build, sig, abi)
        sig = copy.deepcopy(self.fx.sig); sig['modules'][-1] = copy.deepcopy(sig['modules'][0])
        with self.assertRaises(ValueError):
            r7.validate_build(self.fx.build, sig, self.fx.abi)

    def test_metadata_and_supplier_closure_are_bound(self):
        build = copy.deepcopy(self.fx.build)
        build['module_metadata']['modules.order']['installed'] = r7.raw_id(b'foreign-order')
        with self.assertRaises(ValueError):
            r7.validate_build(build, self.fx.sig, self.fx.abi)
        self.fx.docs['r7-initrd-modules.json']['production']['modules'].pop(self.fx.closure[0])
        with self.assertRaises(ValueError):
            self.construction()

    def test_profile_or_protocol_substitution_is_rejected(self):
        for key, value in (('root_label', 'tb371fc-r5-f45'), ('kernel_image_sha256', '0' * 64),
                           ('public_signing_certificate_sha256', '0' * 64), ('transient_worker_sha256', '0' * 64),
                           ('early_selinux_required', False), ('initramfs_root_type_required', 'ramfs'),
                           ('vm_module_signature_enforcement_required', False)):
            saved = copy.deepcopy(self.fx.docs['system-profile.json'])
            self.fx.docs['system-profile.json'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.construction()
            self.fx.docs['system-profile.json'] = saved

    def test_changed_post_vm_root_cannot_reuse_construction_contract(self):
        changed = copy.deepcopy(self.fx.launch_ids)
        changed['rootfs']['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'constructed launch payload'):
            r7.validate_construction(self.fx.docs, self.fx.contract['construction_files'],
                                     self.fx.build, self.fx.build_id, changed)

    def test_modified_missing_extra_link_and_private_files_fail(self):
        target = self.fx.kernel_root / next(iter(self.fx.modules))
        original = target.read_bytes()
        for action in ('modify', 'missing', 'extra', 'link'):
            extra = self.fx.kernel_root / 'signing_key.pem'
            with self.subTest(action=action):
                if action == 'modify': target.write_bytes(b'bad')
                if action == 'missing': target.unlink()
                if action == 'extra': extra.write_bytes(b'never-an-allowed-file')
                if action == 'link': target.unlink(); target.symlink_to(self.fx.root / 'kernel')
                with self.assertRaises((ValueError, OSError)):
                    self.verify()
                if target.is_symlink(): target.unlink()
                target.write_bytes(original); target.chmod(0o644)
                if extra.exists(): extra.unlink()

    def test_snapshot_detects_launch_bundle_and_contract_replacement(self):
        for name in ('rootfs', 'module', 'contract'):
            inputs = self.verify()
            path = {'rootfs': self.fx.root / 'rootfs',
                    'module': self.fx.kernel_root / next(iter(self.fx.modules)),
                    'contract': self.fx.contract_path}[name]
            raw = path.read_bytes(); path.write_bytes(raw)
            with self.subTest(name=name), self.assertRaises(ValueError):
                r7.verify_unchanged(inputs)

    def test_only_memory_reg_delta_is_allowed(self):
        self.assertEqual(r7.check_delta(self.fx.native, self.fx.candidate)[0]['property'], 'reg')
        for candidate in (dt(ram=RAM, unrelated=b'changed\0'), dt(ram=RAM, memreserve=[(0x80900000, 0x200000)])):
            with self.assertRaises(ValueError):
                r7.check_delta(self.fx.native, candidate)

    def test_r5_still_rejects_r7_manifest_and_cli_requires_explicit_selection(self):
        with self.assertRaises(ValueError):
            r5.validate_manifest(self.fx.manifest)
        base = ['--manifest', str(self.fx.manifest_path), '--out', str(self.fx.root / 'out')]
        for args in (base + ['--input-profile', 'r7-rpmh-v1'],
                     base + ['--input-contract', str(self.fx.contract_path)],
                     base + ['--input-profile', 'anything']):
            with self.subTest(args=args), mock.patch.object(launch, 'run_prepared') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    launch.main(args)
                run.assert_not_called()

    def test_duplicate_json_and_same_size_launch_corruption_fail(self):
        raw = self.fx.manifest_path.read_text()
        self.fx.manifest_path.write_text(raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            self.verify()
        self.fx.manifest_path.write_bytes(encoded(self.fx.manifest))
        path = self.fx.root / 'kernel'; data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.verify()

    def test_generic_vm_named_phase_binds_changed_root_and_recorded_scope(self):
        with mock.patch.object(r7, 'GENERIC_VM_WRAPPER_SHA', '1' * 64):
            self.fx.add_generic_vm(); self.fx.write()
            inputs = self.verify()
        self.assertEqual(inputs['evidence_bindings']['rootfs_source'], 'generic-vm-verified-v1')
        self.assertTrue(inputs['evidence_bindings']['generic_vm_recorded_acceptance'])
        self.assertFalse(inputs['evidence_bindings']['generic_vm_acceptance_reexecuted'])
        self.assertFalse(inputs['kernel_bundle_qualification']['physical_hardware_tested'])

    def test_generic_vm_hash_chain_incomplete_children_and_unreparsed_pass_are_rejected(self):
        with mock.patch.object(r7, 'GENERIC_VM_WRAPPER_SHA', '1' * 64):
            self.fx.add_generic_vm()
            ids = {**self.fx.contract['construction_files'], **self.fx.contract['generic_vm_files']}
            initial = copy.deepcopy(self.fx.docs['r7-generic-vm-result.json'])
            for key, value in (('rootfs_before', r7.raw_id(b'wrong chain')),
                               ('acceptance_reparsed', False), ('all_owned_descendants_reaped', False),
                               ('orphan_descendants_found', [12345]), ('exit_code', False)):
                self.fx.docs['r7-generic-vm-result.json'] = copy.deepcopy(initial)
                self.fx.docs['r7-generic-vm-result.json']['phases'][1][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    r7.validate_generic_vm(self.fx.docs, ids, self.fx.launch_ids)

    def test_generic_vm_phase_order_scope_and_guest_result_are_bound(self):
        with mock.patch.object(r7, 'GENERIC_VM_WRAPPER_SHA', '1' * 64):
            self.fx.add_generic_vm()
            ids = {**self.fx.contract['construction_files'], **self.fx.contract['generic_vm_files']}
            receipt = self.fx.docs['r7-generic-vm-result.json']
            receipt['phases'].reverse()
            with self.assertRaises(ValueError):
                r7.validate_generic_vm(self.fx.docs, ids, self.fx.launch_ids)
            receipt['phases'].reverse(); receipt['physical_boot_verified'] = True
            with self.assertRaises(ValueError):
                r7.validate_generic_vm(self.fx.docs, ids, self.fx.launch_ids)
            receipt['physical_boot_verified'] = False
            self.fx.docs['vm-verify-01/guest-result.json']['boot_id'] = 'foreign-boot'
            with self.assertRaises(ValueError):
                r7.validate_generic_vm(self.fx.docs, ids, self.fx.launch_ids)

    def plan(self):
        plan = {key: self.fx.manifest[key] for key in ('kernel_bundle', 'construction_bundle', 'kernel_load_base', 'bootargs')}
        plan['files'] = {name: row['path'] for name, row in self.fx.manifest['files'].items()}
        path = self.fx.root / 'path-plan.json'; path.write_bytes(encoded(plan))
        return path

    def prepare(self, out, **changes):
        args = {'build_sha256': self.fx.build_id['sha256'],
            'construction_sha256': self.fx.contract['construction_files']['r7-construction-result.json']['sha256'],
            'generic_vm_sha256': self.fx.contract['generic_vm_files']['r7-generic-vm-result.json']['sha256']}
        args.update(changes)
        return prepare.prepare(self.plan(), out, **args)

    def test_materializer_requires_actual_three_pins_and_requalifies_post_vm_root_once(self):
        self.fx.add_generic_vm(); self.fx.write()
        out = self.fx.root / 'prepared'
        with mock.patch.object(r7, 'read_file', wraps=r7.read_file) as reader:
            result = self.prepare(out)
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['qemu_started'])
        self.assertFalse(result['contract_auto_activated'])
        self.assertEqual(set(path.name for path in out.iterdir()), {'input-contract.json', 'input-manifest.json', 'qualification.json'})
        self.assertEqual(r7.raw_id((out / 'input-contract.json').read_bytes()), r7.stripped_id(result['input_contract']))
        self.assertEqual(len([call for call in reader.call_args_list if Path(call.args[0]) == self.fx.root / 'rootfs']), 1)
        original = (out / 'input-contract.json').read_bytes()
        with self.assertRaises(ValueError):
            self.prepare(out)
        self.assertEqual((out / 'input-contract.json').read_bytes(), original)
        for pin in ('build_sha256', 'construction_sha256', 'generic_vm_sha256'):
            destination = self.fx.root / pin
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                self.prepare(destination, **{pin: '0' * 64})
            self.assertFalse(destination.exists())

    def test_materializer_preserves_failed_draft_without_activating_bad_root(self):
        self.fx.add_generic_vm(); self.fx.write()
        (self.fx.root / 'rootfs').write_bytes(b'X' * len(self.fx.disk))
        out = self.fx.root / 'failed-preparation'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.prepare(out)
        result = json.loads((out / 'qualification.json').read_bytes())
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['qemu_started'])
        self.assertFalse(result['contract_auto_activated'])


if __name__ == '__main__':
    unittest.main()
