#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Construct an R7 Fedora root/initrd from the fixed R5 Fedora base recipe.

Run only inside the established build container under the owner's original
heavy-job admission, after the exact R7 build receipt has passed. All output
is new ordinary files; this program does not boot, mount, flash or load modules.
The frozen R5/v9 inputs and archive/runtime acceptance gates remain unchanged.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone

RELEASE = "6.12.114-tb371fc-research7-rpmh-clock"
R5_RELEASE = "6.12.114-tb371fc-research5-services"
R6_RELEASE = "6.12.114-tb371fc-research6-tianma-off"
LABEL = "tb371fc-r7-f45"
PROFILE = "research7-rpmh-clock-fedora45-derived-v9"
BUILD_RECIPE_SHA = "dcf48c7491181343406f3d60053c80a3f1fef768040b17e912952aa653d23213"
CONFIG_SHA = "84747cefce945deaf0134e52c3b1a8a2bf771f3082853d6903be59ab6d5a92a4"
NATIVE_DTB_SHA = "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730"
R6_BUILD_SHA = "f37fbe20624e7f49bdf09eeda28b536fe4da24f9379143efeac598da5a110cc7"
METADATA = {"modules.builtin", "modules.builtin.modinfo", "modules.order"}
ARTIFACTS = {"Image", "board.dtb", "kernel.config", "kernel.release", "System.map",
             "Module.symvers", "signing-cert.der", "kernel.btf"} | METADATA
FROZEN = {
    "scripts/research/rootfs/stage_r5_fedora.py": "4a4f8ea16a154b6ef2cfcb49766412c99df5d3ca3945cfc691841f3a8060fbfb",
    "scripts/research/rootfs/materialize_r5_fedora_recipe.py": "6f8a6755830d58219b06933edee000b3a8af7375805a289294647d045a479121",
    "scripts/research/rootfs/r5_system_common.py": "fd7839683e6fcee820c8eb20bc0414ce1157cf5978561ba63b9e02e64b257e1a",
    "scripts/research/boot_rootfs.py": "6bcfb231179f2c2495e45d93cd4b6503c7f6408c5901ce1898533d2e8ad8a806",
}
SUPPLIERS = {
    "kernel/drivers/regulator/qcom-rpmh-regulator.ko",
    "kernel/drivers/interconnect/qcom/qnoc-sm8250.ko",
    "kernel/drivers/interconnect/qcom/icc-rpmh.ko",
    "kernel/drivers/interconnect/qcom/icc-bcm-voter.ko",
    "kernel/drivers/interconnect/qcom/interconnect_qcom.ko",
}
POLICY = "ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798"
OLD_POLICY = "928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430"
BOOTSTRAP = "0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14"
CANCEL_SIGNAL = None


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def identity(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "ordinary file required: " + str(path))
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require(all(getattr(info, k) == getattr(after, k) for k in
                ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")),
            "file changed while hashing: " + str(path))
    return {"bytes": info.st_size, "sha256": sha}


def pinned(path, expected):
    got = identity(path)
    require(got == expected if isinstance(expected, dict) else got["sha256"] == expected,
            "file identity differs: " + str(path))
    return got


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def once(text, old, new):
    require(text.count(old) == 1, "frozen derivation anchor differs: " + repr(old))
    return text.replace(old, new, 1)


def machine_id_permissions(work, expected=None):
    """Restore only the new empty machine-id to its retained backup's 0644."""
    require(work.is_absolute() and work.name.startswith("fedora-r7-system-")
            and work.resolve(strict=True) == work, "canonical R7 work directory required")
    root, etc = work / "rootfs", work / "rootfs/etc"
    names = ("machine-id", "machine-id.before-research7-integration")
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
              "st_size", "st_mtime_ns", "st_ctime_ns")
    directories = {}
    with contextlib.ExitStack() as stack:
        parent = None
        for path in (work, root, etc):
            require(path.resolve(strict=True) == path, "machine-id parent escaped new root")
            fd = os.open(path if parent is None else path.name,
                         os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
            stack.callback(os.close, fd)
            info, named = os.fstat(fd), path.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0 and
                    (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino),
                    "ordinary root-owned machine-id parent required")
            directories[str(path)] = {key: getattr(info, key) for key in
                                      ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")}
            parent = fd
        opened = {}
        for name in names:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                         os.O_NOATIME | os.O_CLOEXEC, dir_fd=parent)
            stack.callback(os.close, fd)
            opened[name] = fd

        def observe(name):
            fd = opened[name]
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
                    before.st_nlink == 1 and before.st_size == 0,
                    "empty single-link root-owned machine-id file required: " + name)
            attrs = {}
            for key in os.listxattr(fd):
                raw = os.getxattr(fd, key)
                attrs[key] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(all(getattr(before, key) == getattr(after, key) == getattr(named, key)
                        for key in fields), "machine-id identity changed while observing: " + name)
            return {"metadata": {key: getattr(after, key) for key in fields},
                    "identity": {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}, "xattrs": attrs}

        before, backup = (observe(name) for name in names)
        require(stat.S_IMODE(backup["metadata"]["st_mode"]) == 0o644,
                "retained empty machine-id backup must be mode 0644")
        require((before["metadata"]["st_dev"], before["metadata"]["st_ino"]) !=
                (backup["metadata"]["st_dev"], backup["metadata"]["st_ino"]),
                "new machine-id must be distinct from retained backup")
        require("system.posix_acl_access" not in before["xattrs"],
                "fresh machine-id must not have a named access ACL")
        if expected is None:
            require(stat.S_IMODE(before["metadata"]["st_mode"]) == 0o600,
                    "fresh configured machine-id must retain the observed empty 0600 prestate")
            os.fchmod(opened[names[0]], 0o644)
            os.fsync(opened[names[0]])
            after = observe(names[0])
            require(stat.S_IMODE(after["metadata"]["st_mode"]) == 0o644 and
                    after["identity"] == before["identity"] and after["xattrs"] == before["xattrs"] and
                    all(after["metadata"][key] == before["metadata"][key]
                        for key in fields if key not in ("st_mode", "st_ctime_ns")),
                    "machine-id repair changed more than the file mode")
            require(observe(names[1]) == backup, "retained machine-id backup changed")
            proof = {"schema": "tb371fc-r7-machine-id-permissions-v1", "path": str(etc / names[0]),
                     "backup_path": str(etc / names[1]), "directories": directories,
                     "before": before, "after": after, "retained_backup": backup,
                     "restored_mode": "0644", "mode_source": "retained pre-research7 configuration",
                     "content_written": False, "backup_changed": False, "global_umask_changed": False}
        else:
            require(stat.S_IMODE(before["metadata"]["st_mode"]) == 0o644 and
                    expected["schema"] == "tb371fc-r7-machine-id-permissions-v1" and
                    expected["restored_mode"] == "0644" and
                    expected["path"] == str(etc / names[0]) and expected["backup_path"] == str(etc / names[1]) and
                    expected["directories"] == directories and expected["after"] == before and
                    expected["retained_backup"] == backup,
                    "machine-id permissions or retained backup changed during construction")
            proof = {"passed": True, "path": str(etc / names[0]), "after": before,
                     "retained_backup": backup, "read_only_reverification": True}
        for path in (work, root, etc):
            require(path.resolve(strict=True) == path and
                    all(getattr(path.lstat(), key) == value for key, value in directories[str(path)].items()),
                    "machine-id parent identity changed")
        return proof


