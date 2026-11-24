# R5 Novatek 0020+0021: signed staging and target kmod evidence

**Offline integration passed.** The corrected signing stage produced the
84-module candidate, and the actual Fedora ARM64 kmod gate passed at
**2026-11-24 12:27:07 UTC**. It verified all module file identities, regenerated
the target indexes, checked the Novatek signer and 64 imported CRCs, and
resolved the Novatek load plan without loading a module. The earlier mode
rejection, storage timeout, ACL extraction failures, and launcher timeout
remain archived separately. This result adds no physical-tablet or native
Linux boot pass.

## Scope and fixed inputs

This work integrates the already-built Novatek patches 0020 and 0021 into a
new candidate for `6.12.114-tb371fc-research5-services`. The frozen R5 inputs
remain the baseline. Only one of the candidate's 84 modules is replaced.
The target kmod commands operate on files through the pinned PRoot/QEMU
tools. They do not load a module, execute its initialization or probe, boot
the target operating system, or access the physical tablet.

| Input or output | Exact identity |
| --- | --- |
| Accepted unsigned 0020+0021 module | 698,512 bytes; SHA-256 `998623b5b8d5666493162b04b01e3b3453777b3586d644d2296b23674881dc69` |
| Original R5 Novatek module | SHA-256 `898aeaad7fdf7425ca514035ad6b2fe3c32c43ecde78b7dc9fff3098149f8f37` |
| Signed replacement | 104,929 bytes; SHA-256 `3428b2ac0acdab29a46282331da4afdbd000b86b463b99781a0f134011b375c9` |
| R5 public certificate | SHA-256 `07a54ba929080f3c5d74cb485afeca7d7acf7c920fde0b26cf003ba45fd57627` |
| Original complete Fedora canonical archive | 1,323,141,120 bytes; SHA-256 `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96` |
| Fedora ARM64 kmod | 202,456 bytes; SHA-256 `bbcc9efbb7f828e68eb8a9e6d81b0019e765e5f113d2c26262d9dcee4b42c6bf` |

The [evidence index](evidence/novatek-r5-signed/index.json) records the exact
size and SHA-256 of each retained file. Original report/log/exit contents
were recovered from their original tool-returned file values and checked
against their saved byte identities. The `transfer-metadata.json` files are
new manifests of that recovery; they are not represented as original
execution receipts. An evidence publication revision is also distinct from
the Git revision whose recipe executed earlier.

## Attempt 01: host signing passed, strict mode gate rejected it

The original [signing report](evidence/novatek-r5-signed/attempt01/signed/r5-novatek-stage.json)
is 22,320 bytes, SHA-256
`25e4921b0cca0120561d89b43f2e655d69936a2028f88a237550307e19624b5b`.
Its 12,753-byte recipe digest matches `stage_r5_novatek.py` at
`1ff6b326837c4380623c3b606361f3f7b51d8a09`:
`8c87eb45f6389eb81b9245d245b84073ba8836dcf247854f005d6d9c18b9438f`.
The original outer exit is 0, and the report records 84 modules with 83
unchanged. It also records the replacement's mode as **0644**.

The frozen module contract requires **0600**. The subsequent
[target log](evidence/novatek-r5-signed/attempt01/target/r5-novatek-depmod-c1296-run01.log)
and [exit file](evidence/novatek-r5-signed/attempt01/target/r5-novatek-depmod-c1296-run01.exit)
retain the strict contract rejection and exit 1. This exception occurred
before the target output directory was created. No target JSON existed
for that attempt, and none has been reconstructed.

The cause was the kernel signer's atomic output replacement: a `chmod`
before signing did not survive replacement of the destination inode. The
fix at `adaa672e3ebb515ae304749ab4895370ebed05a6` restores the required mode
after signing the new candidate and checks its size and SHA-256 before
and after that operation. The downstream strict mode requirement remains
in force. Both the failed candidate and its original reports are retained.

## Attempt 02: corrected signing passed

The [actual signing report](evidence/novatek-r5-signed/attempt02/signed/r5-novatek-stage.json)
is 22,669 bytes, SHA-256
`405e92520d641dbf967630935c886ce664a013ced959926a13cdf25ca6606683`,
with outer exit 0. The readback at **2026-11-24 10:38:54 UTC** records
source HEAD `adaa672e3ebb515ae304749ab4895370ebed05a6`, tree
`190c3a47e6bfe314b038b1e47c7767e0aaaa7d88`, an empty tracked worktree
status, and Python 3.13.5. The report's 13,649-byte signing recipe has
SHA-256 `12b95c75b1b2b7939b0cfbedf6e97353a67a43bb3d48748c44553a91ddee856b`.

