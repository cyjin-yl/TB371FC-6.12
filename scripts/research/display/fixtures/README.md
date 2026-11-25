# Pinned Tianma lifecycle regression inputs

These are source fixtures, not target-execution evidence.

- `linux-v6.12.114-drm_panel.c` is the complete, unchanged
  [upstream Linux v6.12.114 file](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/drm_panel.c),
  Git blob `fd8fa2e0ef6fac9f201d74baf838f09564b05680`,
  SHA-256 `b6deca77d92c2395952114154dd1674e9ee812064318d9a1b15ccb7113588d5a`.
  Its original NVIDIA copyright and permissive license are retained.
  The harness extracts the actual `drm_panel_prepare`, `drm_panel_unprepare`,
  `drm_panel_enable` and `drm_panel_disable` function definitions.
- `tianma-off-pr18-0acacec1.patch` is the unchanged
  [initial PR18 candidate](https://github.com/cyjin-yl/TB371FC-6.12/blob/0acacec10d2864dca3fc44f57d27b853493363f9/mainline-port/backports/linux-6.12/0022-drm-panel-tb371fc-tianma-off-sequence.patch),
  Git blob `97acbf4ffb143743de9cfb1dcf7fbcdd0473f78e`,
  SHA-256 `13debad44edec82adf21f864e1512302da1612642f0024bf293c3417987e5913`.
  It preserves the concrete negative control for a transport error leaving
  `panel->enabled` set across a full power cycle.

The test rejects source identity changes. To bind a local kernel source tree
to the same gate, pass
`--drm-panel-source /path/to/linux/drivers/gpu/drm/drm_panel.c`.
Only the state-handling functions are real kernel code in this host harness:
DSI transport, waits, GPIO/regulator preparation and backlight side effects
remain deterministic mocks. A passing harness is not a kernel build or
physical display/suspend result.
