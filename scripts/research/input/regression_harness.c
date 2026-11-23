/* SPDX-License-Identifier: GPL-2.0-only */
/* Kernel boundary stubs; function bodies are inserted from the prepared tree. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#define MT_PROTOCOL_B 1
#define NVT_TOUCH_ESD_PROTECT 1
#define NVT_TOUCH_SUPPORT_HW_RST 1
#define NVT_TOUCH_ESD_CHECK_PERIOD 1500
#define NVT_IC_SUSPEND_IN 0
#define NVT_IC_SUSPEND_OUT 1
#define NVT_IC_RESUME_IN 2
#define NVT_IC_RESUME_OUT 3
#define RESET_STATE_REK 0xa1
#define EVENT_MAP_HOST_CMD 0x50
#define ABS_MT_TOUCH_MAJOR 1
#define ABS_MT_PRESSURE 2
#define BTN_TOUCH 3
#define MT_TOOL_FINGER 4
#define EPROBE_DEFER 517
#define NVT_LOG(...) ((void)0)
#define NVT_ERR(...) ((void)0)
#define dev_warn(...) ((void)0)
#define DIV_ROUND_CLOSEST(n, d) (((n) + (d) / 2) / (d))
typedef uint32_t u32;

struct device { bool x, y; u32 width, height; int read_error; };
struct spi_device { int irq; struct device dev; };
struct input_dev { int min[4], max[4], res[4]; };
struct memmap { unsigned int EVENT_BUF_ADDR; };
struct nvt_ts_data {
    struct spi_device *client;
    struct input_dev *input_dev;
    struct memmap *mmap;
    int lock, ic_state, db_wakeup, reset_gpio, gesture_command_delayed;
    unsigned int max_touch_num;
    bool irq_enabled, irq_wake_enabled, pen_support, pen_input_dev_enable;
    u32 width_mm, height_mm;
    const char *fw_name;
    bool hw_crc;
};
static struct nvt_ts_data state, *ts = &state;
static struct spi_device client;
static struct input_dev input;
static struct memmap map = { .EVENT_BUF_ADDR = 0x2000 };
static unsigned char bTouchIsAwake;
static int nvt_esd_check_work, nvt_esd_check_wq;
static int mutex_depth, pm_holds, irq_enable_calls, irq_disable_calls;
static int wake_on_calls, wake_off_calls, wake_on_error, wake_off_error;
static int fw_error, fw_calls, reset_error, reset_calls, pen_error, pen_calls;
static int spi_error, page_error, queue_calls, cancel_calls, pen_release_calls;
static bool fail_pen_enable_only;

static int dev_err_probe(struct device *dev, int err, const char *msg) { return err; }
static bool device_property_present(struct device *dev, const char *key) { return key[12] == 'x' ? dev->x : dev->y; }
static int device_property_read_u32(struct device *dev, const char *key, u32 *out) {
    if (dev->read_error) return dev->read_error;
    *out = key[12] == 'x' ? dev->width : dev->height; return 0;
}
static int input_abs_get_max(struct input_dev *in, unsigned int axis) { return in->max[axis]; }
static int input_abs_get_min(struct input_dev *in, unsigned int axis) { return in->min[axis]; }
static void input_abs_set_res(struct input_dev *in, unsigned int axis, int res) { in->res[axis] = res; }
static void enable_irq(int irq) { assert(mutex_depth == 0); irq_enable_calls++; }
static void disable_irq(int irq) { assert(mutex_depth == 0); irq_disable_calls++; }
static int enable_irq_wake(int irq) { wake_on_calls++; return wake_on_error; }
static int disable_irq_wake(int irq) { wake_off_calls++; return wake_off_error; }
static void mutex_lock(int *lock) { assert(mutex_depth++ == 0); }
static void mutex_unlock(int *lock) { assert(--mutex_depth == 0); }
static void pm_stay_awake(struct device *dev) { pm_holds++; }
static void pm_relax(struct device *dev) { assert(--pm_holds == 0); }
static void cancel_delayed_work_sync(int *work) { cancel_calls++; }
static void nvt_esd_check_enable(bool on) { }
static int msecs_to_jiffies(int ms) { return ms; }
static void queue_delayed_work(int queue, int *work, int delay) { queue_calls++; }
static void gpiod_set_value_cansleep(int gpio, int value) { }
static int mock_update_firmware(const char *name) { fw_calls++; return fw_error; }
static int nvt_check_fw_reset_state(int value) { reset_calls++; return reset_error; }
static int disable_pen_input_device(bool disable) {
    assert(bTouchIsAwake); pen_calls++;
    return fail_pen_enable_only && disable ? 0 : pen_error;
}
static int nvt_set_page(unsigned int page) { return page_error; }
static int CTP_SPI_WRITE(struct spi_device *spi, uint8_t *buf, unsigned int size) { return spi_error; }
static void input_mt_slot(struct input_dev *dev, unsigned int slot) { }
static void input_report_abs(struct input_dev *dev, int code, int val) { }
static void input_mt_report_slot_state(struct input_dev *dev, int tool, int val) { }
static void input_report_key(struct input_dev *dev, int key, int val) { }
static void input_sync(struct input_dev *dev) { }
static void msleep(int ms) { }
static void release_pen_event(void) { pen_release_calls++; }

#define nvt_update_firmware mock_update_firmware
/* INSERT_ACTUAL_DRIVER_FUNCTIONS */
#undef nvt_update_firmware