The actual mode restoration is **0644 → 0600**. Both observations contain
the same 104,929-byte signed module and SHA-256 `3428b2ac…375c9`; changing
the mode did not change the signature or payload bytes. The new candidate
retains the other 83 modules. The frozen kernel gate passed, original and
replacement CMS signatures verified, the stripped module retained BTF,
and all 64 imported CRCs were retained. The host-generated dependency
graph contains 84 modules and 143 dependency references.

The original public inputs and accepted unsigned module were checked again.
The signing key remained in its existing build directory. The candidate
and public evidence contain no private signing-key material. The four raw
signing/gate/inventory JSON files, empty outer log, and exit file are
preserved under `attempt02/signed/`.

## Attempt 02 target: runtime read timeout before target tools

The [original target report](evidence/novatek-r5-signed/attempt02/target-failed/r5-novatek-target-depmod.json)
is 2,108 bytes, SHA-256
`d034e43f8a8cb163f0d9d8c2732b05b30b935fd2d7d3dafd96111092802d58ad`.
It started at **10:35:33.717 UTC** and finished at **11:05:38.703 UTC**,
an elapsed 1,804.986 seconds, with outer exit 1. The original canonical
reader has a 1,800-second deadline. The controller observed the source
read advancing until that budget expired. The retained traceback stops
at `common.canonical()`; its stderr file is empty. An independent child
tar-exit receipt was not saved, so no particular child exit code is inferred.

The strict mode contract, copied signed-input gate, public tool identities,
and replacement CMS checks had passed. The complete runtime identity had
not finished reading. Target `depmod`, `modinfo`, and `modprobe` had not
started. This receipt therefore establishes an input-read failure before
target tools, and provides no result about target depmod execution.

The 13,169-byte target recipe digest is
`96dae2e40623ab4d59c1043e8a5b75892e9976b2b75b3f449848d29053b289b4`,
matching the source at `adaa672e…`. The later reference-archive feature
must not be presented as the code that produced this earlier failure.

## Runtime preparation: preserve the ACL failures and exact commands

Moving the complete runtime to faster storage must preserve numeric owners,
modes, timestamps, hardlinks, ACLs, SELinux attributes, and other xattrs.
The separate [public-tools copy receipt](evidence/novatek-r5-signed/runtime-preparation/public-tools-failed/receipt.json)
records `complete=false`. Its extraction subprocess returned 0, but its
[stderr](evidence/novatek-r5-signed/runtime-preparation/public-tools-failed/extract.stderr)
contains POSIX ACL operation-not-supported diagnostics. The wrapper
correctly rejected those diagnostics. The
[pipeline receipt](evidence/novatek-r5-signed/runtime-preparation/public-tools-failed/pipeline.json)
separately records source exit 0 and receiver exit 1. The three final public
tool destination directories were not published by that failed receiver.

The complete runtime receiver saved the exact **1,323,141,120-byte** archive
with the original **`1b3f7bd2…07b96`** digest. Receiving finished at
**12:08:17.184 UTC**. Its original
[final receipt](evidence/novatek-r5-signed/runtime-preparation/full-transfer/ssd-mirror/receipt.json)
is 2,641 bytes with SHA-256
`a5f9af40957623afbeeebca40fc4a7aed5b809f6fc112bb30fed3fb04082e473`.
The [pipeline](evidence/novatek-r5-signed/runtime-preparation/full-transfer/pipeline.json)
finished at **12:08:42.615 UTC** and separately records source exit 0 and
receiver exit 1. The producer's stderr is empty.

The receiver records `archive_identity_verified=true` and `complete=false`:
its subsequent SSD extraction returned 0 but emitted ACL-unsupported
diagnostics. That stderr contains **3,773,902 bytes and 27,419 lines**, with
SHA-256 `3dc093f080d725e76bf4cb2795b8b77fd0e833e52e49d0f3a8fab7aafa82db4d`.
The [retained summary](evidence/novatek-r5-signed/runtime-preparation/full-transfer/ssd-extract-stderr-summary.json)
contains its complete identity, original remote path, and first 12 lines.
The full raw stderr remains at that source path. Its attempted large
transfer exceeded the connector output limit; the truncated transfer is
not part of this archive. The later small receipt transfer was complete
and each file's exact bytes and SHA were verified.

