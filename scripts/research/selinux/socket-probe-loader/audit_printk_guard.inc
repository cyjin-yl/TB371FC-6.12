/*
 * This explicit generic-VM observation path changes only the shared printk
 * interval. It does not change audit admission, queues, backlog, or enforcing.
 * No policy API has been called at this point. All input paths are fixed.
 */
#define AUDIT_PRINTK_INTERVAL "/proc/sys/kernel/printk_ratelimit"
#define AUDIT_PRINTK_BURST "/proc/sys/kernel/printk_ratelimit_burst"
#define AUDIT_PRINTK_OPT_IN "rd.tb371fc.audit-printk-unlimited=1"
#define AUDIT_PRINTK_OPT_KEY "rd.tb371fc.audit-printk-unlimited"

static void audit_guard_require(bool condition, const char *reason)
{
        if (!condition) {
                errno = EINVAL;
                fail(reason);
        }
}

static void audit_guard_check_fd(int fd, unsigned long magic)
{
        struct stat st;
        struct statfs fs;
        if (fstat(fd, &st) < 0 || fstatfs(fd, &fs) < 0)
                fail("audit-observation-file-stat");
        audit_guard_require(S_ISREG(st.st_mode) && st.st_uid == 0 &&
                            (unsigned long)fs.f_type == magic,
                            "audit-observation-file-type");
}

static size_t audit_guard_read(const char *path, unsigned long magic,
                              char *buffer, size_t capacity)
{
        size_t used = 0;
        unsigned calls = 0;
        int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                fail("audit-observation-file-open");
        audit_guard_check_fd(fd, magic);
        for (;;) {
                ssize_t n;
                audit_guard_require(used < capacity && ++calls <= 16,
                                    "audit-observation-read-bound");
                n = read(fd, buffer + used, capacity - used);
                if (n < 0 && errno == EINTR)
                        continue;
                if (n < 0)
                        fail("audit-observation-file-read");
                if (n == 0)
                        break;
                used += (size_t)n;
        }
        if (close(fd) < 0)
                fail("audit-observation-file-close");
        return used;
}

static unsigned audit_guard_read_uint(const char *path)
{
        char text[64];
        unsigned value = 0;
        size_t n = audit_guard_read(path, PROC_SUPER_MAGIC, text, sizeof(text));
        audit_guard_require(n >= 2 && text[n - 1] == '\n',
                            "audit-observation-integer-format");
        for (size_t i = 0; i + 1 < n; i++) {
                unsigned digit;
                audit_guard_require(text[i] >= '0' && text[i] <= '9',
                                    "audit-observation-integer-digit");
                digit = (unsigned)(text[i] - '0');
                audit_guard_require(value <= ((unsigned)INT_MAX - digit) / 10,
                                    "audit-observation-integer-range");
                value = value * 10 + digit;
        }
        return value;
}

static void audit_guard_check_opt_in(void)
{
        char text[16384], *save = NULL, *word;
        unsigned count = 0;
        size_t n = audit_guard_read("/proc/cmdline", PROC_SUPER_MAGIC,
                                   text, sizeof(text) - 1);
        audit_guard_require(!memchr(text, '\0', n),
                            "audit-observation-command-line-nul");
        text[n] = '\0';
        for (word = strtok_r(text, " \t\r\n", &save); word;
             word = strtok_r(NULL, " \t\r\n", &save)) {
                size_t key_size = sizeof(AUDIT_PRINTK_OPT_KEY) - 1;
                if (strncmp(word, AUDIT_PRINTK_OPT_KEY, key_size) == 0 &&
                    (word[key_size] == '=' || word[key_size] == '\0')) {
                        audit_guard_require(strcmp(word, AUDIT_PRINTK_OPT_IN) == 0,
                                            "audit-observation-invalid-opt-in");
                        count++;
                }
        }
        audit_guard_require(count == 1, "audit-observation-unique-opt-in-required");
}

static void audit_guard_check_virtual_hardware(void)
{
        char compatible[4096];
        unsigned matches = 0;
        size_t n = audit_guard_read("/sys/firmware/devicetree/base/compatible",
                                   SYSFS_MAGIC, compatible, sizeof(compatible));
        audit_guard_require(n > 0 && compatible[n - 1] == '\0',
                            "audit-observation-compatible-format");
        for (size_t offset = 0; offset < n;) {
                const char *end = memchr(compatible + offset, '\0', n - offset);
                size_t size;
                audit_guard_require(end != NULL && end != compatible + offset,
                                    "audit-observation-compatible-entry");
                size = (size_t)(end - (compatible + offset));
                if (size == sizeof("linux,dummy-virt") - 1 &&
                    memcmp(compatible + offset, "linux,dummy-virt", size) == 0)
                        matches++;
                offset += size + 1;
        }
        audit_guard_require(matches == 1, "audit-observation-generic-vm-required");
}

static void audit_guard_set_zero_interval(void)
{
        static const char value[] = "0\n";
        unsigned attempts = 0;
        ssize_t n;
        int fd = open(AUDIT_PRINTK_INTERVAL, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                fail("audit-observation-interval-open");
        audit_guard_check_fd(fd, PROC_SUPER_MAGIC);
        do {
                audit_guard_require(++attempts <= 4, "audit-observation-write-bound");
                n = write(fd, value, sizeof(value) - 1);
        } while (n < 0 && errno == EINTR);
        if (n < 0)
                fail("audit-observation-interval-write");
        /* A short write is a failure; never continue a proc-sysctl write at a
         * nonzero offset or turn an incomplete operation into success. */
        audit_guard_require(n == (ssize_t)(sizeof(value) - 1),
                            "audit-observation-short-write");
        if (close(fd) < 0)
                fail("audit-observation-interval-close");
}

static void configure_vm_audit_printk_observation(void)
{
        unsigned before, after, burst_before, burst_after;
        phase = "audit-printk-opt-in";
        audit_guard_require(getpid() == 1 && geteuid() == 0,
                            "audit-observation-root-pid1-required");
        audit_guard_check_opt_in();
        phase = "audit-printk-virtual-hardware";
        audit_guard_check_virtual_hardware();
        phase = "audit-printk-observability";
        before = audit_guard_read_uint(AUDIT_PRINTK_INTERVAL);
        burst_before = audit_guard_read_uint(AUDIT_PRINTK_BURST);
        audit_guard_set_zero_interval();
        /* Each reader opens its fixed node afresh, at offset zero. */
        after = audit_guard_read_uint(AUDIT_PRINTK_INTERVAL);
        burst_after = audit_guard_read_uint(AUDIT_PRINTK_BURST);
        audit_guard_require(after == 0 && burst_after == burst_before,
                            "audit-observation-readback-mismatch");
        if (fprintf(stderr, MARKER " AUDIT_PRINTK_UNLIMITED scope=generic-vm "
                    "opt_in=1 compatible=linux,dummy-virt before=%u after=%u "
                    "burst_before=%u burst_after=%u policy_load_attempted=0\n",
                    before, after, burst_before, burst_after) < 0 ||
            fflush(stderr) != 0)
                fail("audit-observation-marker-output");
}

