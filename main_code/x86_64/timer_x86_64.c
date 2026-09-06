#include "timer.h"

#if !defined(__x86_64__)
#error "timer_x86_64.c must be compiled for x86-64"
#endif

#include <cpuid.h>
#include <stddef.h>
#include <x86intrin.h>

/* Extended-feature CPUID leaf 0x80000001, EDX bit 27: RDTSCP support. */
static bool x86_has_rdtscp(void)
{
    const unsigned int rdtscp_bit = 1u << 27;
    unsigned int eax;
    unsigned int ebx;
    unsigned int ecx;
    unsigned int edx;

    if (!__get_cpuid(0x80000001u, &eax, &ebx, &ecx, &edx)) {
        return false;
    }

    return (edx & rdtscp_bit) != 0u;
}

int timer_init(struct timer_info *info)
{
    if (info == NULL || !x86_has_rdtscp()) {
        return -1;
    }

    info->name = "LFENCE+RDTSC / RDTSCP+LFENCE";
    info->unit = "TSC ticks";
    info->frequency_hz = 0u;
    info->frequency_hz_valid = false;

    return 0;
}

uint64_t timer_start(void)
{
    uint64_t timestamp;

    /* Empty assembly emits no instruction; "memory" orders the compiler. */
    __asm__ __volatile__("" ::: "memory");
    _mm_lfence();
    timestamp = __rdtsc();
    _mm_lfence();
    __asm__ __volatile__("" ::: "memory");

    return timestamp;
}

uint64_t timer_stop(void)
{
    unsigned int auxiliary;
    uint64_t timestamp;

    __asm__ __volatile__("" ::: "memory");
    timestamp = __rdtscp(&auxiliary);
    _mm_lfence();
    __asm__ __volatile__("" ::: "memory");

    return timestamp;
}

#if defined(ECE592_TIMER_SELF_TEST)

#include <inttypes.h>
#include <stdio.h>

int main(void)
{
    struct timer_info info;

    if (timer_init(&info) != 0) {
        fprintf(stderr, "error: RDTSCP is unavailable on this CPU\n");
        return 1;
    }

    printf("timer_name=%s\n", info.name);
    printf("timer_unit=%s\n", info.unit);
    printf("timer_frequency_hz=%s\n",
           info.frequency_hz_valid ? "available" : "not_reported");

    for (unsigned int sample = 0; sample < 5u; ++sample) {
        uint64_t start = timer_start();
        __asm__ __volatile__("" ::: "memory");
        uint64_t stop = timer_stop();

        if (stop <= start) {
            fprintf(stderr, "error: timestamp did not advance\n");
            return 1;
        }

        printf("sample_%u_elapsed=%" PRIu64 "\n",
               sample, stop - start);
    }

    printf("status=ok\n");
    return 0;
}

#endif