def validate_evidence(build, signatures, abi):
    require(build.get("passed") is True and build.get("kernel_release") == RELEASE
            and build.get("recipe", {}).get("sha256") == BUILD_RECIPE_SHA
            and build.get("retained_inputs_reverified") is True
            and build.get("offline_modules_qualified") is True
            and build.get("old_objects_copied") is False
            and build.get("old_private_key_copied") is False
            and build.get("native_hardware_passes_added") == 0,
            "exact completed R7 build required")
    require(build["module_count"] == signatures.get("module_count") == abi.get("module_count") == 84,
            "84 modules required in all build/signature/ABI receipts")
    require(signatures.get("passed") is True and signatures.get("input_snapshot_stable") is True
            and abi.get("passed") is True and abi.get("input_snapshot_stable") is True
            and abi.get("kernel_release") == RELEASE,
            "completed stable signature and ABI receipts required")
    cert = build["artifacts"]["signing-cert.der"]
    require(signatures["public_certificate"]["der_sha256"] == cert["sha256"],
            "signature receipt uses a different public certificate")
    sigs = {"modules/" + row["path"]: {k: row[k] for k in ("bytes", "sha256")}
            for row in signatures["modules"]}
    require(len(sigs) == len(signatures["modules"]) == 84 and sigs == build["modules"]
            and all(row["passed"] is True and row["verified_content_matches"] is True
                    and row["verified_signer_der_sha256"] == cert["sha256"]
                    for row in signatures["modules"]), "signed module bytes differ from build receipt")
    prefix = "modules/lib/modules/" + RELEASE + "/"
    require(all(name.startswith(prefix + "kernel/") and name.endswith(".ko") and
                ".." not in Path(name).parts for name in build["modules"]),
            "foreign release or invalid module path")
    abis = {prefix + row["path"]: {k: row[k] for k in ("bytes", "sha256")}
            for row in abi["modules"]}
    require(len(abis) == len(abi["modules"]) == 84 and abis == build["modules"]
            and all(row["imported_symbol_crcs_match"] is True and row["debug_info_stripped"] is True
                    for row in abi["modules"]), "ABI module bytes differ from signed build")
    require(set(build["artifacts"]) == ARTIFACTS and set(build["module_metadata"]) == METADATA,
            "R7 artifact or Kbuild metadata inventory differs")
    require(build["artifacts"]["kernel.config"]["sha256"] == CONFIG_SHA
            and build["artifacts"]["board.dtb"]["sha256"] == NATIVE_DTB_SHA,
            "R7 config or unchanged native DTB differs")
    require(abi["module_symvers"] == build["artifacts"]["Module.symvers"],
            "ABI CRC export source differs from built artifact")
    for name in METADATA:
        require(build["module_metadata"][name]["installed"] == build["artifacts"][name],
                "installed Kbuild metadata artifact differs: " + name)
    relative = {name[len(prefix):] for name in build["modules"]}
    require(SUPPLIERS <= relative, "required UFS supplier modules absent from qualified build")
    return prefix, sorted(relative)