static void clear_state(void) {
    memset(&state, 0, sizeof(state)); memset(&client, 0, sizeof(client));
    memset(&input, 0, sizeof(input));
    state.client = &client; state.input_dev = &input; state.mmap = &map;
    state.gesture_command_delayed = -1; state.pen_support = true;
    state.pen_input_dev_enable = true; state.max_touch_num = 10;
    bTouchIsAwake = 0; mutex_depth = 0; pm_holds = 0;
    irq_enable_calls = irq_disable_calls = wake_on_calls = wake_off_calls = 0;
    wake_on_error = wake_off_error = fw_error = fw_calls = reset_error = reset_calls = 0;
    pen_error = pen_calls = spi_error = page_error = queue_calls = cancel_calls = pen_release_calls = 0;
    fail_pen_enable_only = false;
}
static void pass(const char *name) { printf("PASS %s\n", name); }
static void check_failed_resume(int expected) {
    assert(nvt_ts_resume(&client.dev) == expected);
    assert(!bTouchIsAwake && !state.irq_enabled && !queue_calls);
    assert(!pm_holds && !mutex_depth);
}

struct firmware { int placeholder; };
static const struct firmware *fw_entry;
static void *bin_map, *fwbuf;
static size_t fw_need_write_size;
static int outstanding, request_error, init_error, download_error, info_error;
static void *alloc_one(void) { void *p = malloc(8); assert(p); outstanding++; return p; }
static void kfree(void *p) { if (p) { assert(outstanding > 0); outstanding--; free(p); } }
static void release_firmware(const struct firmware *fw) { kfree((void *)fw); }
static int update_firmware_request(const char *name) {
    if (request_error) return request_error;
    fw_entry = alloc_one(); bin_map = alloc_one(); fw_need_write_size = 4096; return 0;
}
static int nvt_download_init(void) { if (init_error) return init_error; fwbuf = alloc_one(); return 0; }
static int nvt_download_firmware_hw_crc(void) { return download_error; }
static int nvt_download_firmware(void) { return download_error; }
static int nvt_get_fw_info(void) { return info_error; }

/* INSERT_ACTUAL_FIRMWARE_FUNCTIONS */

