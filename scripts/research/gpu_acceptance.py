#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect GPU acceptance evidence without changing system configuration.

The default is passive filesystem inspection. Optional --probe values select
only fixed EGL/Vulkan/KWin information queries; no shell or user command runs.
Those queries can open graphics devices and create temporary driver contexts.
They do not run a benchmark, request a modeset, or change clocks/governors.
Output is JSON on stdout. Exit 0 means collection completed, not GPU acceptance.
--require-a650-enumeration adds an explicitly limited enumeration gate.

An extracted rootfs (--root other than /) cannot execute probes. Host/container
results are not tablet results. Missing files/permissions remain unknown.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import struct
import subprocess
import time


TEXT_LIMIT = 2 * 1024 * 1024
PROBE_LIMIT = 256 * 1024
FIRMWARE_LIMIT = 32 * 1024 * 1024
CONFIG_KEYS = (
    "DRM", "DRM_MSM", "DRM_MSM_DPU", "DRM_MSM_DSI",
    "DRM_MSM_DSI_7NM_PHY", "DRM_SIMPLEDRM", "DRM_SCHED", "SYNC_FILE",
    "DMA_SHARED_BUFFER", "COMMON_CLK_QCOM", "SM_GCC_8250", "SM_GPUCC_8250",
    "QCOM_GDSC", "ARM_SMMU", "ARM_SMMU_QCOM", "QCOM_SCM",
    "QCOM_MDT_LOADER", "QCOM_AOSS_QMP", "QCOM_LLCC", "QCOM_RPMH",
    "QCOM_RPMHPD", "NVMEM_QCOM_QFPROM", "PM_OPP", "PM_DEVFREQ",
    "DEVFREQ_GOV_SIMPLE_ONDEMAND", "DEVFREQ_THERMAL",
    "INTERCONNECT_QCOM_SM8250", "INTERCONNECT_QCOM_RPMH", "FW_LOADER",
    "FW_LOADER_COMPRESS", "FW_LOADER_COMPRESS_XZ", "FW_LOADER_COMPRESS_ZSTD",
    "MEDIA_SUPPORT", "VIDEO_DEV", "V4L_MEM2MEM_DRIVERS",
    "VIDEO_QCOM_VENUS", "V4L2_MEM2MEM_DEV",
)
GRAPHICS_ENV = (
    "KWIN_COMPOSE", "KWIN_DRM_DEVICES", "KWIN_DRM_FORCE_GL_FINISH_PRESENT",
    "KWIN_DRM_RENDERLOOP_REFRESH_RATE_MHZ", "KWIN_DRM_DUMB_BUFFER_CPU_SYNC",
    "LIBGL_ALWAYS_SOFTWARE", "LIBGL_DRIVERS_PATH", "MESA_LOADER_DRIVER_OVERRIDE",
    "GALLIUM_DRIVER", "DRI_PRIME", "EGL_PLATFORM", "GBM_BACKEND",
    "MESA_GL_VERSION_OVERRIDE", "MESA_GLES_VERSION_OVERRIDE", "TU_DEBUG",
    "FD_MESA_DEBUG", "MESA_VK_WSI_DEBUG", "VK_DRIVER_FILES", "VK_ICD_FILENAMES",
    "__EGL_VENDOR_LIBRARY_FILENAMES", "QT_QUICK_BACKEND", "QSG_RHI_BACKEND",
    "LD_LIBRARY_PATH", "LD_PRELOAD",
)
FIXED_PROBES = {
    "egl": (("/usr/bin/eglinfo", "/bin/eglinfo"), ("-B",)),
    "vulkan": (("/usr/bin/vulkaninfo", "/bin/vulkaninfo"), ("--summary",)),
    "kwin": (("/usr/bin/qdbus6", "/usr/lib/qt6/bin/qdbus", "/usr/bin/qdbus"),
             ("org.kde.KWin", "/KWin", "org.kde.KWin.supportInformation")),
}
A650 = re.compile(r"\b(?:FD650|Adreno\s*(?:\(TM\)\s*)?650)\b", re.I)
SOFTWARE = re.compile(r"llvmpipe|softpipe|lavapipe|swiftshader", re.I)


