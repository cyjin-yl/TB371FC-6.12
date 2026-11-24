#!/usr/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Fixed generic-system initramfs entry, before the first SELinux policy load.
# The independent archive checker pins this file and every tool/payload.
set -Eeuo pipefail
umask 022
export PATH=/usr/bin:/usr/sbin
export LC_ALL=C
unset CDPATH ENV BASH_ENV LD_PRELOAD LD_LIBRARY_PATH
trap - CHLD

phase=entry
target=/tb371fc-initroot

on_exit() {
    local code=$?
    if (( code != 0 )); then
        printf 'TB371FC_TMPFS_STAGE0_V1 FAILED phase=%s code=%d\n' "$phase" "$code" >&2
    fi
}
trap on_exit EXIT

fail() {
    printf 'TB371FC_TMPFS_STAGE0_V1 FAILED phase=%s reason=%s\n' "$phase" "$1" >&2
    trap - EXIT
    exit 1
}

[[ $$ -eq 1 && ${EUID:-1} -eq 0 && $# -eq 0 ]] || fail pid1-root-with-no-arguments-required
[[ -f /etc/initrd-release && ! -L /etc/initrd-release ]] || fail initrd-marker-required

# Enumerate the archive's entire top level before creating a new mountpoint.
# Neither a new hidden input nor an unknown top-level directory is copied.
phase=source-layout
shopt -s nullglob dotglob
top=(/*)
[[ ${#top[@]} -eq 18 ]] || fail unexpected-top-level-count
for name in "${top[@]}"; do
    case "$name" in
        /bin|/dev|/etc|/init|/init.systemd|/init.tmpfs|/init.tmpfs-wait|/lib|/lib64|/proc|/root|/run|/sbin|/sys|/sysroot|/tmp|/usr|/var) ;;
        *) fail unexpected-top-level-path ;;
    esac
done
shopt -u nullglob dotglob
for name in /dev /proc /sys /run; do
    [[ -d "$name" && ! -L "$name" ]] || fail api-mountpoint-must-be-directory
done
[[ ! -e "$target" && ! -L "$target" ]] || fail new-root-already-exists

phase=mount-proc
/usr/bin/mount -n -i -t proc -o nosuid,nodev,noexec proc /proc

# Return one actual mount record without evaluating any input as shell code.
mount_record() {
    local wanted=$1 count=0 id parent device mount_root point options remainder
    local -a words
    local index
    MOUNT_DEVICE= MOUNT_TYPE= MOUNT_OPTIONS=
    while IFS=' ' read -r id parent device mount_root point options remainder; do
        [[ "$point" == "$wanted" ]] || continue
        (( count += 1 ))
        [[ "$device" =~ ^[0-9]+:[0-9]+$ ]] || fail malformed-mount-device
        IFS=' ' read -r -a words <<< "$remainder"
        index=0
        while (( index < ${#words[@]} )) && [[ "${words[index]}" != - ]]; do
            (( index += 1 ))
        done
        (( index + 3 < ${#words[@]} )) || fail malformed-mount-fields
        MOUNT_DEVICE=$device
        MOUNT_TYPE=${words[index + 1]}
        MOUNT_OPTIONS=$options
    done < /proc/self/mountinfo
    [[ $count -eq 1 ]] || fail ambiguous-mount-record
}

phase=initial-root
mount_record /
[[ "$MOUNT_TYPE" == rootfs ]] || fail initial-root-must-be-rootfs
old_dev=$MOUNT_DEVICE

phase=command-line
command_line=
IFS= read -r -n 16384 command_line < /proc/cmdline || [[ -n "$command_line" ]]
(( ${#command_line} < 16384 )) || fail command-line-too-long
IFS=' ' read -r -a arguments <<< "$command_line"
enforcing_count=0
selinux_count=0
early_count=0
tmpfs_count=0
rdinit_count=0
for argument in "${arguments[@]}"; do
    case "$argument" in
        enforcing=*)
            [[ "$argument" == enforcing=1 ]] || fail enforcing-command-line
            (( enforcing_count += 1 )) ;;
        selinux=*)
            [[ "$argument" == selinux=1 ]] || fail selinux-command-line
            (( selinux_count += 1 )) ;;
        rd.tb371fc.early-selinux=*)
            [[ "$argument" == rd.tb371fc.early-selinux=1 ]] || fail early-policy-command-line
            (( early_count += 1 )) ;;
        rd.tb371fc.tmpfs-root=*)
            [[ "$argument" == rd.tb371fc.tmpfs-root=1 ]] || fail tmpfs-root-command-line
            (( tmpfs_count += 1 )) ;;
        rdinit=*)
            [[ "$argument" == rdinit=/init.tmpfs ]] || fail rdinit-command-line
            (( rdinit_count += 1 )) ;;
    esac
done
[[ $enforcing_count -eq 1 && $selinux_count -eq 1 && $early_count -eq 1 &&
   $tmpfs_count -eq 1 && $rdinit_count -eq 1 ]] || fail unique-explicit-opt-ins-required
context=
IFS= read -r -d '' context < /proc/self/attr/current || [[ -n "$context" ]]
[[ "$context" == kernel ]] || fail first-policy-must-not-be-loaded

# Descriptor 3 deliberately survives exec and identifies the actual old root.
# Foreground tools are waited for by Bash; no background jobs are started.
# The only inherited child at stage1 must be switch_root's cleaner.
phase=preserve-old-root
exec 3< /

# Supply a real console on an API mount which standard switch_root moves.
# Do not pre-mount /run: systemd must create/label it after policy is loaded.
phase=mount-devtmpfs
/usr/bin/mount -n -i -t devtmpfs -o mode=0755,nosuid,strictatime devtmpfs /dev

phase=mount-new-root
/usr/bin/mkdir -m 0755 -- "$target"
# No context/fscontext override and no nosuid/noexec/nodev on the new root.
/usr/bin/mount -n -i -t tmpfs -o mode=0755,size=192M tb371fc-initroot "$target"
mount_record "$target"
[[ "$MOUNT_TYPE" == tmpfs && "$MOUNT_DEVICE" != "$old_dev" ]] || fail distinct-tmpfs-required
case ",$MOUNT_OPTIONS," in
    *,nosuid,*|*,noexec,*|*,nodev,*) fail new-root-flags-restrict-executable-transition ;;
esac
new_dev=$MOUNT_DEVICE

phase=copy-static-payload
/usr/bin/mkdir -m 0755 -- "$target/dev" "$target/proc" "$target/sys" "$target/run"
# One invocation preserves hardlinks shared by different top-level inputs.
# API roots are excluded entirely: cp -x would still traverse an API mount
# if that mount itself were supplied as an independent source argument.
/usr/bin/cp -a -x -- \
    /bin /etc /init /init.systemd /init.tmpfs /init.tmpfs-wait /lib /lib64 \
    /root /sbin /sysroot /tmp /usr /var "$target/"
[[ -f "$target/init" && ! -L "$target/init" && -x "$target/init" &&
   -f "$target/init.tmpfs-wait" && ! -L "$target/init.tmpfs-wait" &&
   -x "$target/init.tmpfs-wait" ]] || fail copied-native-entries-required

printf 'TB371FC_TMPFS_STAGE0_V1 COPY_COMPLETE old_dev=%s new_dev=%s policy_load_attempted=0\n' \
    "$old_dev" "$new_dev" >&2
phase=standard-switch-root
exec /usr/bin/switch_root "$target" /init.tmpfs-wait
