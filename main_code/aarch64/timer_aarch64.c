#include "timer.h"

#if !defined(__aarch64__)
#error "timer_aarch64.c must be compiled for AArch64"
#endif

#include <stddef.h>

int timer_init(struct timer_info *info)
{
    uint64_t frequency_hz;

    if (info == NULL) {
        return -1;
    }

    __asm__ __volatile__(
        "mrs %0, cntfrq_el0"
        : "=r"(frequency_hz));

    if (frequency_hz == 0u) {
        return -1;
    }

    info->name = "DSB+ISB+CNTVCT_EL0+ISB";
    info->unit = "generic-timer ticks";
    info->frequency_hz = frequency_hz;
    /* Record CNTFRQ_EL0, but do not convert units until it is validated. */
    info->frequency_hz_valid = false;

    return 0;
}

uint64_t timer_start(void)
{
    uint64_t timestamp;

    __asm__ __volatile__(
        "dsb sy\n\t"
        "isb\n\t"
        "mrs %0, cntvct_el0\n\t"
        "isb\n\t"
        : "=r"(timestamp)
        :
        : "memory");

    return timestamp;
}

uint64_t timer_stop(void)
{
    uint64_t timestamp;

    __asm__ __volatile__(
        "dsb sy\n\t"
        "isb\n\t"
        "mrs %0, cntvct_el0\n\t"
        "isb\n\t"
        : "=r"(timestamp)
        :
        : "memory");

    return timestamp;
}

#if defined(ECE592_TIMER_SELF_TEST)

#include <inttypes.h>
#include <stdio.h>

int main(void)
{
    const unsigned int maximum_attempts = 1000000u;
    struct timer_info info;

    if (timer_init(&info) != 0) {
        fprintf(stderr, "error: Arm generic-timer initialization failed\n");
        return 1;
    }

    printf("timer_name=%s\n", info.name);
    printf("timer_unit=%s\n", info.unit);
    printf("timer_frequency_hz=%" PRIu64 "\n", info.frequency_hz);
    printf("timer_frequency_hz_valid=%s\n",
           info.frequency_hz_valid ? "true" : "false");

    for (unsigned int sample = 0; sample < 5u; ++sample) {
        uint64_t start = timer_start();
        uint64_t stop = start;
        unsigned int attempts = 0u;

        while (stop == start && attempts < maximum_attempts) {
            stop = timer_stop();
            ++attempts;
        }

        if (stop < start) {
            fprintf(stderr, "error: generic timer moved backward\n");
            return 1;
        }
        if (stop == start) {
            fprintf(stderr, "error: generic timer did not advance\n");
            return 1;
        }

        printf("sample_%u_elapsed=%" PRIu64 " attempts=%u\n",
               sample, stop - start, attempts);
    }

    printf("status=ok\n");
    return 0;
}

#endif
