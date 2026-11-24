# R4F result retention contract

This procedure is fixed before running the new candidate. It records outcomes;
it cannot turn a failed controller or incomplete pipeline into acceptance.

1. Materialize the exact source manifest into the fresh recipe prefix and read
   every member back before launching the one owned pipeline unit. Retain the
   uploader/materializer results, source manifests, exact command and launcher
   hash. Refuse any existing pipeline attempt or source mismatch.
2. Each actual stage writes its own exclusive stdout/stderr/result record. A
   nonzero required stage stops the pipeline. Record subsequent phases as not
   run; do not call a pass-only finalizer to manufacture a completion report.
3. Preserve the controller JSON and complete raw serial bytes without newline
   conversion, pruning, repaired JSON frames, or substituted exits. Record QEMU
   termination and the controller's own result separately from guest claims.
4. The already specified result-file reader runs only after the owned QEMU
   process has exited/reaped. It reads only the dedicated image and fixed member
   path through debugfs without write mode, mount or journal replay. Verify
   ordinary root-owned 0600/single-link metadata, exact source size/hash, unique
   receipt, boot ID and profile identity. Retain extraction errors as errors.
5. If an independently qualified complete guest result identifies a same-boot
   policy export, a separate read-only retention helper may copy that one member
   to a fresh private prefix. Verify the reported length/hash and original
   image metadata, and retain the new extraction record. The binary is not
   guessed from an offline serialized policy or placed in a public log packet.
6. Freeze a new outcome report distinguishing stage result, transport
   qualification, every guest/host gate, visible AVC and audit-loss counts,
   actual behavioral evidence and unexecuted gates. Any full-image checksum is
   obtained after closure; do not run filesystem repair on a failed image.
7. The public evidence packet is a strict allowlist of JSON/text/source/log
   records. Preserve raw log bytes. Exclude private signing keys, guest account
   material, complete firmware payloads and the ordinary exported policy binary.
   Hash each file and the compact transfer packet independently.
8. Only an actually successful complete pipeline can enter its normal finalizer.
   The independent udev qualifier must also succeed; zero positive event counts
   do not prove that the original queue was empty. Any missing/lost-event warning
   remains a failure. No result in this generic VM changes owner-tablet hardware
   acceptance states.