def bounded_file(path: Path, limit: int = TEXT_LIMIT) -> bytes:
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("not a regular file/sysfs attribute")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"file exceeds {limit} byte limit")
    return data


class Reader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.unavailable: list[dict] = []

    def path(self, name: str) -> Path:
        return self.root / name.lstrip("/")

    def read(self, path: Path, limit: int = TEXT_LIMIT) -> bytes | None:
        try:
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("symlink escapes selected root")
            return bounded_file(path, limit)
        except (OSError, ValueError) as error:
            self.unavailable.append({"path": str(path), "error": str(error)})
            return None

    def text(self, path: Path, limit: int = 16384) -> str | None:
        data = self.read(path, limit)
        return None if data is None else data.decode("utf-8", "replace").strip()


def selected_environment(values: dict) -> dict:
    return {key: str(values[key])[:2048] for key in GRAPHICS_ENV if key in values}


def parse_config(data: bytes) -> dict:
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(TEXT_LIMIT + 1)
        if len(data) > TEXT_LIMIT:
            raise ValueError("decompressed config exceeds limit")
    values = {}
    for line in data.decode("utf-8", "replace").splitlines():
        match = re.fullmatch(r"CONFIG_([A-Z0-9_]+)=(.*)", line)
        disabled = re.fullmatch(r"# CONFIG_([A-Z0-9_]+) is not set", line)
        if match:
            values[match[1]] = match[2]
        elif disabled:
            values[disabled[1]] = "n"
    return {"CONFIG_" + key: values.get(key) for key in CONFIG_KEYS}


def kernel_config(reader: Reader, override: Path | None) -> dict:
    candidates = [override] if override else [reader.path("/proc/config.gz")]
    if reader.root == Path("/") and not override:
        candidates.append(reader.path("/boot/config-" + platform.release()))
    for path in candidates:
        if path is None or not path.exists():
            continue
        try:
            data = bounded_file(path) if override else reader.read(path)
            if data is not None:
                return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                        "values": parse_config(data),
                        "note": "null means absent/unknown, not disabled"}
        except (OSError, ValueError, EOFError) as error:
            reader.unavailable.append({"path": str(path), "error": str(error)})
    return {"path": None, "values": {}, "note": "kernel config unavailable"}


def drm_snapshot(reader: Reader) -> list[dict]:
    result = []
    for path in sorted(reader.path("/sys/class/drm").glob("*"))[:128]:
        if not re.fullmatch(r"(?:card\d+|renderD\d+|card\d+-.+)", path.name):
            continue
        row = {"name": path.name}
        for attr in ("dev", "status", "enabled", "dpms", "modes"):
            if (path / attr).exists():
                row[attr] = reader.text(path / attr)
        driver = path / "device/driver"
        if driver.is_symlink():
            row["driver"] = driver.resolve().name
        node = reader.path("/dev/dri/" + path.name)
        if node.exists():
            row["device_node"] = str(node)
            row["is_character_device"] = stat.S_ISCHR(node.stat().st_mode)
            row["caller_can_read_write"] = os.access(node, os.R_OK | os.W_OK)
        result.append(row)
    return result


def device_tree(reader: Reader) -> dict:
    base = reader.path("/sys/firmware/devicetree/base")
    if not base.exists():
        base = reader.path("/proc/device-tree")
    if not base.exists():
        return {"available": False, "nodes": {}}
    result = {"available": True, "nodes": {}}
    compatible = reader.read(base / "compatible", 4096)
    result["board_compatible"] = (compatible.rstrip(b"\0").decode("ascii", "replace").split("\0")
                                  if compatible else [])
    for soc in (base / "soc@0", base / "soc"):
        if not soc.exists():
            continue
        for node in sorted(soc.iterdir()):
            if not re.fullmatch(r"(?:gpu@3d00000|gmu@3d6a000|iommu@3da0000|display-subsystem@ae00000)", node.name):
                continue
            for item in [node] + [child for child in node.glob("*zap*") if child.is_dir()]:
                props = {}
                for name in ("compatible", "status", "firmware-name", "tb371fc,headless-gpu",
                             "dma-coherent", "qcom,gmu", "iommus", "operating-points-v2", "memory-region"):
                    path = item / name
                    if not path.exists():
                        continue
                    data = reader.read(path, 4096)
                    if data is None:
                        continue
                    if name in ("compatible", "status", "firmware-name"):
                        props[name] = data.rstrip(b"\0").decode("ascii", "replace").split("\0")
                    elif not data:
                        props[name] = True
                    else:
                        props[name] = {"raw_hex": data.hex()}
                result["nodes"]["/" + str(item.relative_to(base))] = props
    return result


