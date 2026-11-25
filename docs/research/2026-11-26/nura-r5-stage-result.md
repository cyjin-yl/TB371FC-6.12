# Retained Nura root: actual R5 staging result

Date: 2026-11-26 Asia/Shanghai. Execution: 2026-11-25 18:07:16–18:08:23 UTC.

The previously pending stage in PR19 has now executed successfully in the existing CT102 build environment, using source revision `73307d4a9b756fdb024225a934584dd4e36d1b92`. The source archive and frozen R5 kernel inputs were preserved.

## Actual construction

The [stage receipt](evidence/nura-r5-stage/nura-r5-stage.json) records `complete=true`. It binds the original 307,393,454-byte archive (SHA-256 `eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46`), the staging program, candidate, qualifier and executor identities.

GNU tar inspected 11,469 members: 727,496,775 regular-file bytes, 762 symbolic links and 254 hard links. The original init/OpenRC inventory was checked before and after staging. The separate R5 namespace contains 84 signed modules and three Kbuild input files; all 69 firmware entries match the retained manifest.

The actual Nura AArch64 kmod reports version 34.3 with ZSTD/XZ/ZLIB/OPENSSL support. Target `depmod` exited successfully with empty stdout and stderr. Its [command receipt](evidence/nura-r5-stage/target-depmod.json) and [version output](evidence/nura-r5-stage/target-depmod-version.stdout) are retained unchanged. The [offline module-tree report](evidence/nura-r5-stage/root-module-report.json) reports both `passed=true` and `input_snapshot_stable=true`.

All published execution files are copied from the actual candidate directory, not reconstructed. The 2026-11-24 pending-stage note is historical; this dated result supplies the missing construction evidence.

## Next runtime boundary

The new [generic ARM64 direct-root runner](nura-r5-direct-root.md) derives an independent root and ordinary ext4 image from this successful stage. Its critical evidence and owned-process tests, together with the existing archive tests, passed 20/20 both in the coding workspace and in CT102.

Staging alone does not establish PID1, OpenRC, a root-loader, physical display, firmware loading or native tablet operation. This receipt retains `target_booted=false`, `root_loader_built=false`, and zero owner-native passes. A VM result is recorded separately when actually obtained.
