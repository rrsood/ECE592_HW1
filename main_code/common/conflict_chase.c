#define _POSIX_C_SOURCE 200809L

#include "conflict_chase.h"

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

static struct chase_node *conflict_node(const struct conflict_chase *chase,
                                        size_t line_index)
{
    unsigned char *bytes = chase->allocation;

    return (struct chase_node *)(void *)(
        bytes + line_index * chase->conflict_stride_bytes);
}

int conflict_chase_create(struct conflict_chase *chase, size_t line_count,
                          size_t conflict_stride_bytes, uint64_t seed)
{
    struct random_state random = {seed};
    size_t *line_order;
    size_t allocation_bytes;
    long page_size;
    void *allocation;
    int allocation_error;

    if (chase == NULL || line_count < 2u ||
        conflict_stride_bytes < sizeof(struct chase_node) ||
        conflict_stride_bytes % _Alignof(struct chase_node) != 0u) {
        errno = EINVAL;
        return -1;
    }

    if ((line_count - 1u) >
            (SIZE_MAX - sizeof(struct chase_node)) /
                conflict_stride_bytes ||
        line_count > SIZE_MAX / sizeof(*line_order)) {
        errno = EOVERFLOW;
        return -1;
    }
    allocation_bytes = (line_count - 1u) * conflict_stride_bytes +
                       sizeof(struct chase_node);

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

    line_order = malloc(line_count * sizeof(*line_order));
    if (line_order == NULL) {
        free(allocation);
        return -1;
    }

    /* Pinning occurs before this first-touch write, keeping placement local. */
    memset(allocation, 0, allocation_bytes);
    for (size_t index = 0; index < line_count; ++index) {
        line_order[index] = index;
    }

    for (size_t remaining = line_count; remaining > 1u; --remaining) {
        size_t selected =
            (size_t)random_below(&random, (uint64_t)remaining);
        size_t temporary = line_order[remaining - 1u];

        line_order[remaining - 1u] = line_order[selected];
        line_order[selected] = temporary;
    }

    memset(chase, 0, sizeof(*chase));
    chase->allocation = allocation;
    chase->allocation_bytes = allocation_bytes;
    chase->allocation_alignment_bytes = (size_t)page_size;
    chase->line_count = line_count;
    chase->conflict_stride_bytes = conflict_stride_bytes;
    chase->seed = seed;
    chase->start = conflict_node(chase, line_order[0]);

    for (size_t position = 0; position < line_count; ++position) {
        size_t current_line = line_order[position];
        size_t next_line = line_order[(position + 1u) % line_count];
        struct chase_node *current = conflict_node(chase, current_line);

        current->next = conflict_node(chase, next_line);
    }

    free(line_order);
    return 0;
}

void conflict_chase_destroy(struct conflict_chase *chase)
{
    if (chase == NULL) {
        return;
    }

    free(chase->allocation);
    memset(chase, 0, sizeof(*chase));
}

#if defined(ECE592_CONFLICT_CHASE_SELF_TEST)

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
    const size_t test_line_count = 17u;
    const size_t test_conflict_stride = 4096u;
    struct affinity_info affinity;
    struct conflict_chase chase;
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
    if (conflict_chase_create(&chase, test_line_count, test_conflict_stride,
                              UINT64_C(592)) != 0) {
        perror("conflict_chase_create");
        return 1;
    }

    allocation_address = (uintptr_t)chase.allocation;
    current = chase.start;
    for (size_t visit = 0; visit < test_line_count; ++visit) {
        uintptr_t current_address = (uintptr_t)(void *)current;
        size_t allocation_offset;
        size_t line_index;

        if (current_address < allocation_address) {
            fprintf(stderr, "error: node precedes allocation\n");
            conflict_chase_destroy(&chase);
            return 1;
        }
        allocation_offset = (size_t)(current_address - allocation_address);
        if (allocation_offset % test_conflict_stride != 0u) {
            fprintf(stderr, "error: node does not preserve page offset\n");
            conflict_chase_destroy(&chase);
            return 1;
        }
        line_index = allocation_offset / test_conflict_stride;
        if (line_index >= test_line_count || visited[line_index]) {
            fprintf(stderr, "error: duplicate or invalid line\n");
            conflict_chase_destroy(&chase);
            return 1;
        }
        visited[line_index] = true;

        current = current->next;
        if ((uintptr_t)(void *)current >= allocation_address) {
            size_t next_offset = (size_t)(
                (uintptr_t)(void *)current - allocation_address);

            if (next_offset % test_conflict_stride == 0u &&
                next_offset / test_conflict_stride !=
                    (line_index + 1u) % test_line_count) {
                saw_randomized_transition = true;
            }
        }
    }

    if (current != chase.start ||
        (uintptr_t)chase.allocation % chase.allocation_alignment_bytes != 0u ||
        !saw_randomized_transition) {
        fprintf(stderr, "error: chain is not one aligned randomized cycle\n");
        conflict_chase_destroy(&chase);
        return 1;
    }

    printf("line_count=%zu\n", chase.line_count);
    printf("conflict_stride_bytes=%zu\n", chase.conflict_stride_bytes);
    printf("allocation_bytes=%zu\n", chase.allocation_bytes);
    printf("allocation_alignment_bytes=%zu\n",
           chase.allocation_alignment_bytes);
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);
    printf("fixed_page_offset=true\n");
    printf("randomized_line_order=true\n");
    printf("single_cycle=true\n");
    printf("status=ok\n");

    conflict_chase_destroy(&chase);
    return 0;
}

#endif