def firmware_snapshot(reader: Reader, dt: dict) -> dict:
    zap = "qcom/sm8250/lenovo/tb371fc/a650_zap.mbn"
    source = "checked-in TB371FC DTS fallback; running DT not confirmed"
    for node, props in dt["nodes"].items():
        if "zap" in node and props.get("firmware-name"):
            zap = props["firmware-name"][0]
            source = "captured DT firmware-name"
    if Path(zap).is_absolute() or ".." in Path(zap).parts:
        return {"error": "unsafe firmware-name path in DT"}
    result = {"zap_lookup_source": source, "files": {}}
    for name in ("qcom/a650_sqe.fw", "qcom/a650_gmu.bin", zap):
        matches, seen = [], set()
        for directory in ("/usr/lib/firmware", "/lib/firmware"):
            for suffix in ("", ".xz", ".zst"):
                path = reader.path(directory) / (name + suffix)
                if not path.exists() or path.resolve() in seen:
                    continue
                seen.add(path.resolve())
                data = reader.read(path, FIRMWARE_LIMIT)
                if data is None:
                    continue
                row = {"path": str(path), "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest(), "compression": suffix or None}
                if name == zap and not suffix:
                    row["elf_packaging"] = inspect_zap(data, path, reader)
                matches.append(row)
        result["files"][name] = matches
    return result


def inspect_zap(data: bytes, path: Path, reader: Reader) -> dict:
    """Inspect ELF32 split packaging only; never authenticate or load firmware.

    The valid-segment/split rule follows Linux v6.12.114 qcom mdt_loader.c.
    Compressed sibling presence is recorded without claiming decompressed size.
    """
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        return {"format": "not inspected: expected little-endian ELF32"}
    phoff = struct.unpack_from("<I", data, 28)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 42)
    if phsize != 32 or phnum > 128 or phoff + phsize * phnum > len(data):
        return {"format": "invalid or unsupported program-header table"}
    valid = []
    split = False
    for index in range(phnum):
        ptype, offset, _, _, filesz, memsz, flags, _ = struct.unpack_from("<8I", data, phoff + index * 32)
        # qcom_mdt_bins_are_split checks every nonempty program header,
        # including hash/non-load headers, but ignores zero-size/BSS entries.
        if filesz and offset + filesz > len(data):
            split = True
        if ptype == 1 and memsz and (flags & (7 << 24)) != (2 << 24):
            valid.append((index, offset, filesz))
    checks = []
    if split:
        for index, _, size in valid:
            if not size:
                continue
            sibling = path.with_name(path.name[:-3] + f"b{index:02d}")
            variants = []
            for suffix in ("", ".xz", ".zst"):
                candidate = Path(str(sibling) + suffix)
                if not candidate.exists():
                    continue
                blob = reader.read(candidate, FIRMWARE_LIMIT)
                if blob is not None:
                    variants.append({"path": str(candidate), "size": len(blob),
                                     "sha256": hashlib.sha256(blob).hexdigest(),
                                     "compression": suffix or None,
                                     "uncompressed_size_matches": None if suffix else len(blob) == size})
            checks.append({"segment_index": index, "expected_size": size, "files": variants})
    return {"format": "ELF32", "split_payload_required": split, "segments": checks,
            "signature_authentication": "not tested"}


