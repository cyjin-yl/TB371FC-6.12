#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""CT102: transfer the actual qualified R5 public runtime to a new shared prefix.

The original bounded tar pump is reused byte for byte. Both endpoints run in
their development containers. A passed report with an explicitly supplied hash
is mandatory. No private key, old module index or firmware is in the allowlist.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import signal

import copy_baseline as pump

RELEASE = '6.12.114-tb371fc-research5-services'
SOURCE = 'tb371fc-build-ssd-20261123'
DESTINATION = 'tb371fc-build-20261123'
SOURCE_ROOT = '/work/research5-services'
DEST_ROOT = '/work/research5-services-kernel-inputs-v1'
REPORT = 'research5-services-build.json'
PUMP_SHA = '21e2d3b9887a52ed9fce96366eb71930fd9f5bcdfed901145cfc3a84ebd54ea0'
ARTIFACTS = {
    'Image', 'Module.symvers', 'SHA256SUMS', 'System.map', 'board.dtb',
    'builder-packages.tsv', 'configuration.json', 'kernel.btf', 'kernel.config',
    'kernel.release', 'modules.SHA256SUMS', 'modules.builtin',
    'modules.builtin.modinfo', 'modules.order', 'signing-cert.der',
    'source-manifest-input.json', 'source-manifest.json',
}

CHECK = r'''from pathlib import Path, PurePosixPath
import hashlib,json,os,stat,sys
root=Path(sys.argv[1]);items=json.loads(sys.argv[2]);strict=sys.argv[3]=='exact'
assert root.is_dir() and not root.is_symlink()
observed={}
for name,expected in sorted(items.items()):
 parts=PurePosixPath(name).parts
 assert name and not name.startswith('/') and '/'.join(parts)==name
 assert all(x not in ('','.','..') for x in parts)
 parent=root
 for component in parts[:-1]:
  parent=parent/component;s=parent.lstat()
  assert stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0,str(parent)
 p=root/name;fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd)
  assert stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0 and before.st_nlink==1,name
  with os.fdopen(fd,'rb',closefd=False) as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
  after=os.fstat(fd)
  stable=lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
  assert stable(before)==stable(after),name
  assert before.st_size==expected['size'] and digest==expected['sha256'],name
  observed[name]={'size':before.st_size,'sha256':digest,'mode':stat.S_IMODE(before.st_mode),'uid':before.st_uid,'gid':before.st_gid}
 finally:os.close(fd)
if strict:
 actual=set()
 for current,dirs,files in os.walk(root,followlinks=False):
  for name in dirs:
   p=Path(current)/name
   assert not p.is_symlink(),str(p)
  for name in files:actual.add((Path(current)/name).relative_to(root).as_posix())
 assert actual==set(items),{'unexpected':sorted(actual-set(items)),'missing':sorted(set(items)-actual)}
print(json.dumps(observed,sort_keys=True,separators=(',',':')))
'''


def require(value, message):
    if not value:
        raise RuntimeError(message)


def canonical(name):
    parts = PurePosixPath(name).parts
    require(name and not name.startswith('/') and '/'.join(parts) == name and
            all(item not in ('', '.', '..') for item in parts), 'noncanonical payload name')
    return name