def qualify_kernel(repo, kernel, expected_build_sha):
    receipt = pinned(kernel / "build-result.json", expected_build_sha)
    build = json.loads((kernel / "build-result.json").read_text())
    pinned(kernel / "module-signatures.json", build["offline_signature_result"])
    pinned(kernel / "module-abi.json", build["offline_abi_result"])
    signatures = json.loads((kernel / "module-signatures.json").read_text())
    abi = json.loads((kernel / "module-abi.json").read_text())
    prefix, relative = validate_evidence(build, signatures, abi)
    r6 = repo / "docs/research/2026-11-26/evidence/tianma-r6-build/build-result.json"
    pinned(r6, R6_BUILD_SHA)
    expected = sorted(name.split("/" + R6_RELEASE + "/", 1)[1]
                      for name in json.loads(r6.read_text())["modules"])
    require(relative == expected, "module-relative paths differ from the qualified R6 set")
    files = {}
    for name, wanted in build["modules"].items():
        pinned(kernel / name, wanted)
        files[name] = {**wanted, "mode": stat.S_IMODE((kernel / name).lstat().st_mode)}
    for name, wanted in build["artifacts"].items():
        pinned(kernel / "artifacts" / name, wanted)
    for name in METADATA:
        path = kernel / prefix / name
        pinned(path, build["module_metadata"][name]["installed"])
        files[prefix + name] = {**identity(path), "mode": stat.S_IMODE(path.lstat().st_mode)}
    source = kernel / "source-inventory.json"
    pinned(source, build["source_inventory"])
    require((kernel / "artifacts/kernel.release").read_text() == RELEASE + "\n", "release payload differs")
    contract = {"schema_version": 1, "scope": "R7 module identity/depmod contract only; not the R5 boot contract",
                "kernel": {"release": RELEASE, "module_count": 84},
                "kernel_files": [{"path": name, **files[name]} for name in sorted(files)],
                "build_result": receipt, "physical_boot_verified": False}
    return build, contract


