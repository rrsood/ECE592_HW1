#define _POSIX_C_SOURCE 200809L

#include "spatial_chase.h"

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct random_state {
    uint64_t value;
};

static uint64_t splitmix64_next(struct random_state *state)
{
    uint64_t value;

    state->value += UINT64_C(0x9e3779b97f4a7c15);
    value = state->value;
    value = (value ^ (value >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31);
}

static uint64_t random_below(struct random_state *state, uint64_t bound)
{
    uint64_t threshold = (UINT64_C(0) - bound) % bound;
    uint64_t value;

    do {
        value = splitmix64_next(state);
    } while (value < threshold);

    return value % bound;
}

static struct chase_node *region_node(const struct spatial_chase *chase,
                                      size_t region_index,
                                      size_t offset_bytes)
{
    unsigned char *bytes = chase->allocation;

    return (struct chase_node *)(void *)(
        bytes + region_index * chase->region_spacing_bytes + offset_bytes);
}

int spatial_chase_create(struct spatial_chase *chase, size_t region_count,
                         size_t region_spacing_bytes,
                         size_t probe_offset_bytes, uint64_t seed)
{
    struct random_state random = {seed};
    size_t *region_order;
    size_t allocation_bytes;
    long page_size;
    void *allocation;
    int allocation_error;

    if (chase == NULL || region_count < 2u ||
        region_spacing_bytes < 2u * sizeof(struct chase_node) ||
        region_spacing_bytes % _Alignof(struct chase_node) != 0u ||
        probe_offset_bytes < sizeof(struct chase_node) ||
        probe_offset_bytes % _Alignof(struct chase_node) != 0u ||
        probe_offset_bytes > region_spacing_bytes - sizeof(struct chase_node)) {
        errno = EINVAL;
        return -1;
    }

    if ((region_count - 1u) >
            (SIZE_MAX - probe_offset_bytes - sizeof(struct chase_node)) /
                region_spacing_bytes ||
        region_count > SIZE_MAX / sizeof(*region_order)) {
        errno = EOVERFLOW;
        return -1;
    }
    allocation_bytes = (region_count - 1u) * region_spacing_bytes +
                       probe_offset_bytes + sizeof(struct chase_node);

    page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || ((size_t)page_size & ((size_t)page_size - 1u)) != 0u ||
        (size_t)page_size % sizeof(void *) != 0u) {
        errno = EINVAL;
        return -1;
    }

    allocation = NULL;
    allocation_error = posix_memalign(
        &allocation, (size_t)page_size, allocation_bytes);
    if (allocation_error != 0) {
        errno = allocation_error;
        return -1;
    }

    region_order = malloc(region_count * sizeof(*region_order));
    if (region_order == NULL) {
        free(allocation);
        return -1;
    }

    /* Pinning occurs before this first-touch write, keeping placement local. */
    memset(allocation, 0, allocation_bytes);
    for (size_t index = 0; index < region_count; ++index) {
        region_order[index] = index;
    }

    for (size_t remaining = region_count; remaining > 1u; --remaining) {
        size_t selected =
            (size_t)random_below(&random, (uint64_t)remaining);
        size_t temporary = region_order[remaining - 1u];

        region_order[remaining - 1u] = region_order[selected];
        region_order[selected] = temporary;
    }

    memset(chase, 0, sizeof(*chase));
    chase->allocation = allocation;
    chase->allocation_bytes = allocation_bytes;
    chase->allocation_alignment_bytes = (size_t)page_size;
    chase->region_count = region_count;
    chase->region_spacing_bytes = region_spacing_bytes;
    chase->probe_offset_bytes = probe_offset_bytes;
    chase->seed = seed;
    chase->start = region_node(chase, region_order[0], 0u);

    for (size_t position = 0; position < region_count; ++position) {
        size_t current_region = region_order[position];
        size_t next_region = region_order[(position + 1u) % region_count];
        struct chase_node *base = region_node(chase, current_region, 0u);
        struct chase_node *probe = region_node(
            chase, current_region, probe_offset_bytes);

        base->next = probe;
        probe->next = region_node(chase, next_region, 0u);
    }

    free(region_order);
    return 0;
}