def devfreq_snapshot(reader: Reader) -> list[dict]:
    rows = []
    for path in sorted(reader.path("/sys/class/devfreq").glob("*"))[:64]:
        resolved = str(path.resolve())
        name = reader.text(path / "name") if (path / "name").exists() else path.name
        if not re.search(r"gpu|kgsl|adreno|3d00000", (name or "") + resolved, re.I):
            continue
        row = {"name": name, "path": str(path)}
        for attr in ("governor", "cur_freq", "min_freq", "max_freq", "available_frequencies"):
            if (path / attr).exists():
                row[attr] = reader.text(path / attr)
        rows.append(row)
    return rows


def kernel_backend(reader: Reader, drm: list[dict]) -> dict:
    kgsl_node = reader.path("/dev/kgsl-3d0")
    kgsl_class = reader.path("/sys/class/kgsl/kgsl-3d0")
    kgsl_driver = kgsl_class / "device/driver"
    driver = kgsl_driver.resolve().name if kgsl_driver.is_symlink() else None
    vendor_drm = any(row.get("driver") == "msm_drm" for row in drm)
    vendor = kgsl_node.exists() or kgsl_class.exists() or driver == "kgsl-3d" or vendor_drm
    msm = any(row.get("driver") == "msm" for row in drm)
    return {
        "classification": ("android_vendor_kgsl_or_msm_drm" if vendor else
                           "mainline_msm_candidate" if msm else "unknown_no_msm_candidate"),
        "kgsl_device_present": kgsl_node.exists(), "kgsl_class_present": kgsl_class.exists(),
        "kgsl_driver": driver, "vendor_msm_drm_node_present": vendor_drm,
        "mainline_driver_name_present": msm,
        "note": "a vendor Android renderD node or KGSL Turnip result does not prove mainline MSM support",
    }


def icd_snapshot(reader: Reader) -> list[dict]:
    rows = []
    for directory in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d"):
        for path in sorted(reader.path(directory).glob("*.json"))[:64]:
            data = reader.read(path, 65536)
            if data is None:
                continue
            try:
                icd = json.loads(data).get("ICD", {})
                rows.append({"path": str(path), "library_path": icd.get("library_path"),
                             "manifest_api_version": icd.get("api_version"),
                             "sha256": hashlib.sha256(data).hexdigest()})
            except (ValueError, AttributeError) as error:
                rows.append({"path": str(path), "error": str(error)})
    return rows


def kwin_environments(reader: Reader) -> list[dict]:
    rows = []
    for process in reader.path("/proc").glob("[0-9]*"):
        try:
            if not process.resolve().is_relative_to(reader.root):
                continue
            comm = bounded_file(process / "comm", 128).decode().strip()
            if comm != "kwin_wayland":
                continue
            raw = reader.read(process / "environ", 262144)
            env = {}
            for value in (raw or b"").split(b"\0"):
                key, separator, val = value.partition(b"=")
                if separator and key.decode("ascii", "replace") in GRAPHICS_ENV:
                    env[key.decode("ascii")] = val.decode("utf-8", "replace")
            rows.append({"pid": int(process.name), "environment": selected_environment(env),
                         "environment_readable": raw is not None})
        except (OSError, ValueError, UnicodeError):
            continue
    return rows


def parse_probe(kind: str, text: str) -> dict:
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    if kind == "vulkan":
        devices, current = [], {}
        fields = {"apiVersion", "driverVersion", "vendorID", "deviceID", "deviceType",
                  "deviceName", "driverID", "driverName", "driverInfo", "conformanceVersion"}
        for line in text.splitlines():
            if re.fullmatch(r"\s*GPU\d+:\s*", line):
                if current:
                    devices.append(current)
                current = {}
            match = re.fullmatch(r"\s*(\w+)\s*=\s*(.*?)\s*", line)
            if match and match[1] in fields:
                current[match[1]] = match[2][:1024]
        if current:
            devices.append(current)
        renderers = [device["deviceName"] for device in devices if "deviceName" in device]
        result = {"devices": devices}
    else:
        lines = [line.strip()[:2048] for line in text.splitlines()
                 if re.search(r"(?:EGL (?:vendor|version|driver)|OpenGL.*(?:renderer|vendor|version)|"
                              r"Compositing (?:Type|is)|OpenGL platform interface)", line, re.I)][:100]
        renderers = [line.split(":", 1)[-1].strip() for line in lines if "renderer" in line.lower()]
        result = {"selected_information": lines}
    result.update({"renderers": sorted(set(renderers)),
                   "a650_reported": any(A650.search(value) for value in renderers),
                   "software_reported": any(SOFTWARE.search(value) for value in renderers),
                   "software_only": bool(renderers) and all(SOFTWARE.search(value) for value in renderers),
                   "zink_reported": any("zink" in value.lower() for value in renderers),
                   "diagnostics": [line.strip()[:1024] for line in text.splitlines()
                                   if re.search(r"error|failed|denied|cannot|not found", line, re.I)
                                   and not re.search(r"uuid|serial", line, re.I)][:12],
                   "scope": "identity/context information, not a draw/readback or presentation test"})
    return result


