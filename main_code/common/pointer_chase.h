#ifndef ECE592_POINTER_CHASE_H
#define ECE592_POINTER_CHASE_H

#include <stddef.h>
#include <stdint.h>

struct chase_node {
    struct chase_node *next;
};

enum pointer_chase_order {
    POINTER_CHASE_RANDOMIZED,
    POINTER_CHASE_SEQUENTIAL
};

struct pointer_chase {
    void *allocation;
    size_t allocation_bytes;
    size_t allocation_alignment_bytes;
    size_t node_count;
    size_t node_spacing_bytes;
    uint64_t seed;
    enum pointer_chase_order order;
    struct chase_node *start;
};

/*
 * Allocate and first-touch a page-aligned region, then link its nodes into
 * one reproducible randomized cycle. The calling thread must already be
 * pinned to the intended logical CPU.
 */
int pointer_chase_create(struct pointer_chase *chase, size_t node_count,
                         size_t node_spacing_bytes, uint64_t seed,
                         enum pointer_chase_order order);

const char *pointer_chase_order_name(enum pointer_chase_order order);

void pointer_chase_destroy(struct pointer_chase *chase);

#endif