void spatial_chase_destroy(struct spatial_chase *chase)
{
    if (chase == NULL) {
        return;
    }

    free(chase->allocation);
    memset(chase, 0, sizeof(*chase));
}

#if defined(ECE592_SPATIAL_CHASE_SELF_TEST)

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

int main(int argc, char **argv)
{
    const size_t test_region_count = 17u;
    const size_t test_region_spacing = 64u;
    const size_t test_probe_offset = 16u;
    struct affinity_info affinity;
    struct spatial_chase chase;
    struct chase_node *current;
    bool visited[17] = {false};
    bool saw_randomized_transition = false;
    uintptr_t allocation_address;
    int logical_cpu;

    if (argc != 2 || parse_logical_cpu(argv[1], &logical_cpu) != 0) {
        fprintf(stderr, "usage: %s <logical-cpu>\n", argv[0]);
        return 2;
    }
    if (affinity_pin_current_thread(logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (spatial_chase_create(&chase, test_region_count,
                             test_region_spacing, test_probe_offset,
                             UINT64_C(592)) != 0) {
        perror("spatial_chase_create");
        return 1;
    }

    allocation_address = (uintptr_t)chase.allocation;
    current = chase.start;
    for (size_t visit = 0; visit < test_region_count; ++visit) {
        uintptr_t current_address = (uintptr_t)(void *)current;
        size_t allocation_offset;
        size_t region_index;
        struct chase_node *probe;

        if (current_address < allocation_address) {
            fprintf(stderr, "error: base node precedes allocation\n");
            spatial_chase_destroy(&chase);
            return 1;
        }
        allocation_offset = (size_t)(current_address - allocation_address);
        if (allocation_offset % test_region_spacing != 0u) {
            fprintf(stderr, "error: expected a region-base node\n");
            spatial_chase_destroy(&chase);
            return 1;
        }
        region_index = allocation_offset / test_region_spacing;
        if (region_index >= test_region_count || visited[region_index]) {
            fprintf(stderr, "error: duplicate or invalid region\n");
            spatial_chase_destroy(&chase);
            return 1;
        }
        visited[region_index] = true;

        probe = current->next;
        if ((uintptr_t)(void *)probe != current_address + test_probe_offset) {
            fprintf(stderr, "error: base does not point to its probe offset\n");
            spatial_chase_destroy(&chase);
            return 1;
        }
        current = probe->next;
        if ((uintptr_t)(void *)current >= allocation_address) {
            size_t next_offset = (size_t)(
                (uintptr_t)(void *)current - allocation_address);

            if (next_offset % test_region_spacing == 0u &&
                next_offset / test_region_spacing !=
                    (region_index + 1u) % test_region_count) {
                saw_randomized_transition = true;
            }
        }
    }

    if (current != chase.start ||
        (uintptr_t)chase.allocation % chase.allocation_alignment_bytes != 0u ||
        !saw_randomized_transition) {
        fprintf(stderr, "error: chain is not one aligned closed cycle\n");
        spatial_chase_destroy(&chase);
        return 1;
    }

    printf("region_count=%zu\n", chase.region_count);
    printf("region_spacing_bytes=%zu\n", chase.region_spacing_bytes);
    printf("probe_offset_bytes=%zu\n", chase.probe_offset_bytes);
    printf("allocation_bytes=%zu\n", chase.allocation_bytes);
    printf("dependent_nodes_per_cycle=%zu\n", 2u * chase.region_count);
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);
    printf("randomized_region_order=true\n");
    printf("single_cycle=true\n");
    printf("status=ok\n");

    spatial_chase_destroy(&chase);
    return 0;
}

#endif
