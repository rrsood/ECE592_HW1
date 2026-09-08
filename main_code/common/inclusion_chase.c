#define _POSIX_C_SOURCE 200809L

#include "inclusion_chase.h"

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int inclusion_chase_create(struct inclusion_chase *chase,
                           size_t probe_node_count,
                           size_t pressure_node_count,
                           size_t node_spacing_bytes,
                           uint64_t seed)
{
    const uint64_t pressure_seed = seed ^ UINT64_C(0xd1b54a32d192ed03);

    if (chase == NULL || probe_node_count < 2u ||
        pressure_node_count < 2u ||
        node_spacing_bytes < sizeof(struct chase_node)) {
        errno = EINVAL;
        return -1;
    }

    memset(chase, 0, sizeof(*chase));
    chase->seed = seed;

    if (pointer_chase_create(&chase->probe, probe_node_count,
                             node_spacing_bytes, seed,
                             POINTER_CHASE_RANDOMIZED) != 0) {
        return -1;
    }

    if (pointer_chase_create(&chase->pressure, pressure_node_count,
                             node_spacing_bytes, pressure_seed,
                             POINTER_CHASE_RANDOMIZED) != 0) {
        pointer_chase_destroy(&chase->probe);
        return -1;
    }

    return 0;
}

void inclusion_chase_destroy(struct inclusion_chase *chase)
{
    if (chase == NULL) {
        return;
    }

    pointer_chase_destroy(&chase->pressure);
    pointer_chase_destroy(&chase->probe);
    memset(chase, 0, sizeof(*chase));
}

#if defined(ECE592_INCLUSION_CHASE_SELF_TEST)

#include "affinity.h"

#include <limits.h>

static int parse_logical_cpu(const char *text, int *logical_cpu)
{
    char *end;
    long parsed;

    errno = 0;
    end = NULL;
    parsed = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        parsed < 0 || parsed > INT_MAX) {
        return -1;
    }

    *logical_cpu = (int)parsed;
    return 0;
}

static int count_unique_cycle_nodes(struct chase_node *start,
                                    size_t expected_count)
{
    struct chase_node *current = start;

    for (size_t index = 0; index < expected_count; ++index) {
        if (current == NULL) {
            return -1;
        }
        current = current->next;
    }

    return current == start ? 0 : -1;
}

int main(int argc, char **argv)
{
    const size_t probe_nodes = 257u;
    const size_t pressure_nodes = 4099u;
    const size_t node_spacing = sizeof(struct chase_node);
    struct affinity_info affinity;
    struct inclusion_chase chase;
    int logical_cpu;

    if (argc != 2 || parse_logical_cpu(argv[1], &logical_cpu) != 0) {
        fprintf(stderr, "usage: %s <logical-cpu>\n", argv[0]);
        return 2;
    }

    if (affinity_pin_current_thread(logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }

    if (inclusion_chase_create(&chase, probe_nodes, pressure_nodes,
                               node_spacing, UINT64_C(592)) != 0) {
        perror("inclusion_chase_create");
        return 1;
    }

    if (count_unique_cycle_nodes(chase.probe.start, probe_nodes) != 0 ||
        count_unique_cycle_nodes(chase.pressure.start, pressure_nodes) != 0) {
        fprintf(stderr, "error: inclusion cycles are malformed\n");
        inclusion_chase_destroy(&chase);
        return 1;
    }

    printf("probe_node_count=%zu\n", chase.probe.node_count);
    printf("pressure_node_count=%zu\n", chase.pressure.node_count);
    printf("node_spacing_bytes=%zu\n", chase.probe.node_spacing_bytes);
    printf("probe_allocation_bytes=%zu\n", chase.probe.allocation_bytes);
    printf("pressure_allocation_bytes=%zu\n", chase.pressure.allocation_bytes);
    printf("probe_traversal=%s\n",
           pointer_chase_order_name(chase.probe.order));
    printf("pressure_traversal=%s\n",
           pointer_chase_order_name(chase.pressure.order));
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);
    printf("status=ok\n");

    inclusion_chase_destroy(&chase);
    return 0;
}

#endif
