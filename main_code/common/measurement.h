#ifndef ECE592_MEASUREMENT_H
#define ECE592_MEASUREMENT_H

#include "pointer_chase.h"

#include <stddef.h>
#include <stdint.h>

#define ECE592_MINIMUM_TIMED_SAMPLES ((size_t)1000000)

struct measurement_config {
    size_t timed_sample_count;
    size_t warmup_batch_count;
    size_t dependent_accesses_per_sample;
};

struct measurement_results {
    uint64_t *elapsed_ticks;
    uint64_t *timer_overhead_ticks;
    size_t sample_count;
    size_t zero_elapsed_count;
    size_t zero_overhead_count;
    struct chase_node *final_node;
};

/*
 * Run a warmed, dependent pointer chase and preserve every raw batch time and
 * every empty timer/fence time. The caller must initialize the timer first.
 */
int measurement_run(const struct pointer_chase *chase,
                    const struct measurement_config *config,
                    struct measurement_results *results);

/*
 * Lower-level form used by experiments that build their own dependent
 * chase cycle. The start node must be non-NULL and must eventually form a
 * valid cycle so repeated batches can keep traversing safely.
 */
int measurement_run_from_start(struct chase_node *start,
                               const struct measurement_config *config,
                               struct measurement_results *results);

void measurement_results_destroy(struct measurement_results *results);

#endif
