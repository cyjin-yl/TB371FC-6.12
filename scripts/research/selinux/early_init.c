/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Research-only initramfs PID 1 bootstrap. Use the unmodified Fedora libselinux
 * APIs in one process: loading the policy must not be followed by exec of an
 * executable which still has the initramfs root_t label.
 *
 * No policy editor, setcon, setenforce, shell, alternate command, or owner-tablet
 * boot operation is implemented here. The independent VM recipe supplies the
 * fixed policy, contexts and complete shared-library closure.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <selinux/label.h>
#include <selinux/restorecon.h>
#include <selinux/selinux.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

#define MARKER "TB371FC_EARLY_SELINUX_V1"
#define SYSTEMD "/usr/lib/systemd/systemd"
#define UDEVADM "/usr/bin/udevadm"
#define POLICY_CONFIG "/etc/selinux/config"
#define SELINUX_MOUNT "/sys/fs/selinux"
#define POLICY_FILE "/etc/selinux/targeted/policy/policy.35"
#define LIBSELINUX "/usr/lib64/libselinux.so.1"

static const char *phase = "entry";

struct selinux_api {
        void *handle;
        __typeof__(selinux_init_load_policy) *load_policy;
        __typeof__(selinux_restorecon) *restorecon;
        __typeof__(selinux_restorecon_default_handle) *default_handle;
        __typeof__(selinux_restorecon_set_sehandle) *set_handle;
        __typeof__(selabel_lookup_raw) *lookup;
        __typeof__(getcon_raw) *getcon;
        __typeof__(getfilecon_raw) *filecon;
        __typeof__(freecon) *freecon;
        __typeof__(security_getenforce) *getenforce;
};

static _Noreturn void fail(const char *reason)
{
        int saved = errno;
        fprintf(stderr, MARKER " FAILED phase=%s reason=%s errno=%d\n",
                phase, reason, saved);
        fflush(NULL);
        /* PID 1 exiting is an explicit failed boot. The VM harness preserves
         * its serial log; there is no continuation or success fallback. */
        _exit(EXIT_FAILURE);
}