def derive_recipe(repo, template, recipe, materializer, staging):
    original = materializer.derive_sources(repo, template)
    recipe.mkdir()
    values = {name: (template / name).read_bytes() for name in original["derived"]}
    guest = once(values["guest_verify_system.py"].decode(),
                 "profile['root_label'] == 'tb371fc-r5-f45'",
                 "profile['root_label'] == '" + LABEL + "'")
    # R7-only failure shutdown derivation; the frozen v9/R5 sources stay pinned.
    guest_before = {"bytes": len(guest.encode()), "sha256": hashlib.sha256(guest.encode()).hexdigest()}
    require(guest_before["sha256"] == "31c4aab964d9a771893509bdf680f18f4f1068a50287154e3f3744cc238b2a6c",
            "R7 guest base before failure-shutdown derivation differs")
    guest = once(guest, "        print('TB371FC_R4F_VM_VALIDATION_FAILED', flush=True)\n        sys.exit(1)\n",
                 "        print('TB371FC_R4F_VM_VALIDATION_FAILED', flush=True)\n        if DIAGNOSTICS_READY and RESULT_IDENTITY is not None:\n            # The exact isolated VM/root/profile and Enforcing guards passed.\n            # Keep the failure, but let the evidence filesystem close cleanly.\n            try:\n                subprocess.run(['/usr/bin/systemctl', '--no-block', 'poweroff'], check=True, timeout=30)\n            except Exception as error:\n                print('TB371FC_R4F_FAILURE_POWEROFF_ERROR ' + type(error).__name__ + ': ' +\n                      str(error)[:1024], file=sys.stderr, flush=True)\n        sys.exit(1)\n")
    values["guest_verify_system.py"] = guest.encode()
    require(hashlib.sha256(values["guest_verify_system.py"]).hexdigest() ==
            "79529ba8d7ee80e7195e8a0e250e5eda701fa62e7eafb231e8294909aa3f258b",
            "R7 guest failure-shutdown derivation differs")
    boot = values["boot_system_vm.py"].decode()
    boot_before = {"bytes": len(boot.encode()), "sha256": hashlib.sha256(boot.encode()).hexdigest()}
    require(boot_before["sha256"] == "4d1f59691bb4faccdcdbd791ae2120a89e56f7712fd63270f0a2204662842736",
            "frozen VM driver before failure-shutdown derivation differs")
    boot = once(boot, 'cancelled = None\n',
                'cancelled = None\nFAILURE_SHUTDOWN_GRACE_SECONDS = 60.0\n')
    boot = once(boot, '    reason = None\n    child = None\n',
                '    reason = None\n    failure_shutdown_deadline = None\n    child = None\n')
    boot = once(boot, "                if b'TB371FC_R4F_VM_VALIDATION_FAILED' in tail or b'Kernel panic - not syncing' in tail:\n                    reason = 'guest reported failure'\n                    break\n",
                "                if b'Kernel panic - not syncing' in tail:\n                    reason = 'guest reported failure'\n                    break\n                if failure_shutdown_deadline is None and b'TB371FC_R4F_VM_VALIDATION_FAILED' in tail:\n                    # Preserve failure while the isolated guest closes its evidence\n                    # filesystem. Repeated markers never extend the original bound.\n                    reason = 'guest reported failure'\n                    failure_shutdown_deadline = min(start + 900, time.monotonic() +\n                                                    FAILURE_SHUTDOWN_GRACE_SECONDS)\n                if failure_shutdown_deadline is not None and time.monotonic() >= failure_shutdown_deadline:\n                    reason = 'guest reported failure; shutdown grace expired'\n                    break\n")
    values["boot_system_vm.py"] = boot.encode()
    require(hashlib.sha256(values["boot_system_vm.py"]).hexdigest() ==
            "1843945b757fafd2c3d50753886faa21b13a0aced0f3a4bd894645be4bf038da",
            "VM driver failure-shutdown derivation differs")
    failure_shutdown = {"scope": "R7 failure evidence shutdown only; acceptance gates unchanged",
        "base": {"guest_verify_system.py": guest_before, "boot_system_vm.py": boot_before},
        "derived": {name: {"bytes": len(values[name]), "sha256": hashlib.sha256(values[name]).hexdigest()}
                    for name in ("guest_verify_system.py", "boot_system_vm.py")}}
    worker = once(values["guest_transient_worker.py"].decode(),
                  "PROFILE_NAME = 'research5-services-fedora45-derived-v9'", "PROFILE_NAME = '" + PROFILE + "'")
    require(worker.count(R5_RELEASE) == 2, "R5 worker release guards changed")
    worker = worker.replace(R5_RELEASE, RELEASE)
    worker = once(worker, "'worker is limited to the owned research5 ARM64 kernel'",
                  "'worker is limited to the owned research7 ARM64 kernel'")
    worker = once(worker, "profile['root_label'] == 'tb371fc-r5-f45'", "profile['root_label'] == '" + LABEL + "'")
    values["guest_transient_worker.py"] = worker.encode()
    common = values["system_common.py"].decode()
    for old, new in (("R5-specific", "R7-specific"), ("tb371fc-r5-f45", LABEL),
                     ("fedora45-research5-services.ext4", "fedora45-research7-rpmh-clock.ext4"),
                     (".before-research5-integration", ".before-research7-integration"),
                     ("fedora-r5-system-", "fedora-r7-system-"),
                     ("r5-runtime-stage.json", "r7-runtime-stage.json"),
                     ("FEDORA_R5_IMAGE_CREATED", "FEDORA_R7_IMAGE_CREATED")):
        require(old in common, "R5 adapter anchor absent: " + old)
        common = common.replace(old, new)
    common = common.replace("staging.RELEASE", repr(RELEASE))
    common = once(common, 'record["stage_source"] != staging.identity(Path(staging.__file__))',
                  'record["staging_helpers"] != staging.identity(Path(staging.__file__))')
    values["system_common.py"] = common.encode()
    values["assemble_system.py"] = once(values["assemble_system.py"].decode(),
        "tb371fc-research5-vm\\n", "tb371fc-research7-vm\\n").encode()
    # Include supplier modules before probing UFS; ordinary depmod expands the
    # dependency closure. This does not force-load unrelated peripheral drivers.
    drivers = " ".join(Path(name).stem for name in sorted(SUPPLIERS))
    values["early_initramfs.py"] = once(values["early_initramfs.py"].decode(),
        "'--keep', '--modules',", "'--keep', '--add-drivers', " + repr(drivers) + ", '--modules',").encode()
    for name, raw in values.items():
        if name.endswith(".py"):
            compile(raw, str(recipe / name), "exec")
        with (recipe / name).open("xb") as stream:
            stream.write(raw)
        (recipe / name).chmod(stat.S_IMODE((template / name).stat().st_mode))
    unchanged = ("verify_initramfs.py", "verify_early_policy_initramfs.py", "verify_runtime_policy_initramfs.py",
                 "initrd-domain-proof.sh", "initrd-domain-proof.service", "guest_result_file.py",
                 "read_vm_result.py", "transient_protocol.py", "probe_fd_route_v2.py")
    for name in unchanged:
        require(values[name] == (template / name).read_bytes(), "frozen acceptance source changed: " + name)
    result = {"schema_version": 1, "r5_template_derivation": identity(template / "derivation.json"),
              "kernel_release": RELEASE, "root_label": LABEL, "profile": PROFILE,
              "derived": {name: staging.identity(recipe / name) for name in sorted(values)},
              "changed_from_r5_template": [name for name in sorted(values) if values[name] != (template / name).read_bytes()],
              "byte_identical_acceptance_sources": list(unchanged), "failure_shutdown_derivation": failure_shutdown,
              "supplier_drivers": drivers.split(),
              "frozen_recipe_written": False, "runtime_acceptance_verified": False}
    save(recipe / "derivation.json", result)
    return result


