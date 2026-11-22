# Lenovo TB371FC native Linux hardware matrix

## Scope and current reference

The table below preserves the early **4.19.325 diagnostic bridge / Linux 7.1.x
porting record**. Its original target was Arch Linux ARM on Linux 7.1.y;
"not tested", "pending" and failed probes refer to those named experiments.
4PDA reports are separate community evidence, not local validation of this
repository's kernel or the owner's tablet.

The latest installed, device-tested project profile is **R226 on Linux 6.12**,
as recorded on 2026-11-05: [R226](../experimental/r226/README.md),
[current installation/status guide](INSTALL_CURRENT.md) and
[current feature summary](../README.en.md#what-works). That profile reports
working touch, Wi-Fi, Bluetooth, audio, GPU and MM8013 battery telemetry with a
capacity-based charge limiter. Native DPU/DSI display, suspend and the pogo
keyboard remain incomplete or unvalidated in that profile; hubs/PD/DP remain
unfinished, and R241 was built but not hardware-tested.

The [2026-11-23 research record](research/2026-11-23/README.md) adds this
owner's Android captures, isolated traces and source comparisons. It does
**not** add a new mainline boot or peripheral-validation result. See the
[display audit](research/2026-11-23/display.md),
[keyboard/pen audit](research/2026-11-23/input-and-pen.md) and
[power audit](research/2026-11-23/power-management.md) for current evidence and
explicit differences from the historical assumptions below.

## Historical bring-up matrix

| Subsystem | Exact hardware / wiring | Evidence | Upstream path | Historical local status / later correction |
|---|---|---|---|---|
| SoC / GPU | Qualcomm SM8250 (Snapdragon 870), Adreno 650 | Android properties and stock DT | `qcom/sm8250`, MSM DRM/Freedreno | GMU/GPU enabled and stock firmware packaged; not boot-tested |
| Internal display | Dual DSI 2944x1840, BOE or Tianma NT36532, DSC 1.1; Android advertises up to 144 Hz | Live Android DRM, exact stock panel DTS and 4.19.325 diagnostic boot | Extended upstream NT36523 dual-DSI driver | Vendor bridge boot identified Tianma and exposed 30/60/120 Hz; 140/144 Hz was not exposed there. MSM DRM fbdev plus `tty0` is now built for the next test so Linux can replace the retained Lenovo splash; hardware validation is pending. Mainline graph remains staged |
| Touch / AP500U inking | Novatek NT36532 SPI at 9.6 MHz on GPIO40-43, reset GPIO56, IRQ GPIO68; 10x 18400x29440 reports; pressure 4095, hover, tilt +/-60, two buttons | Live Android input capabilities, exact stock overlay, source and 4.19.325 diagnostic boot | Out-of-tree Novatek SPI input driver, later upstream cleanup | Tianma cascade controller firmware loaded successfully and both touch/AP500U input nodes registered on hardware; live event quality still needs interactive validation; Linux 7.1 port remains compile-tested |
| Magnetic keyboard / touchpad | Lenovo keyboard cover I2C-HID at QUPv3 SE13 address `0x60`, VID:PID `17ef:6175`; reset GPIO114, wake GPIO108, IRQ GPIO110 | Historical overlay and V56.2 keyboard/touchpad/gesture result; current Android HID descriptor and DT in the [input audit](research/2026-11-23/input-and-pen.md) | `i2c-hid-of`, generic HID and HID multitouch | V56.2 downstream result; Linux 7.1.8 r7 was offline verified. Current stock DT has `interrupts = <110 0>`; the port uses `<110 8>` (`IRQ_TYPE_LEVEL_LOW`). Zero does not confirm level-low behavior. Mainline cold attach, hotplug and suspend/resume remain unvalidated |
| AP500U dock charging | NXP CTN730 NFC wireless-charging transmitter at I2C `0x28`; reset GPIO84, enable GPIO160, IRQ GPIO111. Lenovo moved PCIe1 wake from GPIO84 to GPIO81 to free this pin | Vendor-derived overlay, [4PDA post #1751](https://4pda.to/forum/index.php?showtopic=1086877&view=findpost&p=144438358), and current Android `ctn730` binding | No usable upstream driver identified; public GPL downstream implementations have been located and are linked in the [input/pen audit](research/2026-11-23/input-and-pen.md) | PCIe1 remap is present; the normal mainline DTS does not implement pen charging. Android enumeration/binding is confirmed, but no charging cycle was tested; downstream source availability is not a completed mainline port |
| Storage | UFS | Stock DT, Android partitions and 4.19.325 diagnostic boot | `ufshcd-qcom` | UFS and 119 GiB microSD enumerated on the vendor bridge; mainline still untested |
| Wi-Fi | Qualcomm QCA6390 over PCIe 1; wake GPIO 81 | Stock DT, live Android, 6.12 port notes and 4.19.325 diagnostic boot | `ath11k_pci` + board/firmware blobs | Downstream bridge now reaches the complete single-client WLFW handshake and loads the stock QCACLD INI. Hardware created `wlan0`, `p2p0` and `wifi-aware0`; `phy0` was unblocked and firmware reported 802.11ax support. Missing optional `wlan_mac.bin` caused a firmware-class delay and fallback MAC, then the unused device entered clean idle shutdown. Scan/association and stable-7.1 `ath11k` remain untested. |
| Bluetooth | QCA6390 on UART6; enable GPIO 21 | Stock DT, live Android and 4.19.325 diagnostic boot | `qcom,qca6390-bt` + `btqca` firmware | `bt_power` rfkill and `ttyHS0` on `msm_geni_serial` confirmed; soft-blocked in diagnostic Linux, no `hci0` yet |
| USB-C data | DWC3 at `a600000`, dual-role | Live Android USB HAL and 4.19.325 diagnostic boot | DWC3 + PM8150B Type-C | USB NCM device mode and Type-C partner verified; host mode/dock remains untested |
| USB-C charging / PD | PM8150B Type-C/PD; Android reports sink/device and source/host combinations | Live Android USB HAL, stock DT and 4.19.325 diagnostic boot | PM8150B Type-C, power-supply framework | Early 4.19.325 diagnostic: sink/device and charging observed, but the gauge failed to bind and SOC was invalid. Later 6.12 profiles report MM8013 telemetry and a capacity-based charging hold; this does not establish complete Type-C/PD policy. R226/PD experiments and the current Android charging snapshot are separated in the [power audit](research/2026-11-23/power-management.md) |
| External display | DP Alt Mode; ONNN redriver at I2C 0x1c; DP connector exists as `DP-1` | Live sysfs, stock DT, 4PDA reports working hubs/adapters | MSM DP + QMP combo PHY + NB7VPQ904M-compatible redriver | DRM/PHY/Type-C graph staged; needs hardware test |
| USB-C analog audio | FSA4480 at I2C 0x42 | Live driver binding and stock DT | `TYPEC_MUX_FSA4480` | Node staged; audio routing pending |
| Speakers | Four NXP TFA9894 N1A1 smart amps at 0x34-0x37; reset GPIOs 115/117/118/116; YC/QS ID is vendor GPIO 1171 | Stock DT, firmware containers and static analysis of stock `audio_tfa98xx.ko` | Temporary sdm845-mainline downstream-derived TFA98xx codec, later proper upstream driver | V56.3 hardware check: no ALSA cards (`/dev/snd` has only `timer`) because `CONFIG_SND_SOC_QCOM` and the SM8250 machine path are absent. USB audio is built in as a temporary route. Linux 7 TFA98xx module and disabled DT nodes compile; YC/QS GPIO mapping and TDM slots must be captured before probing |
| Fuel gauge | Mitsumi MM8013C06 at I2C 0x55 | Exact stock overlay and 4.19.325 diagnostic boot; later R184/R187 source and R226 feature report | `FUEL_GAUGE_MM8013` | Corrected from the J716F BQ27541 assumption. `exfg not found` and invalid SOC belong to the early 4.19.325 diagnostic; they are not the current R226 status. Later 6.12 profiles report working telemetry. The [power audit](research/2026-11-23/power-management.md) distinguishes gauge measurement, charge limiting, PD and suspend |
| Cameras | Fitted rear: OFILM S5K4H7 on CCI0/CSIPHY0, MCLK GPIO94/reset GPIO93. Fitted front: TXD HI1339 on CCI1/CSIPHY1, MCLK GPIO95/reset GPIO92 | Read-only Android properties and CameraService; exact stock DT and AX6637 CamX modules | SM8250 CAMSS/CCI plus new exact S5K4H7/HI1339 V4L2 drivers; libcamera | S5K4H7 driver, binding and isolated DTB compile and validate; HI1339 pending; normal DT remains disabled |
| Sensors | Bosch BMI3x0 accel/gyro, QST QMC630x magnetometer, ams TCS3408 ambient/RGB, ROHM BU52053NVX Hall plus Qualcomm sensor fusion | Read-only live Android sensor service and stock DT | `qcom_q6v5_pas`, IIO, firmware | Exact inventory confirmed; ADSP/CDSP/SLPI firmware packaged; Linux drivers and orientation matrices still need validation |
| Suspend/resume | Platform sleep plus panel power sequencing | 4PDA reports working screen suspend/resume | RPMh, remoteprocs, panel/DRM | Not tested |

## Safety gates

1. Keep the first boot temporary and non-writing.
2. Preserve the stock panel power sequence before enabling native DSI; use simple framebuffer first.
3. Do not enable camera rails or clocks from guessed data.
4. Validate USB device mode first, then host mode/PD, then DP Alt Mode with logs.
5. Do not design dual boot or write partitions until the temporary image boots reliably and recovery paths are verified.

## Primary references

- [4PDA TB371FC topic](https://4pda.to/forum/index.php?showtopic=1086877)
- [Older TB371FC kernel project](https://github.com/tb371fc-desktop/linux-android-msm-lenovo-p12)
- [4PDA post #1751: 6.12 DTS, recovered overlay and GPIO84/PCIe warning](https://4pda.to/forum/index.php?showtopic=1086877&view=findpost&p=144438358)
- Exact vendor-derived DTS in `tb371fc-devicetree/qcom/lenovo-tb371fc-overlay.dts`
- Linux 7.1 reference boards `qrb5165-rb5.dts` and `sm8250-xiaomi-elish-common.dtsi`
