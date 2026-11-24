#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect a supplied rootfs's modules without executing or changing it.

The caller qualifies the candidate contract's provenance. This helper checks
the exact module/Kbuild bytes and the *text* dependency graph. Binary depmod
indexes are inventoried, not interpreted or attributed to a depmod execution.
An offline pass is never a rootfs boot or a module-loading result.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_CONTRACT_BYTES = 512 * 1024 * 1024
MAX_TREE_ENTRIES = 16384
MAX_MODULES = 4096
KBUILD_METADATA = ("modules.builtin", "modules.builtin.modinfo", "modules.order")
REQUIRED_INDEXES = ("modules.dep", "modules.dep.bin", "modules.alias",
                    "modules.alias.bin", "modules.symbols", "modules.symbols.bin",
                    "modules.softdep", "modules.builtin.bin")
# These are not emitted by every supported kmod version. Record presence; do
# not invent a producer version from an index filename or from arbitrary bytes.
OPTIONAL_INDEXES = ("modules.builtin.alias.bin", "modules.devname", "modules.weakdep")


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _relative(value):
    if (not isinstance(value, str) or not value or value.startswith("/") or
            "\\" in value or any(ord(ch) <= 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("invalid relative module path")
    path = PurePosixPath(value)
    if str(path) != value or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("noncanonical or traversing module path: " + value)
    return path.parts


def _expected(contract):
    kernel = contract["kernel"]
    release = kernel["release"]
    count = kernel["module_count"]
    if (not isinstance(release, str) or
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+~-]{0,199}", release) is None or
            type(count) is not int or not 0 < count <= MAX_MODULES):
        raise ValueError("invalid kernel release or module count")
    prefix = "modules/lib/modules/" + release + "/"
    entries = contract["kernel_files"]
    if not isinstance(entries, list) or len(entries) > MAX_TREE_ENTRIES:
        raise ValueError("bounded kernel_files list required")
    selected = {}
    seen = set()
    for entry in entries:
        path = entry["path"]
        _relative(path)
        if path in seen:
            raise ValueError("duplicate kernel_files path: " + path)
        seen.add(path)
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        _relative(relative)
        size, digest, mode = entry["bytes"], entry["sha256"], entry["mode"]
        if (type(size) is not int or not 0 <= size <= MAX_FILE_BYTES or
                not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None or
                type(mode) is not int or not 0 <= mode <= 0o7777):
            raise ValueError("invalid byte identity: " + relative)
        selected[relative] = {"bytes": size, "sha256": digest, "mode": mode}
    modules = {name: entry for name, entry in selected.items() if name.endswith(".ko")}
    if len(modules) != count or any(not name.startswith("kernel/") for name in modules):
        raise ValueError("contract module count or kernel/ prefix is inconsistent")
    if not set(KBUILD_METADATA) <= set(selected):
        raise ValueError("contract lacks the three installed Kbuild metadata identities")
    if sum(entry["bytes"] for entry in selected.values()) > MAX_CONTRACT_BYTES:
        raise ValueError("contract module tree total exceeds byte limit")
    return release, modules, {name: selected[name] for name in KBUILD_METADATA}


class _RootReader:
    """Descriptor-relative reads; only the root's lib alias may be a symlink."""

    def __init__(self, root):
        self.fds = {}
        self.snapshots = {}
        self.file_snapshots = {}
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.fds[()] = fd
        self.snapshots[()] = _identity(os.fstat(fd))

    def close(self):
        for fd in reversed(list(self.fds.values())):
            os.close(fd)
        self.fds.clear()

    def directory(self, parts):
        parts = tuple(parts)
        if parts not in self.fds:
            parent = self.directory(parts[:-1])
            fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
            self.fds[parts] = fd
            self.snapshots[parts] = _identity(os.fstat(fd))
        return self.fds[parts]

    def module_directory(self, release):
        info = os.stat("lib", dir_fd=self.fds[()], follow_symlinks=False)
        prefix = ("lib",)
        alias = None
        if stat.S_ISLNK(info.st_mode):
            alias = os.readlink("lib", dir_fd=self.fds[()])
            after = os.stat("lib", dir_fd=self.fds[()], follow_symlinks=False)
            if _identity(info) != _identity(after):
                raise ValueError("root lib alias changed during inspection")
            # Absolute links are resolved inside the supplied root, never on
            # the execution host. Arbitrary aliases and traversal are refused.
            if alias not in ("usr/lib", "/usr/lib"):
                raise ValueError("root lib alias must resolve inside rootfs to usr/lib")
            prefix = ("usr", "lib")
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError("root lib is not an ordinary directory or merged-usr alias")
        result = prefix + ("modules", release)
        self.directory(result)
        return result, alias

    def inventory(self, base):
        result = {}
        pending = [(tuple(base), ())]
        entries = 0
        while pending:
            directory, relative = pending.pop()
            with os.scandir(self.directory(directory)) as children:
                names = sorted(entry.name for entry in children)
            for name in names:
                _relative(name)
                entries += 1
                if entries > MAX_TREE_ENTRIES:
                    raise ValueError("module tree entry limit exceeded")
                info = os.stat(name, dir_fd=self.directory(directory), follow_symlinks=False)
                path = relative + (name,)
                if stat.S_ISDIR(info.st_mode):
                    pending.append((directory + (name,), path))
                elif stat.S_ISREG(info.st_mode):
                    result["/".join(path)] = info
                else:
                    raise ValueError("nonordinary node inside module tree: " + "/".join(path))
        return result

    def read(self, base, name, maximum, content=False):
        parts = _relative(name)
        directory = self.directory(tuple(base) + parts[:-1])
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= maximum:
                raise ValueError("input is not a bounded regular file: " + name)
            digest, size, chunks = hashlib.sha256(), 0, []
            while True:
                block = os.read(fd, min(1024 * 1024, maximum - size + 1))
                if not block:
                    break
                size += len(block)
                if size > maximum:
                    raise ValueError("file exceeds read limit: " + name)
                digest.update(block)
                if content:
                    chunks.append(block)
            after = os.fstat(fd)
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if (_identity(before) != _identity(after) or _identity(after) != _identity(current) or
                    size != before.st_size):
                raise ValueError("file changed during inspection: " + name)
            record = {"path": name, "bytes": size, "sha256": digest.hexdigest(),
                      "mode": stat.S_IMODE(before.st_mode)}
            self.file_snapshots[tuple(base) + parts] = _identity(after)
            return record, b"".join(chunks) if content else None
        finally:
            os.close(fd)

    def unchanged(self):
        for path, fd in self.fds.items():
            if _identity(os.fstat(fd)) != self.snapshots[path]:
                raise ValueError("rootfs directory changed during inspection: " + "/".join(path))
        for path, expected in self.file_snapshots.items():
            actual = os.stat(path[-1], dir_fd=self.directory(path[:-1]), follow_symlinks=False)
            if _identity(actual) != expected:
                raise ValueError("previously read file changed during inspection: " + "/".join(path))


def _dependency_graph(data, modules):
    graph = {}
    for number, line in enumerate(data.decode("utf-8", errors="strict").splitlines(), 1):
        if not line:
            continue
        if line.count(":") != 1:
            raise ValueError(f"modules.dep line {number}: one separator required")
        name, values = line.split(":", 1)
        _relative(name)
        dependencies = values.split()
        for dependency in dependencies:
            _relative(dependency)
        if name not in modules or name in graph:
            raise ValueError("modules.dep has an unknown or repeated module: " + name)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("modules.dep repeats a dependency: " + name)
        if any(dependency not in modules for dependency in dependencies):
            raise ValueError("modules.dep references a missing or foreign-release dependency: " + name)
        graph[name] = dependencies
    if set(graph) != set(modules):
        raise ValueError("modules.dep does not cover the exact candidate module set")
    # Kmod records the full load order, not only direct symbol edges. Any
    # cycle still contradicts a loadable dependency ordering.
    indegree = {name: 0 for name in graph}
    for dependencies in graph.values():
        for name in dependencies:
            indegree[name] += 1
    ready = [name for name, count in indegree.items() if count == 0]
    visited = 0
    while ready:
        name = ready.pop()
        visited += 1
        for dependency in graph[name]:
            indegree[dependency] -= 1
            if indegree[dependency] == 0:
                ready.append(dependency)
    if visited != len(graph):
        raise ValueError("modules.dep contains a dependency cycle")
    return {"modules": len(graph), "dependency_references": sum(map(len, graph.values())),
            "scope": "exact keys, path membership, uniqueness and acyclicity; dependency completeness from ELF imports is not verified"}


def inspect_root_module_tree(root: Path, contract: dict) -> dict:
    """Return layered offline evidence; no target code or external command runs."""
    result = {"schema_version": 1, "passed": False, "status": "failed",
              "scope": "offline rootfs module bytes and depmod text inventory",
              "root": str(root), "module_bytes_verified": False,
              "kbuild_metadata_verified": False, "text_dependency_graph_verified": False,
              "binary_indexes_recorded": False, "binary_index_semantics_verified": False,
              "native_depmod_provenance_not_verified": True,
              "rootfs_runtime_ready": False, "physical_hardware_tested": False,
              "rootfs_modified": False, "target_code_executed": False,
              "input_snapshot_stable": False,
              "errors": [], "module_files": [], "kbuild_metadata": [], "indexes": [],
              "optional_indexes_missing": [],
              "limits": {"file_bytes": MAX_FILE_BYTES, "index_bytes": MAX_INDEX_BYTES,
                         "contract_bytes": MAX_CONTRACT_BYTES,
                         "tree_entries": MAX_TREE_ENTRIES, "modules": MAX_MODULES}}
    reader = None
    stage = "contract"
    try:
        release, modules, metadata = _expected(contract)
        result.update({"kernel_release": release, "module_count_expected": len(modules)})
        stage = "module-tree"
        reader = _RootReader(root)
        base, alias = reader.module_directory(release)
        result.update({"resolved_module_directory": "/".join(base), "root_lib_alias": alias})
        inventory = reader.inventory(base)
        actual_modules = {name for name in inventory if re.search(r"\.ko(?:\.[^/]+)?$", name)}
        if actual_modules != set(modules):
            result["module_set_difference"] = {"missing": sorted(set(modules) - actual_modules),
                                               "extra": sorted(actual_modules - set(modules))}
            raise ValueError("rootfs module set differs from the candidate")
        stage = "module-bytes"
        for name, expected in sorted(modules.items()):
            actual, unused = reader.read(base, name, MAX_FILE_BYTES)
            if any(actual[key] != value for key, value in expected.items()):
                raise ValueError("rootfs module bytes or mode differ: " + name)
            result["module_files"].append(actual)
        result["module_bytes_verified"] = True
        stage = "kbuild-metadata"
        for name, expected in metadata.items():
            actual, unused = reader.read(base, name, MAX_FILE_BYTES)
            if any(actual[key] != value for key, value in expected.items()):
                raise ValueError("rootfs Kbuild metadata bytes or mode differ: " + name)
            result["kbuild_metadata"].append(actual)
        result["kbuild_metadata_verified"] = True
        stage = "depmod-indexes"
        missing = sorted(set(REQUIRED_INDEXES) - set(inventory))
        if missing:
            result["missing_required_indexes"] = missing
            result["status"] = "blocked"
            raise FileNotFoundError("required depmod indexes missing: " + ", ".join(missing))
        result["optional_indexes_missing"] = sorted(set(OPTIONAL_INDEXES) - set(inventory))
        dependency_data = None
        for name in REQUIRED_INDEXES + OPTIONAL_INDEXES:
            if name not in inventory:
                continue
            actual, data = reader.read(base, name, MAX_INDEX_BYTES, content=name == "modules.dep")
            if name.endswith(".bin") and actual["bytes"] == 0:
                raise ValueError("empty binary depmod index: " + name)
            actual["role"] = "binary-index-bytes-only" if name.endswith(".bin") else "text-index-bytes"
            result["indexes"].append(actual)
            if name == "modules.dep":
                dependency_data = data
        result["binary_indexes_recorded"] = True
        stage = "text-dependencies"
        result["dependency_graph"] = _dependency_graph(dependency_data, modules)
        result["text_dependency_graph_verified"] = True
        stage = "read-stability"
        reader.unchanged()
        result.update({"passed": True, "status": "passed", "input_snapshot_stable": True})
    except (KeyError, TypeError, ValueError, OSError, UnicodeError) as error:
        if stage == "read-stability":
            for flag in ("module_bytes_verified", "kbuild_metadata_verified",
                         "text_dependency_graph_verified", "binary_indexes_recorded"):
                result[flag] = False
        if isinstance(error, FileNotFoundError):
            result["status"] = "blocked"
        result["errors"].append({"stage": stage, "type": type(error).__name__, "message": str(error)})
    finally:
        if reader is not None:
            reader.close()
    return result
