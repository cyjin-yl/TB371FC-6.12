# Optional Linux reference firmware handoff

`launch_second_stage.py --firmware-profile linux-reference-v1` selects one
explicit synthetic firmware handoff for a paused TB371FC board-model
experiment. The default `--firmware-profile none` retains the existing QEMU
machine arguments and validation path. This option is not a native-device
boot verdict and has not yet been exercised by the retained R5/R7 experiment.

The selected machine suffix is exactly:

```text
rpmh-profile=reference,rpmh-boot-configured=on,aop-profile=reference-qdss-vote,smem-profile=reference-empty
```

The only additional global is
`qcom-tcsr-mutex.boot-unlocked-reference=on`. No raw machine-option argument
is accepted. Kernel, supplied DT, initramfs, root snapshot, command line,
signature enforcement, eight CPUs and 8 GiB model RAM retain their existing
input checks. The unchanged layout validator still checks the actual final
FDT, all native device properties, PSCI domain topology, RAM holes, original
reservations, payload addresses and complete loaded Image/initramfs bytes.

## Three complete pre-resume measurements

The launcher uses QMP `pmemsave` while the VM is paused, retains each actual
capture, and checks its complete length and SHA256 before the sole `cont`.
It confirms the paused state again after capturing these 2,232,320 bytes.

| Region | Address | Bytes | SHA256 |
| --- | --- | ---: | --- |
| CommandDB | `0x80860000` | 131072 | `416efcf69817cc7b0465a33724bace31e576040b3ec775e0a184a2d051f8c6f8` |
| AOP message SRAM | `0x0c300000` | 4096 | `7710db6e1ce6a491cfcc437385464af84fa2bcf272c65575171d88f7dd4fa2a4` |
| SMEM | `0x80900000` | 2097152 | `ffb04af24ae4463ce841fee8f340ae0b1da5c7c72d102784a8689bc1cd904a3d` |

These expectations come from QEMU source
[`6287cd9a41e5114de6cf3a4ac38b0fd85872ee06`](https://github.com/cyjin-yl/qemu-tb371fc/tree/6287cd9a41e5114de6cf3a4ac38b0fd85872ee06).
They describe synthetic model inputs, not captured tablet firmware. The
ordinary qualification of the actual QEMU executable remains a separate
required preparation step; a matching reference image does not establish
the executable's source identity or its complete test coverage.

The public [RPMh reference fixture](https://github.com/cyjin-yl/qemu-tb371fc/blob/6287cd9a41e5114de6cf3a4ac38b0fd85872ee06/tb371fc/fixtures/rpmh-reference.json)
defines 98 typed resources with synthetic addresses and auxiliary maps.
The reference boot handoff seeds the AP/DRV2 XO request, producing the
modeled 19.2 MHz `bi_tcxo` from the board's 38.4 MHz oscillator. The six
catalogued UFS supply resources already exist in this full reference table.
R5/R6's missing `CONFIG_QCOM_CLK_RPMH` remains a separate Linux build issue;
selecting this model profile cannot add a driver to those images.

The [AOP reference peer](https://github.com/cyjin-yl/qemu-tb371fc/blob/6287cd9a41e5114de6cf3a4ac38b0fd85872ee06/hw/misc/qcom-aop-qmp.c)
initializes a MAIL-v1 descriptor and two reference mailboxes in initially
zero SRAM. It supports only `qdss` and `qdss_ao` off/dynamic votes, values
0 and 1. Other services remain unsupported; actual AOP firmware is not run.

The [SMEM builder](https://github.com/cyjin-yl/qemu-tb371fc/blob/6287cd9a41e5114de6cf3a4ac38b0fd85872ee06/hw/misc/qcom-smem-handoff.c)
constructs an empty v12 global allocator. No socinfo, GLINK channel, remote
processor, or remote firmware response is supplied by this handoff.

## Exact additional ROM and reservation

The selected profile requires precisely the existing Image, initramfs, DTB
and bootloader ROM records plus one `tb371fc.smem-reference-empty` ROM at
`0x80900000`, size `0x200000`, targeting RAM. Missing, duplicated, moved,
resized or additional ROM records fail before continuation. The actual SMEM
payload must also match the full-region hash above.

The supplied DT is passed unchanged to QEMU. Its actual final FDT is passed
unchanged to the ordinary layout validator. The reference layer additionally
requires the original FDT reservation multiset plus `(0x80900000, 0x200000)`
exactly once if that pair was absent. If it already existed, the reservation
multiset must remain identical. The final reservation remains part of the
ordinary payload-exclusion arithmetic. No node/property or PSCI exception is
added, and no final DT byte is rewritten or stripped to pass a gate.

## Validation and limits

The fixture suite checks the fixed command, all three complete captures,
tail-byte corruption in each region, missing and duplicate reservations,
wrong/extra ROMs, unrelated device changes, lost PSCI children, and an
unexpected resume during capture. These are controller regression tests with
a QMP fixture; they execute no guest and do not establish R5/R7 boot success.

The run receipt records `synthetic_firmware=true` and the measured hashes.
It retains `physical_firmware_verified=false`, `userspace_verified=false`,
`physical_boot_verified=false`, and zero new owner-native Linux passes. The
existing bounded observation, unchanged-input checks and owned-QEMU cleanup
still apply after a successful paused gate.