def write_new(name, raw):
    canonical(name)
    code = ('from pathlib import Path; import os,sys; '
            'p=Path(%r); f=p.open("xb"); f.write(sys.stdin.buffer.read()); '
            'f.close(); p.chmod(0o600)') % (DEST_ROOT + '/' + name)
    pump.docker_python(DESTINATION, code, content=raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-sha256', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{64}', args.report_sha256), 'explicit actual report SHA-256 required')
    require(hashlib.sha256(Path(pump.__file__).read_bytes()).hexdigest() == PUMP_SHA,
            'reused bounded transfer helper differs')
    signal.signal(signal.SIGTERM, pump.handle_signal)
    signal.signal(signal.SIGINT, pump.handle_signal)
    pump.SOURCE, pump.DEST = SOURCE, DESTINATION
    read = r'''from pathlib import Path
import hashlib,os,stat,sys
p=Path('/work/research5-services/artifacts/research5-services-build.json')
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 s=os.fstat(fd);assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and s.st_nlink==1 and 0<s.st_size<=2*1024**2
 with os.fdopen(fd,'rb',closefd=False) as f: raw=f.read()
 assert len(raw)==s.st_size and hashlib.sha256(raw).hexdigest()==sys.argv[1]
 sys.stdout.buffer.write(raw)
finally:os.close(fd)
'''
    raw = pump.docker_python(SOURCE, read, [args.report_sha256])
    require(hashlib.sha256(raw).hexdigest() == args.report_sha256, 'report transport differs')
    report = json.loads(raw)
    require(report['kernel_release'] == RELEASE and report['profile'] == 'research5-services' and
            report['physical_hardware_tested'] is False and report['module_loaded_by_inspector'] is False,
            'actual R5 offline-build scope differs')
    for name in ('passed', 'full_image_built', 'complete_modules_installed', 'joint_native_dtb_built',
                 'all_module_cms_signatures_verified', 'all_module_imported_crcs_match_new_build',
                 'all_module_vermagic_matches', 'all_modules_elf_aarch64', 'all_module_btf_present',
                 'all_module_dwarf_debug_sections_stripped'):
        require(report.get(name) is True, 'actual R5 inspection gate is absent: ' + name)
    require(report['recipes']['build_system.py']['sha256'] ==
            '053178a79838a69440a5e18f01f4fc9a9dc8a81c11347f1689c8e062d530439a', 'actual build recipe differs')
    require(report['recipes']['inspect_system.py']['sha256'] ==
            'dbcd4389a5f88549f9bee645c0faa047a13005206933790a589a52b23e5e4ba1', 'actual inspector differs')
    require(report['source_manifest']['services_contract_sha256'] ==
            '3b9730335d5573d98f2f9382f83ba79810c9dd563a9e9eed83668a9b3f24ce21' and
            len(report['configuration_changes']) == 14, 'actual service configuration contract differs')
    require(report['module_set_changes_from_research4'] == {'added': [], 'removed': []},
            'the complete module path set changed')
    require(report['kernel_btf']['exact_bytes_present_in_image'] is True and
            report['signing']['public_certificate_exact_bytes_in_image'] is True and
            report['signing']['private_key_copied_from_old_build'] is False, 'linked public identities differ')
    require(report['files']['board.dtb']['sha256'] ==
            'af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730', 'native joint DT differs')
    require(set(report['files']) == ARTIFACTS, 'exact public artifact allowlist differs')
    identities = {'artifacts/' + name: row for name, row in report['files'].items()}
    report_identity = {'size': len(raw), 'sha256': args.report_sha256}
    identities['artifacts/' + REPORT] = report_identity
    index = {**report['files'], REPORT: report_identity}
    index_raw = ''.join(row['sha256'] + '  ' + name + '\n' for name, row in sorted(index.items())).encode()
    identities['artifacts/qualified-artifacts.SHA256SUMS'] = {
        'size': len(index_raw), 'sha256': hashlib.sha256(index_raw).hexdigest()}
    modules = report['modules']
    require(len(modules) == report['module_count'] == 84, 'all 84 modules are required')
    for row in modules:
        name = canonical(row['path'])
        require(name.startswith('lib/modules/' + RELEASE + '/kernel/') and name.endswith('.ko'), 'module destination differs')
        for field in ('cms_verified', 'all_imported_crcs_match', 'module_btf_present', 'dwarf_debug_sections_stripped'):
            require(row[field] is True, 'module inspection gate is absent')
        require(row['vermagic'].split()[0] == RELEASE and row['sig_hashalgo'] == 'sha512', 'module ABI/signature differs')
        require('modules/' + name not in identities, 'duplicate module payload')
        identities['modules/' + name] = {key: row[key] for key in ('size', 'sha256')}
    require(set(report['module_metadata']) == {'modules.order', 'modules.builtin', 'modules.builtin.modinfo'},
            'three original Kbuild metadata files required')
    for name, row in report['module_metadata'].items():
        relative = 'lib/modules/' + RELEASE + '/' + name
        require(row['installed_path'] == relative and row['artifact_name'] == name and
                all(row[key] == report['files'][name][key] for key in ('size', 'sha256')),
                'original module metadata differs')
        identities['modules/' + relative] = {key: row[key] for key in ('size', 'sha256')}
    require(len(identities) == 106, 'complete runtime/public-evidence allowlist must contain 106 regular files')
    payload = json.dumps(identities, sort_keys=True, separators=(',', ':'))
    before = json.loads(pump.docker_python(SOURCE, CHECK, [SOURCE_ROOT, payload, 'subset']))
    create = r'''from pathlib import Path
import os,shutil
p=Path('/work/research5-services-kernel-inputs-v1')
assert not p.exists() and not p.is_symlink() and shutil.disk_usage('/work').free>1024**3
os.umask(0o077);p.mkdir(mode=0o700)
'''
    pump.docker_python(DESTINATION, create)
    record = {'schema_version': 1, 'complete': False, 'kernel_release': RELEASE,
              'source_container': SOURCE, 'destination_container': DESTINATION,
              'source_root': SOURCE_ROOT, 'destination_root': DEST_ROOT,
              'kernel_report': report_identity, 'source_before': before,
              'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'bounded_tar_pump_sha256': PUMP_SHA,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'private_signing_key_transferred': False, 'firmware_transferred': False,
              'old_depmod_indexes_transferred': False, 'module_loaded': False,
              'original_artifacts_modified': False, 'physical_hardware_tested': False}
    try:
        names = sorted(identities)
        sent = pump.hash_or_copy('r5-services-kernel-copy-v1', SOURCE_ROOT, DEST_ROOT, names, True)
        record['source_stream'] = sent
        received = pump.hash_or_copy('r5-services-kernel-verify-v1', SOURCE_ROOT, DEST_ROOT, names, False)
        record['destination_stream'] = received
        require((sent['sha256'], sent['bytes']) == (received['sha256'], received['bytes']),
                'destination canonical archive differs')
        after = json.loads(pump.docker_python(SOURCE, CHECK, [SOURCE_ROOT, payload, 'subset']))
        destination = json.loads(pump.docker_python(DESTINATION, CHECK, [DEST_ROOT, payload, 'exact']))
        require(before == after == destination, 'complete source/destination bytes or ordinary metadata differ')
        record['source_after'], record['destination_readback'] = after, destination
        bundle = {'schema_version': 1, 'kernel_release': RELEASE,
                  'source_report_sha256': args.report_sha256, 'module_count': 84,
                  'files': identities, 'source_container': SOURCE, 'source_root': SOURCE_ROOT,
                  'private_keys_or_firmware_included': False, 'old_depmod_indexes_included': False}
        bundle_raw = (json.dumps(bundle, sort_keys=True, indent=2) + '\n').encode()
        write_new('bundle.json', bundle_raw)
        record['bundle'] = {'size': len(bundle_raw), 'sha256': hashlib.sha256(bundle_raw).hexdigest()}
        record['files_verified'] = len(identities)
        record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_new('transfer.json', (json.dumps(record, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'complete': True, 'files_verified': 106, 'kernel_report_sha256': args.report_sha256,
                      'destination': DEST_ROOT, 'physical_hardware_tested': False}), flush=True)


if __name__ == '__main__':
    main()
