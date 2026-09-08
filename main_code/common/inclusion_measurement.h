#ifndef ECE592_INCLUSION_MEASUREMENT_H
#define ECE592_INCLUSION_MEASUREMENT_H

#include "inclusion_chase.h"

#include <stddef.h>
#include <stdint.h>

struct inclusion_measurement_config {
    size_t timed_sample_count;
    size_t warmup_batch_count;
    size_t probe_accesses_per_sample;
    size_t pressure_accesses_per_sample;
};

struct inclusion_measurement_results {
    uint64_t *probe_before_ticks;
    uint64_t *pressure_ticks;
    uint64_t *probe_after_ticks;
    uint64_t *timer_overhead_ticks;
    size_t sample_count;
    size_t zero_probe_before_count;
    size_t zero_pressure_count;
    size_t zero_probe_after_count;
    size_t zero_overhead_count;
    struct chase_node *final_probe_node;
    struct chase_node *final_pressure_node;
};

/*
 * For each sample:
 *   1. prime a probe segment outside timing, then time that same segment,
 *   2. time at least one full traversal of the pressure cycle,
 *   3. time the identical probe segment again from its saved start,
 *   4. record empty timer overhead.
 *
 * The raw arrays are preserved so analysis can use distributions, not only
 * averages. The caller must initialize the timer and pin before allocation.
 * Pressure counts smaller than pressure.node_count are rejected. A full
 * traversal does not guarantee eviction or identify an inclusion policy.
 * Probe batches longer than the probe cycle include repeated addresses.
 */
int inclusion_measurement_run(
    const struct inclusion_chase *chase,
    const struct inclusion_measurement_config *config,
    struct inclusion_measurement_results *results);

void inclusion_measurement_results_destroy(
    struct inclusion_measurement_results *results);

#endif