def dependency_graph(raw, module_names):
    graph = {}
    for line in raw.decode("utf-8").splitlines():
        if not line:
            continue
        name, sep, dependencies = line.partition(":")
        require(sep and name not in graph and name in module_names, "invalid R7 modules.dep entry")
        graph[name] = dependencies.split()
        require(len(graph[name]) == len(set(graph[name])) and all(x in module_names for x in graph[name]),
                "foreign or duplicate module dependency")
    require(set(graph) == set(module_names), "dependency graph must cover exactly its signed module set")
    return graph


def dependency_closure(graph):
    closure, pending = set(), list(SUPPLIERS)
    while pending:
        name = pending.pop()
        if name not in closure:
            require(name in graph, "required supplier absent from dependency graph")
            closure.add(name)
            pending.extend(graph[name])
    return sorted(closure)


def verify_archive_modules(image, recipe, contract, required, root_graph):
    legacy = load_module(recipe / "verify_initramfs.py", "r7_archive_legacy")
    checker = load_module(recipe / "verify_runtime_policy_initramfs.py", "r7_archive_runtime")
    archive, unused = checker.parse_image(legacy, image)
    prefix = "usr/lib/modules/" + RELEASE + "/"
    expected = {row["path"].split("/" + RELEASE + "/", 1)[1]: row for row in contract["kernel_files"]}
    included = {}
    for name, entry in archive.entries.items():
        if name.startswith("usr/lib/modules/") and entry["kind"] == "regular" and (name.endswith(".ko") or ".ko." in name):
            require(name.startswith(prefix), "foreign module release in R7 initramfs")
            rel = name[len(prefix):]
            require(rel in expected and all(entry[key] == expected[rel][key] for key in ("sha256",))
                    and entry["size"] == expected[rel]["bytes"], "initrd changed a signed module: " + rel)
            included[rel] = {"bytes": entry["size"], "sha256": entry["sha256"]}
    require(set(required) <= set(included), "UFS supplier/dependency closure missing from initrd")
    require(not any("signing_key.pem" in name for name in archive.entries), "private signing key in initrd")
    dependency = archive.regular(prefix + "modules.dep")
    graph = dependency_graph(bytes(archive.payload(dependency)), set(included))
    require(graph == {name: root_graph[name] for name in included},
            "initrd dependency graph differs from the qualified root")
    indexes = {}
    for name in ("modules.dep.bin", "modules.alias", "modules.alias.bin", "modules.symbols", "modules.symbols.bin"):
        entry = archive.regular(prefix + name)
        indexes[name] = {"bytes": entry["size"], "sha256": entry["sha256"]}
    return {"passed": True, "image": identity(image), "kernel_release": RELEASE,
            "included_module_count": len(included), "modules": included,
            "required_supplier_closure": required, "signed_bytes_match_qualified_build": True,
            "text_dependency_graph_matches_root": True, "indexes": indexes,
            "binary_index_semantics_verified": False,
            "module_loading_verified": False, "signature_enforcement_runtime_verified": False}


