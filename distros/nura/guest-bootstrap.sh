#!/bin/sh
# Run only inside the disposable Alpine ARM VM, after its private 9p mounts.
set -eu
export PMB_CHANNELS_CFG=/work/pmaports/channels.cfg
export PYTHONDONTWRITEBYTECODE=1
test "$(uname -m)" = aarch64
test -f /work/pmbootstrap/pmbootstrap.py
test -f /work/pmaports/pmaports.cfg
# The initial repository is served from the GPG-verified ISO on the container's
# loopback interface. Keep APK signature checks enabled while installing its CA
# bundle, then use HTTPS for subsequent official repositories.
apk add --no-cache --repository http://10.0.2.2:18083/apks ca-certificates-bundle
printf '%s\n' \
    https://dl-cdn.alpinelinux.org/alpine/v3.24/main \
    https://dl-cdn.alpinelinux.org/alpine/v3.24/community \
    > /etc/apk/repositories
apk update
apk add --no-cache python3 git kpartx util-linux openssl procps tar rsync ca-certificates

test "$(git -C /work/pmbootstrap rev-parse HEAD)" = \
    e0dfe2cda7f3a0b70cdcc96f3060100839322aa4
test "$(git -C /work/pmaports rev-parse HEAD)" = \
    d7e3e81fd579f01d4742157257897e2b07fade5c
python3 --version
python3 /work/pmbootstrap/pmbootstrap.py --version
date -u
uname -a
apk info -v > /work/arm-builder-packages.txt

# Initialize a *new empty* work directory with the same version/cache_git state
# as pmb.config.init.ask_for_work_path(). Never mark an old workdir as migrated.
python3 - <<'PY'
import pathlib
import sys
sys.path.insert(0, "/work/pmbootstrap")
import pmb.config
work = pathlib.Path("/work/pmwork")
work.mkdir(mode=0o700, parents=True, exist_ok=True)
version = work / "version"
if not version.exists():
    if list(work.iterdir()):
        raise SystemExit("Refusing to initialize a nonempty, unversioned work directory")
    work.chmod(0o700)
    (work / "cache_git").mkdir(mode=0o700)
    version.write_text(str(pmb.config.work_version) + "\n")
PY

python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --timeout 180 --details-to-stdout work_migrate
python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --timeout 180 --details-to-stdout chroot --output stdout -- \
    /bin/sh -c 'set -eu; test "$(uname -m)" = aarch64; test "$(apk --print-arch)" = aarch64; uname -m; apk --version; apk info -e alpine-baselayout apk-tools busybox musl-utils'
