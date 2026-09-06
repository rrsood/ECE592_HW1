#define _GNU_SOURCE

#include "affinity.h"

#include <errno.h>
#include <sched.h>
#include <stddef.h>

int affinity_pin_current_thread(int logical_cpu, struct affinity_info *info)
{
    cpu_set_t requested_set;
    cpu_set_t observed_set;
    int running_cpu;

    if (info == NULL || logical_cpu < 0 || logical_cpu >= CPU_SETSIZE) {
        errno = EINVAL;
        return -1;
    }

    CPU_ZERO(&requested_set);
    CPU_SET(logical_cpu, &requested_set);

    /* PID 0 means the calling thread on Linux. */
    if (sched_setaffinity(0, sizeof(requested_set), &requested_set) != 0) {
        return -1;
    }

    if (sched_getaffinity(0, sizeof(observed_set), &observed_set) != 0) {
        return -1;
    }

    running_cpu = sched_getcpu();
    if (running_cpu < 0) {
        return -1;
    }

    info->requested_cpu = logical_cpu;
    info->running_cpu = running_cpu;
    info->allowed_cpu_count = CPU_COUNT(&observed_set);

    if (info->allowed_cpu_count != 1 ||
        !CPU_ISSET(logical_cpu, &observed_set) ||
        running_cpu != logical_cpu) {
        errno = EIO;
        return -1;
    }

    return 0;
}

#if defined(ECE592_AFFINITY_SELF_TEST)

#include <stdio.h>
#include <stdlib.h>

static int parse_logical_cpu(const char *text, int *logical_cpu)
{
    char *end;
    long value;

    if (text == NULL || logical_cpu == NULL) {
        return -1;
    }

    errno = 0;
    end = NULL;
    value = strtol(text, &end, 10);

    if (errno != 0 || end == text || *end != '\0' ||
        value < 0 || value >= CPU_SETSIZE) {
        return -1;
    }

    *logical_cpu = (int)value;
    return 0;
}

int main(int argc, char **argv)
{
    struct affinity_info info;
    int logical_cpu;

    if (argc != 2 || parse_logical_cpu(argv[1], &logical_cpu) != 0) {
        fprintf(stderr, "usage: %s <logical-cpu>\n", argv[0]);
        return 2;
    }

    if (affinity_pin_current_thread(logical_cpu, &info) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }

    printf("requested_logical_cpu=%d\n", info.requested_cpu);
    printf("running_logical_cpu=%d\n", info.running_cpu);
    printf("allowed_logical_cpu_count=%d\n", info.allowed_cpu_count);
    printf("status=ok\n");

    return 0;
}

#endif