int main(void) {
    clear_state(); input.max[0] = 18400; input.max[1] = 29440;
    assert(!nvt_parse_phys_size(&client.dev)); nvt_set_abs_resolution(&input, 0, 1);
    assert(!input.res[0] && !input.res[1]); pass("geometry_absent_is_unknown");
    client.dev.x = true; assert(nvt_parse_phys_size(&client.dev) == -EINVAL);
    pass("geometry_incomplete_rejected");
    client.dev.y = true; client.dev.width = 0; client.dev.height = 320;
    assert(nvt_parse_phys_size(&client.dev) == -EINVAL); pass("geometry_zero_rejected");
    client.dev.read_error = -EPROTO; assert(nvt_parse_phys_size(&client.dev) == -EPROTO);
    pass("geometry_read_error_preserved");
    client.dev.read_error = 0; client.dev.width = 200;
    assert(!nvt_parse_phys_size(&client.dev)); nvt_set_abs_resolution(&input, 0, 1);
    assert(input.res[0] == 92 && input.res[1] == 92); pass("geometry_declared_axes_counts_per_mm");

    clear_state(); assert(!nvt_irq_set_wake(true)); assert(!nvt_irq_set_wake(true));
    assert(wake_on_calls == 1 && state.irq_wake_enabled);
    assert(!nvt_irq_set_wake(false)); assert(!nvt_irq_set_wake(false));
    assert(wake_off_calls == 1 && !state.irq_wake_enabled); pass("irq_wake_ownership_balanced_idempotent");
    clear_state(); wake_on_error = -EINVAL; assert(nvt_irq_set_wake(true) == -EINVAL);
    assert(!state.irq_wake_enabled); pass("irq_wake_enable_failure_preserved");

    clear_state(); fw_error = -ENOENT; check_failed_resume(-ENOENT);
    assert(fw_calls == 1 && !reset_calls && !pen_calls); pass("resume_missing_firmware_fails_quiescent");
    clear_state(); reset_error = -ETIMEDOUT; check_failed_resume(-ETIMEDOUT);
    assert(reset_calls == 1 && !pen_calls); pass("resume_reset_failure_fails_quiescent");
    clear_state(); pen_error = -EIO; check_failed_resume(-EIO);
    assert(pen_calls == 1); pass("resume_pen_error_rolls_back_awake");
    clear_state(); state.irq_wake_enabled = true; state.irq_enabled = true;
    wake_off_error = -EBUSY; check_failed_resume(-EBUSY);
    assert(state.irq_wake_enabled && !fw_calls); pass("resume_wake_disarm_failure_not_hidden");
    clear_state(); state.irq_wake_enabled = true; state.irq_enabled = true;
    assert(!nvt_ts_resume(&client.dev));
    assert(bTouchIsAwake && state.irq_enabled && !state.irq_wake_enabled);
    assert(queue_calls == 1 && wake_off_calls == 1 && !pm_holds && !mutex_depth);
    pass("resume_success_disarms_wake_then_reenables_irq");
    clear_state(); fw_error = -EIO; check_failed_resume(-EIO); fw_error = 0;
    assert(!nvt_ts_resume(&client.dev)); assert(bTouchIsAwake && state.irq_enabled);
    pass("failed_resume_can_be_retried");

    clear_state(); bTouchIsAwake = 1; state.irq_enabled = true; spi_error = -EIO;
    assert(nvt_ts_suspend(&client.dev) == -EIO);
    assert(bTouchIsAwake && state.irq_enabled && queue_calls == 1 && pen_calls == 2);
    assert(!state.irq_wake_enabled && !pm_holds && !mutex_depth);
    pass("suspend_spi_failure_restores_active_state");
    clear_state(); bTouchIsAwake = 1; state.irq_enabled = true; state.db_wakeup = 1;
    wake_on_error = -EINVAL; assert(nvt_ts_suspend(&client.dev) == -EINVAL);
    assert(bTouchIsAwake && state.irq_enabled && !state.irq_wake_enabled);
    pass("suspend_wake_failure_returns_error");
    clear_state(); bTouchIsAwake = 1; state.irq_enabled = true;
    assert(!nvt_ts_suspend(&client.dev));
    assert(!bTouchIsAwake && !state.irq_enabled && !queue_calls && pen_release_calls == 1);
    assert(!pm_holds && !mutex_depth); pass("suspend_deep_sleep_success_quiesces_irq");
    clear_state(); bTouchIsAwake = 1; state.irq_enabled = true; state.db_wakeup = 1;
    assert(!nvt_ts_suspend(&client.dev));
    assert(!bTouchIsAwake && state.irq_enabled && state.irq_wake_enabled);
    assert(!nvt_ts_resume(&client.dev)); assert(wake_on_calls == wake_off_calls);
    pass("suspend_resume_wake_pair_balanced");

    for (int failure = 0; failure < 5; failure++) {
        request_error = failure == 1 ? -ENOENT : 0;
        init_error = failure == 2 ? -ENOMEM : 0;
        download_error = failure == 3 ? -EIO : 0;
        info_error = failure == 4 ? -EPROTO : 0;
        int expected = request_error ?: init_error ?: download_error ?: info_error;
        assert(nvt_update_firmware("test-only") == expected);
        assert(!outstanding && !fw_entry && !bin_map && !fwbuf && !fw_need_write_size);
    }
    pass("firmware_success_and_four_error_paths_release_all_resources");
    return 0;
}
