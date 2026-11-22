# Owner Android camera, sensor and audio inventory

## Result and evidence level

This bounded passive capture was made on the owner's current Android session
at **2026-11-22 23:47:37.939173 UTC**, running `4.19.157-perf+`.
It adds current-owner identity and static enumeration evidence for SYS-02.
It does **not** establish camera image quality, microphone or speaker operation,
sensor sample quality, calibration, measured rates, suspend behavior or any
Linux hardware acceptance result.

The [original sanitized JSON](evidence/android-peripheral-inventory.json) is
33,046 bytes, SHA-256
`43613572077d28589c94ec4c07ec216b7bf668ef20f30256835da6580b974c36`.
The [collector](../../../scripts/research/collect_android_peripherals.py) is
11,958 bytes, SHA-256
`332ad3a48c920268c8407a3afa3d12534f3b91a10b02b1ff84e9582404cfaa9b`.
The capture records that same collector hash. The compressed transfer was
checked against the original JSON size and SHA before saving its bytes.

Three kinds of evidence must remain distinct:

| Evidence | What this capture can establish | What it cannot establish |
| --- | --- | --- |
| Device-tree compatible/name properties | This Android DT declares that device or candidate | A fitted chip, successful probe or working device |
| Runtime device/class entry and driver symlink | The named device is registered and, where a symlink exists, bound to that driver | Correct channels, electrical behavior, calibration or data quality |
| SensorService/CameraService static descriptors | Android currently advertises these identities, roles and limited capabilities | Independent chip-ID verification, successful streams, measured sampling or performance |

The collector found 15 I2C clients, 22 video-class entries, 3 IIO entries,
49 logical SensorService descriptors, 2 CameraService devices and one ALSA
card exposing 32 PCM entries. These are **interface counts**, not physical chip,
camera, microphone or speaker counts. The DT scan visited 4,276 nodes and
retained 69 matching compatible-bearing declarations without reaching its
limits; this remains a scoped selection, not an exhaustive board inventory.

## Motion, magnetic, light and Hall sensors

The actual SensorService static list reports:

| Advertised family/function | Advertised vendor | Retained static capability | Interpretation |
| --- | --- | --- | --- |
| `icm4x6xx` accelerometer and gyroscope | TDK-Invensense | `minRate=1.00 Hz`, `maxRate=400.00 Hz` on the corresponding physical-family descriptors | Current HAL identity at the family level; the exact ICM part/revision was not read |
| `qmc630x` magnetometer | QST | `minRate=1.00 Hz`, `maxRate=100.00 Hz` | Current HAL family identity; exact part/revision remains unverified |
| `tcs3408` ambient light and RGB | ams AG | Retained delay fields are zero; no periodic min/max rate was retained | Advertised ALS/RGB identity, without illumination/color measurements |
| `bu52053nvx` Hall effect | ROHM | Retained delay fields are zero | Advertised Hall identity; no lid, keyboard or pen-docking action was performed |

Wakeup and non-wakeup versions appear, as do calibrated/uncalibrated variants.
The list also contains Qualcomm fusion/gesture/step/orientation descriptors and
AOSP derived/debug descriptors. Those do not represent an additional physical
sensor for every listed entry. The JSON preserves their exact names, vendors,
types and retained capability fields, without sensor events or client state.

**This current list advertises `icm4x6xx`; it does not contain a BMI3x0
descriptor.** Historical project references to BMI3x0 therefore cannot be used
as this owner's confirmed IMU identity. The HAL name is itself a descriptor,
not a direct read of the chip's identification register.

The Android IIO entries captured here are three PMIC `qcom,spmi-adc5` instances
associated with PM8150, PM8150B and PM8150L. They are not direct Linux IIO
enumerations of the motion/light/Hall families advertised by SensorService.
This capture did not determine the complete transport and remoteproc protocol
for those HAL sensors.

There is a separate DT/I2C candidate at `3-0018`, named `OCH8801-0`, compatible
`isentek,OCH8801-0`, under `dhall@18`. No `driver` symlink was present for that
client in the capture. Its declaration must not replace the ROHM Hall identity
advertised by SensorService, nor does the missing symlink prove that the part
is physically absent.

**The advertised frequency ranges are not measured sample rates.** No events
were subscribed to, no device was moved for a fixture test, and no bias, noise,
orientation, timestamps, wakeup or data-loss measurements were made.

## Cameras

CameraService successfully returned two static devices, both HAL API 3.5:

| Camera ID | Advertised role | `pixelArraySize` | Orientation | Raw `activeArraySize` tuple | Advertised AE target FPS pairs |
| --- | --- | --- | ---: | --- | --- |
| `0` | Back | 3264 × 2448 | 90° | `[0, 0, 3264, 2448]` | `[15,15]`, `[12,30]`, `[30,30]` |
| `1` | Front | 4240 × 3152 | 270° | `[16,16,4208,3120]` | `[15,15]`, `[10,30]`, `[30,30]` |

The active-array tuples are retained as the raw metadata values. **Pixel-array
dimensions are not an output-stream mode list.** These AE target ranges also
do not prove that every output format, resolution or recording mode operates
at those rates. No stream-configuration matrix, camera frame, video recording,
focus test or image-quality comparison was attempted.

The current DT declares generic `qcom,cam-sensor` nodes at:

