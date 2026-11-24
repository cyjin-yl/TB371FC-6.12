#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only, run04-specific R5 release identity gate; never boots or repairs.

Evidence-only validation does not establish possession of the actual artifacts.
Live mode checks the preserved CT102 candidate under the existing lane lock.
The receipt describes generic ARM64 virt only, not a native boot package.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path

from run_r5_vm_phase import (
    IMAGE, LABEL, RELEASE, boot_inputs, identity, require, result_matches, save,
)

SOURCE = "6b24e66087e80c6847f0a759e1f6e9a2b9bd4f0d"
WORK = Path("/work/fedora-r5-system-v4")
JOB = Path("/work/r5-fedora-job-6b24e66-run04")
EVIDENCE = Path("docs/research/2026-11-24/evidence/r5-run04")
PINS = {
    "collected-build-and-lineage.json": (26030, "a2acb928750670fd356a0fd0f49e25ee9943b99f37760cddd3b9cee509b39122"),
    "verify-result.json": (675980, "9f67a541172b9711fd05fdc76e6501ad6ddd956464aa86c43d515da086144c5f"),
    "initrd.stderr": (232, "0ea652cd4cee591c050be455ad79c0afd868df5c6dc1c2f4878dc1e833a22eb4"),
    "run.sh": (2326, "a350134be7acfb44f827ab24c69098bb2c48367bbeb6dbae21ed9e218630f419"),
}
PHASES = ("download", "extract", "regression", "stage", "materialize",
          "configure", "initrd", "image", "label", "verify")
ROUTES = {"noop", "pids", "proc_read_baseline", "proc_read_restricted"}
WARNINGS = {
    "any_kernel_callback_suppression_count", "audit_backlog_overflow_count",
    "audit_loss_reason_count", "audit_lost_positive_count",
    "audit_printk_suppression_count", "autofs4_module_warning_count",
    "bpf_lsm_not_supported_count", "pids_max_read_warning_count",
    "selinux_avc_denial_count", "udev_event_fd_loss_count", "virtual_gpio_failure_count",
}


def exact(path, expected):
    require(path.resolve() == path, "symlink or noncanonical path: " + str(path))
    actual = identity(path)
    require(actual == expected, "identity mismatch: " + str(path))
    return actual


def pinned_json(path, expected):
    exact(path, expected)
    data = json.loads(path.read_bytes())
    exact(path, expected)
    require(isinstance(data, dict), "object required")
    return data


def record_identity(record):
    return {k: record[k] for k in ("bytes", "sha256")}


def validate_records(c, v):
    require(c["schema_version"] == 1 and c["source_revision"] == SOURCE
            and c["work"] == str(WORK) and c["job"] == str(JOB), "wrong source/run")
    receipts = c["run_receipts"]
    require(receipts["exit-code"] == "0"
            and all(receipts[p + ".exit"] == "0" for p in PHASES),
            "construction or VM phase failed")
    rec = c["records"]
    label = rec["lineage-label/after.json"]["content"]
    verify = rec["lineage-verify/after.json"]["content"]
    lresult = rec["vm-label-01/result.json"]
    for stage, lineage, result in (("label", label, lresult["content"]),
                                   ("verify", verify, v)):
        require(lineage["phase"] == stage and lineage["passed"] is True
                and type(lineage["runner_exit_code"]) is int
                and lineage["runner_exit_code"] == 0
                and lineage["physical_hardware_tested"] is False
                and result_matches(result, lineage["before"], stage),
                "VM lineage/runner gate failed: " + stage)
        require(all(result[k] is False for k in ("board_dtb_used",
                    "physical_device_passthrough", "physical_hardware_tested",
                    "host_filesystem_shared", "network", "compiled_module_sig_force")),
                "scope or kernel contract changed")
    l, p = label["before"], verify["before"]
    require(l["image"] == l["original_image"] and label["image_after"] == p["image"]
            and all(l[k] == p[k] for k in ("profile_sha256", "kernel_image_sha256",
                    "runner", "archives", "image_manifest", "original_image"))
            and l["initramfs_sha256"] == l["archives"]["label"]
            and p["initramfs_sha256"] == p["archives"]["verify"]
            and l["archives"]["label"] != p["archives"]["verify"],
            "discontinuous image or boot inputs")
    require(label["result"] == record_identity(lresult)
            and verify["result"] == {"bytes": PINS["verify-result.json"][0],
                                      "sha256": PINS["verify-result.json"][1]},
            "result identity mismatch")
    for k in ("guest_gates_match", "persistent_result_qualified",
              "actual_audit_printk_readback_gate", "actual_pl061_binding_gate",
              "actual_success_path_journal_sync_gate"):
        require(v[k] is True, "production gate failed: " + k)
    for k in ("independent_same_boot_av_gates", "independent_transient_route_gates"):
        require(set(v[k]) == ROUTES and all(x is True for x in v[k].values()),
                "route gates incomplete: " + k)
    gates = v["behavioral_probe_gates"]
    require(set(gates) == {"actual_bpf_file_open_eperm", "actual_tasks_max",
                           "same_boot_policy_export_record"}
            and all(x is True for x in gates.values()), "behavioral gates failed")
    warnings = v["observed_warning_counts"]
    require(set(warnings) == WARNINGS and all(type(x) is int and x == 0
            for x in warnings.values()), "production warnings")
    guest = v["guest_result"]
    expected = {"kernel_release": RELEASE, "root_label": LABEL, "root_type": "ext4",
                "root_source": "/dev/vda", "selinux": "Enforcing",
                "module_files_verified": 84, "firmware_files_verified": 69,
                "module_sig_enforce_sysfs": "Y", "kernel_tainted": 0,
                "multi_user_target": "active", "pid1": "/usr/lib/systemd/systemd",
                "failed_units": []}
    require(all(type(guest[k]) is type(x) and guest[k] == x
                for k, x in expected.items()), "guest identity changed")
    require(guest["module_signature_enforced"] is True
            and guest["all_runtime_hashes_verified"] is True
            and guest["gpu_acceleration_tested"] is False
            and v["vm_module_sig_enforce_argument"] == "module.sig_enforce=1",
            "guest enforcement or scope changed")
    metadata = v["persistent_result_metadata"]
    raw = metadata["receipt"]
    require(metadata["qualified"] is True
            and metadata["source_image_metadata_unchanged"] is True
            and all(metadata[k] is False for k in ("image_mounted",
                    "image_opened_for_write", "filesystem_replayed_or_repaired"))
            and metadata["retained_path"] == str(WORK / "vm-verify-01/guest-result.json")
            and raw["status"] == v["guest_file_status"] == "pass"
            and raw["profile_sha256"] == p["profile_sha256"],
            "persistent result not qualified")
    return {"source_revision": SOURCE, "profile_sha256": p["profile_sha256"],
            "kernel_image_sha256": p["kernel_image_sha256"], "archives": p["archives"],
            "final_image": verify["image_after"], "host_result": verify["result"],
            "raw_guest_result": {"bytes": raw["size"], "sha256": raw["sha256"]},
            "scope": "generic ARM64 virt; no owner hardware or GPU validation",
            "owner_native_linux_passes_added": 0, "native_boot_readiness": "blocked"}


