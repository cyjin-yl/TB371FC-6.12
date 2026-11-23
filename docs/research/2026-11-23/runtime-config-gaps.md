# Runtime configuration gaps in the frozen Fedora VM

Date: 2026-11-23. Exact observations, source hashes and follow-up gates: [runtime-config-gaps.json](evidence/runtime-config-gaps.json).

**The four warning families have concrete configuration explanations.** The successful `vm-verify-01` result still establishes its recorded full-system and SELinux gates. It does not establish PIDs-controller enforcement, automount support, BPF LSM filesystem restrictions or the virtual GPIO power button. This diagnosis read existing files and official source only; it changed no frozen kernel, rootfs or helper.

## Observed inputs

Research1's build and artifact configuration both hash to `1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da`. Research2-display's corresponding files both hash to `e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8`. Both disable `CGROUP_PIDS`, `AUTOFS_FS`, `GPIO_PL061`, `FTRACE`, `KPROBES` and `DEBUG_KERNEL`. BPF events, BPF LSM and BTF are not enabled. Both retain `BPF_SYSCALL`, `BPF_JIT`, `CGROUP_BPF`, `PERF_EVENTS`, `SECURITY` and `SECURITYFS`; the LSM order string already contains `selinux` and `bpf`.

The 75,606-byte serial log hashes to `688895559c3a7ae7e155b898c95fe0f9e137813ada422408292e0c1ed7a730e9`. The guest identifies systemd `262.1-1.fc45` and the research1 kernel; a separate read-only builder version query reports QEMU `10.0.13`. The VM result records exit zero, Enforcing SELinux, PID1 `init_t`, no failed units and no physical tablet hardware test. Warning counts below count matching serial-log lines, including repeated unit transitions; they are not counts of distinct hardware failures.

| Warning | Occurrences | Established cause | Separate future candidate |
| --- | ---: | --- | --- |
| Missing `autofs4` | 2 | `AUTOFS_FS=n` omits the actual module | `CONFIG_AUTOFS_FS=m`; include the new module in rootfs and initramfs |
| BPF LSM hook unavailable | 2 | BPF LSM and its events dependency are not compiled | Enable the minimal events/LSM/BTF chain, then verify active attachment |
| Cannot read `pids.max`: ENODATA | 32 | PIDs controller absent; systemd tries the attribute during unit cleanup | `CONFIG_CGROUP_PIDS=y`; verify the controller and a non-root service attribute |
| `gpio-keys` deferred probe | 1 | The QEMU PL061 GPIO supplier driver is absent | `CONFIG_GPIO_PL061=y`; verify the virtual GPIO consumer |

## Why the PIDs warning is not merely a shutdown race

[systemd v262.1 `unit.c`](https://github.com/systemd/systemd/blob/v262.1/src/core/unit.c) reads `pids.max` during the SIGKILL phase of `unit_kill_context()`. It temporarily prevents additional processes from being spawned while a service cgroup is being cleared, then restores the previous value. [`cg_get_attribute_as_uint64()`](https://github.com/systemd/systemd/blob/v262.1/src/basic/cgroup-util.c) explicitly maps a missing attribute's `ENOENT` to `ENODATA`, which produces “No data available.”

These messages occur during `initrd-parse-etc` and `initrd-cleanup`, before switch-root, as well as during final shutdown. The trigger is a unit's cleanup stage, but the independent kernel configuration explains why the attribute cannot exist: `kernel/cgroup/Makefile` compiles `pids.o` only with `CGROUP_PIDS`, and `include/linux/cgroup_subsys.h` conditionally registers that controller. The root cgroup intentionally lacks `pids.max`; the observed warnings concern non-root unit cgroups. A warning alone could also occur after cgroup removal, so the diagnosis rests on both the code path and the actual configuration.

## Autofs and BPF LSM are distinct missing facilities

[systemd's module setup table](https://github.com/systemd/systemd/blob/v262.1/src/core/kmod-setup.c) explicitly requests `autofs4` early because normal auto-loading cannot yet rely on udev's device nodes. Linux 6.12.114's actual `fs/autofs/Makefile` builds `autofs4.o` for `CONFIG_AUTOFS_FS`. This is a missing implementation, not evidence of a module-name typo. A system that never needs an automount can still reach multi-user successfully.

[systemd's BPF filesystem restriction setup](https://github.com/systemd/systemd/blob/v262.1/src/core/bpf-restrict-fs.c) asks [`lsm_supported("bpf")`](https://github.com/systemd/systemd/blob/v262.1/src/shared/lsm-util.c) to inspect `/sys/kernel/security/lsm`. The exact observed warning means that this check did not find BPF LSM. The existing `CONFIG_LSM` string cannot activate code that was not compiled, and `CGROUP_BPF=y` is a different facility.

The minimal selected chain for a new candidate is:

```text
CONFIG_FTRACE=y
CONFIG_KPROBES=y
CONFIG_KPROBE_EVENTS=y
# CONFIG_UPROBE_EVENTS is not set
CONFIG_BPF_LSM=y
CONFIG_DEBUG_KERNEL=y
CONFIG_DEBUG_INFO_DWARF4=y
CONFIG_DEBUG_INFO_BTF=y
```

`BPF_EVENTS` is a hidden option derived by Kconfig from `BPF_SYSCALL`, `(KPROBE_EVENTS || UPROBE_EVENTS)` and `PERF_EVENTS`; it sits inside the `FTRACE` menu. One probe-events path suffices. Full function tracing is not required. `BPF_LSM` additionally requires the already-enabled syscall, JIT and security facilities.

BTF is an additional runtime integration requirement for BTF-based LSM attachment and CO-RE, not a direct `BPF_LSM` Kconfig dependency. In this kernel, DWARF4 plus pahole 1.16 or newer satisfies the BTF build dependency; the SSD builder actually has pahole 1.30. Keep the existing SELinux/LSM order and unprivileged-BPF default restriction. Validate the resolved configuration, active LSM list, kernel BTF and systemd's successful LSM-program attachment separately.

## The GPIO warning belongs to QEMU's virtual power key

[QEMU v10.0.13 `hw/arm/virt.c`](https://github.com/qemu/qemu/blob/v10.0.13/hw/arm/virt.c) creates a PL061 controller and a `gpio-keys/poweroff` child referencing it. The kernel has the GPIO-key consumer but disables its PL061 supplier. Its `gpiolib-of.c` returns `-EPROBE_DEFER` when that GPIO device is not registered, and `gpio_keys.c` reports the observed message.

Enabling `GPIO_PL061` addresses this generic-VM device. It neither diagnoses nor qualifies the Lenovo tablet's physical PMIC GPIOs, keys, touchscreen or keyboard. The next system candidate must still be checked against its own complete boot log and live interfaces; no configuration recommendation here is a claim that those checks have already passed.

The JSON records the official versioned systemd/QEMU source hashes and the matching research1/research2 kernel-source hashes. Fedora's exact downstream source-patch identity was not independently audited in this bounded diagnosis; the installed version, emitted messages and kernel configurations are actual observations.