def run_probe(kind: str, timeout: int) -> dict:
    paths, arguments = FIXED_PROBES[kind]
    executable = next((path for path in paths if os.path.isfile(path) and os.access(path, os.X_OK)), None)
    if executable is None:
        return {"status": "unavailable", "reason": "fixed information-query executable not installed"}
    env = dict(os.environ)
    env["MESA_SHADER_CACHE_DISABLE"] = "true"
    process = subprocess.Popen([executable, *arguments], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               env=env, start_new_session=True)
    chunks, size, reason, finished = [], 0, None, False
    started = time.monotonic()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    reason = "timeout"
                    break
                for key, _ in selector.select(min(remaining, 0.25)):
                    data = os.read(key.fileobj.fileno(), min(65536, PROBE_LIMIT - size + 1))
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    chunks.append(data)
                    size += len(data)
                    if size > PROBE_LIMIT:
                        reason = "output_limit"
                        break
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
                    finished = True
                except subprocess.TimeoutExpired:
                    reason = "timeout"
    finally:
        if not finished:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        process.stdout.close()
    raw = b"".join(chunks)[:PROBE_LIMIT]
    return {"status": reason or ("completed" if process.returncode == 0 else "query_failed"),
            "command": [executable, *arguments], "returncode": process.returncode,
            "output_complete": reason is None, "output_sha256": hashlib.sha256(raw).hexdigest(),
            "parsed": parse_probe(kind, raw.decode("utf-8", "replace")),
            "note": "graphics environment preserved; shader disk cache disabled only in this child"}


