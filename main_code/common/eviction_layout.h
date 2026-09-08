#ifndef ECE592_EVICTION_LAYOUT_H
#define ECE592_EVICTION_LAYOUT_H

#include "pointer_chase.h"

/* Explicit virtual offsets are candidates, not proof of cache congruence.
 * The caller pins before allocation and preserves offsets/seed as metadata.
 * One arena gives the target and pressure addresses a known relative layout.
 */
struct eviction_layout {
    void *allocation;
    size_t allocation_bytes;
    struct chase_node *target;
    struct chase_node *pressure_start;
    size_t *target_offsets;
    size_t *pressure_offsets;
    size_t pressure_count;
    size_t target_count;
    uint64_t seed;
};

int eviction_layout_create(struct eviction_layout *layout,
                           size_t target_offset,
                           const size_t *pressure_offsets,
                           size_t pressure_count, uint64_t seed);
void eviction_layout_destroy(struct eviction_layout *layout);
int eviction_layout_create_targets(struct eviction_layout *layout,
    const size_t *target_offsets, size_t target_count,
    const size_t *pressure_offsets, size_t pressure_count, uint64_t seed);

#endif
