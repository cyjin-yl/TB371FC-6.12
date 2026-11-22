#!/usr/bin/env python3
"""Run bounded, explicitly software-only ARM64 graphics checks under PRoot.

This orchestrates fixed commands in the Fedora build rootfs. It never exposes
DRM/input/block devices, changes host binfmt, or claims Adreno/native-DSI support.
All child groups are terminated on timeout or compositor cleanup.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


def stop(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
    except ProcessLookupError:
        process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work"))
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,32}", args.run_id):
        parser.error("run-id must be 1-32 letters, digits or hyphens")
    work = args.work.resolve()
    root = work / "fedora-bundle/rootfs"
    if "VERSION_ID=45\n" not in (root / "etc/os-release").read_text():
        parser.error("expected the assembled Fedora 45 rootfs")
    if (root / "dev/dri").exists() or (root / "dev/kgsl-3d0").exists():
        parser.error("software-only experiment requires no guest DRM/KGSL nodes")
    output = work / f"fedora-smoke-{args.run_id}"
    output.mkdir(exist_ok=False)
    guest_runtime = f"/run/fedora-smoke-{args.run_id}"
    runtime = root / guest_runtime.lstrip("/")
    runtime.mkdir(mode=0o700, exist_ok=False)
    helper = root / "opt/tb371fc-build-tools/fedora_guest_egl.py"
    helper.parent.mkdir(parents=True, exist_ok=True)
    if not helper.resolve().is_relative_to(root.resolve()):
        parser.error("guest helper path escapes the build rootfs")
    shutil.copyfile(Path(__file__).with_name("fedora_guest_egl.py"), helper)

    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith(("MESA_", "TU_", "VK_", "GALLIUM_", "LIBGL_")) or name in (
            "LD_PRELOAD", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "EGL_PLATFORM"
        ):
            environment.pop(name, None)
    environment.update({
        "LD_LIBRARY_PATH": str(work / "fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu"),
        "SYSTEMD_OFFLINE": "1",
        "XDG_RUNTIME_DIR": guest_runtime,
        "WAYLAND_DISPLAY": "wayland-fedora-smoke",
        "LP_NUM_THREADS": "1",
    })
    base = [str(work / "fedora-proot-src/src/proot"), "--kill-on-exit",
            "-0", "-r", str(root), "-q", "/usr/bin/qemu-aarch64-static",
            "-b", "/proc", "-b", "/dev/null", "-b", "/dev/zero",
            "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/"]
    report = {
        "schema_version": 1,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "rootfs": str(root), "output_directory": str(output),
        "execution": "ARM64 QEMU user mode through fixed PRoot 5.5.0",
        "physical_gpu_exposed": False,
        "hardware_acceleration_tested": False,
        "native_display_tested": False,
        "probes": {},
    }

    def run(name, command, extra=None, seconds=60):
        target = output / f"{name}.log"
        started = time.monotonic()
        timed_out = False
        with target.open("wb") as stream:
            process = subprocess.Popen(base + command,
                                       env=environment | (extra or {}),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                process.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                stop(process)
        data = target.read_bytes()
        text = data.decode("utf-8", "replace")
        row = {
            "command": command, "environment_overrides": extra or {},
            "exit_code": process.returncode, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "log": str(target), "log_bytes": len(data),
            "log_sha256": hashlib.sha256(data).hexdigest(),
        }
        report["probes"][name] = row
        print(json.dumps({"probe": name, **row}), flush=True)
        return row, text

    try:
        egl, text = run("egl_readback", ["/usr/bin/python3",
                          "/opt/tb371fc-build-tools/fedora_guest_egl.py"])
        try:
            egl["result"] = json.loads(text)
        except json.JSONDecodeError:
            egl["result"] = {"passed": False, "error": "probe did not emit a JSON result"}

        icd_directory = root / "usr/share/vulkan/icd.d"
        lvp_files = sorted(icd_directory.glob("lvp_icd*.json"))
        turnip_files = sorted(icd_directory.glob("freedreno_icd*.json"))
        if len(lvp_files) != 1 or len(turnip_files) != 1:
            raise RuntimeError("expected exactly one packaged Lavapipe and one Freedreno ICD")
        lvp = "/" + str(lvp_files[0].relative_to(root))
        turnip = "/" + str(turnip_files[0].relative_to(root))
        report["packaged_icds"] = {
            "lavapipe": {"path": lvp, "content": json.loads(lvp_files[0].read_text())},
            "freedreno": {"path": turnip, "content": json.loads(turnip_files[0].read_text())},
        }
        vk, text = run("lavapipe_vulkaninfo", ["/usr/bin/vulkaninfo", "--summary"],
                       {"VK_DRIVER_FILES": lvp})
        vk["software_device_reported"] = "llvmpipe" in text.lower() and "CPU" in text
        run("turnip_without_device", ["/usr/bin/vulkaninfo", "--summary"],
            {"VK_DRIVER_FILES": turnip})

        weston_command = ["/usr/bin/weston", "--backend=headless", "--renderer=pixman",
                          "--shell=kiosk-shell.so", "--no-config", "--idle-time=0",
                          "--width=256", "--height=256", "--socket=wayland-fedora-smoke"]
        weston_log = output / "weston.log"
        with weston_log.open("wb") as stream:
            compositor = subprocess.Popen(base + weston_command, env=environment,
                                          stdout=stream, stderr=subprocess.STDOUT,
                                          stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                deadline = time.monotonic() + 30
                while not (runtime / "wayland-fedora-smoke").is_socket():
                    if compositor.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Weston did not create its private Wayland socket")
                    time.sleep(0.2)
                info, text = run("wayland_info", ["/usr/bin/wayland-info"])
                info["compositor_and_output_reported"] = all(
                    name in text for name in ("wl_compositor", "wl_output", "xdg_wm_base"))
                shm, text = run("simple_shm", ["/usr/bin/weston-simple-shm"],
                                {"WAYLAND_DEBUG": "1"}, seconds=5)
                shm["frame_callbacks"] = len(re.findall(r"wl_callback[^\n]*\.done\(", text))
                cube, text = run("lavapipe_vkcube", ["/usr/bin/vkcube", "--wsi", "wayland", "--c", "8"],
                                 {"VK_DRIVER_FILES": lvp, "WAYLAND_DEBUG": "1"})
                cube["requested_frames"] = 8
                cube["wayland_buffer_commits"] = len(re.findall(r"wl_surface[^\n]*\.commit\(", text))
            finally:
                stop(compositor)
        weston_data = weston_log.read_bytes()
        report["weston"] = {
            "command": weston_command, "log": str(weston_log),
            "log_sha256": hashlib.sha256(weston_data).hexdigest(),
            "renderer": "explicit Pixman software renderer",
            "exit_code_after_requested_shutdown": compositor.returncode,
        }
        report["software_smoke_passed"] = bool(
            egl["exit_code"] == 0 and egl["result"].get("passed")
            and vk["exit_code"] == 0 and vk["software_device_reported"]
            and info["exit_code"] == 0 and info["compositor_and_output_reported"]
            and shm["frame_callbacks"] > 0
            and cube["exit_code"] == 0 and not cube["timed_out"]
            and cube["wayland_buffer_commits"] >= 8)
    except Exception as exc:
        report["software_smoke_passed"] = False
        report["error"] = str(exc)
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    destination = output / "result.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": str(destination),
                      "software_smoke_passed": report["software_smoke_passed"],
                      "hardware_acceleration_tested": False}), flush=True)
    return 0 if report["software_smoke_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
