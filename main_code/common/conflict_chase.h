#ifndef ECE592_CONFLICT_CHASE_H
#define ECE592_CONFLICT_CHASE_H

#include "pointer_chase.h"

#include <stddef.h>
#include <stdint.h>

struct conflict_chase {
    void *allocation;
    size_t allocation_bytes;
    size_t allocation_alignment_bytes;
    size_t line_count;
    size_t conflict_stride_bytes;
    uint64_t seed;
    struct chase_node *start;
};

/*
 * Build one randomized dependent cycle whose nodes are separated by a fixed
 * conflict stride. The fixed byte offset within each stride-sized region keeps
 * low address bits controlled while line_count is varied.
 */
int conflict_chase_create(struct conflict_chase *chase, size_t line_count,
                          size_t conflict_stride_bytes, uint64_t seed);

void conflict_chase_destroy(struct conflict_chase *chase);

#endif
