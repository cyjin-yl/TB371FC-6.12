#!/usr/bin/env bash
# Build the Fedora 45 ARM64 userspace experiment inside the prepared container.
# This never configures host binfmt_misc and never mounts or flashes a tablet.
set -euo pipefail

fedora_work=${TB371FC_FEDORA_WORK:-/work}
fedora_root="$fedora_work/fedora-bundle/rootfs"
fedora_tools="$fedora_work/fedora-host-tools"
fedora_proot="$fedora_work/fedora-proot-src"
proot_revision=25dc6a3134891f98a79f57ce1c2c1b23ff15cad1
uthash_revision=e493aa90a2833b4655927598f169c31cfcdf7861
phase=${1:-check}

test -f "$fedora_root/etc/os-release"
grep -qx 'VERSION_ID=45' "$fedora_root/etc/os-release"
test -x /usr/bin/qemu-aarch64-static

fedora_run() {
    # Only these container resources are explicitly bound. In particular,
    # physical DRM, input, block devices, /sys and the host /run are not bound.
    # PRoot is an execution compatibility layer, not a security boundary.
    LD_LIBRARY_PATH="$fedora_tools/unpacked/usr/lib/x86_64-linux-gnu" \
    SYSTEMD_OFFLINE=1 \
    "$fedora_proot/src/proot" -0 -r "$fedora_root" \
        -q /usr/bin/qemu-aarch64-static \
        -b /proc -b /dev/null -b /dev/zero -b /dev/random -b /dev/urandom \
        -b /etc/resolv.conf:/etc/resolv.conf -w / "$@"
}

dnf_flags=(--releasever=45 --forcearch=aarch64 --setopt=zchunk=False
           --setopt=install_weak_deps=False --setopt=keepcache=True
           --repo=fedora --repo=updates)
packages=(
    mesa-dri-drivers-26.2.7-1.fc45.aarch64
    mesa-vulkan-drivers-26.2.7-1.fc45.aarch64
    mesa-libEGL-26.2.7-1.fc45.aarch64
    mesa-libGL-26.2.7-1.fc45.aarch64
    mesa-libgbm-26.2.7-1.fc45.aarch64
    egl-utils-9.0.0-12.fc45.aarch64
    glx-utils-9.0.0-12.fc45.aarch64
    vulkan-tools-1.4.350.0-2.fc45.aarch64
    weston-15.0.1-3.fc45.aarch64
    weston-demo-15.0.1-3.fc45.aarch64
    libdrm-2.4.134-2.fc45.aarch64
    libinput-utils-1.32.0-1.fc45.aarch64
    wayland-utils-1.3.0-4.fc45.aarch64
)

case "$phase" in
    prepare-tools)
        # Download/extract build dependencies locally; do not install packages
        # into the container's root layer. Versions match the captured build.
        mkdir -p "$fedora_tools/packages" "$fedora_tools/unpacked"
        (
            cd "$fedora_tools/packages"
            apt-get download \
                libtalloc2=2:2.4.3+samba4.22.11+dfsg-0+deb13u1 \
                libtalloc-dev=2:2.4.3+samba4.22.11+dfsg-0+deb13u1 \
                pkgconf=1.8.1-4 pkgconf-bin=1.8.1-4 libpkgconf3=1.8.1-4
            for package in libtalloc2_*.deb libtalloc-dev_*.deb \
                           pkgconf_*.deb pkgconf-bin_*.deb libpkgconf3_*.deb; do
                dpkg-deb -x "$package" "$fedora_tools/unpacked"
            done
            sha256sum ./*.deb
        )
        if ! test -d "$fedora_proot/.git"; then
            test ! -e "$fedora_proot"
            git init "$fedora_proot"
            git -C "$fedora_proot" remote add origin https://github.com/proot-me/proot.git
            git -C "$fedora_proot" fetch --depth=1 origin "$proot_revision"
            git -C "$fedora_proot" checkout --detach "$proot_revision"
        fi
        test "$(git -C "$fedora_proot" rev-parse HEAD)" = "$proot_revision"
        git -C "$fedora_proot" diff --exit-code
        git -C "$fedora_proot" submodule update --init --depth=1
        test "$(git -C "$fedora_proot/lib/uthash" rev-parse HEAD)" = "$uthash_revision"
        PATH="$fedora_tools/unpacked/usr/bin:$PATH" \
        PKG_CONFIG_PATH="$fedora_tools/unpacked/usr/lib/x86_64-linux-gnu/pkgconfig" \
        PKG_CONFIG_SYSROOT_DIR="$fedora_tools/unpacked" \
        LD_LIBRARY_PATH="$fedora_tools/unpacked/usr/lib/x86_64-linux-gnu" \
            make -C "$fedora_proot/src" -j2 WITHOUT_PYTHON=1 proot
        LD_LIBRARY_PATH="$fedora_tools/unpacked/usr/lib/x86_64-linux-gnu" \
            "$fedora_proot/src/proot" --version
        sha256sum "$fedora_proot/src/proot"
        ;;
    query)
        fedora_run /usr/bin/bash -c \
            '/usr/bin/true && /usr/bin/test -r /etc/os-release && /usr/bin/stat /etc/os-release'
        fedora_run /usr/bin/dnf5 "${dnf_flags[@]}" repoquery --available \
            --queryformat '%{name} %{evr} %{arch}' \
            mesa-dri-drivers mesa-vulkan-drivers mesa-libEGL mesa-libgbm \
            mesa-libGL egl-utils glx-utils vulkan-tools weston weston-demo \
            libdrm libinput-utils wayland-utils
        ;;
    install)
        if ! test -f "$fedora_work/fedora-base-packages.tsv"; then
            fedora_run /usr/bin/rpm -qa \
                --qf '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n' \
                > "$fedora_work/fedora-base-packages.tsv"
        fi
        # Deliberately keep all RPM scriptlets enabled. SYSTEMD_OFFLINE=1
        # prevents service-manager operations from targeting a live system.
        fedora_run /usr/bin/dnf5 -y "${dnf_flags[@]}" install "${packages[@]}"
        ;;
    check)
        fedora_run /usr/bin/dnf5 "${dnf_flags[@]}" --cacheonly check
        fedora_run /usr/bin/rpm --verifydb
        fedora_run /usr/bin/rpm -q "${packages[@]}"
        fedora_run /usr/bin/rpm -V \
            mesa-dri-drivers mesa-vulkan-drivers mesa-libEGL mesa-libgbm \
            weston weston-demo
        for target in /usr/bin/weston /usr/bin/eglinfo /usr/bin/vulkaninfo \
                      /usr/lib64/libEGL_mesa.so.0 /usr/lib64/libgbm.so.1 \
                      /usr/lib64/libvulkan_freedreno.so /usr/lib64/dri/msm_dri.so; do
            printf 'DYNAMIC_LINK_CHECK %s\n' "$target"
            fedora_run /lib/ld-linux-aarch64.so.1 --list "$target"
        done
        fedora_run /usr/bin/rpm -qa \
            --qf '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n' \
            > "$fedora_work/fedora-final-packages.tsv"
        ;;
    *)
        printf 'Usage: %s {prepare-tools|query|install|check}\n' "$0" >&2
        exit 2
        ;;
esac
