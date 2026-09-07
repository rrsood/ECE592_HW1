#define _POSIX_C_SOURCE 200809L

#include "pointer_chase.h"

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
    uint64_t threshold;
    uint64_t value;

    /* Reject the short remainder interval instead of introducing modulo bias. */
    threshold = (UINT64_C(0) - bound) % bound;
    do {
        value = splitmix64_next(state);
    } while (value < threshold);

    return value % bound;
}

static struct chase_node *node_at(const struct pointer_chase *chase,
                                  size_t index)
{
    unsigned char *bytes = chase->allocation;

    return (struct chase_node *)(void *)(bytes + index *
                                        chase->node_spacing_bytes);
}

int pointer_chase_create(struct pointer_chase *chase, size_t node_count,
                         size_t node_spacing_bytes, uint64_t seed,
                         enum pointer_chase_order order)
{
    struct random_state random = {seed};
    size_t *node_order;
    size_t allocation_bytes;
    long page_size;
    void *allocation;
    int allocation_error;

    if (chase == NULL || node_count < 2u ||
        node_spacing_bytes < sizeof(struct chase_node) ||
        node_spacing_bytes % _Alignof(struct chase_node) != 0u ||
        (order != POINTER_CHASE_RANDOMIZED &&
         order != POINTER_CHASE_SEQUENTIAL)) {
        errno = EINVAL;
        return -1;
    }

    if (node_count > (SIZE_MAX - sizeof(struct chase_node)) /
                         node_spacing_bytes + 1u ||
        node_count > SIZE_MAX / sizeof(*node_order)) {
        errno = EOVERFLOW;
        return -1;
    }

    allocation_bytes = (node_count - 1u) * node_spacing_bytes +
                       sizeof(struct chase_node);
    page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || ((size_t)page_size & ((size_t)page_size - 1u)) != 0u ||
        (size_t)page_size % sizeof(void *) != 0u) {
        errno = EINVAL;
        return -1;
    }

    allocation = NULL;
    allocation_error = posix_memalign(&allocation, (size_t)page_size,
                                      allocation_bytes);
    if (allocation_error != 0) {
        errno = allocation_error;
        return -1;
    }

    node_order = malloc(node_count * sizeof(*node_order));
    if (node_order == NULL) {
        free(allocation);
        return -1;
    }

    /* This write establishes local first-touch placement after CPU pinning. */
    memset(allocation, 0, allocation_bytes);

    for (size_t index = 0; index < node_count; ++index) {
        node_order[index] = index;
    }

    if (order == POINTER_CHASE_RANDOMIZED) {
        /* Fisher-Yates produces a uniformly shuffled ordering of all nodes. */
        for (size_t remaining = node_count; remaining > 1u; --remaining) {
            size_t selected =
                (size_t)random_below(&random, (uint64_t)remaining);
            size_t temporary = node_order[remaining - 1u];

            node_order[remaining - 1u] = node_order[selected];
            node_order[selected] = temporary;
        }
    }

    memset(chase, 0, sizeof(*chase));
    chase->allocation = allocation;
    chase->allocation_bytes = allocation_bytes;
    chase->allocation_alignment_bytes = (size_t)page_size;
    chase->node_count = node_count;
    chase->node_spacing_bytes = node_spacing_bytes;
    chase->seed = seed;
    chase->order = order;
    chase->start = node_at(chase, node_order[0]);

    for (size_t position = 0; position < node_count; ++position) {
        size_t current_index = node_order[position];
        size_t next_index = node_order[(position + 1u) % node_count];

        node_at(chase, current_index)->next = node_at(chase, next_index);
    }

    free(node_order);
    return 0;
}

const char *pointer_chase_order_name(enum pointer_chase_order order)
{
    if (order == POINTER_CHASE_RANDOMIZED) {
        return "randomized-dependent-single-cycle";
    }
    if (order == POINTER_CHASE_SEQUENTIAL) {
        return "sequential-dependent-single-cycle";
    }

    return "invalid";
}

