# R4B / v5: archive qualified, early filesystem relabel denied

**Result: failed before systemd execution.** The new native initramfs program
successfully loaded the fixed Fedora policy with Enforcing active, but its
recursive relabel stopped at `/var`. The kernel denied `filesystem associate`
from `var_t` to the initramfs filesystem's `root_t` context. The helper returned
an error; PID1 exited and the kernel panicked. The host correctly reported
failure even though QEMU itself returned exit code 0. The old image, native
helper, policy, recipe and raw log are retained without repair or rerun.

This is an isolated generic ARM64 VM result. It is not an owner-tablet boot,
a working initrd process-domain proof, a successful D-Bus fix, or a completed
TasksMax/BPF test. The exact machine report is
[evidence/fedora-r4b-early-failed.json](evidence/fedora-r4b-early-failed.json),
16,698 bytes, SHA-256
`679c225df602523acf3f0c4775b3b94ba98da539dfc01826f2fe5f6340dd88fd`.

## Fixed candidate and source

The independent candidate is `/work/fedora-input-system-v5` in the standard
HDD Docker builder `tb371fc-build-20261123` on CT102. It uses the frozen
`6.12.114-tb371fc-research4-system` Image, its inspected 84-module set and 69
owner firmware files, with the joint Lenovo display/input DT packaged as an
artifact. The QEMU machine uses its own generic `virt` DT and has no physical
device passthrough, network or host filesystem share.

| Identity | SHA-256 |
|---|---|
| Actual 14-file execution recipe manifest | `660693cac452a8bb8ce6cee14c6381a98fcadb53e11165befa6c702e19e7ff05` |
| Kernel Image | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Fixed native `/init`, 72,048 bytes | `e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d` |
| Fixed early-policy archive checker | `58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e` |
| Maintenance initramfs, 30,710,305 bytes | `d51e8bed022157e2c41da417f42a52c1c32689a117292211319809e5fa85700d` |
| Production initramfs, 32,466,768 bytes | `9f2a664305c968f4fc3efecd4ef5298a1723cae9030d896a2bc35f2f94bb6668` |
| System profile | `db050eeb6240e43cf1870602c6b51fdc03f64585ccc8a627216edb68b03e6184` |

The exact source map is
[evidence/fedora-r4b-execution-source.json](evidence/fedora-r4b-execution-source.json).
Its repository-tracked full overrides are under
`scripts/research/input/system-integration/profiles/early-selinux-v5`, with a
materializer and pinned supplemental sources. The immutable executed recipe
is `/work/fedora-input-system-recipe-r4-v3`; the checked source overlay is
`/work/fedora-r4-early-profile-source-v1`. These do not overwrite the earlier
[R3 failure](fedora-research3-system.md) or
[first R4 broker-path failure](fedora-research4-bus-failed.md).

## Actual preparation and VM results

| Phase | Result | Controller duration |
|---|---:|---:|
| Checked runtime staging | Exit 0 | 3.00 s |
| Independent root configuration | Exit 0 | 4.50 s |
| Two actual initramfs archives and checks | Exit 0 | 231.62 s |
| Ordinary ext4 image creation | Exit 0 | 51.53 s |
| Maintenance labeling VM | Exit 0 | 167.59 s |
| Production Enforcing VM | **Exit 1** | 8.02 s |

The maintenance QEMU lifetime was 166.82 s. It used the explicitly separate
maintenance archive and `enforcing=0` to label the new ext4 image, then shut
down cleanly. Its diagnostic denial lines are not production Enforcing
success. The production QEMU lifetime was 7.01 s, with
`selinux=1 enforcing=1 rd.tb371fc.early-selinux=1 module.sig_enforce=1`.
No production boot relaxation was introduced.

The production archive really passed the fixed checker. The actual compressed
newc bytes contained the pinned native `/init`, the original `/init.systemd`
symlink and original systemd ELF; all 34 policy/config/context files matched
the fixed Fedora source; all 69 firmware payloads matched their manifest.
The actual target ARM `ldconfig -p -C` map agreed with the qualified old 38
libraries plus libsepol, and all 137 non-firmware ELF payloads inspected in the
archive were ARM64. The proof script, unit and activation link were also
checked by bytes, mode and target. These are archive qualifications, not proof
that a policy permits every runtime relabel operation.

