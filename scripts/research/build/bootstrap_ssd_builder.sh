#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Install only kernel/VM build tools in the dedicated SSD Docker builder.
# /src is read-only. /seed exposes only the public kernel archive and manifest.
set -euo pipefail
test "$(id -u)" = 0
test -d /work
test -d /src/scripts/research/build
test ! -e /work/builder-ready.json
mkdir -p /work/tmp /work/downloads /work/reference-hdd /work/toolchain-check
export DEBIAN_FRONTEND=noninteractive

apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 \
    -o Acquire::https::Timeout=30 update
apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 \
    -o Acquire::https::Timeout=30 install -y --no-install-recommends \
    ca-certificates curl git build-essential clang-19 lld-19 llvm-19 llvm-19-tools \
    bc bison flex libssl-dev libelf-dev dwarves cpio rsync kmod \
    device-tree-compiler python3 xz-utils zstd file pkg-config openssl tmux \
    qemu-system-arm

python3 - <<'PY'
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

work = Path('/work')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True)
    return result.stdout.strip()

archive_hash = '7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3'
manifest_hash = '1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821'
copied = []
for source, target, expected in (
    (Path('/seed/linux-6.12.114.tar.xz'), work/'downloads/linux-6.12.114.tar.xz', archive_hash),
    (Path('/seed/source-manifest.json'), work/'reference-hdd/source-manifest.json', manifest_hash),
):
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise SystemExit('Invalid existing seed target: ' + str(target))
    already_present = target.exists()
    if not already_present:
        with source.open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
    actual = sha(target)
    if actual != expected:
        raise SystemExit('Copied seed checksum mismatch; file retained for inspection: ' + str(target))
    copied.append({'source':str(source),'path':str(target),'size':target.stat().st_size,'sha256':actual,
                   'already_present':already_present})

tools = {}
for name, argv in (
    ('clang',['clang','--version']), ('lld',['ld.lld','--version']),
    ('make',['make','--version']), ('bison',['bison','--version']), ('flex',['flex','--version']),
    ('dtc',['dtc','--version']), ('modinfo',['modinfo','--version']), ('python',['python3','--version']),
    ('qemu_system_aarch64',['qemu-system-aarch64','--version']), ('tmux',['tmux','-V']),
):
    tools[name] = run(argv).splitlines()
if 'clang version 19.' not in tools['clang'][0] or 'LLD 19.' not in tools['lld'][0]:
    raise SystemExit('The selected generic compiler/linker names are not LLVM 19')

probe = work/'toolchain-check/aarch64-probe.c'
probe.write_text('int tb371fc_builder_probe(void) { return 42; }\n')
obj = probe.with_suffix('.o')
run(['clang','--target=aarch64-linux-gnu','-ffreestanding','-c',str(probe),'-o',str(obj)])
header = obj.read_bytes()[:20]
if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20],'little') != 183:
    raise SystemExit('LLVM 19 cross-compile did not produce AArch64 ELF')
packages = work/'builder-packages.tsv'
packages.write_text(run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'])+'\n')

# This session carries real subsequent source/build processes. It is not a
# tailing dashboard and does not replace or restart the old builder's session.
subprocess.run(['tmux','new-session','-d','-s','tb371fc-ssd','-n','ready','-c','/work','bash'],check=True)
subprocess.run(['tmux','set-option','-w','-t','tb371fc-ssd:ready','remain-on-exit','on'],check=True)
record = {
    'schema_version':1,
    'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope':'Dedicated standard Docker kernel builder with SSD work; no tablet or old build modified',
    'ready':True, 'base_image':'debian@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a',
    'tools':tools, 'seed_files':copied,
    'cross_compile':{'aarch64_elf':True,'object_sha256':sha(obj)},
    'package_manifest':{'path':str(packages),'sha256':sha(packages)},
    'bootstrap_script_sha256':sha(work/'control/bootstrap_ssd_builder.sh'),
    'tmux_session':'tb371fc-ssd',
    'kernel_source_assembled':False, 'kernel_built':False, 'physical_hardware_tested':False,
    'limits':['APT packages are inventoried, not from an immutable repository snapshot.',
              'Compiler/tools remain in the fresh Docker writable layer; active source/output use the SSD bind.',
              'No old container snapshot, Nix store, private firmware or signing key was copied.'],
}
with (work/'builder-ready.json').open('x') as output:
    json.dump(record,output,indent=2,sort_keys=True)
    output.write('\n')
print(json.dumps(record,indent=2,sort_keys=True))
PY
