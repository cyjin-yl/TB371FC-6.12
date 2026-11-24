#!/usr/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read the actual initrd processes after systemd and udevd have executed.
set -eu
umask 077

test -e /etc/initrd-release
test -r /proc/1/attr/current
test ! -e /run/tb371fc-r4b-initrd-domains.json

read_context() {
    value=
    # The fixed Fedora /usr/bin/sh is Bash. read -d '' consumes the proc
    # attribute's NUL terminator without command-substitution warnings.
    IFS= read -r -d '' value < "$1" || test -n "$value"
    case "$value" in
        ''|*[!A-Za-z0-9_:.,-]*) return 1 ;;
    esac
    printf '%s' "$value"
}

IFS= read -r boot_id < /proc/sys/kernel/random/boot_id
case "$boot_id" in
    ''|*[!0-9a-f-]*) exit 1 ;;
esac
test "${#boot_id}" -eq 36
pid1_context=$(read_context /proc/1/attr/current)
test "$pid1_context" = system_u:system_r:init_t:s0
udevd_pid=$(/usr/bin/systemctl show --property=MainPID --value systemd-udevd.service)
case "$udevd_pid" in
    ''|*[!0-9]*) exit 1 ;;
esac
test "$udevd_pid" -gt 1
udevd_context=$(read_context "/proc/$udevd_pid/attr/current")
case "$udevd_context" in
    system_u:system_r:udev_t:*) ;;
    *) exit 1 ;;
esac

proof=$(printf '{"schema_version":1,"scope":"initrd before switch-root","boot_id":"%s","pid1_context":"%s","udevd_pid":"%s","udevd_context":"%s","read_only_process_probe":true}' \
    "$boot_id" "$pid1_context" "$udevd_pid" "$udevd_context")
set -C
printf '%s\n' "$proof" > /run/tb371fc-r4b-initrd-domains.json
printf '\nTB371FC_R4B_INITRD_DOMAINS %s\n' "$proof" > /dev/console