- `/soc/qcom,cci@ac4f000/qcom,cam-sensor0`, cell index 0, status `ok`.
- `/soc/qcom,cci@ac50000/qcom,cam-sensor2`, cell index 2, status `ok`.

Runtime V4L2 subdevices `v4l-subdev9` and `v4l-subdev10` are named
`cam-sensor-driver`. Their recorded class-device binding leads to the Qualcomm
`cam_req_mgr` platform driver; it does not expose a particular sensor chip
name. Other registered subdevice names include `cam-cpas`, `cam-isp`,
`cam-csiphy-driver`, `cam-actuator-driver`, `cam-eeprom`, `cam-flash-dev`,
`cam-icp`, `cam-jpeg` and `cam-fd`.

**The fitted rear/front silicon model and module variants remain unconfirmed
by this capture.** Generic CCI nodes, image dimensions and installed driver
infrastructure do not confirm historical S5K4H7, HI1339 or GC08A3 references.
No EEPROM, sensor registers, calibration data or unfiltered camera log was
read to fill that gap.

The same video class also exposes `video32`/`video33` bound to Android's
`msm_vidc_v4l2`, with `qcom,msm-vidc`/`qcom,kona-vidc` DT compatibles. That is
an Android vendor video-driver binding, not mainline Venus decoding evidence.

## Audio and related bound devices

ALSA exposes card 0:

- Card ID: `konaqrdsndcard`.
- Card name/description: `kona-qrd-snd-card`.
- 32 enumerated PCM interfaces, including `MultiMedia1`, `MultiMedia2`,
  `MultiMedia3`, `MM_NOIRQ`, `AFE-PROXY RX/TX`, `AUXPCM Hostless`,
  `CDC_DMA Hostless`, `TX3_CDC_DMA Hostless`, `Tertiary MI2S_TX Hostless Capture`,
  `WSA CDC DMA0 Capture`, `USB Audio Hostless` and `TX CDC DMA5 Capture`.

The JSON retains `/proc/asound/cards`, `/proc/asound/pcm` and the card ID.
These are registered interfaces and potential routing names, not observations
of playback, recording, active clients or successful internal audio paths.
No PCM, mixer control, recording endpoint or playback endpoint was opened.

There are four **actually bound** Android I2C clients:

| Runtime client | DT node | Runtime name | Bound driver |
| --- | --- | --- | --- |
| `6-0034` | `tfa98xx@34` | `tfa98xx` | `/sys/bus/i2c/drivers/tfa98xx` |
| `6-0035` | `tfa98xx@35` | `tfa98xx` | Same |
| `6-0036` | `tfa98xx@36` | `tfa98xx` | Same |
| `6-0037` | `tfa98xx@37` | `tfa98xx` | Same |

All four DT compatibles are `tfa,tfa98xx`. This confirms four driver-bound
addresses, **not the precise TFA9894 silicon/revision, fitted QS versus YC
speaker variant, active acoustic container, calibration success or four
working output channels**. It supplies no basis for selecting one stock
acoustic container over another. The [frozen Linux firmware contract](firmware-kernel-contract.md)
still records the missing TFA9894 DSP integration in the research2 candidate.

The DT also declares Bolero/WCD938x codec and SoundWire slave nodes. This
limited capture did not verify the corresponding SoundWire bindings or exact
codec revision. Microphone part numbers, count, placement and routes remain
unconfirmed.

Two other static audio-related bindings were observed:

- `8-0042`, name `fsa4480-i2c`, compatible `qcom,fsa4480-i2c`, bound to
  `fsa4480-driver`. Analog accessory routing was not exercised.
- `6-0064`, name/compatible `rtc6226`, bound to `rtc6226`; `radio0` is named
  `rtc6226-fmtuner`. No tuner command, reception or audio routing was tested.

These interfaces do not establish usable external audio, FM reception,
accessory detection or coexistence.

## Collection boundaries and use in acceptance

The collector used fixed whitelists for DT identity properties, sysfs names and
binding symlinks, plus ALSA card/PCM names. The two fixed `dumpsys` commands
ran with bounded output and time. Their raw text was filtered only in process
memory. The exported JSON contains a static Sensor List and five allowlisted
camera-characteristic tags per device, counts and static facing/orientation.
It contains no app/package/client list, camera activity history, sensor event
log, audio-client status or raw service dump. Only the sanitized JSON was
hashed/compressed for transfer.

An initial bounded DT selection reached its node limit because pinctrl labels
matched camera names. The final collector restricts DT retention to matching
**compatible-bearing device declarations** and completed its scan within the
bound. The original service logs were not retained during either passive run.
The final evidence file above is the actual output of the final collector.

No stream was started, no device-node data was read, and no hardware-control,
power, calibration, tracing or SELinux setting was changed. The only Android
files created for this task were the new collector helpers in the existing
research directory. In particular, CTN730 command/test attributes and
`wakeup_count` were not read.

For SYS-02, this capture strengthens the owner baseline for sensor-family
descriptors, camera roles and a small static capability subset, ALSA routing
names and amplifier driver bindings. It leaves exact camera parts,
amplifier/codec revision and acoustic variant, microphone identities, complete
stream modes and the remaining board inventory open. All dynamic Android
baselines and native Linux acceptance cases remain separate and unpassed.
