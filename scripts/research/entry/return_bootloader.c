/* SPDX-License-Identifier: GPL-2.0-only
 * Explicit operator action in a future qualified first stage only.
 * Build qualification invokes --version; it never invokes the restart path.
 */
#include <errno.h>
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        puts("tb371fc-entry-return-bootloader 1 (physical return unverified)");
        return 0;
    }
    if (argc != 2 || strcmp(argv[1], "--request-bootloader") != 0) {
        fputs("Usage: entry-return-bootloader --version | --request-bootloader\n", stderr);
        return 64;
    }
    sync();
    long result = syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
                          LINUX_REBOOT_CMD_RESTART2, "bootloader");
    if (result < 0) {
        perror("reboot(RESTART2, bootloader)");
        return 1;
    }
    return 0;
}
