# SPDX-License-Identifier: GPL-2.0-only
"""R5-specific system_common adapter for the frozen v9 validation recipe.

Materialize this as system_common.py in a fresh recipe directory. It does not
import or mutate the previous v9 system_common.py or work directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

import stage_r5_fedora as staging

WORK = Path(__file__).resolve().parent.parent
ROOT = WORK / "rootfs"
LABEL = "tb371fc-r5-f45"
IMAGE = WORK / "fedora45-research5-services.ext4"
PROFILE = ROOT / "usr/share/tb371fc/system-profile.json"
QEMU = staging.QEMU
PROOT = staging.PROOT


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative(name):
    return staging.relative(name)


def check(path, expected, size=None):
    result = staging.check(path, expected)
    if size is not None and result["bytes"] != size:
        raise ValueError("size mismatch: " + str(path))


def save(name, value):
    path = staging.under(WORK, name, mkdir=True)
    staging.save(path, value)


def copy_new(source, destination):
    expected = staging.identity(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.copy_exact(source, destination, expected)


def preserve_write(name, text):
    path = staging.under(ROOT, name, mkdir=True)
    if path.exists() or path.is_symlink():
        backup = path.with_name(path.name + ".before-research5-integration")
        if backup.exists() or backup.is_symlink():
            raise ValueError("configuration backup already exists")
        path.rename(backup)
    with path.open("x") as stream:
        stream.write(text)


def qualified_stage():
    if WORK.parent != Path("/work") or not WORK.name.startswith("fedora-r5-system-"):
        raise ValueError("dedicated R5 work directory required")
    staging.ordinary_dir(WORK)
    staging.ordinary_dir(ROOT)
    receipt = WORK / "r5-runtime-stage.json"
    record = json.loads(receipt.read_text())
    if (record.get("complete") is not True or record.get("kernel_release") != staging.RELEASE
            or record.get("owner_native_linux_passes_added") != 0):
        raise ValueError("successful independent R5 staging required")
    staging.check(PROOT, staging.PINS[PROOT])
    staging.check(QEMU, staging.PINS[QEMU])
    if record["stage_source"] != staging.identity(Path(staging.__file__)):
        raise ValueError("staging recipe differs from the executed staging code")
    check(WORK / "root-module-report.json", record["root_module_report"]["sha256"])
    report = json.loads((WORK / "root-module-report.json").read_text())
    if not report["root_module_tree"]["passed"]:
        raise ValueError("R5 offline root module gate failed")
    return record


def profile():
    qualified_stage()
    result = json.loads(PROFILE.read_text())
    if (result.get("schema_version") != 1 or result.get("root_label") != LABEL
            or result.get("kernel_release") != staging.RELEASE
            or result.get("staging_receipt_sha256") != sha(WORK / "r5-runtime-stage.json")
            or result.get("configured_module_sig_force") is not False
            or result.get("vm_module_signature_enforcement_required") is not True):
        raise ValueError("unexpected R5 profile identity")
    check(WORK / "system-profile.json", sha(PROFILE))
    return result


def run_guest(arguments, capture=False, timeout=600):
    qualified_stage()
    env = dict(os.environ, LD_LIBRARY_PATH=staging.HOST_LIBS, SYSTEMD_OFFLINE="1")
    return subprocess.run([str(PROOT), "-0", "-r", str(ROOT), "-q", str(QEMU),
                           "-b", "/proc", "-b", "/dev/null", "-b", "/dev/zero",
                           "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/", *arguments],
                          env=env, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None)


def create_ext4(root, image, label, *, size_bytes=4 * 1024**3, mkfs_timeout=2400):
    """Build only an exclusively created ordinary file, never a block device.

    Preserve the failed output and command receipts. The longer explicit HDD
    deadline addresses the retained v9 copy-into-ext4 timeout; it does not
    guarantee completion and does not modify the host storage configuration.
    """
    staging.ordinary_dir(root)
    staging.ordinary_dir(image.parent)
    if (not label.isascii() or not 1 <= len(label) <= 16 or
            any(not (ch.isalnum() or ch in "-_") for ch in label)):
        raise ValueError("invalid ext4 label")
    if type(size_bytes) is not int or not 64 * 1024**2 <= size_bytes <= 8 * 1024**3:
        raise ValueError("invalid image byte bound")
    if not 1 <= mkfs_timeout <= 3600:
        raise ValueError("invalid image construction timeout")
    if shutil.disk_usage(image.parent).free < size_bytes + 64 * 1024**2:
        raise ValueError("insufficient space for independent image")
    with image.open("xb") as stream:
        stream.truncate(size_bytes)
    if image.is_symlink() or not image.is_file() or image.stat().st_size != size_bytes:
        raise ValueError("ordinary image file required")
    # The image name is a single owned, exclusive path. Do not mount it or
    # attach it to a loop device.
    prefix = image.name
    staging.run(image.parent, prefix + ".mkfs",
                ["/usr/sbin/mkfs.ext4", "-F", "-L", label, "-E",
                 "lazy_itable_init=0,lazy_journal_init=0", "-d", str(root), str(image)],
                timeout=mkfs_timeout)
    staging.run(image.parent, prefix + ".fsck", ["/usr/sbin/e2fsck", "-fn", str(image)],
                timeout=600)
    staging.run(image.parent, prefix + ".label",
                ["/usr/sbin/blkid", "-p", "-s", "LABEL", "-o", "value", str(image)])
    if (image.parent / (prefix + ".label.stdout")).read_text().strip() != label:
        raise ValueError("actual image label mismatch")
    result = {"path": str(image), "size_bytes": size_bytes, "sha256": sha(image),
              "filesystem": "ext4", "label": label, "physical_block_device_used": False,
              "mkfs_timeout_seconds": mkfs_timeout,
              "scope": "host ordinary-file construction and read-only fsck; not a guest boot"}
    return result


def build_image():
    data = profile()
    archives = {}
    for name, suffix, role in (
            ("initramfs.json", "", "production-tmpfs-early-selinux"),
            ("maintenance-initramfs.json", "-maintenance", "maintenance-label-only")):
        record = json.loads((WORK / name).read_text())
        path = ROOT / "boot" / ("initramfs-" + data["kernel_release"] + suffix + ".img")
        if (record.get("archive_verified") is not True or record.get("role") != role
                or record.get("kernel_release") != data["kernel_release"]
                or Path(record["path"]) != path):
            raise ValueError("unqualified phase-specific archive")
        check(path, record["sha256"], record["size_bytes"])
        archives[role] = record["sha256"]
    if len(set(archives.values())) != 2:
        raise ValueError("production and maintenance archives must be distinct")
    result = create_ext4(ROOT, IMAGE, LABEL)
    result["archives"] = archives
    result["profile_sha256"] = sha(PROFILE)
    save("image.before-boot.json", result)
    print("FEDORA_R5_IMAGE_CREATED", flush=True)
