/* SPDX-License-Identifier: GPL-2.0-only */
/* ARM64 EL0 probe for a generic QEMU virt machine, never a tablet init. */
typedef unsigned long usize;

static long syscall3(long number, long a, long b, long c)
{
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x8 __asm__("x8") = number;
	__asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x8) : "memory");
	return x0;
}

static int output(const char *text)
{
	usize length = 0;
	while (text[length])
		length++;
	while (length) {
		long done = syscall3(64, 1, (long)text, length); /* write */
		if (done <= 0)
			return -1;
		text += done;
		length -= done;
	}
	return 0;
}

struct utsname {
	char sysname[65], nodename[65], release[65];
	char version[65], machine[65], domainname[65];
};

__attribute__((noreturn)) void _start(void)
{
	static struct utsname info;
	if (syscall3(160, (long)&info, 0, 0) == 0) { /* uname */
		output("TB371FC_QEMU_RELEASE=");
		output(info.release);
		output("\nTB371FC_QEMU_MACHINE=");
		output(info.machine);
		output("\nTB371FC_QEMU_EL0_READY\n");
	} else {
		output("TB371FC_QEMU_EL0_ERROR\n");
	}
	/* The parent ends its own QEMU process after reading the marker.
	 * No shutdown, reboot, device access or disk writes occur in this init.
	 */
	for (;;)
		__asm__ volatile("wfe");
}