def construct(repo, kernel, expected_build_sha, work):
    global CANCEL_SIGNAL
    require(work.parent == Path("/work") and work.name.startswith("fedora-r7-system-")
            and work.is_absolute() and not os.path.lexists(work), "fresh /work/fedora-r7-system-* required")
    require(os.environ.get("MAKEFLAGS") == "-j2", "original admitted two-job environment required")
    require(re.fullmatch("[0-9a-f]{64}", expected_build_sha) is not None, "exact build receipt SHA required")
    for path in (repo, kernel, work.parent):
        require(path.is_dir() and not path.is_symlink() and path.resolve(strict=True) == path,
                "canonical input directory required: " + str(path))
    require(shutil.disk_usage(work.parent).free >= 8 * 1024**3, "eight GiB free construction space required")
    os.umask(0o077)
    sys.dont_write_bytecode = True
    frozen = {name: pinned(repo / name, digest) for name, digest in FROZEN.items()}
    staging = load_module(repo / "scripts/research/rootfs/stage_r5_fedora.py", "stage_r5_fedora")
    materializer = load_module(repo / "scripts/research/rootfs/materialize_r5_fedora_recipe.py", "r7_frozen_materializer")
    inspector = load_module(repo / "scripts/research/boot_rootfs.py", "r7_root_inspector")
    build, contract = qualify_kernel(repo, kernel, expected_build_sha)
    work.mkdir(mode=0o700)
    record = {"schema_version": 1, "started_utc": utc(), "complete": False, "kernel_release": RELEASE,
              "scope": "new R7 root/initramfs/ordinary ext4 construction; no VM or native acceptance",
              "owner_native_linux_passes_added": 0, "physical_boot_verified": False,
              "userspace_verified": False, "runtime_signature_enforcement_verified": False,
              "commands": [], "build_result": identity(kernel / "build-result.json"), "frozen_recipe_inputs": frozen}
    started = time.monotonic()
    def on_signal(number, unused):
        global CANCEL_SIGNAL
        if CANCEL_SIGNAL is None:
            CANCEL_SIGNAL = number
    def cancelled():
        if CANCEL_SIGNAL is not None:
            raise InterruptedError("R7 construction interrupted by signal " + str(CANCEL_SIGNAL))
    handlers = {number: signal.signal(number, on_signal) for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    def run(name, argv, *, env=None, timeout=1800, hash_stdout=False):
        cancelled()
        row = {"name": name, "argv": [str(x) for x in argv], "started_utc": utc(), "timeout_seconds": timeout}
        record["commands"].append(row)
        print(json.dumps({"phase_started": name, "argv": row["argv"], "started_utc": row["started_utc"]}), flush=True)
        log_path, err_path = work / (name + ".stdout"), work / (name + ".stderr")
        digest, count = hashlib.sha256(), 0
        try:
            with log_path.open("xb") as log, err_path.open("xb") as err:
                proc = subprocess.Popen(row["argv"], stdout=subprocess.PIPE, stderr=err, env=env,
                                        stdin=subprocess.DEVNULL, start_new_session=True)
                row["pid"] = proc.pid
                try:
                    deadline = time.monotonic() + timeout
                    cancelled()
                    with selectors.DefaultSelector() as selector:
                        selector.register(proc.stdout, selectors.EVENT_READ)
                        while selector.get_map():
                            cancelled()
                            if time.monotonic() >= deadline:
                                raise subprocess.TimeoutExpired(row["argv"], timeout)
                            for key, unused in selector.select(.5):
                                chunk = os.read(key.fd, 65536)
                                if not chunk:
                                    selector.unregister(key.fileobj)
                                    continue
                                digest.update(chunk); count += len(chunk)
                                if not hash_stdout:
                                    log.write(chunk); log.flush()
                                    sys.stdout.buffer.write(chunk); sys.stdout.buffer.flush()
                    while proc.poll() is None:
                        cancelled()
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(row["argv"], timeout)
                        try:
                            proc.wait(timeout=min(.5, remaining))
                        except subprocess.TimeoutExpired:
                            pass
                    cancelled()
                except BaseException:
                    for sig, limit in ((signal.SIGTERM, 10), (signal.SIGKILL, None)):
                        try:
                            os.killpg(proc.pid, sig)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=limit)
                        except subprocess.TimeoutExpired:
                            pass
                    raise
                finally:
                    proc.stdout.close()
                row.update(exit_code=proc.returncode, stdout_bytes=count, stdout_sha256=digest.hexdigest())
                require(proc.returncode == 0, name + " failed; inspect " + str(err_path))
        finally:
            row.update(finished_utc=utc(), stdout_log=identity(log_path), stderr_log=identity(err_path))
            print(json.dumps(row), flush=True)
        return row
    def canonical(name, root):
        row = run(name, ["tar", "--sort=name", "--format=posix",
            "--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime", "--numeric-owner",
            "--acls", "--selinux", "--xattrs", "--xattrs-include=*", "-cf", "-", "-C", root, "."], hash_stdout=True)
        require(row["stderr_log"]["bytes"] == 0, "canonical baseline emitted warnings")
        result = {"sha256": row["stdout_sha256"], "bytes": row["stdout_bytes"]}
        staging.require_baseline(result)
        return result
    try:
        record["constructor"] = identity(Path(__file__))
        record["baseline_inputs"] = {str(path): staging.check(path, sha) for path, sha in staging.PINS.items()}
        vm = json.loads((staging.BASE / "vm-verify-01/result.json").read_text())
        require(vm["passed"] and vm["guest_gates_match"] and vm["guest_result"]["selinux"] == "Enforcing",
                "historical Fedora baseline acceptance missing")
        record["source_tree"] = canonical("source-tree", staging.BASE / "rootfs")
        root = work / "rootfs"
        run("copy-root", ["cp", "-a", "--reflink=auto", "--", staging.BASE / "rootfs", root])
        record["copied_tree"] = canonical("copied-tree", root)
        acls = {}
        for key in ("system.posix_acl_access", "system.posix_acl_default"):
            before = os.getxattr(staging.BASE / "rootfs/var/log/journal", key, follow_symlinks=False)
            after = os.getxattr(root / "var/log/journal", key, follow_symlinks=False)
            require(before == after, "journal ACL changed while copying")
            acls[key] = {"sha256": hashlib.sha256(before).hexdigest(), "size": len(before), "byte_identical": True}
        firmware = staging.firmware_inventory(root)
        dest = staging.under(root, "usr/lib/modules/" + RELEASE)
        dest.mkdir()
        prefix = "modules/lib/modules/" + RELEASE + "/"
        for item in contract["kernel_files"]:
            rel = item["path"][len(prefix):]
            staging.copy_exact(kernel / item["path"], staging.under(dest, rel, mkdir=True),
                               {k: item[k] for k in ("bytes", "sha256", "mode")})
        mappings = {"Image": "boot/Image-" + RELEASE,
                    "board.dtb": "boot/dtb-" + RELEASE + "/qcom/sm8250-lenovo-tb371fc.dtb",
                    "kernel.config": "boot/config-" + RELEASE, "System.map": "boot/System.map-" + RELEASE}
        meta = "usr/share/tb371fc/" + RELEASE + "/"
        mappings.update({name: meta + name for name in ("signing-cert.der", "kernel.btf", "Module.symvers", "kernel.release")})
        for name, target in mappings.items():
            staging.copy_exact(kernel / "artifacts" / name, staging.under(root, target, mkdir=True),
                               staging.identity(kernel / "artifacts" / name))
        for name, source in (("research7-build.json", kernel / "build-result.json"),
                             ("source-manifest.json", kernel / "source-inventory.json"),
                             ("module-signatures.json", kernel / "module-signatures.json"),
                             ("module-abi.json", kernel / "module-abi.json")):
            staging.copy_exact(source, staging.under(root, meta + name, mkdir=True), staging.identity(source))
        sums = "".join(item["sha256"] + "  " + item["path"][len(prefix):] + "\n"
                       for item in contract["kernel_files"] if item["path"].endswith(".ko"))
        with staging.under(root, meta + "modules.SHA256SUMS").open("x") as stream:
            stream.write(sums)
        wrapper = [staging.PROOT, "-0", "-r", root, "-q", staging.QEMU,
                   "-b", "/proc", "-b", "/dev/null", "-b", "/dev/zero", "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/"]
        guest_env = dict(os.environ, LD_LIBRARY_PATH=staging.HOST_LIBS, SYSTEMD_OFFLINE="1",
                         TMPDIR="/var/tmp", TMP="/var/tmp", TEMP="/var/tmp", PYTHONDONTWRITEBYTECODE="1")
        run("target-depmod-version", wrapper + ["/usr/sbin/depmod", "--version"], env=guest_env)
        run("target-depmod", wrapper + ["/usr/sbin/depmod", "-a", RELEASE], env=guest_env)
        checked = inspector.inspect_root_module_tree(root, contract)
        require(checked["passed"] and checked["input_snapshot_stable"], "exact R7 root module tree did not qualify")
        save(work / "root-module-report.json", {"root_module_tree": checked})
        module_tree = {str(path.relative_to(dest)): staging.identity(path) for path in sorted(dest.rglob("*")) if path.is_file()}
        graph = dependency_graph((dest / "modules.dep").read_bytes(),
                                 {name for name in module_tree if name.endswith(".ko")})
        required = dependency_closure(graph)
        save(work / "r7-module-contract.json", contract)
        recipe = work / "recipe"
        derived = derive_recipe(repo, work / "recipe-r5-template", recipe, materializer, staging)
        stage = {"complete": True, "kernel_release": RELEASE, "owner_native_linux_passes_added": 0,
                 "stage_source": identity(Path(__file__)), "staging_helpers": staging.identity(recipe / "stage_r5_fedora.py"),
                 "root_module_report": staging.identity(work / "root-module-report.json"),
                 "module_tree": module_tree, "journal_acls": acls, "firmware_inventory": firmware,
                 "build_result": identity(kernel / "build-result.json"), "supplier_closure": required}
        save(work / "r7-runtime-stage.json", stage)
        old = root / "usr/share/tb371fc"
        archive = old / "archive/research1"
        archive.mkdir(parents=True)
        moved = []
        for name in ("kernel-build.json", "kernel-source-manifest.json", "modules.SHA256SUMS", "runtime.json"):
            src, dst = old / name, archive / name
            ident = staging.identity(src); src.rename(dst)
            moved.append({"from": str(src.relative_to(root)), "to": str(dst.relative_to(root)), **ident})
        runtime_files = {"usr/lib/modules/" + RELEASE + "/" + name: entry["sha256"] for name, entry in module_tree.items()}
        runtime_files.update({"usr/" + name: entry["sha256"] for name, entry in firmware.items()})
        runtime_files["usr/share/tb371fc/stock-firmware-manifest.json"] = staging.FW_PIN
        runtime_files.update({target: staging.identity(root / target)["sha256"] for target in mappings.values()})
        for path in sorted((root / meta).iterdir()):
            runtime_files[str(path.relative_to(root))] = identity(path)["sha256"]
        runtime = {"schema_version": 1, "kernel_release": RELEASE, "module_count": 84, "firmware_file_count": 69,
                   "runtime_files": runtime_files, "old_runtime_metadata_preserved": moved,
                   "physical_tablet_tested": False, "firmware_selection_verified": False}
        save(work / "runtime.json", runtime)
        staging.copy_exact(work / "runtime.json", old / "runtime.json", staging.identity(work / "runtime.json"))
        autofs = [name for name in module_tree if name.endswith("/autofs4.ko")]
        require(len(autofs) == 1, "one signed autofs module required")
        signature = {}
        for field in ("signer", "sig_key", "sig_hashalgo"):
            name = "target-modinfo-" + field
            run(name, wrapper + ["/usr/sbin/modinfo", "-F", field, "/usr/lib/modules/" + RELEASE + "/" + autofs[0]], env=guest_env)
            signature[field] = (work / (name + ".stdout")).read_text().strip()
            require(signature[field], "signed module metadata missing: " + field)
        btf = build["artifacts"]["kernel.btf"]
        profile = {"schema_version": 1, "profile": PROFILE, "kernel_release": RELEASE, "root_label": LABEL,
            "module_count": 84, "firmware_file_count": 69, "runtime_manifest_sha256": identity(work / "runtime.json")["sha256"],
            "kernel_image_sha256": build["artifacts"]["Image"]["sha256"], "board_dtb_sha256": NATIVE_DTB_SHA,
            "kernel_btf_sha256": btf["sha256"], "kernel_btf_size": btf["bytes"],
            "public_signing_certificate_sha256": build["artifacts"]["signing-cert.der"]["sha256"],
            "autofs_module_signature": signature, "validation_tasks_max": 128,
            "validation_selinux_context": "system_u:system_r:sysadm_t:s0", "transient_selinux_context": "system_u:system_r:sysadm_t:s0",
            "transient_worker_sha256": derived["derived"]["guest_transient_worker.py"]["sha256"],
            "guest_result_writer_sha256": derived["derived"]["guest_result_file.py"]["sha256"],
            "host_result_reader_sha256": derived["derived"]["read_vm_result.py"]["sha256"],
            "audit_printk_opt_in_required": True, "audit_printk_interval_required": 0,
            "source_policy_sha256": POLICY, "original_source_policy_sha256": OLD_POLICY,
            "actual_exported_kernel_policy_sha256_predetermined": False, "early_bootstrap_sha256": BOOTSTRAP,
            "early_bootstrap_build_policy_sha256": POLICY, "early_bootstrap_embeds_policy_hash": False,
            "early_bootstrap_expected_policy_size": 3835468, "early_selinux_required": True,
            "initramfs_root_type_required": "tmpfs", "kernel_rdinit_required": "/init.tmpfs", "journal_acl_check": acls,
            "staging_receipt_sha256": identity(work / "r7-runtime-stage.json")["sha256"],
            "configured_module_sig_force": False, "vm_module_signature_enforcement_required": True,
            "module_enforcement_scope": "unique module.sig_enforce=1 and actual sysfs readback",
            "scope": "R7 construction; generic-VM acceptance remains separate from board-model and native acceptance"}
        save(work / "system-profile.json", profile)
        staging.copy_exact(work / "system-profile.json", old / "system-profile.json", staging.identity(work / "system-profile.json"))
        phase_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run("configure", [sys.executable, "-B", "-O", recipe / "assemble_system.py", "configure"], env=phase_env)
        record["machine_id_permissions"] = machine_id_permissions(work)
        save(work / "machine-id-permissions.json", record["machine_id_permissions"])
        record["machine_id_permissions_proof"] = identity(work / "machine-id-permissions.json")
        run("initrd", [sys.executable, "-B", "-O", recipe / "assemble_system.py", "initrd"], env=phase_env, timeout=3600)
        archive_reports = {}
        for role, name in (("production", "initramfs-production-qualified.img"), ("maintenance", "initramfs-maintenance-qualified.img")):
            archive_reports[role] = verify_archive_modules(work / name, recipe, contract, required, graph)
        save(work / "r7-initrd-modules.json", archive_reports)
        run("image", [sys.executable, "-B", "-O", recipe / "assemble_system.py", "image"], env=phase_env, timeout=3600)
        require(inspector.inspect_root_module_tree(root, contract)["passed"], "R7 root module tree changed after construction")
        require(staging.firmware_inventory(root) == firmware, "R7 root firmware changed")
        require(qualify_kernel(repo, kernel, expected_build_sha)[0] == build, "R7 build inputs changed")
        canonical("source-tree-after", staging.BASE / "rootfs")
        for name, expected in frozen.items():
            pinned(repo / name, expected)
        pinned(Path(__file__), record["constructor"])
        for name, expected in derived["derived"].items():
            require(staging.identity(recipe / name) == expected, "derived recipe changed: " + name)
        pinned(work / "machine-id-permissions.json", record["machine_id_permissions_proof"])
        record["machine_id_permissions_reverification"] = machine_id_permissions(work, record["machine_id_permissions"])
        cancelled()
        image = work / "fedora45-research7-rpmh-clock.ext4"
        record.update(complete=True, rootfs={"path": str(image), **identity(image), "label": LABEL},
                      initrd={"path": str(work / "initramfs-production-qualified.img"), **identity(work / "initramfs-production-qualified.img")},
                      module_count=84, supplier_closure=required, archive_module_checks=archive_reports,
                      profile=identity(work / "system-profile.json"), retained_inputs_reverified=True)
    except BaseException as error:
        record["error"] = repr(error)
        raise
    finally:
        record.update(finished_utc=utc(), elapsed_seconds=time.monotonic() - started)
        save(work / "r7-construction-result.json", record)
        for number, previous in handlers.items():
            signal.signal(number, previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--kernel-work", type=Path, required=True)
    parser.add_argument("--build-result-sha256", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    construct(args.repo, args.kernel_work, args.build_result_sha256, args.work)