def observations(report: dict) -> list[dict]:
    rows = []
    config = report["kernel_config"]["values"]
    for name, files in report["firmware"].get("files", {}).items():
        if files and all(item["compression"] for item in files) and config.get("CONFIG_FW_LOADER_COMPRESS") == "n":
            rows.append({"item": "compressed_firmware_without_loader_support", "file": name})
        for item in files:
            for segment in item.get("elf_packaging", {}).get("segments", []):
                if not segment["files"]:
                    rows.append({"item": "missing_split_zap_segment", "metadata": item["path"],
                                 "segment_index": segment["segment_index"]})
    for node, props in report["device_tree"]["nodes"].items():
        if "iommu@3da0000" in node and "qcom,adreno-smmu" not in props.get("compatible", []):
            rows.append({"item": "gpu_smmu_adreno_compatible_absent", "node": node,
                         "meaning": "may select the documented global-address-space fallback; runtime mode unproven"})
    if config.get("CONFIG_V4L_MEM2MEM_DRIVERS") == "n":
        rows.append({"item": "venus_parent_kconfig_gate_disabled", "scope": "video codec, independent of GL/Vulkan"})
    for kind, query in report["queries"].items():
        if query.get("parsed", {}).get("software_only"):
            rows.append({"item": "software_renderer_reported", "query": kind})
    environments = [("collector", report["collector_graphics_environment"])]
    environments += [("kwin:" + str(row["pid"]), row["environment"]) for row in report["kwin_processes"]]
    for owner, env in environments:
        for name in ("MESA_GL_VERSION_OVERRIDE", "MESA_GLES_VERSION_OVERRIDE"):
            if env.get(name):
                rows.append({"item": "API_version_override_present", "owner": owner, "variable": name})
        if "noconform" in env.get("TU_DEBUG", ""):
            rows.append({"item": "turnip_noconform_override_present", "owner": owner})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="live / or extracted filesystem root")
    parser.add_argument("--kernel-config", type=Path, help="read this config instead of live config")
    parser.add_argument("--probe", action="append", default=[], choices=tuple(FIXED_PROBES))
    parser.add_argument("--timeout", type=int, default=15, choices=range(1, 31), metavar="1..30")
    for kind in FIXED_PROBES:
        parser.add_argument("--" + kind + "-report", type=Path, help="parse an existing information-query log")
    parser.add_argument("--require-a650-enumeration", action="store_true",
                        help="exit 1 unless a successful live query identifies A650 and an accessible msm render node exists")
    args = parser.parse_args()
    reader = Reader(args.root)
    if not reader.root.is_dir():
        parser.error("--root is not a directory")
    if args.probe and reader.root != Path("/"):
        parser.error("probes cannot run against an extracted root; that would mix host and target evidence")
    for kind in FIXED_PROBES:
        if kind in args.probe and getattr(args, kind + "_report"):
            parser.error(f"choose either --probe {kind} or --{kind}-report")
    drm = drm_snapshot(reader)
    dt = device_tree(reader)
    config = kernel_config(reader, args.kernel_config)
    report = {
        "schema_version": 1, "captured_utc": datetime.now(timezone.utc).isoformat(),
        "collection_host": {"machine": platform.machine(), "kernel_release": platform.release()},
        "target_root": str(reader.root), "live_filesystem": reader.root == Path("/"),
        "scope": "passive inspection plus explicitly selected fixed information queries; no performance settings changed",
        "drm": drm, "kernel_backend": kernel_backend(reader, drm),
        "device_tree": dt, "kernel_config": config,
        "firmware": firmware_snapshot(reader, dt), "gpu_devfreq": devfreq_snapshot(reader),
        "vulkan_icds": icd_snapshot(reader), "kwin_processes": kwin_environments(reader),
        "collector_graphics_environment": selected_environment(os.environ), "queries": {},
        "not_tested": ["correct GPU draw/readback", "cross-device GBM/dma-buf import and fences",
                       "native DPU/DSI frame and refresh", "presentation latency or frame rate",
                       "Venus hardware decode", "GPU suspend/resume", "multi-process address-space isolation"],
    }
    for kind in FIXED_PROBES:
        supplied = getattr(args, kind + "_report")
        if supplied:
            try:
                data = bounded_file(supplied, PROBE_LIMIT)
                report["queries"][kind] = {"status": "supplied_log", "source": str(supplied),
                                          "sha256": hashlib.sha256(data).hexdigest(),
                                          "parsed": parse_probe(kind, data.decode("utf-8", "replace")),
                                          "note": "origin, exit status and completeness not independently verified"}
            except (OSError, ValueError) as error:
                report["queries"][kind] = {"status": "unavailable", "reason": str(error)}
        elif kind in args.probe:
            try:
                report["queries"][kind] = run_probe(kind, args.timeout)
            except OSError as error:
                report["queries"][kind] = {"status": "query_failed", "reason": str(error)}
    render = [row for row in drm if row["name"].startswith("renderD") and row.get("driver") == "msm"]
    accessible = any(row.get("is_character_device") and row.get("caller_can_read_write") for row in render)
    identified = any(row.get("status") == "completed" and row.get("parsed", {}).get("a650_reported")
                     for row in report["queries"].values())
    report["enumeration_gate"] = {
        "accessible_msm_render_node_observed": accessible,
        "successful_live_query_reports_a650": identified,
        "mainline_backend_candidate": report["kernel_backend"]["classification"] == "mainline_msm_candidate",
        "satisfied": bool(accessible and identified and reader.root == Path("/") and
                          report["kernel_backend"]["classification"] == "mainline_msm_candidate"),
        "meaning": "enumeration only; never a complete GPU, compositor or tablet acceptance result",
    }
    report["observations"] = observations(report)
    report["unavailable"] = reader.unavailable
    print(json.dumps(report, indent=2))
    return 1 if args.require_a650_enumeration and not report["enumeration_gate"]["satisfied"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
