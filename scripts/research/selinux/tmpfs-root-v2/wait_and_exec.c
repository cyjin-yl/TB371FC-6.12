// SPDX-License-Identifier: GPL-2.0-only
//
// Pre-policy PID 1 continuation for the fixed util-linux switch_root.
// Reap its asynchronous old-root cleaner and prove the saved root is empty,
// then execute the separately pinned V3 native SELinux /init.
// This waiter validates shape and byte length, not a content hash.
// The independent archive/profile must pin both complete ELF hashes.
// No policy operation, mount operation, file-tree deletion or alternate
// executable is implemented here.
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/sysmacros.h>
#include <sys/vfs.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MARKER "TB371FC_TMPFS_STAGE1_V2"
#define OLD_ROOT_FD 3
#define CLEANUP_TIMEOUT_NS (UINT64_C(30) * UINT64_C(1000000000))
#define HELPER "/init"
#define HELPER_SIZE 72528

static const char *phase = "entry";

static _Noreturn void fail(const char *reason)
{
        int saved = errno;
        fprintf(stderr, MARKER " FAILED phase=%s reason=%s errno=%d\n",
                phase, reason, saved);
        fflush(NULL);
        _exit(EXIT_FAILURE);
}

static uint64_t monotonic_ns(void)
{
        struct timespec value;
        if (clock_gettime(CLOCK_MONOTONIC, &value) < 0)
                fail("monotonic-clock");
        return (uint64_t)value.tv_sec * UINT64_C(1000000000) +
               (uint64_t)value.tv_nsec;
}

static void require_initial_context(void)
{
        char text[32] = {0};
        size_t used = 0;
        int fd = open("/proc/self/attr/current", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                fail("initial-context-open");
        while (used < sizeof(text)) {
                ssize_t count = read(fd, text + used, sizeof(text) - used);
                if (count < 0 && errno == EINTR)
                        continue;
                if (count < 0)
                        fail("initial-context-read");
                if (count == 0)
                        break;
                used += (size_t)count;
        }
        if (close(fd) < 0)
                fail("initial-context-close");
        if (used == sizeof(text))
                fail("initial-context-bound");
        while (used && (text[used - 1] == '\0' || text[used - 1] == '\n'))
                used--;
        if (used != 6 || memcmp(text, "kernel", 6) != 0)
                fail("first-policy-must-not-be-loaded");
}

static void reconnect_console(void)
{
        struct stat st;
        int fd = open("/dev/console", O_RDWR | O_NOCTTY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0)
                fail("console-open");
        if (fstat(fd, &st) < 0 || !S_ISCHR(st.st_mode) ||
            major(st.st_rdev) != 5 || minor(st.st_rdev) != 1)
                fail("console-device-identity");
        for (int number = 0; number < 3; number++)
                if (dup2(fd, number) < 0 || fcntl(number, F_SETFD, 0) < 0)
                        fail("console-stdio");
        if (fd > STDERR_FILENO && close(fd) < 0)
                fail("console-close");
}

int main(int argc, char **argv)
{
        (void)argv;
        struct stat old_root, new_root, helper;
        struct statfs old_fs, new_fs;
        struct statvfs new_flags;
        struct sigaction child_action;
        unsigned reaped = 0;

        if (getpid() != 1 || geteuid() != 0 || argc != 1)
                fail("pid1-root-with-no-arguments-required");
        phase = "root-identities";
        int descriptor_flags = fcntl(OLD_ROOT_FD, F_GETFD);
        if (descriptor_flags < 0 || (descriptor_flags & FD_CLOEXEC))
                fail("saved-root-descriptor");
        if (fstat(OLD_ROOT_FD, &old_root) < 0 || !S_ISDIR(old_root.st_mode) ||
            fstatfs(OLD_ROOT_FD, &old_fs) < 0 ||
            ((unsigned long)old_fs.f_type != RAMFS_MAGIC &&
             (unsigned long)old_fs.f_type != TMPFS_MAGIC))
                fail("saved-root-is-not-memory-root");
        if (stat("/", &new_root) < 0 || !S_ISDIR(new_root.st_mode) ||
            statfs("/", &new_fs) < 0 ||
            (unsigned long)new_fs.f_type != TMPFS_MAGIC ||
            new_root.st_dev == old_root.st_dev)
                fail("new-root-is-not-distinct-tmpfs");
        if (statvfs("/", &new_flags) < 0 ||
            (new_flags.f_flag & (ST_RDONLY | ST_NOSUID | ST_NOEXEC | ST_NODEV)))
                fail("new-root-flags");
        require_initial_context();

        phase = "console";
        reconnect_console();
        phase = "cleanup-child";
        if (sigaction(SIGCHLD, NULL, &child_action) < 0 ||
            child_action.sa_handler != SIG_DFL ||
            (child_action.sa_flags & SA_NOCLDWAIT))
                fail("cleanup-child-must-remain-waitable");
        uint64_t deadline = monotonic_ns() + CLEANUP_TIMEOUT_NS;
        for (;;) {
                int status;
                pid_t child = waitpid(-1, &status, WNOHANG);
                if (child > 0) {
                        reaped++;
                        if (reaped != 1 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
                                fail("unexpected-child-or-cleanup-status");
                        continue;
                }
                if (child < 0) {
                        if (errno == EINTR)
                                continue;
                        if (errno == ECHILD)
                                break;
                        fail("cleanup-wait");
                }
                if (monotonic_ns() >= deadline)
                        fail("cleanup-timeout");
                struct timespec delay = {.tv_sec = 0, .tv_nsec = 50000000};
                if (nanosleep(&delay, NULL) < 0 && errno != EINTR)
                        fail("cleanup-delay");
        }
        if (reaped != 1)
                fail("cleanup-child-not-reaped");

        phase = "old-root-empty";
        int duplicate = fcntl(OLD_ROOT_FD, F_DUPFD_CLOEXEC, 4);
        if (duplicate < 0 || lseek(duplicate, 0, SEEK_SET) < 0)
                fail("old-root-directory-duplicate-or-rewind");
        DIR *directory = fdopendir(duplicate);
        if (!directory)
                fail("old-root-directory-open");
        for (;;) {
                errno = 0;
                struct dirent *entry = readdir(directory);
                if (!entry) {
                        if (errno)
                                fail("old-root-directory-read");
                        break;
                }
                if (strcmp(entry->d_name, ".") != 0 && strcmp(entry->d_name, "..") != 0)
                        fail("old-root-still-has-entries");
        }
        if (closedir(directory) < 0 || close(OLD_ROOT_FD) < 0)
                fail("old-root-descriptor-close");

        phase = "native-entry";
        if (lstat(HELPER, &helper) < 0 || !S_ISREG(helper.st_mode) ||
            helper.st_size != HELPER_SIZE || (helper.st_mode & 07777) != 0755 ||
            helper.st_uid != 0 || helper.st_gid != 0)
                fail("unchanged-native-entry-shape");
        require_initial_context();
        fprintf(stderr, MARKER " CLEANUP_COMPLETE old_dev=%u:%u new_dev=%u:%u"
                " cleanup_children=1 old_root_empty=1 policy_load_attempted=0\n",
                major(old_root.st_dev), minor(old_root.st_dev),
                major(new_root.st_dev), minor(new_root.st_dev));
        fflush(NULL);
        char *const next[] = {HELPER, NULL};
        execv(HELPER, next);
        fail("native-entry-exec");
}
