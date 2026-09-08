#ifndef ECE592_EVICTION_MEASUREMENT_H
#define ECE592_EVICTION_MEASUREMENT_H
#include "eviction_layout.h"

struct eviction_measurement_config {
    size_t sample_count;
    size_t reloads_per_sample; /* Must equal layout.target_count, >= 2. */
    size_t warmup_pairs;
};

struct eviction_measurement_results {
    /* One timer interval per full target pass, one entry per sample.
     * Each target node is loaded once. Preserve unadjusted batch ticks. */
    uint64_t *baseline_ticks;
    uint64_t *pressure_ticks;
    uint64_t *overhead_ticks;
    size_t event_count;
    size_t zero_baseline_count;
    size_t zero_pressure_count;
    size_t zero_overhead_count;
};

/* Caller initializes architecture timer and pins before creating the layout.
 * No-pressure baseline and pressure condition alternate execution order.
 * Targets form a randomized cycle separate from the pressure cycle.
 * Each condition primes all targets, then times one pass through them.
 * Target nodes must occupy distinct inferred cache lines in production:
 * distinct pointer addresses alone do not ensure distinct cache lines.
 * Timer resolution and upper-level residency still require calibration.
 * This diagnostic does not establish lower-level eviction or cache policy. */
int eviction_measurement_run(const struct eviction_layout *layout,
    const struct eviction_measurement_config *config,
    struct eviction_measurement_results *results);
void eviction_measurement_destroy(struct eviction_measurement_results *results);
#endif