The accepted archive was used as a read-only input to the new RAM attempt.
The ACL-incompatible extracted SSD tree is not qualified. An initial
host-side collector's permission error also did not change the archive or
determine its validity; the original process receipts above establish those
outcomes. The completed RAM target receipts are retained below.

The preparation recipes are retained in both applicable forms:

| Recipe | Actual argument identity | Reproduction file identity |
| --- | --- | --- |
| Runtime receiver Python | 9,142 bytes; `63cb331c63ca2fd1e659811fefa614955e0fdd6a331aaa7b873370e478cdc1c2` | Identical |
| Runtime copy shell | 1,836 bytes; `9912e7cf3d04c4f834a1cbb8624ef11974d9493f55092fd83979c1e602259830` | 1,837 bytes; `9775518fd6337c16562a8caba16f7a9461f0473ca43043577479a8e32911d686` |
| Public-tools copy shell | 4,552 bytes; `31d3f55793dbc70f6577e5612f4f06e149fe4f508ee3adbd53afc4f6e89d98b9` | 4,553 bytes; `dbca7c6d31a29137a79891de5bbfb5e8a531cade337f6a18de73a042e29e8b32` |

Each reproduction shell file adds one final LF to the actual `bash -c`
argument. Both versions are preserved, and their identities are not
interchanged. The runtime producer's preparation budget is 3,600 seconds;
the receiver uses 3,650 seconds for receiving and 600 seconds for extraction.
Those preparation limits do not change the target's original 1,800-second
canonical-read budget.

## Exact cause of the cross-filesystem canonical difference

The actual no-recursion journal directory probe retained its owner, group,
mode, nanosecond mtime, and both 52-byte POSIX ACL values. Each ACL has
SHA-256 `fc742256255ddf9fd3878c1a93c0a2f49b1f9cf2793a30b23ea9d64ea5740aff`.
GNU tar nevertheless wrote the two binary xattr records in a different
order: the source filesystem enumerated default ACL before access ACL,
while tmpfs enumerated access ACL before default ACL.

The complete 10,240-byte
[source](../../../scripts/research/input/signing/fixtures/runtime-pax-order/journal-source.tar)
and
[tmpfs](../../../scripts/research/input/signing/fixtures/runtime-pax-order/journal-target.tar)
metadata archives and their
[diagnostic record](../../../scripts/research/input/signing/fixtures/runtime-pax-order/journal-diagnostic.json)
are preserved as test fixtures. They contain directory metadata and no
journal file bodies.

| Journal probe | SHA-256 |
| --- | --- |
| Source raw tar | `caa6484314f6421fe1f1b9f906da5148f5e6df85823a17e5182a5a9aca54df10` |
| Tmpfs raw tar | `1e9dc9584cb6d7e82599c2309610514efa2810e87d00c0232fa1b2d648e1ca59` |
| Both after ordering only unique PAX records | `d4d9569fcf5dfbdcd6cd5c1a4094002e246afdc63ca8eb16f258c29c5c11ff1c` |

The observed difference is exactly the exchange of those two complete
PAX records. The 512-byte headers, other records, metadata values, padding,
and remaining archive bytes are identical.

## Explicit reference-archive mode

