#!/usr/bin/env bash
# Fetch fixed upstream userspace sources without attaching any tablet device.
set -euo pipefail
work=${TB371FC_BUILD_WORK:-/work}
mkdir -p "$work/downloads"
fedora=Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz
fedora_sha=bc6c3b3e132e3ed5eff398112d16fcdca13dc8abd63550f8aad40e882b9617b6
fedora_base=https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Container/aarch64/images
if ! test -f "$work/downloads/$fedora"; then
    curl --fail --location --retry 3 --connect-timeout 20 --max-time 1800 \
        "$fedora_base/$fedora" --output "$work/downloads/$fedora.partial"
    printf '%s  %s\n' "$fedora_sha" "$work/downloads/$fedora.partial" | sha256sum -c -
    mv "$work/downloads/$fedora.partial" "$work/downloads/$fedora"
fi
printf '%s  %s\n' "$fedora_sha" "$work/downloads/$fedora" | sha256sum -c -
curl --fail --location --retry 3 --output "$work/downloads/Fedora-Container-45-1.4-aarch64-CHECKSUM" \
    "$fedora_base/Fedora-Container-45-1.4-aarch64-CHECKSUM"
curl --fail --location --retry 3 --output "$work/downloads/fedora.gpg" https://fedoraproject.org/fedora.gpg
gpgv --keyring "$work/downloads/fedora.gpg" "$work/downloads/Fedora-Container-45-1.4-aarch64-CHECKSUM"
if ! test -f "$work/downloads/${fedora%.xz}"; then
    xz --decompress --keep "$work/downloads/$fedora"
fi
test ! -e "$work/fedora-oci"
skopeo copy --override-arch arm64 \
    "oci-archive:$work/downloads/${fedora%.xz}" "oci:$work/fedora-oci:45"
umoci unpack --rootless --image "$work/fedora-oci:45" "$work/fedora-bundle"
cat "$work/fedora-bundle/rootfs/etc/os-release"
file "$work/fedora-bundle/rootfs/usr/bin/rpm"

for item in \
    pmbootstrap:e0dfe2cda7f3a0b70cdcc96f3060100839322aa4 \
    pmaports:d7e3e81fd579f01d4742157257897e2b07fade5c; do
    name=${item%%:*}
    revision=${item#*:}
    test ! -e "$work/$name"
    git init "$work/$name"
    git -C "$work/$name" remote add origin "https://gitlab.nura.eco/nura/$name.git"
    git -C "$work/$name" -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=60 \
        fetch --depth=1 origin "$revision"
    git -C "$work/$name" checkout --detach "$revision"
    git -C "$work/$name" rev-parse HEAD
done
python3 "$work/pmbootstrap/pmbootstrap.py" --version
