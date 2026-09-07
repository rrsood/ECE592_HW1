#ifndef ECE592_SPATIAL_CHASE_H
#define ECE592_SPATIAL_CHASE_H

#include "pointer_chase.h"

#include <stddef.h>
#include <stdint.h>

struct spatial_chase {
    void *allocation;
    size_t allocation_bytes;
    size_t allocation_alignment_bytes;
    size_t region_count;
    size_t region_spacing_bytes;
    size_t probe_offset_bytes;
    uint64_t seed;
    struct chase_node *start;
};

/*
 * Build one read-only measurement cycle with two dependent nodes per region:
 * region base -> region base + probe offset -> next randomized region base.
 * The calling thread must already be pinned so first-touch memory is local.
 */
int spatial_chase_create(struct spatial_chase *chase, size_t region_count,
                         size_t region_spacing_bytes,
                         size_t probe_offset_bytes, uint64_t seed);

void spatial_chase_destroy(struct spatial_chase *chase);

#endif
