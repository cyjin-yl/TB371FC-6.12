# Owner TFA9894: a verified cached firmware-request selection

## Observed result

A bounded, read-only capture of the owner's Android metadata returned:

```text
/sys/class/huaqin/interface/hw_info/tfa98xx
tfa98xx_QS.cnt
```

The matching owner module and owner kernel machine code establish that this
specific attribute, hardware-info id **131**, reads a cached registered string.
The TFA probe registers the selected name **before** calling
`request_firmware_nowait()`. The observation therefore identifies a cached
**firmware-request choice**, not successful firmware loading, DSP setup,
calibration or playback. Four amplifiers share this registration id; this one
field does not establish four independent choices or their physical speaker
vendor. Full evidence is in
[`evidence/tfa9894-cached-metadata.json`](evidence/tfa9894-cached-metadata.json).

The two candidate parameters were also safely read:

| Attribute | Actual cached value | Meaning |
| --- | --- | --- |
| `/sys/module/tfa98xx_dlkm/parameters/fw_name_first` | `tfa98xx_YC.cnt` | Configured first candidate |
| `/sys/module/tfa98xx_dlkm/parameters/fw_name_second` | `tfa98xx_QS.cnt` | Configured second candidate |
| `/sys/class/huaqin/interface/hw_info/tfa98xx` | `tfa98xx_QS.cnt` | Name stored in the shared HQ registration slot |

Each read had a two-second timeout and a 1,024-byte output cap. The three
values total **45 bytes including newlines**. No other hardware-info values or
summary attribute were read. No register/I²C operation, calibration, playback,
module load, firmware load, or attribute write was requested by this work.

## Actual inputs, rather than a similar public driver

The owner module is `/vendor/lib/modules/audio_tfa98xx.ko`, **267,094 bytes**,
SHA-256
`94ec336cab4e1aa338e93ac7a8a9f4671b6c3dbfc7109b0530f2318910a89f37`.
Its module name is `tfa98xx_dlkm`, with vermagic
`4.19.157-perf+ SMP preempt mod_unload modversions aarch64`.
It was read as an ordinary fixed file and privately transferred using the
existing, strictly checked SSH connection. Source, receiver and builder copies
match in size and hash. The new private directories are mode `0700` and the
module is `0600`; the initial inherited directory setgid bit was removed while
retaining the original receipt. The module was never loaded or executed.

The existing private `recovery_a.img` backup supplies the uncompressed owner
kernel member at offset 4,096, length **37,445,648 bytes**, SHA-256
`ef9e7b5cdb9ef3c66977a04d6b6e21cf83e83f2f45476390c861827d1bb1cf0f`.
The earlier [boot header inspection](evidence/boot-header-inspection.json)
establishes that this member matches the owner `boot_a` kernel. This task
extracted that already retained file; it did not read live kernel memory or
take another boot-partition dump.

The public tem423 Android source used elsewhere in this project is 4.19.325,
not a byte-equivalent source for the running 4.19.157 kernel. The matching
`tfa98xx` implementation was not found there. Its generic `kernel/params.c`
initially explained the standard parameter ABI, but the safe-read decision was
then corroborated against the **actual owner Image** and module relocations.

## Static chain for the two candidate parameters

Both 40-byte `__param` records in the actual module have a direct AArch64
`ABS64` relocation to the imported `param_ops_charp`, with mode `0644`.
Their argument pointers resolve to the module's `fw_name_first` and
`fw_name_second` cached pointers; their compiled defaults are YC and QS,
respectively. There is no custom TFA getter in this parameter path.

In the owner Image, the `param_ops_charp.get` relocation resolves to
`param_get_charp` at relative `_text` offset `0x6a3e0`. Its machine code loads
`kp->arg`, loads the cached string pointer, and calls `scnprintf()` with a
4,096-byte bound and the constant `%s\n`. It performs no device access.

This distinction matters because the same module also registers binary `rw`
and `reg` attributes. `rw`'s read implementation calls `i2c_transfer()` and
contains a retry path; `reg` is write-only. Neither is a metadata-safe substitute,
and neither was read or written during this work.

## How the actual module chooses and registers a name

All offsets below are relative to the module's `.text` section, not live
addresses.

| Site | Observed machine-code operation |
| --- | --- |
| `tfa98xx_i2c_probe`, `0x1367c` / `0x13680` | The normal probe obtains a GPIO result and stores it at private-structure offset `0x3c0`. This task did not invoke that operation. |
| `tfa98xx_probe`, `0x14b44`–`0x14b6c` | Reads the cached value; zero selects the first candidate and nonzero selects the second. |
| `0x14b7c` | Stores the selected string pointer at private-structure offset `0x328`. |
| `0x14b84`–`0x14b8c` | Passes that pointer to `hq_register_hw_info(131, name)`. |
| `0x14b94`–`0x14bbc` | Passes the same stored pointer to `request_firmware_nowait()`. |

