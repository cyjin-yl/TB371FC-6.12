# Tianma OFF: preserve recovery across a failed disable

Date: 2026-11-26 (Asia/Shanghai); host execution on 2026-11-25 UTC.
This updates the candidate introduced by PR18 at
`0acacec10d2864dca3fc44f57d27b853493363f9`.

## Correct the real DRM caller contract

The initial candidate accurately expressed the captured HS OFF table and
retained the first transfer error, but returned that error from the panel's
`.disable` callback. That is unsafe with the selected Linux 6.12.114
lifecycle:

1. [`drm_panel_disable()`](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/drm_panel.c)
   disables the backlight, calls the panel callback, and returns immediately
   on a negative callback result. Its subsequent `panel->enabled = false`
   is skipped.
2. The project's
   [panel bridge](../../../mainline-port/backports/linux-6.12/drm-panel-bridge.c)
   ignores that return value in `panel_bridge_atomic_disable()`.
   `panel_bridge_atomic_post_disable()` still calls `drm_panel_unprepare()`;
   the driver resets the panel and disables its regulator.
3. The next prepare powers and initializes the panel again, but
   `drm_panel_enable()` sees the stale `enabled = true` and returns early.
   It skips `backlight_enable()`, leaving the backlight disabled.

The [corrected patch](../../../mainline-port/backports/linux-6.12/0022-drm-panel-tb371fc-tianma-off-sequence.patch)
retains the first error inside the sequence helper. The Tianma disable
callback reports that error and returns zero after both phases and waits,
allowing the core to complete its state transition before normal unprepare.
The underlying DSI multi helpers already log individual failed commands;
the callback adds a first-error summary. Returning zero here means the
best-effort disable lifecycle completed, not that the panel received every
command. It does not introduce a device retry or claim a physical OFF pass.

The HS request, 15 ms / 60 ms requested waits, first-error retention in the
helper, preservation/restoration of other device flags and unchanged
BOE/single-link paths are retained. The frozen R5 recipe and artifacts are
not changed.

## API calls are not independent physical-link transfers

The board DTS selects `qcom,dual-dsi-mode` and `qcom,sync-dual-dsi`. In
[Linux 6.12's MSM manager](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/msm/dsi/dsi_manager.c),
a synchronized write through DSI0 returns the payload length without issuing
the transfer. DSI1 prepares both hosts and triggers both links using its
message. Therefore the harness's four fault positions are four panel-to-DSI
API calls, not four independent physical-link transactions or a guarantee
that one surviving link can always be driven after the other fails.

[`mipi_dsi_device_transfer()`](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/drm_mipi_dsi.c)
maps the device's LPM bit into the outgoing message.
[MSM host preparation](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/msm/dsi/dsi_host.c)
uses that message flag for the transmission's power mode. Clearing LPM
around each API call thus requests HS for the DSI1 message used to prepare
both hosts. Restoring DSI0's device flag before DSI1 does not turn the latter
message into an LP request. This is source-level reasoning; on-wire mode,
timing and synchronization still need target observation.

## Regression with actual Linux panel-core code

The [host harness](../../../scripts/research/display/test_tianma_off.py)
compiles the actual OFF functions extracted after zero-fuzz patch
application. It also extracts the unchanged `drm_panel_prepare()`,
`drm_panel_unprepare()`, `drm_panel_enable()` and `drm_panel_disable()`
definitions from the complete
[pinned upstream 6.12.114 source fixture](../../../scripts/research/display/fixtures/linux-v6.12.114-drm_panel.c).
It does not replace those four functions with a model. DSI transfer, delays,
power callbacks and backlight side effects remain deterministic host mocks.

The regression covers 16 transfer-fault masks at the helper boundary, all
16 masks through disable → unprepare → prepare → enable, and two legacy
panel cases. Every nonzero mask verifies that the callback reports the
first error while the core clears `enabled` and actually invokes the
backlight's enable operation after the full cycle.

An unchanged
[copy of the first PR18 patch](../../../scripts/research/display/fixtures/tianma-off-pr18-0acacec1.patch)
is a second negative control. It reproduces the stale-enabled and skipped
backlight behavior for all 15 nonzero masks. The unchanged pre-PR18 panel
source remains the first negative control for the missing staged HS
sequence. The original November 24 evidence index and log digests are
unchanged; the new tests do not reinterpret those old host-only results.

Actual execution in the x86_64 coding workspace used GCC 14.2.0, Python
3.12.14 and UBSan with recovery disabled:

| Input | Wrapper exit | Compiled harness exit | Result |
| --- | ---: | ---: | --- |
| Original unpatched panel | 0 | 1 | Expected rejection; 239 failed predicates in the expanded harness |
| Initial PR18 patch | 0 | 1 | Expected lifecycle rejection; 60 failed predicates, including the stale-enabled/backlight counterexample |
| Corrected candidate | 0 | 0 | All 34 cases passed |

The [source identity manifest](evidence/tianma-off-lifecycle/source-identities.json)
and [execution receipt](evidence/tianma-off-lifecycle/result.json) retain
the exact inputs, commands and full wrapper stdout/stderr files, with
byte lengths and SHA-256 hashes. These are new execution records.
The harness also accepts
`--drm-panel-source /path/to/linux/drivers/gpu/drm/drm_panel.c` to verify
the same upstream bytes in the actual build tree.

This receipt establishes the host lifecycle regression only. The completed
[fresh ARM64 build and 84 offline module-signature checks](tianma-r6-build.md)
have their own later source/artifact receipts. Actual bonded transport,
panel-off, suspend/resume and power-failure recovery remain unverified.
Owner-native passes added: zero.