The full positive archive record is
[evidence/fedora-r4b-early-initramfs-validation.json](evidence/fedora-r4b-early-initramfs-validation.json)
(109,842 bytes, SHA-256
`8500f905f34f5074289f15bc1ad86843cd2c137963008614023c814ba6c121dd`).
The activation record is
[evidence/fedora-r4b-early-initrd-proof-payloads.json](evidence/fedora-r4b-early-initrd-proof-payloads.json)
(SHA-256 `dd78c328257308fdd9055135c8de9900266464ba9451730491620ce975224054`).
The immutable original R1 archive remained the independent baseline for this
check; the new maintenance archive was not substituted for it.

## Exact early failure

The raw production log first records:

```text
TB371FC_EARLY_SELINUX_V1 POLICY_LOADED enforcing=1 context=system_u:system_r:kernel_t:s0
```

At approximately 5.35 s of guest time, the observed AVC is:

```text
avc: denied { associate } ... pid=1 comm="init" name="var" dev="rootfs"
scontext=system_u:object_r:var_t:s0
tcontext=system_u:object_r:root_t:s0
tclass=filesystem permissive=0
```

The next lines are:

```text
Could not set context for /var: Permission denied
TB371FC_EARLY_SELINUX_V1 FAILED phase=restore-initramfs-contexts reason=initramfs-relabel-failed errno=13
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000100
```

The source/target above are the new inode label and filesystem context in the
association check; the denial must not be recast as an `init_t`/D-Bus pipe
failure. The real kernel observation identifies an additional permission
boundary absent from the earlier compile, API-only and archive checks. It
requires a source-supported filesystem-label or bootstrap correction in a new
candidate. No policy allow, `setenforce`, ignored restorecon error, or relaxed
host gate is applied to this failed candidate.

There is no native `EXEC_SYSTEMD` success line, no initrd post-exec process-domain
record, and no root-side guest result. Consequently the strict `initrc_t`
validator, actual loaded-policy AV query, broker child/pipe checks, real
`--wait --pipe` probes, TasksMax enforcement and BPF controlled denial were
**not executed in this production boot**. Their source remains available and
their gates remain required for any later candidate.

## Independent queue-loss qualification also rejects this run

Before production, a separate read-only qualification script was fixed to
inspect the full raw log against its original controller hash and reject the
matched udev monitor/storage/push/receive/insert/restore error paths. Its source
SHA-256 is
`1eddb80693eec755cad7cfbc4aa53681c6b923863e6a8f9c331f22fc91de42c2`.
The [predeclared plan](evidence/udev-handoff-qualification-plan.json) includes a
negative check against the real retained first-R4 lost-FD log.

For this v5 run the supplementary qualification returned exit 1, because the
original production VM failed. It found no queue-count proof and does not
infer an empty queue from absent debug lines. Counts, when present, count only
successful storage and insertion operations; even equality is not an
independent inventory of the complete original queue. The frozen result is
[evidence/fedora-r4b-early-udev-qualification.json](evidence/fedora-r4b-early-udev-qualification.json),
SHA-256 `c031446f3c5060af04fe886cb23b217896f62ae578fea527f5aaaf8f1b2613c4`.

## Retained image and raw evidence

The retained image is
`/work/fedora-input-system-v5/fedora45-research4b-early-selinux.ext4`,
4,294,967,296 bytes, SHA-256
`d3db01728e1b02640d98504fd9c445f68975908da0aa9ad3bf66c3b068fd017c`.
The failed production run has no successful-system or clean-poweroff claim,
and no filesystem repair was performed while freezing it.

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| [Maintenance raw serial](evidence/fedora-r4b-early-failed-label.log) | 1,112,853 | `9deff1641fc1c6b4832d2b3db24595eb4c4c99a33195308875586663df4526c7` |
| [Production raw serial](evidence/fedora-r4b-early-failed-verify.log) | 19,359 | `4bcf21659de6f20fe700626897f26deafa3ed125fd394d14d65ca3f206005a75` |
| [Original production controller result](evidence/fedora-r4b-early-failed-verify.json) | 2,161 | `0debd6eb20b5f08c6ada549ff994d57215b7ba476543360e6d7351d7d1c40e8a` |

Original CR/LF bytes are preserved. The previous failed copy, quiescent copy
and exact three-directory-mtime comparison also remain separate. This run
adds no owner-tablet Linux pass and changes no hardware acceptance threshold.