The probe does not check the registration call's return value before proceeding
to the firmware request. The branch tests **zero versus nonzero**, not whether
a GPIO read successfully returned the boolean value 1. Consequently, the
cached QS choice must not be promoted to a verified physical strap state or
speaker supplier. The asynchronous firmware request has not yet completed at
the registration site.

## Why the exact HQ attribute is safe to read

The owner Image contains 121,415 compressed kallsyms names with 475 markers.
The decoder checked every name-block marker and the exact end of the names
stream. Its fixed input hash, dictionary/index offsets and relative symbol
offsets are recorded in the evidence. The file has unrelocated pointer slots;
the corresponding `R_AARCH64_RELATIVE` records were used to resolve the selected
metadata pointers. No live/KASLR address or kernel memory contents were used.

The following chain is present in the actual Image:

1. `hw_info_tfa98xx` has id 131 and attribute name `tfa98xx`.
2. Entry 25 of `huaqin_attrs` points to that attribute. `huaqin_ktype` points to
   this attribute table and `huaqin_sysfs_ops`.
3. The `show` pointer in those sysfs operations resolves to `huaqin_show`.
4. The initialization code creates class `huaqin`, device `interface`, and
   child kobject `hw_info`. These constants yield the exact captured path.
5. In `huaqin_show`, id 131 bypasses the special-id branches. It checks the
   cached registration flag, loads the cached name pointer and formats it with
   `sprintf("%s\n", name)`. Unregistered and null-pointer cases copy fixed
   messages. That branch has no register, I²C, GPIO, firmware or calibration
   call.

The **whole** `huaqin_show` function is not classified as a harmless generic
reader: other ids, including its summary branch, have different behavior.
Only the proven id-131 path was captured. The report records the selected
relocation links, audited function ranges/hashes and branch offsets so the
conclusion can be reviewed without distributing the private kernel Image.

## Shared-slot semantics and limits

`hq_register_hw_info` walks one global attribute array to find the id. If its
registration flag is clear, it stores the supplied name pointer and sets the
flag. If the flag is already set, it returns `-4` without replacing the pointer
on that branch. This is a shared registration record, not one record per
amplifier. The audit does not establish synchronization between simultaneous
registrations, identify which probe populated the slot, or prove that it has
never been deregistered. A single observed value cannot establish the four
amplifiers' individual request histories.

The named candidate already exists in the privately verified firmware bundle:
`vendor/firmware/tfa98xx_QS.cnt`, **26,245 bytes**, SHA-256
`a3f641609cbb617ea2c3169e5a9edc6c04f89a342e99fd96dacc44f216cdfa81`.
Its file identity comes from the previously frozen
[`stock-firmware-bundle.json`](evidence/stock-firmware-bundle.json), not a new
load or compatibility test.

This narrows a genuine Android selection question. It does **not** create a
mainline TFA9894 loader contract: the previously audited generic `tfa989x`
driver and disabled amplifier nodes remain separate porting work. The canonical
firmware staging tree was not changed. DSP programming, speaker routing,
calibration/protection, playback, and physical Linux audio acceptance remain
unverified.

## Reproduce the offline inspection

The version-specific, read-only helper is
[`scripts/research/audio/inspect_tfa_cached_metadata.py`](../../../scripts/research/audio/inspect_tfa_cached_metadata.py).
It accepts only the two audited file sizes/hashes and emits selected metadata
as JSON. It does not open sysfs, access a device, extract or publish binaries,
or perform the live capture automatically.

```sh
python3 -B /src/scripts/research/audio/inspect_tfa_cached_metadata.py \
  --image /work/tfa9894-static-20261123/owner-Image \
  --module /work/tfa9894-static-20261123/audio_tfa98xx.ko
```

The actual run used the dedicated SSD build container and exited **0 in 0.62
seconds**. The remotely verified helper SHA-256 is
`16ee901669d33a55878b3d36045a707fa2f0f471c9729f0e6911e9d1e204e074`.
Its completed job-result SHA-256 is
`1f65ccf178b2ac34f9d4e21dbd4322e0d01bac59c6b7f375c7ac6110bd4168ed`,
and its JSON-output log SHA-256 is
`e8d6c3b4290737ce76863b50395d6b17b71ba68ab3df597ac92bf48e3c420b07`.
A temporary device-bridge disconnect interrupted metadata transport after the
inspection; the evidence retains that failure and the subsequent independent
hash verification. No host or Docker restart was attempted.

The separate evidence retains the exact bounded Android capture commands and
values. Later devices or firmware versions require a fresh getter review;
matching filenames alone do not extend this proof to different binary inputs.
