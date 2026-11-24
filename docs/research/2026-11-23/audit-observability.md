# Audit printk visibility in the fixed research4 generic VM

## Finding and scope

The retained Fedora v7 serial log contains a real suppression warning:
`kauditd_printk_skb: 6 callbacks suppressed` at 60.671667 seconds. Therefore,
that log cannot establish a complete absence of SELinux denials merely from
the AVC records that remain visible. The warning is adjacent to an ordinary
successful service-start audit record, well before the later `journalctl`
socket denial. It does not reveal the suppressed messages or prove that six
AVCs were suppressed. The already failed v7 result remains unchanged.

The fixed Linux 6.12.114 source identifies a narrow mechanism for a subsequent
generic VM: setting the shared printk rate-limit **interval to zero** makes
future `printk_ratelimit()` calls pass that limiter. This changes neither audit
record admission nor audit queue limits, and it cannot recover previous
messages. It must accompany complete-log loss checks; it is not a substitute
for them. The source analysis and proposed guard perform no sysctl setting,
policy load, VM execution, Android operation, or TB371FC hardware test.

Evidence: [source excerpts and analysis](evidence/audit-observability.json),
[frozen V3 source derivation](evidence/audit-observability-source-manifest.json),
[retained v7 raw log](evidence/fedora-r4d-reload-fd-failed-verify.log),
[v7 failed-run report](fedora-r4d-reload-fd-failed.md), and
[frozen research4 kernel](research4-system-kernel.md).

## Fixed inputs

The source was read as ordinary files from the existing research4 build:
`/work/research4-system/source-input/linux-6.12.114-input-integration`.
No source, configuration, kernel artifact, VM disk, or runtime setting was
changed by these source reads. The existing build report binds the kernel
release to `6.12.114-tb371fc-research4-system` and the following identities:

| Input | SHA-256 |
|---|---|
| Kernel Image | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Kernel configuration | `0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275` |
| Source manifest | `840b2b0ae21424061fc218fc9b0f1dcb02165c3aaef77b5398d264234954ad04` |
| Retained v7 serial log, 1,115,806 bytes | `cfe215d2a33dc01f8ffdf7ab5bc2d7dd2f7fafec309d06c82eb3db48bb5658aa` |

The machine-readable evidence contains the full SHA-256, size, and numbered
excerpts for every source used below. It combines two already completed
read-only captures; report preparation did not repeat device access.

## Why the visible warning is not an audit-loss counter

`kernel/audit.c:541–548` sends a non-EOE audit message to printk only if
`printk_ratelimit()` returns true. A false result on this path suppresses the
printk rendering without incrementing `audit_lost`. The intentional exclusion
of the EOE record is also distinct from accidental loss.

`include/linux/printk.h:178–183` routes this macro to
`__printk_ratelimit(__func__)`. `kernel/printk/printk.c:4613–4617` uses one
shared `printk_ratelimit_state`, initially five seconds with a burst of ten.
Those are source defaults; this analysis did not read a live VM's interval or
burst and does not assert their actual values at the warning.

`lib/ratelimit.c:53–70` prints the suppression count when a later caller
reopens the time window. Its displayed function name is the caller at that
time. Because the state is shared, the warning alone cannot assign every
suppressed callback to a particular earlier caller, event type, or AVC. In
addition, `lib/ratelimit.c:41–48` can return false on spinlock contention
without incrementing `missed`; a missing suppression warning is not itself a
proof of complete printing under the nonzero interval.

The actual v7 warning appears at raw line 8043. The following line is a
successful `SERVICE_START` audit record. These facts bound the observation;
they do not reconstruct the omitted content. The already documented v7 AVCs
remain positive evidence of their specific denials.

## Exact scalar interface and minimal change

`kernel/printk/sysctl.c:32–43,81–83` registers these two scalar nodes:

| Node | Underlying value | Handler | Proposed access |
|---|---|---|---|
| `/proc/sys/kernel/printk_ratelimit` | `printk_ratelimit_state.interval` | `proc_dointvec_jiffies` | Read; on an explicitly qualified generic VM, write ASCII `0\n`; reopen and read back |
| `/proc/sys/kernel/printk_ratelimit_burst` | `printk_ratelimit_state.burst` | `proc_dointvec` | Read before and after; require unchanged |

The nodes are registered mode 0644. `kernel/sysctl.c:1149–1166,1248–1266`
implements the interval conversion as a scalar integer represented as ASCII
seconds. The write path multiplies the supplied value by `HZ`; zero becomes
zero without a timing approximation. These handlers read scalar state; this
is not the blocking wakeup-count synchronization interface encountered in
the earlier Android collector.

The decisive condition is `lib/ratelimit.c:33–39`: an interval of zero returns
true **before** locking, quota accounting, and suppression. It therefore
removes this shared limiter's quota and try-lock rejection from subsequent
calls. Setting the burst to zero is not the desired operation: with a nonzero
interval, the quota condition requires a nonzero burst and would reject the
callbacks. The proposed operation leaves burst unchanged. The same interval
behavior is documented in the fixed
`Documentation/admin-guide/sysctl/kernel.rst:1088–1106`.

