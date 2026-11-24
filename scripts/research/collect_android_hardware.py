#!/usr/bin/env python3
"""Read a bounded, hardware-only TB371FC Android reference to stdout.

No device writes, input-event recording, register reads, network configuration,
unfiltered logs, serials, or Bluetooth addresses. Python 3 standard library only.
Run through an existing root shell; the script does not change SELinux.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import glob
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time

MAX_FILE = 65536
DT_ROOT = "/sys/firmware/devicetree/base"
PROPS = (
    "ro.product.manufacturer", "ro.product.model", "ro.product.device",
    "ro.board.platform", "ro.soc.model", "ro.build.version.release",
    "ro.build.version.sdk", "ro.build.version.security_patch",
    "ro.build.display.id", "ro.boot.slot_suffix", "ro.boot.flash.locked",
    "ro.boot.vbmeta.device_state", "ro.boot.verifiedbootstate",
)
SUPPLY_ATTRS = (
    "status", "health", "present", "online", "type", "real_type", "capacity",
    "temp", "current_now", "voltage_now", "current_max", "voltage_max",
    "voltage_max_design", "charge_counter", "charge_full", "charge_full_design",
    "cycle_count", "input_current_limit", "input_current_limited",
    "constant_charge_current_max", "constant_charge_voltage_max", "typec_mode",
    "typec_power_role", "typec_cc_orientation", "pd_active", "pd_current_max",
    "pd_voltage_min", "pd_voltage_max", "usb_type", "scope",
)
PM_ATTRS = ("runtime_status", "runtime_active_time", "runtime_suspended_time",
            "control", "autosuspend_delay_ms", "wakeup")
DT_NODE = re.compile(
    r"(?:^qcom,mdss_dsi_panel_spinel_(?:boe|tianma)_nt36532_dsc_3k_video$"
    r"|^(?:qcom,)?(?:mdss_)?dsi(?:_ctrl|_phy|_pll)?[01]?@"
    r"|^qcom,dsi-display@|(?:^|[,._-])(?:smb5|ctn730|mm8013|ktz8866)(?:@|$)"
    r"|^novatek@0$|^mouse@60$|^keyboard-cover@60$|qcom,cnss-qca6390"
    r"|^qcom,pm8150b@[0-9]+:.*(?:charger|typec|smb|power-on)"
    r"|^qcom,pm8150a@[0-9]+:.*(?:regulator|ldo|typec)|^ldo[ab]?2$)"
)
# Explicit runtime-hardware properties audited against the sanitized TB371FC
# Android capture dated 2026-11-23. Do not add broad vendor-prefix matches:
# unknown properties are recorded by name without reading or hashing values.
DT_PROPERTY_ALLOWLIST = frozenset({
    '#address-cells',
    '#clock-cells',
    '#cooling-cells',
    '#size-cells',
    'cell-index',
    'clock-names',
    'clock-rate',
    'clocks',
    'cnss-daemon-support',
    'cnss-enable-self-recovery',
    'compatible',
    'device_type',
    'dpdm-supply',
    'enable-gpios',
    'frame-threshold-time-us',
    'hid-descr-addr',
    'interrupt-gpios',
    'interrupt-names',
    'interrupt-parent',
    'interrupts',
    'io-channel-names',
    'io-channels',
    'ktz8866,enn-gpio',
    'ktz8866,enp-gpio',
    'ktz8866,hwen-gpio',
    'label',
    'lenovo,jeita_enable',
    'linux,phandle',
    'mcu_resume_gpio',
    'mcu_rst_gpio',
    'memory-region',
    'mhi,auto-queue',
    'mhi,auto-start',
    'mhi,brstmode',
    'mhi,buffer-len',
    'mhi,chan',
    'mhi,chan-dir',
    'mhi,data-type',
    'mhi,doorbell-mode',
    'mhi,early-notify',
    'mhi,ee',
    'mhi,event-ring',
    'mhi,intmod',
    'mhi,m2-no-db-access',
    'mhi,max-channels',
    'mhi,msi',
    'mhi,num-elements',
    'mhi,priority',
    'mhi,timeout',
    'name',
    'novatek,irq-gpio',
    'novatek,mp-support-dt',
    'novatek,pen-support',
    'novatek,reset-gpio',
    'novatek,stylus-resol-double',
    'panel',
    'phandle',
    'pinctrl-names',
    'post-power-on-delay-ms',
    'qcom,auto-recharge-vbat-mv',
    'qcom,battery-data',
    'qcom,bt-en-gpio',
    'qcom,charger-temp-max',
    'qcom,chg-control-gpio',
    'qcom,chg-term-src',
    'qcom,cmd-sync-wait-broadcast',
    'qcom,cmd_db_name',
    'qcom,compression-mode',
    'qcom,converged-dt',
    'qcom,default-topology-index',
    'qcom,display-topology',
    'qcom,dsi-ctrl-num',
    'qcom,dsi-phy-num',
    'qcom,dsi-pll-ssc-en',
    'qcom,dsi-pll-ssc-mode',
    'qcom,dsi-select-clocks',
    'qcom,dsi-supported-dfps-list',
    'qcom,esd-check-enabled',
    'qcom,fastchg-current-ma',
    'qcom,fcc-max-ua',
    'qcom,fv-max-uv',
    'qcom,hvdcp2-max-icl-ua',
    'qcom,jeita-fcc-ranges',
    'qcom,jeita-fv-ranges',
    'qcom,low-latency',
    'qcom,max-voltage-uv',
    'qcom,mdss-brightness-max-level',
    'qcom,mdss-dsc-bit-per-component',
    'qcom,mdss-dsc-bit-per-pixel',
    'qcom,mdss-dsc-block-prediction-enable',
    'qcom,mdss-dsc-scr-version',
    'qcom,mdss-dsc-slice-height',
    'qcom,mdss-dsc-slice-per-pkt',
    'qcom,mdss-dsc-slice-width',
    'qcom,mdss-dsc-version',
    'qcom,mdss-dsi-bl-max-level',
    'qcom,mdss-dsi-bl-min-level',
    'qcom,mdss-dsi-bl-pmic-control-type',
    'qcom,mdss-dsi-bllp-eof-power-mode',
    'qcom,mdss-dsi-bllp-power-mode',
    'qcom,mdss-dsi-border-color',
    'qcom,mdss-dsi-bpp',
    'qcom,mdss-dsi-dispparam-pen-120hz-command',
    'qcom,mdss-dsi-dispparam-pen-120hz-command-state',
    'qcom,mdss-dsi-dispparam-pen-144hz-command',
    'qcom,mdss-dsi-dispparam-pen-144hz-command-state',
    'qcom,mdss-dsi-dispparam-pen-30hz-command',
    'qcom,mdss-dsi-dispparam-pen-30hz-command-state',
    'qcom,mdss-dsi-dispparam-pen-60hz-command',
    'qcom,mdss-dsi-dispparam-pen-60hz-command-state',
    'qcom,mdss-dsi-dma-trigger',
    'qcom,mdss-dsi-h-back-porch',
    'qcom,mdss-dsi-h-front-porch',
    'qcom,mdss-dsi-h-left-border',
    'qcom,mdss-dsi-h-pulse-width',
    'qcom,mdss-dsi-h-right-border',
    'qcom,mdss-dsi-h-sync-pulse',
    'qcom,mdss-dsi-h-sync-skew',
    'qcom,mdss-dsi-lane-0-state',
    'qcom,mdss-dsi-lane-1-state',
    'qcom,mdss-dsi-lane-2-state',
    'qcom,mdss-dsi-lane-3-state',
    'qcom,mdss-dsi-mdp-trigger',
    'qcom,mdss-dsi-off-command',
    'qcom,mdss-dsi-off-command-state',
    'qcom,mdss-dsi-on-command',
    'qcom,mdss-dsi-on-command-state',
    'qcom,mdss-dsi-pan-enable-dynamic-fps',
    'qcom,mdss-dsi-pan-fps-update',
    'qcom,mdss-dsi-panel-blackness-level',
    'qcom,mdss-dsi-panel-broadcast-mode',
    'qcom,mdss-dsi-panel-clockrate',
    'qcom,mdss-dsi-panel-count',
    'qcom,mdss-dsi-panel-framerate',
    'qcom,mdss-dsi-panel-hdr-color-primaries',
    'qcom,mdss-dsi-panel-hdr-enabled',
    'qcom,mdss-dsi-panel-height',
    'qcom,mdss-dsi-panel-name',
    'qcom,mdss-dsi-panel-peak-brightness',
    'qcom,mdss-dsi-panel-phy-timings',
    'qcom,mdss-dsi-panel-status-check-mode',
    'qcom,mdss-dsi-panel-type',
    'qcom,mdss-dsi-panel-width',
    'qcom,mdss-dsi-reset-sequence',
    'qcom,mdss-dsi-rx-eot-ignore',
    'qcom,mdss-dsi-stream',
    'qcom,mdss-dsi-traffic-mode',
    'qcom,mdss-dsi-tx-eot-append',
    'qcom,mdss-dsi-underflow-color',
    'qcom,mdss-dsi-v-back-porch',
    'qcom,mdss-dsi-v-bottom-border',
    'qcom,mdss-dsi-v-front-porch',
    'qcom,mdss-dsi-v-pulse-width',
    'qcom,mdss-dsi-v-top-border',
    'qcom,mdss-dsi-virtual-channel-id',
    'qcom,mdss-pan-physical-height-dimension',
    'qcom,mdss-pan-physical-width-dimension',
    'qcom,msm-bus,name',
    'qcom,msm-bus,num-cases',
    'qcom,msm-bus,num-paths',
    'qcom,msm-bus,vectors-KBps',
    'qcom,net-id',
    'qcom,otg-cl-ua',
    'qcom,panel-supply-entries',
    'qcom,pd-thermal-mitigation',
    'qcom,platform-lane-config',
    'qcom,platform-regulator-settings',
    'qcom,platform-reset-gpio',
    'qcom,platform-strength-ctrl',
    'qcom,platform-te-gpio',
    'qcom,pmic-revid',
    'qcom,sec-charger-config',
    'qcom,set-wlaon-pwr-ctrl',
    'qcom,smb-internal-pull-kohm',
    'qcom,smb-temp-max',
    'qcom,smmu-s1-enable',
    'qcom,supply-disable-load',
    'qcom,supply-enable-load',
    'qcom,supply-max-voltage',
    'qcom,supply-min-voltage',
    'qcom,supply-name',
    'qcom,sw-ctrl-gpio',
    'qcom,thermal-mitigation',
    'qcom,ulps-enabled',
    'qcom,vdd-wlan-aon-config',
    'qcom,vdd-wlan-dig-config',
    'qcom,vdd-wlan-io-config',
    'qcom,vdd-wlan-rfa1-config',
    'qcom,vdd-wlan-rfa2-config',
    'qcom,wd-bark-time-secs',
    'qcom,wlan-ant-switch-config',
    'qcom,wlan-ramdump-dynamic',
    'qcom,wlan-rc-num',
    'refgen-supply',
    'reg',
    'reg-names',
    'regulator-name',
    'rst-gpios',
    'spi-max-frequency',
    'status',
    'vdd-wlan-aon-supply',
    'vdd-wlan-dig-supply',
    'vdd-wlan-io-supply',
    'vdd-wlan-rfa1-supply',
    'vdd-wlan-rfa2-supply',
    'vdda-0p9-supply',
    'vdda-1p2-supply',
    'wlan-ant-switch-supply',
    'wlan-en-gpio',
})
DT_PINCTRL_PROPERTY = re.compile(r"pinctrl-[0-9]+")
CONFIG = re.compile(r"^#? ?CONFIG_(?:KEXEC|FTRACE|TRACING|TRACEPOINTS|EVENT_TRACING|"
                    r"FUNCTION_TRACER|FUNCTION_GRAPH_TRACER|IKCONFIG|DEBUG_FS|PM|SUSPEND|"
                    r"HIBERNATION|CPU_IDLE|CPU_FREQ|QCOM|HID|I2C_HID|TOUCHSCREEN_NT|"
                    r"TOUCHSCREEN_NVT|DRM|BACKLIGHT|REGULATOR|POWER_SUPPLY|CHARGER|"
                    r"BATTERY|TYPEC|USB_ROLE|WLAN|ATH11K|NFC|CTN730)")
TRACE_PREFIXES = ("power:", "drm:", "sde:", "dsi:", "mdss:", "kgsl:")


class Reader:
    def __init__(self, root="/"):
        self.root = Path(root)
        self.errors = {}

    def path(self, path):
        return self.root / str(path).lstrip("/")

    def raw(self, path, limit=MAX_FILE):
        try:
            # Some sysfs reads wait for a hardware state transition. Bound every
            # read instead of letting an observational collection hang forever.
            def expired(signum, frame):
                raise TimeoutError("bounded hardware read")
            previous = signal.signal(signal.SIGALRM, expired)
            signal.setitimer(signal.ITIMER_REAL, 0.75)
            with self.path(path).open("rb") as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                self.errors[path] = "oversize; omitted"
                return None
            return data
        except OSError as exc:
            self.errors[path] = exc.__class__.__name__
            return None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)

    def text(self, path, limit=MAX_FILE):
        data = self.raw(path, limit)
        return None if data is None else data.decode("utf-8", "replace").strip()

    def match(self, pattern):
        return sorted("/" + str(Path(p).relative_to(self.root))
                      for p in glob.glob(str(self.path(pattern))))

    def attrs(self, directory, names):
        return {name: value for name in names
                if (value := self.text(directory + "/" + name)) is not None}

    def link(self, path):
        try:
            if not self.path(path).is_symlink():
                return None
            return os.path.realpath(self.path(path))
        except OSError:
            return None


def command_text(reader, argv, *, error_key, stdout_limit, timeout=2):
    """Return a complete nonempty command result, or register unavailability.

    Commands are fixed argument lists at the call sites, never shell strings.
    Read output as bytes so the limit cannot be bypassed by multibyte text.
    Do not publish partial stdout or stderr from unsuccessful commands.
    """
    try:
        run = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        reader.errors[error_key] = exc.__class__.__name__
        return None
    if run.returncode != 0:
        reader.errors[error_key] = f"exit status {run.returncode}; omitted"
        return None
    if len(run.stdout) > stdout_limit:
        reader.errors[error_key] = "oversize stdout; omitted"
        return None
    value = run.stdout.decode("utf-8", "replace").strip()
    if not value:
        reader.errors[error_key] = "empty stdout; omitted"
        return None
    return value


def dt_property_allowed(name):
    """Only reviewed literal properties and indexed pinctrl references."""
    return name in DT_PROPERTY_ALLOWLIST or DT_PINCTRL_PROPERTY.fullmatch(name) is not None


def binary_value(data):
    out = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "base64": base64.b64encode(data).decode("ascii")}
    if not data:
        out["boolean"] = True
    elif data[-1:] == b"\0" and all(b in (0, 9, 10, 13) or 32 <= b < 127 for b in data):
        out["strings"] = data.rstrip(b"\0").decode("ascii").split("\0")
    if data and len(data) % 4 == 0:
        out["be32"] = list(struct.unpack(">" + "I" * (len(data) // 4), data))
    return out


def dt_snapshot(reader):
    selected, references, omitted_names = {}, {}, {}
    base = reader.path(DT_ROOT)
    if not base.is_dir():
        return {"nodes": {}, "phandles": {}, "omitted_property_names": {}}
    roots = []
    for path, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if not name.startswith("novatek-mp-criteria-")]
        relative = "/" + str(Path(path).relative_to(base))
        for phandle in ("phandle", "linux,phandle"):
            if phandle in files:
                data = reader.raw(DT_ROOT + relative + "/" + phandle, 4)
                if data is not None and len(data) == 4:
                    references[str(struct.unpack(">I", data)[0])] = relative
        if DT_NODE.search(Path(path).name):
            roots.append(relative)
    for relative in sorted(set(roots)):
        for path, dirs, files in os.walk(base / relative.lstrip("/")):
            # Manufacturing-test threshold matrices are unrelated to runtime
            # input/display support and need not be copied into public evidence.
            dirs[:] = [name for name in dirs if not name.startswith("novatek-mp-criteria-")]
            node = "/" + str(Path(path).relative_to(base))
            if node in selected:
                continue
            props = {}
            for name in sorted(files):
                if not dt_property_allowed(name):
                    omitted_names.setdefault(node, []).append(name)
                    continue
                data = reader.raw(DT_ROOT + node + "/" + name)
                if data is not None:
                    props[name] = binary_value(data)
            selected[node] = props
    # Only retain phandles directly named by hardware properties, not a full DT.
    used = set()
    for props in selected.values():
        for name, value in props.items():
            cells = value.get("be32", [])
            if re.fullmatch(r"pinctrl-[0-9]+", name):
                used.update(str(v) for v in cells)
            elif cells and (name.endswith("-supply") or name in ("interrupt-parent", "phys", "power-domains", "clocks", "qcom,panel-supply-entries") or "gpio" in name):
                used.add(str(cells[0]))
    return {"nodes": selected,
            "phandles": {k: v for k, v in references.items() if k in used},
            "omitted_property_names": omitted_names}


def capture(reader):
    result = {"schema_version": 1, "capture_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "collection": "passive Android reference; no input stream or register access",
              "kernel_release": reader.text("/proc/sys/kernel/osrelease"),
              "uptime": reader.text("/proc/uptime"), "properties": {}}
    if str(reader.root) == "/":
        for prop in PROPS:
            value = command_text(reader, ["/system/bin/getprop", prop],
                                 error_key="getprop:" + prop, stdout_limit=4096)
            if value is not None:
                result["properties"][prop] = value
    cmdline = reader.text("/proc/cmdline") or ""
    boot_keys = {"androidboot.verifiedbootstate", "androidboot.vbmeta.device_state",
                 "androidboot.veritymode", "androidboot.secureboot", "msm_drm.dsi_display0",
                 "msm_drm.dsi_display1", "video"}
    result["boot_arguments"] = dict(item.split("=", 1) for item in cmdline.split()
                                    if "=" in item and item.split("=", 1)[0] in boot_keys)
    result["device_tree"] = dt_snapshot(reader)
    result["display"] = {}
    for node in reader.match("/sys/class/drm/card*-DSI-*"):
        result["display"][node] = reader.attrs(node, ("status", "enabled", "dpms", "modes"))
    result["backlight"] = {node: reader.attrs(node, ("type", "brightness", "actual_brightness", "max_brightness", "bl_power"))
                           for node in reader.match("/sys/class/backlight/*")}
    result["power_supply"] = {name: reader.attrs("/sys/class/power_supply/" + name, SUPPLY_ATTRS)
                              for name in ("battery", "bms", "usb", "main", "dc", "charge_pump_master", "pc_port")}
    result["cpufreq"] = {node: reader.attrs(node, ("affected_cpus", "related_cpus", "scaling_governor", "scaling_min_freq", "scaling_max_freq", "scaling_cur_freq", "cpuinfo_min_freq", "cpuinfo_max_freq", "scaling_available_frequencies"))
                         for node in reader.match("/sys/devices/system/cpu/cpufreq/policy*")}
    result["cpuidle"] = {node: reader.attrs(node, ("name", "desc", "latency", "residency", "usage", "time", "disable"))
                         for node in reader.match("/sys/devices/system/cpu/cpu[0-9]*/cpuidle/state*")}
    # wakeup_count is intentionally omitted: its blocking read is a suspend
    # synchronization protocol, not a harmless instantaneous counter read.
    result["system_power"] = reader.attrs("/sys/power", ("state", "mem_sleep", "pm_async"))
    result["typec"] = {node: reader.attrs(node, ("power_role", "data_role", "port_type", "power_operation_mode", "orientation"))
                       for node in reader.match("/sys/class/typec/port[0-9]*") if "-" not in Path(node).name}
    result["dual_role_usb"] = {node: reader.attrs(node, ("mode", "power_role", "data_role", "supported_modes"))
                               for node in reader.match("/sys/class/dual_role_usb/*")}
    result["suspend_stats"] = reader.attrs("/sys/power/suspend_stats", ("success", "fail", "failed_freeze", "failed_prepare", "failed_suspend", "failed_suspend_late", "failed_suspend_noirq", "failed_resume", "failed_resume_early", "failed_resume_noirq"))
    result["input_devices"] = []
    wanted = ("NVTCapacitive", "Lenovo Keyboard Pack for Spinel", "Lenovo Precision Pen 3")
    for node in reader.match("/sys/class/input/input*"):
        name = reader.text(node + "/name") or ""
        if not name.startswith(wanted):
            continue
        item = {"path": node, "name": name,
                "id": reader.attrs(node + "/id", ("bustype", "vendor", "product", "version")),
                "capabilities": reader.attrs(node + "/capabilities", ("ev", "key", "rel", "abs", "msc", "led", "sw", "ff"))}
        events = reader.match(node + "/event*")
        item["event_nodes"] = ["/dev/input/" + Path(e).name for e in events]
        if str(reader.root) == "/":
            item["axis_capabilities"] = []
            for event in item["event_nodes"]:
                value = command_text(reader, ["/system/bin/getevent", "-lp", event],
                                     error_key=event, stdout_limit=16384)
                if value is not None:
                    item["axis_capabilities"].append(value)
        result["input_devices"].append(item)
    result["keyboard_hid"] = []
    for node in reader.match("/sys/bus/hid/devices/0018:17EF:6175.*"):
        data = reader.raw(node + "/report_descriptor", 16384)
        result["keyboard_hid"].append({"path": node, "driver": reader.link(node + "/driver"),
                                       "descriptor": None if data is None else binary_value(data)})
    result["hardware_bindings"] = {}
    for pattern in ("/sys/bus/i2c/devices/*-0060", "/sys/bus/i2c/devices/*-0028", "/sys/bus/spi/devices/spi*.0", "/sys/bus/pci/devices/0000:01:00.0"):
        for node in reader.match(pattern):
            result["hardware_bindings"][node] = {
                **reader.attrs(node, ("name", "modalias", "vendor", "device")),
                "driver": reader.link(node + "/driver"), "of_node": reader.link(node + "/of_node"),
                "power": reader.attrs(node + "/power", PM_ATTRS)}
    events = reader.text("/sys/kernel/tracing/available_events", 512 * 1024) or ""
    result["trace_capabilities"] = {"events": sorted(e for e in events.splitlines() if e.startswith(TRACE_PREFIXES)),
                                    "global_tracing_on": reader.text("/sys/kernel/tracing/tracing_on"),
                                    "global_current_tracer": reader.text("/sys/kernel/tracing/current_tracer"),
                                    "instances_supported": reader.path("/sys/kernel/tracing/instances").is_dir()}
    compressed = reader.raw("/proc/config.gz", 128 * 1024)
    if compressed:
        try:
            config = gzip.decompress(compressed).decode()
            result["kernel_config"] = [line for line in config.splitlines() if CONFIG.match(line)]
        except (OSError, UnicodeError):
            reader.errors["/proc/config.gz"] = "invalid config gzip"
    result["firmware_metadata"] = []
    for pattern in ("/vendor/firmware/novatek*", "/vendor/firmware_mnt/image/novatek*"):
        for node in reader.match(pattern):
            if not reader.path(node).is_file():
                continue
            data = reader.raw(node, 2 * 1024 * 1024)
            if data is not None:
                result["firmware_metadata"].append({"path": node, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    result["unavailable"] = reader.errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/", help="read a fixture tree instead of the live filesystem")
    parser.add_argument("--gzip-base64", action="store_true", help="bounded relay transport; decode on the analysis host")
    args = parser.parse_args()
    if args.root == "/" and os.geteuid() != 0:
        parser.error("run in an existing root shell; no privilege changes are attempted")
    data = json.dumps(capture(Reader(args.root)), ensure_ascii=True, sort_keys=True, indent=2).encode()
    if len(data) > 4 * 1024 * 1024:
        raise SystemExit("capture exceeds 4 MiB bound; inspect selection before retrying")
    if args.gzip_base64:
        print("TB371FC_EVIDENCE_BASE64:" + base64.b64encode(gzip.compress(data, mtime=0)).decode())
    else:
        sys.stdout.buffer.write(data + b"\n")


if __name__ == "__main__":
    main()