Commit `ff3b485190f9d589c7600da41590f221cb14ec2f` adds
`--reference-runtime-archive`. Its
[exact-head CI](https://github.com/cyjin-yl/TB371FC-6.12/actions/runs/45390913894)
passed. The default mode retains the original raw canonical requirement.
Selecting the new mode explicitly requires the entire reference archive's
original fixed byte count and SHA-256 before using its normalized digest.

The parser orders complete original records only within one PAX `x` or `g`
header. Keys must be unique in that header. It preserves each record's
length prefix, arbitrary binary value, and final LF; it preserves all tar
headers, ordinary bodies, padding, member order, and the complete zero tail.
It rejects duplicate keys, malformed lengths, invalid header checksums,
truncation, unsupported keyword/header encodings, size overrides, sparse
representations, and unsupported member framing. It does not drop ACLs,
xattrs, or timestamps.

The source runtime, copied tool root, and source runtime after the commands
all undergo the same full comparison against that one raw-pinned reference.
All three canonical commands retain the original flags and 1,800-second
budget. Reports retain raw SHA-256, normalized SHA-256, byte counts, and
parsing/reordering counts. The reference itself is read and pinned again
afterward. A normalized match must not be described as equality of the raw
canonical streams.

The 11 new tests use the actual journal pair and targeted negative cases,
including changed or removed ACL values, changed file bodies/headers/padding,
binary values containing LF/NUL/equals signs, duplicate keys, invalid lengths,
checksum failures, truncation, size overrides, and sparse formats. The three
existing target-contract tests also passed locally. These are source and
metadata-comparison checks. The separate actual full-runtime execution is
documented below.

## Initial run03 launcher: client timeout before the worker started

The new helper uses the published `ff3b4851…` source, the successful run02
signed input, and the complete raw-pinned archive. Its external inputs are
read-only bindings. The restored runtime and the target's separate tool
root are new tmpfs trees. The helper is limited to 4 GiB memory with the
same combined memory/swap limit, a 5 GiB `/work` tmpfs, and a 128 MiB
`/tmp` tmpfs. It has no network or tablet-device assignment.

The [initial launcher](evidence/novatek-r5-signed/attempt03/initial-launch/launcher.json)
started at **12:15:14.673 UTC** and returned exit 1
at **12:16:14.740 UTC** when its Docker-create client reached a 60-second
deadline. The subsequent
[structured readback](evidence/novatek-r5-signed/attempt03/initial-launch/inspect-created.json)
found the named container created, with
`Running=false`, PID 0, no start/finish timestamps, and `OOMKilled=false`.
The worker and target gate had not started. This is a launcher/client
failure and adds no target-kmod test result. The original failed launch
record, exact launcher/worker source files, and source contract are retained
independently. The worker file was supplied as a read-only input but had not
executed at this observation. The later start of that already-created
helper has its own controller receipt and validation of its reviewed
configuration and inputs, described next.

## Completed run03: actual Fedora ARM64 target gate passed

The [separate resume controller](evidence/novatek-r5-signed/attempt03/resume-launch/recipes/resume_created_tmpfs.py)
checked the fixed, never-started container's exact configuration, current
inputs, memory availability, and the original failed-launch identities.
It started that existing container once. It did not create a replacement
container or rewrite the initial failed receipts. Its
[original result](evidence/novatek-r5-signed/attempt03/completed/resume-launch.json)
records `complete=true`, exit 0, and unchanged original inputs and recipes.

The worker restored the entire pinned archive into tmpfs, verified the
journal access/default ACL values, and invoked the original published target
script with the explicit reference-archive option. The actual source HEAD
was `ff3b485190f9d589c7600da41590f221cb14ec2f`, tree
`42f9b5b10ac65f1ca59ba30e73ca1f5c861cb03e`, with empty tracked status.
The worker records all ten input-source identities and five public-tool
pins. Those source bytes are checked against that immutable Git revision
in CI; this later evidence publication is not the execution revision.

| Execution | UTC start | UTC finish | Result |
| --- | --- | --- | --- |
| Resume controller | 12:25:02.946604 | 12:27:11.725414 | Complete, exit 0 |
| Helper worker | 12:26:05.393159 | 12:27:07.438854 | Verified, complete, text export complete, exit 0 |
| Target gate | 12:26:36.503440 | 12:27:07.359386 | `target_depmod_verified=true`, complete, exit 0; 30.855946 seconds |
| Docker process | 12:25:45.903430548 | 12:27:08.224783574 | Exit 0, `OOMKilled=false` |

The target stage created a new module root from the 84 modules and three
Kbuild metadata files and regenerated indexes with actual Fedora ARM64
**kmod 34.2**. All 84 `.ko` files match the signed run02 candidate in bytes,
mode, and SHA-256; 83 remain unchanged from frozen R5. Novatek is still
104,929 bytes, mode **0600**, SHA-256 `3428b2ac…375c9`.
The target's four `modinfo` fields—signer, key identifier, hash algorithm,
and vermagic—and all 64 `--show-modversions` CRCs match the signing report.
The eight target commands each have retained command/exit metadata, stdout,
and stderr: all exits are 0, all stderr files are empty, and each command
retains its 120-second budget.

The actual `modprobe --show-depends -C /dev/null -d /candidate -S
6.12.114-tb371fc-research5-services nt36523_ts` lookup returned one loadable
node, `kernel/drivers/input/touchscreen/nt36523/nt36523_ts.ko`. The printed
`insmod` line is the dry-run output format; the executed program was
`modprobe --show-depends`. Built-in dependencies do not become loadable
nodes. The executed gate compared that plan against the newly generated
`modules.dep` closure and passed. The scope of this binary-index query is
**Novatek**, not an independent semantic query for every one of the 84
modules.

The new `modules.dep` identity is 9,595 bytes, SHA-256
`0731a90fb1ad28af8039faa317a209adf6076c5d2bcc2dee45c03c5ef1948218`.
Its graph check records 84 modules and 143 dependency references. The raw
`modules.dep` and binary index files are **not** in the exported text bundle.
The recorded identities, executed source, gate result, and load-plan output
support this check; this archive does not claim an independent recalculation
from a retained `modules.dep` body.

### Whole-runtime equality and resource bounds

All five reference/runtime reads completed with exit 0 and empty stderr.
Each contains **1,323,141,120 bytes**. Their normalized SHA-256 is
`aee1cc942d4f73c648078702d32e9db69b528c910f08c21771872d10cd884b18`.
The comparison still reads the whole runtime and preserves all metadata;
the only normalization is the previously described PAX-record ordering.

| Stream group | Raw SHA-256 | Observation |
| --- | --- | --- |
| Original reference before and after | `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96` | Original hard pin preserved on both reads |
| RAM source, separate tool-root copy, and RAM source after | `7c84d83f307d86b9239aa2ebeb60b64ddc6df04b8c7a61a20cadfddce8414e67` | All three raw streams are identical to each other |

Each parsed stream contains 32,647 tar headers, 5,098 PAX headers, and 5,568
PAX records. The reports retain the per-stream sorting counts as well;
these counts describe record reordering, not a count of changed files.
The reference file's size, mode, and raw hash also match before and after.
The gate reports `inputs_unchanged=true` and
`runtime_source_raw_digest_stable=true`. All canonical comparisons retain
the original 1,800-second deadline.

The restored archive contains 27,549 members. The worker's two-tree memory
estimate, including reserve, was 3,456,475,136 bytes, below its 4 GiB bound.
The observed `memory.peak` was **2,854,940,672 bytes** (about 2.659 GiB),
`memory.max` was 4,294,967,296, and `memory.swap.max` was 0. Every recorded
memory event counter was 0. The read-only root, input bindings, no-network
configuration, and absence of tablet devices remained in force.

### Original receipts and source binding

The completed bundle preserves **60 original files totaling 160,661 bytes**.
Its [transfer metadata](evidence/novatek-r5-signed/attempt03/completed/transfer-metadata.json)
records the source paths, byte identities, and capture at
**12:29:59.692667 UTC**. The 36 exported target files total 116,333 bytes;
their raw bytes match the original export manifest. The final Docker state
and [source-binding summary](evidence/novatek-r5-signed/attempt03/source-binding.json)
are separately marked archival summaries, rather than new execution results.

| Original receipt | Bytes | SHA-256 |
| --- | ---: | --- |
| [Target](evidence/novatek-r5-signed/attempt03/completed/results/target/r5-novatek-target-depmod.json) | 34,486 | `e43372c19d3ae4af72835fbfd47c9a1d81b472504ce3d78f60fb5800d0849598` |
| [Worker](evidence/novatek-r5-signed/attempt03/completed/results/runner.json) | 19,226 | `2bc5eecd22843ec152739c52ce7a00cc59831b66fae49194561d0238301052db` |
| [Resume controller](evidence/novatek-r5-signed/attempt03/completed/resume-launch.json) | 16,803 | `7d9e2b20b608a343071ca90bf382c03a851a3187886104cc23337ef088e5c461` |
| [Target export](evidence/novatek-r5-signed/attempt03/completed/results/target-export.json) | 5,824 | `98aaa071987311b6298a8b92d5f98ac12a29518a0105efe565af355b65333621` |

The worker binds the exact target-receipt bytes, and the resume controller
binds the exact worker-receipt bytes. The original five frozen launcher and
recipe inputs match before and after. The complete archive index covers
111 retained evidence files, including earlier failures and exact preparation
recipes; the index itself is the additional inventory file. CI checks all
retained file sizes/hashes, recipe bindings, immutable source files and tree,
and the target → worker → resume receipt chain using a bounded eight-commit
checkout.

The successful signed run02 candidate remains in its independent SSD
directory. The helper's tool root, regenerated indexes, and module tree
were temporary RAM outputs; bounded text receipts were exported before exit.

## Remaining boundary

Kernel-side signature acceptance, physical touch/pen behavior, WDT/ESD
recovery, suspend/resume, and native Linux boot remain outside this gate.
No 6.12 module was loaded into the tablet's vendor kernel. The owner
native-Linux pass count remains unchanged at this integration step.
