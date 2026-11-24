# R241 TCPM/PMIC diagnostic modules against the new research ABI

The complete exported R241 source was compiled in the isolated CT102 builder
against the already completed `6.12.114-tb371fc-research1` kernel output and
its `Module.symvers`. The build exited **0** after 275.80 seconds. The exported
handoff source checksum list was verified first. Both resulting modules are
ELF64 AArch64 and report the new research release in their vermagic.

| Module | Bytes | SHA-256 |
| --- | ---: | --- |
| `tcpm.ko` | 121,688 | `f9c52a69113c2188b1c4332de612a048f2b99f7b28c945296ef1d1c134da2e4f` |
| `r233_pmic_tcpm.ko` | 37,912 | `13054da40756858cd1309e1789594609cd0cad658def3c7e3026681f34eba176` |

The input kernel `Module.symvers` SHA-256 is
`8e71a956b3c79112228f92cd234a13a39aa7a3193a5d1222d1dab5123043d9d0`.
Exact command/exit records, log hashes, source-manifest hash and compiler
warnings are in [r241-build.json](evidence/r241-build.json).

The reproduction helper is
[build_handoff_modules.sh](../../../scripts/research/build/build_handoff_modules.sh).
It refuses an existing work directory, verifies the export checksums, copies
the complete matched R241 source to `/work/r241-research1`, and builds with
`ARCH=arm64 LLVM=1 M=... W=1`. It does not run `modules_install`, `insmod`,
`modprobe`, a register-writing program or a charging service. These two
diagnostic modules remain separate from the baseline's 83 installed modules.
Their release-string checks do not establish runtime ABI or driver correctness.

The `W=1` build retained two warnings in `qcom_pmic_typec_port.c`: unused
`rp_sel_to_name` and `qcom_pmic_set_cc_debounce` helpers. They were not deleted
or made active merely to obtain a warning-free result. In particular, changing
debounce or timing without a new trace would not establish the cause of the
historical first-message/reset failure.

The existing host-only handoff policy, current-limit/transaction and old/new
RX cleanup models also ran in the same container using `CC=clang`. That job
exited **0** in 8.89 seconds and emitted `OFFLINE_MODELS_PASS`. It rechecked all
17 exported-source checksum entries. These models and the module compilation
are host evidence; **there was no PD negotiation, cable/orientation test,
watchdog activation or charger ownership change on the physical tablet**.

The historical [handoff](../../../experimental/community-handoff/README.md)
still supplies the hardware investigation boundary: R240 acknowledged a first
valid message but observed a later partner reset; R241 was diagnostic logging
and had not been booted by its author. The new build does not resolve that
failure. Single ownership of Type-C/charging, actual negotiated power, both
orientations, role transitions, normal protections and repeated reconnect/
suspend behavior remain in the [whole-device acceptance plan](acceptance.md).