static void load_api(struct selinux_api *api)
{
        phase = "load-library";
        api->handle = dlopen(LIBSELINUX, RTLD_NOW | RTLD_LOCAL);
        if (!api->handle)
                fail("libselinux-unavailable");

#define LOAD_API(field, symbol) do {                                      \
        void *address = dlsym(api->handle, #symbol);                      \
        _Static_assert(sizeof(api->field) == sizeof(address),            \
                       "POSIX function pointer size");                  \
        if (!address)                                                   \
                fail("missing-" #symbol);                               \
        memcpy(&api->field, &address, sizeof(address));                   \
} while (0)
        LOAD_API(load_policy, selinux_init_load_policy);
        LOAD_API(restorecon, selinux_restorecon);
        LOAD_API(default_handle, selinux_restorecon_default_handle);
        LOAD_API(set_handle, selinux_restorecon_set_sehandle);
        LOAD_API(lookup, selabel_lookup_raw);
        LOAD_API(getcon, getcon_raw);
        LOAD_API(filecon, getfilecon_raw);
        LOAD_API(freecon, freecon);
        LOAD_API(getenforce, security_getenforce);
#undef LOAD_API
}

static void ensure_directory(const char *path)
{
        struct stat st;
        if (mkdir(path, 0755) < 0 && errno != EEXIST)
                fail("api-directory-create");
        if (lstat(path, &st) < 0 || !S_ISDIR(st.st_mode))
                fail("api-directory-type");
}

static void mount_api(const char *name, const char *path, unsigned long flags,
                      const char *options, unsigned long magic)
{
        struct statfs st;
        ensure_directory(path);
        if (mount(name, path, name, flags, options) < 0 && errno != EBUSY)
                fail("api-mount");
        if (statfs(path, &st) < 0 || (unsigned long)st.f_type != magic)
                fail("api-filesystem-type");
}

static void read_text(const char *path, char *buffer, size_t capacity)
{
        struct stat st;
        size_t used = 0;
        int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                fail("required-file-open");
        if (fstat(fd, &st) < 0 || !S_ISREG(st.st_mode))
                fail("required-file-type");
        for (;;) {
                ssize_t n;
                if (used == capacity - 1)
                        fail("required-file-too-large");
                n = read(fd, buffer + used, capacity - 1 - used);
                if (n < 0 && errno == EINTR)
                        continue;
                if (n < 0)
                        fail("required-file-read");
                if (n == 0)
                        break;
                used += (size_t)n;
        }
        if (close(fd) < 0)
                fail("required-file-close");
        if (memchr(buffer, '\0', used))
                fail("required-file-embedded-nul");
        buffer[used] = '\0';
}

static void check_cmdline(void)
{
        char text[16384], *save = NULL, *word;
        bool enforcing = false, opted_in = false;
        phase = "command-line";
        read_text("/proc/cmdline", text, sizeof(text));
        for (word = strtok_r(text, " \t\r\n", &save); word;
             word = strtok_r(NULL, " \t\r\n", &save)) {
                if (strncmp(word, "enforcing=", 10) == 0) {
                        if (strcmp(word, "enforcing=1") != 0)
                                fail("non-enforcing-command-line");
                        enforcing = true;
                }
                if (strncmp(word, "selinux=", 8) == 0 &&
                    strcmp(word, "selinux=1") != 0)
                        fail("selinux-disable-command-line");
                if (strcmp(word, "rd.tb371fc.early-selinux=1") == 0)
                        opted_in = true;
        }
        if (!enforcing || !opted_in)
                fail("explicit-early-enforcing-opt-in-required");
}

static char *trim(char *text)
{
        char *end;
        while (isspace((unsigned char)*text))
                text++;
        end = text + strlen(text);
        while (end > text && isspace((unsigned char)end[-1]))
                *--end = '\0';
        return text;
}

static void check_policy_config(void)
{
        char text[16384], *save = NULL, *line;
        unsigned enforcing = 0, targeted = 0;
        struct stat st;
        phase = "policy-config";
        read_text(POLICY_CONFIG, text, sizeof(text));
        for (line = strtok_r(text, "\n", &save); line;
             line = strtok_r(NULL, "\n", &save)) {
                char *key = trim(line), *equal, *value;
                if (!*key || *key == '#')
                        continue;
                equal = strchr(key, '=');
                if (!equal)
                        continue;
                *equal = '\0';
                value = trim(equal + 1);
                key = trim(key);
                if (strcmp(key, "SELINUX") == 0) {
                        if (strcmp(value, "enforcing") != 0)
                                fail("non-enforcing-config");
                        enforcing++;
                } else if (strcmp(key, "SELINUXTYPE") == 0) {
                        if (strcmp(value, "targeted") != 0)
                                fail("unexpected-policy-type");
                        targeted++;
                }
        }
        if (enforcing != 1 || targeted != 1)
                fail("ambiguous-policy-config");
        if (lstat(POLICY_FILE, &st) < 0 || !S_ISREG(st.st_mode) ||
            st.st_size != 3835432)
                fail("expected-policy-file-missing");
}

static bool context_has_type(const char *context, const char *type)
{
        const char *first, *second, *end;
        if (!context || !(first = strchr(context, ':')) ||
            !(second = strchr(first + 1, ':')) ||
            !(end = strchr(second + 1, ':')))
                return false;
        return (size_t)(end - second - 1) == strlen(type) &&
               memcmp(second + 1, type, strlen(type)) == 0;
}

static void check_file_label(struct selinux_api *api,
                             struct selabel_handle *labels,
                             const char *path, const char *type, bool actual)
{
        char *context = NULL;
        int rc = actual ? api->filecon(path, &context) :
                          api->lookup(labels, &context, path, S_IFREG);
        if (rc < 0 || !context_has_type(context, type))
                fail(actual ? "unexpected-actual-file-label" :
                              "unexpected-file-context-specification");
        if (actual)
                fprintf(stderr, MARKER " file=%s context=%s\n", path, context);
        api->freecon(context);
}

int main(int argc, char **argv)
{
        struct selinux_api api = {0};
        struct selabel_handle *labels;
        char *context = NULL;
        int enforcing = 0;
        const unsigned flags = SELINUX_RESTORECON_SET_SPECFILE_CTX |
                               SELINUX_RESTORECON_RECURSE |
                               SELINUX_RESTORECON_XDEV |
                               SELINUX_RESTORECON_ABORT_ON_ERROR |
                               SELINUX_RESTORECON_SKIP_DIGEST;

        /* This mode only resolves library symbols. It neither calls a policy
         * API nor mounts anything and is deliberately unavailable to PID 1. */
        if (getpid() != 1 && argc == 2 && strcmp(argv[1], "--check-api") == 0) {
                load_api(&api);
                printf(MARKER " API_ONLY flags=0x%x policy_load_attempted=0\n", flags);
                dlclose(api.handle);
                return EXIT_SUCCESS;
        }
        if (getpid() != 1 || argc != 1)
                fail("pid1-with-no-arguments-required");
        phase = "mount-proc";
        mount_api("proc", "/proc", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                  NULL, PROC_SUPER_MAGIC);
        check_cmdline();
        check_policy_config();
        phase = "mount-sysfs";
        mount_api("sysfs", "/sys", MS_NOSUID | MS_NODEV | MS_NOEXEC,
                  NULL, SYSFS_MAGIC);
        phase = "mount-devtmpfs";
        mount_api("devtmpfs", "/dev", MS_NOSUID | MS_STRICTATIME,
                  "mode=0755", TMPFS_MAGIC);
        phase = "mount-selinuxfs";
        /* Match libselinux: no MS_NODEV, because selinuxfs has a null device. */
        mount_api("selinuxfs", SELINUX_MOUNT, MS_NOSUID | MS_NOEXEC,
                  NULL, SELINUX_MAGIC);
        load_api(&api);
        phase = "initial-security-state";
        if (api.getenforce() != 1 || api.getcon(&context) < 0 ||
            !context || strcmp(context, "kernel") != 0)
                fail("expected-initial-kernel-context-and-enforcing");
        api.freecon(context);
        context = NULL;
        phase = "file-context-handle";
        labels = api.default_handle();
        if (!labels)
                fail("file-context-handle-unavailable");
        check_file_label(&api, labels, SYSTEMD, "init_exec_t", false);
        check_file_label(&api, labels, UDEVADM, "udev_exec_t", false);
        api.set_handle(labels);
        phase = "load-policy";
        if (api.load_policy(&enforcing) != 0 || enforcing != 1 ||
            api.getenforce() != 1)
                fail("standard-policy-load-failed-or-not-enforcing");
        if (api.getcon(&context) < 0 || !context_has_type(context, "kernel_t"))
                fail("unexpected-post-load-bootstrap-domain");
        fprintf(stderr, MARKER " POLICY_LOADED enforcing=1 context=%s\n", context);
        api.freecon(context);
        phase = "restore-initramfs-contexts";
        /* No child process is exec'd between policy loading and this call.
         * XDEV confines the recursive walk to the initramfs; no ignored-error
         * mode or label-digest cache can turn a skipped relabel into success. */
        if (api.restorecon("/", flags) != 0)
                fail("initramfs-relabel-failed");
        check_file_label(&api, labels, SYSTEMD, "init_exec_t", true);
        check_file_label(&api, labels, UDEVADM, "udev_exec_t", true);
        if (api.getenforce() != 1)
                fail("enforcing-state-changed");
        phase = "exec-systemd";
        fprintf(stderr, MARKER " EXEC_SYSTEMD enforcing=1 flags=0x%x\n", flags);
        fflush(NULL);
        char *const next_argv[] = {SYSTEMD, NULL};
        execv(SYSTEMD, next_argv);
        fail("systemd-exec-failed");
}
