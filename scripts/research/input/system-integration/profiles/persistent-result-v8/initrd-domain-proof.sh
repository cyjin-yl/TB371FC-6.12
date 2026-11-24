#!/usr/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read the actual initrd processes after systemd and udevd have executed.
set -eu
umask 077

test -e /etc/initrd-release
test -r /proc/1/attr/current
test ! -e /run/tb371fc-r4e-initrd-domains.json

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

IFS=' ' read -r -a cmdwords < /proc/cmdline
rdinit_count=0
tmpfs_opt_in_count=0
for word in "${cmdwords[@]}"; do
    case "$word" in
        rdinit=*)
            test "$word" = rdinit=/init.tmpfs
            rdinit_count=$((rdinit_count + 1)) ;;
        rd.tb371fc.tmpfs-root=*)
            test "$word" = rd.tb371fc.tmpfs-root=1
            tmpfs_opt_in_count=$((tmpfs_opt_in_count + 1)) ;;
    esac
done
test "$rdinit_count" -eq 1
test "$tmpfs_opt_in_count" -eq 1

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

# Inspect PID1's real mount, independently of stage0/1 log messages.
root_matches=0
root_device=
root_source=
root_mount_options=
root_super_options=
while IFS= read -r mountline; do
    IFS=' ' read -r -a fields <<< "$mountline"
    test "${fields[4]-}" = / || continue
    root_matches=$((root_matches + 1))
    root_device=${fields[2]}
    root_mount_options=${fields[5]}
    separator=0
    for ((index=6; index<${#fields[@]}; index++)); do
        if test "${fields[$index]}" = -; then
            separator=$index
            break
        fi
    done
    test "$separator" -ge 6
    test "${fields[$((separator + 1))]}" = tmpfs
    root_source=${fields[$((separator + 2))]}
    root_super_options=${fields[$((separator + 3))]}
done < /proc/1/mountinfo
test "$root_matches" -eq 1
test "$root_source" = tb371fc-initroot
case "$root_device" in
    ''|*[!0-9:]*|:*|*:) exit 1 ;;
esac
case ",$root_mount_options,$root_super_options," in
    *,nosuid,*|*,noexec,*) exit 1 ;;
esac
case ",$root_mount_options," in
    *,rw,*) ;;
    *) exit 1 ;;
esac
for value in "$root_source" "$root_mount_options" "$root_super_options"; do
    case "$value" in
        ''|*[!A-Za-z0-9_:.,=/-]*) exit 1 ;;
    esac
done

# Expected labels are from the unchanged fixed Fedora file_contexts. The
# /run/log directory differs from the separately typed socket pathname rule.
test -c /dev/null
test -c /dev/kmsg
test -d /run
test -d /run/log
test -d /run/log/journal
null_context=$(/usr/bin/stat --format=%C -- /dev/null)
kmsg_context=$(/usr/bin/stat --format=%C -- /dev/kmsg)
run_context=$(/usr/bin/stat --format=%C -- /run)
log_context=$(/usr/bin/stat --format=%C -- /run/log)
journal_context=$(/usr/bin/stat --format=%C -- /run/log/journal)
test "$null_context" = system_u:object_r:null_device_t:s0
test "$kmsg_context" = system_u:object_r:kmsg_device_t:s0
test "$run_context" = system_u:object_r:var_run_t:s0
test "$log_context" = system_u:object_r:syslogd_var_run_t:s0
test "$journal_context" = system_u:object_r:syslogd_var_run_t:s0
journald_pid=$(/usr/bin/systemctl show --property=MainPID --value systemd-journald.service)
case "$journald_pid" in ''|*[!0-9]*) exit 1 ;; esac
test "$journald_pid" -gt 1
journald_context=$(read_context "/proc/$journald_pid/attr/current")
case "$journald_context" in system_u:system_r:syslogd_t:*) ;; *) exit 1 ;; esac
shopt -s nullglob
journal_files=(/run/log/journal/*/system.journal)
test "${#journal_files[@]}" -ge 1
test "${#journal_files[@]}" -le 8
for journal_file in "${journal_files[@]}"; do
    test -f "$journal_file"
    test ! -L "$journal_file"
    test "$(/usr/bin/stat --format=%C -- "$journal_file")" = system_u:object_r:syslogd_var_run_t:s0
done

proof=$(printf '{"schema_version":3,"scope":"initrd before switch-root","boot_id":"%s","pid1_context":"%s","udevd_pid":"%s","udevd_context":"%s","read_only_process_probe":true,"kernel_rdinit":"/init.tmpfs","tmpfs_root_opt_in":true,"root_filesystem":"tmpfs","root_device":"%s","root_source":"%s","root_mount_options":"%s","root_super_options":"%s","early_api_contexts":{"/dev/null":"%s","/dev/kmsg":"%s","/run":"%s","/run/log":"%s","/run/log/journal":"%s"},"journald_pid":"%s","journald_context":"%s","actual_journal_files_count":%s,"actual_journal_files_context":"system_u:object_r:syslogd_var_run_t:s0"}' \
    "$boot_id" "$pid1_context" "$udevd_pid" "$udevd_context" "$root_device" "$root_source" "$root_mount_options" "$root_super_options" \
    "$null_context" "$kmsg_context" "$run_context" "$log_context" "$journal_context" \
    "$journald_pid" "$journald_context" "${#journal_files[@]}")
set -C
printf '%s\n' "$proof" > /run/tb371fc-r4e-initrd-domains.json
printf '\nTB371FC_R4E_INITRD_DOMAINS %s\n' "$proof" > /dev/console
