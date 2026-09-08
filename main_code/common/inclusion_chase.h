#ifndef ECE592_INCLUSION_CHASE_H
#define ECE592_INCLUSION_CHASE_H

#include "pointer_chase.h"

#include <stddef.h>
#include <stdint.h>

struct inclusion_chase {
    struct pointer_chase probe;
    struct pointer_chase pressure;
    uint64_t seed;
};

/*
 * Build two independent randomized dependent cycles. The probe cycle is timed
 * before and after walking the pressure cycle; any probe slowdown after
 * pressure is timing evidence about reuse/inclusion behavior.
 */
int inclusion_chase_create(struct inclusion_chase *chase,
                           size_t probe_node_count,
                           size_t pressure_node_count,
                           size_t node_spacing_bytes,
                           uint64_t seed);

void inclusion_chase_destroy(struct inclusion_chase *chase);

#endif
