# CNSS IPC reader contract and the owner's missing runtime endpoint

The follow-up checked whether CNSS's separate IPC log could still provide the
actual QMI board ID or selected `bdwlan` filename. **No IPC payload was read:**
the owner's running kernel reports `CONFIG_IPC_LOGGING=y` but
`# CONFIG_DEBUG_FS is not set`, and neither the current root process nor
PID 1 has a debugfs mount. The fixed `cnss/log` and `cnss-long/log` entries
were absent. This is an endpoint/configuration finding, not an empty-log
result or evidence that no firmware was loaded.

The [bounded owner metadata and source record](evidence/android-radio-ipc-readiness.json)
retains all three small acquisition programs, their hashes, the filtered
results and the inspected source hashes. The earlier
[cached WLAN version](radio-board-selection.md) remains unchanged: its BDF
descriptor fields still do not identify the QMI board ID or selected file.

## What the source reader actually does

The inspected implementation is the already acquired public
[`tem423/android_kernel_lenovo_tb371fc` source at
`9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1`](https://github.com/tem423/android_kernel_lenovo_tb371fc/tree/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1).
It is 4.19.325 source evidence, not a claim that the owner's 4.19.157 kernel
is byte-equivalent.

| Source path / function | Contract relevant to a bounded capture |
| --- | --- |
| `drivers/net/wireless/cnss2/debug.c`: `cnss_debug_init()` | Creates contexts named `cnss` and `cnss-long`; the path is not named `cnss2` |
| `drivers/net/wireless/cnss2/debug.h` | Allocates 32 pages per context; ordinary debug messages go to `cnss`, verbose debug messages to `cnss-long` |
| `drivers/net/wireless/cnss2/qmi.c` | Target-capability diagnostics include `board_id`; the BDF-download diagnostic includes the selected filename. Both use the ordinary CNSS debug macro |
| `kernel/trace/ipc_logging_debug.c`: `debug_open()` | Assigns the shared logging context to `file->private_data`; it does not allocate or reset a private per-open cursor |
| Same file: `debug_read()` / `debug_read_cont()` | `log` calls the non-continuous path. `log_cont` can wait for more data; it is unsuitable for the requested one-read capture |
| `kernel/trace/ipc_logging.c`: `ipc_log_read()` / `ipc_log_extract()` | Advance the shared `nd_read_page` and per-page `nd_read_offset`; an empty extraction may reinitialize shared `read_avail` |
| `kernel/trace/ipc_logging_private.h` | With `CONFIG_DEBUG_FS` disabled, `create_ctx_debugfs()` is an empty stub even when IPC logging itself is enabled |

The implementation calls debug extraction **non-destructive** because it
retains underlying ring bytes for later crash-dump extraction. It is not
stateless: successive debugfs reads share an advancing cursor. Reopening the
file or supplying another file offset does not provide an independent
snapshot in this implementation. The destructive ring-space reclamation
path, `ipc_log_drop()`, is separate; a debugfs read does not call that path.
A byte or time bound would not eliminate the shared-cursor side effect.

The first source audit therefore did not treat these files as ordinary
non-consuming metadata. The session then explicitly authorized one controlled
capture that could advance the shared read position, while retaining ring
bytes and preserving returned data in new private files before publication
filtering. It allowed only fixed `cnss/log` and, if needed, `cnss-long/log`,
each with a 256 KiB / one-second read bound; concurrent readers would prevent
the capture. It did not authorize `log_cont`, clearing/resetting a cursor,
changing debug settings, restarting a radio or making a QMI call.

That capture never reached the payload-read stage because no eligible
endpoint was found. No private raw-log file needed to be created, and no
shared cursor was advanced by this investigation.

## Actual owner observations

| UTC capture time | Bounded observation |
| --- | --- |
| `2026-11-23T03:29:15.416943+00:00` | Names/metadata lookup of `/sys/kernel/debug/ipc_logging` and `/d/ipc_logging` returned `ENOENT`; no log file was opened |
| `2026-11-23T03:29:38.168254+00:00` | Filtered current-process mount information contained no debugfs mount. `/sys/kernel/debug` was absent; `/d` was a dangling symlink |
| `2026-11-23T03:30:08.723782+00:00` | Filtered PID 1 mount information also contained no debugfs mount. The running kernel configuration explicitly disabled `CONFIG_DEBUG_FS` and enabled `CONFIG_IPC_LOGGING` |

Each metadata operation had a one-second deadline and fixed size/name bounds.
Only the two configuration lines and debugfs mount metadata were emitted;
the complete mount tables and kernel configuration were not published.
These were root reads of existing metadata, without entering another mount
namespace, mounting a filesystem or changing kernel settings.

The PID 1 check distinguishes a missing endpoint in the current root shell
from a debugfs mount merely hidden in PID 1's namespace. It is not an
exhaustive scan of every process's mount namespace. The explicit compiled
configuration is the further limitation: a new mount cannot supply a feature
that this running kernel did not enable. The source shows why IPC storage
can still be compiled while its debugfs export is absent. It does not prove
whether the shipping CNSS context was created or which old messages it retains.

## Source identities and outcome

The core reader's SHA256 is
`ecb463480282f6af4e8cc72fee5c805b1e36c4bfd9f35844fdd9c35a54e94edf`;
the debugfs frontend is
`ada4f1c6ae02be8f0e54c3e80ad64e66b1ba0ef5ace9e8a5cb352fb404943849`;
the shared-context header is
`7917588147515bb7d633a8a449597dc8b50b193aa0d958e16215c09d505f01e8`.
The JSON also records the exact CNSS logger/QMI-source and public-header
hashes, so the contracts can be checked independently.

No IPC read was repeated after a negative result: **there were zero IPC
payload reads in total**. The current result does not reveal a QMI board ID,
selected BDF path, Bluetooth ROM suffix or firmware authentication status.
It does not promote a candidate `bdwlan` file into ath11k's board database.
It also does not prove that every other possible passive interface has been
exhausted. It closes the narrower question of whether this source's existing
debugfs IPC reader is available on the observed running kernel.

All log-clear/reset, cursor-advance, debugfs-mount, debug-configuration-write,
radio-restart, explicit-QMI, register/MMIO and module-load flags remain false.
No owner Linux test or hardware pass is supplied by this result.