This is a shared setting, so it affects other callers of the same global
`printk_ratelimit()` state within that disposable generic VM. It does not
disable the separate local states used by `printk_ratelimited()` macros.
`printk_devkmsg` is a different control for userspace `/dev/kmsg` writes and is
not this call chain. No change to either independent mechanism is proposed.

## Boundaries that remain after an interval readback of zero

Audit has separate admission and queue mechanisms:

- `kernel/audit.c:316–342` implements `audit_rate_check()` using
  `audit_rate_limit`; this remains unchanged.
- `audit_log_lost()` increments the separate `audit_lost` counter at line 360
  before deciding whether to print its diagnostic. That diagnostic can itself
  encounter printk limiting.
- The retry and hold queues check the audit backlog limit and can call
  `audit_log_lost()` on overflow. Allocation failures, backlog exhaustion, and
  the audit admission limit remain possible independently of printk visibility.
- Kernel log-buffer loss, console transport loss, retained-output truncation,
  and any other per-call-site limiter need their own evidence checks.

No proposal here modifies `audit_rate_limit`, the backlog limit or wait time,
audit rules, the audit failure mode, SELinux permissions, or Enforcing. Zero
interval does not reset or recover old `missed` records. It does not establish
an absence of earlier losses, nor does it prove that every later event reaches
the saved serial log.

## Frozen V3 source contract; runtime pending

The source-only V3 guard is a separate derivative of the frozen native early
loader. Its [build recipe](../../../scripts/research/selinux/standard-services/build_early_init_v3.py)
and [guard source](../../../scripts/research/selinux/standard-services/audit_printk_guard.inc)
are frozen at `21e912fa4a2b79b771b70e7b6a46187bde2f746425e549e7e4151d0ce3caf268`
and `f715d823ac20181b916afac5c4db9ae9af8226454508e2dff9bb9b8f35e035cc`,
respectively. The source manifest records the complete five-anchor C diff,
the fixed original source and recipe, and the full new policy identity. It
keeps the original non-PID-1 rejection and uses the following gates
before its main path first loads libselinux or calls the policy loader:

1. Existing API mounts must be present with the expected filesystem types.
2. The kernel command line must contain exactly one
   `rd.tb371fc.audit-printk-unlimited=1` token. A missing, duplicated, bare, or
   differently valued instance fails.
3. The process must be root PID 1. The actual NUL-separated sysfs device-tree
   `compatible` property must contain exactly one `linux,dummy-virt` entry.
   This confines the supported recipe to the separately controlled generic VM;
   it is not hardware authentication or authorization to change a tablet.
4. Fixed, bounded reads obtain interval and burst. The guard writes only the
   two-byte interval value, closes the descriptor, and performs fresh-open
   readbacks. It requires interval zero and an unchanged burst.
5. A flushed marker records scope, opt-in, compatible, before/after values,
   unchanged burst, and that this helper has not yet attempted policy loading.
   Any failed operation terminates the candidate boot.

The host must bind the actual helper and policy bytes, require the unique
successful marker before the helper's policy-load marker, and retain all
existing Enforcing, labels, descriptor-route, BPF, process-limit, kernel, and
archive checks. The compile, marker values, setting, and runtime effects are
**not yet observed by this report**. A subsequent actual build/run needs its
own evidence. The independently reviewed policy candidate is described in
[the standard-services policy report](selinux-standard-service-policy.md);
policy permissions and printk visibility are separate contracts.

## Complete-log failure indications

The subsequent host validator should treat the following as failures, with
source-aware matching over the complete raw log rather than just the final
guest JSON:

| Indication | Source meaning |
|---|---|
| Positive `callbacks suppressed` count from the audit/kauditd path | Shared printk callbacks were omitted; their original content cannot be reconstructed |
| Positive `audit_lost=` | The audit subsystem has recorded dropped records |
| `audit_backlog=N > audit_backlog_limit=M` | Backlog limit exceeded while attempting audit logging |
| `kauditd retry queue overflow` or `kauditd hold queue overflow` | A queue-specific audit loss path |
| Audit-context `backlog limit exceeded` or `rate limit exceeded` | A separate backlog or admission rejection |
| `out of memory in audit_log_start` or `out of memory in audit_expand` | An audit allocation failure |

A conservative validator may reject other positive kernel suppression counts
too; the shared-state warning cannot determine which earlier event classes
were affected. The actual source strings and locations are included in the
JSON. Existing AVC, kernel failure, serial truncation, source-binding, and
runtime gates must remain independent. Absence of these printed diagnostics
alone is not a proof of losslessness. A successful new candidate can report
the exact observed guard readback, complete captured log, and absence of known
loss indicators within that bounded run; it cannot certify all possible audit
transport paths or TB371FC hardware.