def evidence_only(repo):
    folder = repo / EVIDENCE
    pins = {k: {"bytes": n, "sha256": h} for k, (n, h) in PINS.items()}
    for k, pin in pins.items():
        exact(folder / k, pin)
    c = pinned_json(folder / "collected-build-and-lineage.json", pins["collected-build-and-lineage.json"])
    v = pinned_json(folder / "verify-result.json", pins["verify-result.json"])
    return c, v, validate_records(c, v)


def live_check(c, v, summary):
    # Called with the cooperative R5 lane lock held. No mount, boot, copy or repair.
    require(WORK.resolve() == WORK and WORK.is_dir(), "preserved work missing")
    require({p.name for p in WORK.glob("vm-*")} == {"vm-label-01", "vm-verify-01"}
            and {p.name for p in WORK.glob("lineage-*")} == {"lineage-label", "lineage-verify"},
            "not the original pair of VM attempts")
    for name, value in c["records"].items():
        exact(WORK / name, record_identity(value))
    for name, value in c["originals"].items():
        exact(WORK / name, value)
    for name, value in c["run_receipts"].items():
        require((JOB / name).resolve() == JOB / name
                and (JOB / name).read_text().strip() == value, "job receipt changed: " + name)
    exact(JOB / "run.sh", {"bytes": PINS["run.sh"][0], "sha256": PINS["run.sh"][1]})
    exact(JOB / "initrd.stderr", {"bytes": PINS["initrd.stderr"][0], "sha256": PINS["initrd.stderr"][1]})
    exact(WORK / "vm-verify-01/result.json", summary["host_result"])
    exact(WORK / "vm-verify-01/guest-result.json", summary["raw_guest_result"])
    for stage in ("label", "verify"):
        actual = boot_inputs(WORK, stage)
        recorded = c["records"]["lineage-" + stage + "/after.json"]["content"]["before"]
        require(all(actual[k] == recorded[k] for k in recorded if k != "image")
                and actual["image"] == summary["final_image"],
                "live artifacts differ from qualified run")
    exact(WORK / IMAGE, summary["final_image"])
    return dict(summary, live_artifacts_verified=True, generic_release_identity_verified=True,
                release_package_created=False, physical_hardware_tested=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--live-receipt", type=Path,
                        help="new absolute JSON path directly under /work; omit for evidence-only")
    args = parser.parse_args()
    c, v, summary = evidence_only(args.repo.resolve())
    if args.live_receipt is None:
        print(json.dumps(dict(summary, live_artifacts_verified=False,
                              generic_release_identity_verified=False), indent=2, sort_keys=True))
        return
    out = args.live_receipt
    require(out.parent == Path("/work") and out.name.startswith("r5-run04-seal-")
            and out.suffix == ".json" and not out.exists() and not out.is_symlink(),
            "new independent receipt path required")
    with Path("/work/r5-fedora-lane.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = live_check(c, v, summary)
        save(out, result)


if __name__ == "__main__":
    main()
