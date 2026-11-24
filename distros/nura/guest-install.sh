#!/bin/sh
# Run inside the disposable ARM VM after guest-bootstrap.sh succeeds.
set -eu
export PMB_CHANNELS_CFG=/work/pmaports/channels.cfg
export PYTHONDONTWRITEBYTECODE=1
test "$(uname -m)" = aarch64
test "$(git -C /work/pmbootstrap rev-parse HEAD)" = \
    e0dfe2cda7f3a0b70cdcc96f3060100839322aa4
test "$(git -C /work/pmaports rev-parse HEAD)" = \
    d7e3e81fd579f01d4742157257897e2b07fade5c

# pmbootstrap intentionally creates a minimal build chroot without the
# distribution release package. Check native execution and its actual base
# dependencies, not the optional /etc/alpine-release file.
python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --timeout 180 --details-to-stdout chroot --output stdout -- \
    /bin/sh -c 'set -eu; test "$(uname -m)" = aarch64; test "$(apk --print-arch)" = aarch64; uname -m; apk --version; apk info -e alpine-baselayout apk-tools busybox musl-utils'
printf '%s\n' NURA_NATIVE_CHROOT_VERIFIED

# This public dummy password only permits noninteractive image construction.
# The research/root passwords must be locked before the rootfs is exported.
python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --timeout 180 --details-to-stdout install --no-image --no-sshd --no-recommends \
    --no-local-pkgs --password nura-build-only-lock-before-export \
    --add mesa-dri-gallium,mesa-vulkan-freedreno,vulkan-tools,weston,libinput-tools,evtest,networkmanager,bluez
printf '%s\n' NURA_TARGET_INSTALL_COMPLETED

python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --timeout 180 --details-to-stdout chroot --rootfs --output stdout -- /bin/sh -c '
        set -eu
        test "$(uname -m)" = aarch64
        test "$(apk --print-arch)" = aarch64
        uname -m
        cat /etc/os-release
        apk info -e postmarketos-base device-qemu-aarch64 mesa-vulkan-freedreno
        test -f /usr/lib/libvulkan_freedreno.so
        weston --version
        libinput --version
        NetworkManager --version
        passwd -l root
        passwd -l research
        awk -F: "(\$1 == \"root\" || \$1 == \"research\") { if (\$2 !~ /^[!*]/) exit 1; n++ } END { if (n != 2) exit 1 }" /etc/shadow
        printf "synthetic_accounts_locked=2\n"
        apk info -v | sort > /tmp/nura-installed-packages.txt
    '

# These mounts belong to the ARM guest. No host mounts or binfmt entries are
# touched; the guest used native aarch64 chroots throughout this build.
python3 /work/pmbootstrap/pmbootstrap.py --as-root --config /work/pmos.cfg \
    --details-to-stdout shutdown
test -f /work/pmwork/chroot_rootfs_qemu-aarch64/tmp/nura-installed-packages.txt
cp /work/pmwork/chroot_rootfs_qemu-aarch64/tmp/nura-installed-packages.txt \
    /work/target-packages.txt
sync