void pointer_chase_destroy(struct pointer_chase *chase)
{
    if (chase == NULL) {
        return;
    }

    free(chase->allocation);
    memset(chase, 0, sizeof(*chase));
}

#if defined(ECE592_POINTER_CHASE_SELF_TEST)

#include "affinity.h"

#include <inttypes.h>
#include <limits.h>

static int parse_unsigned(const char *text, uint64_t maximum, uint64_t *value)
{
    char *end;
    unsigned long long parsed;

    if (text == NULL || value == NULL || text[0] == '-') {
        return -1;
    }

    errno = 0;
    end = NULL;
    parsed = strtoull(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0' || parsed > maximum) {
        return -1;
    }

    *value = (uint64_t)parsed;
    return 0;
}

int main(int argc, char **argv)
{
    const size_t test_node_count = 32u;
    const size_t test_spacing = sizeof(struct chase_node);
    struct affinity_info affinity;
    struct pointer_chase chase;
    struct chase_node *current;
    bool visited[test_node_count];
    uint64_t logical_cpu;
    uint64_t seed;
    enum pointer_chase_order order;

    if (argc != 4 ||
        parse_unsigned(argv[1], INT_MAX, &logical_cpu) != 0 ||
        parse_unsigned(argv[2], UINT64_MAX, &seed) != 0) {
        fprintf(stderr,
                "usage: %s <logical-cpu> <seed> randomized|sequential\n",
                argv[0]);
        return 2;
    }

    if (strcmp(argv[3], "randomized") == 0) {
        order = POINTER_CHASE_RANDOMIZED;
    } else if (strcmp(argv[3], "sequential") == 0) {
        order = POINTER_CHASE_SEQUENTIAL;
    } else {
        fprintf(stderr, "error: invalid traversal order: %s\n", argv[3]);
        return 2;
    }

    if (affinity_pin_current_thread((int)logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (pointer_chase_create(&chase, test_node_count, test_spacing, seed,
                             order) != 0) {
        perror("pointer_chase_create");
        return 1;
    }

    memset(visited, 0, sizeof(visited));
    current = chase.start;
    for (size_t step = 0; step < chase.node_count; ++step) {
        unsigned char *node_bytes = (unsigned char *)(void *)current;
        unsigned char *base = chase.allocation;
        size_t offset;
        size_t index;

        if (node_bytes < base ||
            node_bytes >= base + chase.allocation_bytes) {
            fprintf(stderr, "error: node lies outside allocation\n");
            pointer_chase_destroy(&chase);
            return 1;
        }

        offset = (size_t)(node_bytes - base);
        if (offset % chase.node_spacing_bytes != 0u) {
            fprintf(stderr, "error: node is not on a spacing boundary\n");
            pointer_chase_destroy(&chase);
            return 1;
        }

        index = offset / chase.node_spacing_bytes;
        if (index >= chase.node_count || visited[index]) {
            fprintf(stderr, "error: cycle repeated before visiting every node\n");
            pointer_chase_destroy(&chase);
            return 1;
        }

        visited[index] = true;
        if (step < 8u) {
            printf("cycle_index_%zu=%zu\n", step, index);
        }
        current = current->next;
    }

    if (current != chase.start) {
        fprintf(stderr, "error: traversal did not close at the start node\n");
        pointer_chase_destroy(&chase);
        return 1;
    }

    printf("seed=%" PRIu64 "\n", chase.seed);
    printf("node_count=%zu\n", chase.node_count);
    printf("node_spacing_bytes=%zu\n", chase.node_spacing_bytes);
    printf("traversal=%s\n", pointer_chase_order_name(chase.order));
    printf("allocation_bytes=%zu\n", chase.allocation_bytes);
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);
    printf("single_cycle_verified=true\n");
    printf("status=ok\n");

    pointer_chase_destroy(&chase);
    return 0;
}

#endif
