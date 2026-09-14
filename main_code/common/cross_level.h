#ifndef ECE592_CROSS_LEVEL_H
#define ECE592_CROSS_LEVEL_H

/*
 * ECE 592 Homework I, Section 8.2 item 7: inclusion/exclusion behavior.
 *
 * EXPERIMENTAL QUESTION
 * --------------------------------------------------------------------------
 * When a cache line is displaced from the shared last-level cache (LLC), is
 * the copy that lives in the measuring core's PRIVATE caches (L1D/L2)
 * invalidated as well?
 *
 *   - If yes, the LLC enforces inclusion: an LLC eviction must back-invalidate
 *     every private copy so the LLC remains a superset.  A line that was a
 *     private hit before the pressure becomes a DRAM-latency access after it.
 *   - If no, the LLC is non-inclusive or exclusive/victim-like: the private
 *     copy survives independently, so the reload stays at private-hit latency.
 *
 * WHY THE PRESSURE MUST COME FROM ANOTHER CORE
 * --------------------------------------------------------------------------
 * A single-threaded "walk a big array, then re-probe" test cannot answer the
 * question.  Any array the measuring core walks passes through its own L1 and
 * L2 first, so the target is evicted from every level at once and the reload
 * is slow under every inclusion policy.  The two hypotheses predict the same
 * measurement, so the experiment has no discriminating power.
 *
 * The discriminating condition needs LLC occupancy pressure that does NOT
 * touch the measuring core's private caches.  That is exactly what a helper
 * thread pinned to a DIFFERENT PHYSICAL CORE in the SAME LLC sharing domain
 * provides: it competes for the shared LLC while the measuring core sits idle
 * on a spin flag and keeps its private copies untouched.
 *
 * CONDITIONS IMPLEMENTED
 * --------------------------------------------------------------------------
 *   PRESSURE_SOURCE_NONE    no pressure at all.  Negative control: proves the
 *                           round structure alone does not evict the targets.
 *   PRESSURE_SOURCE_SELF    the measuring thread walks the pressure footprint
 *                           itself.  Positive control: proves the probe can
 *                           detect eviction, and (when the footprint is swept)
 *                           produces the private-eviction latency ladder that
 *                           shows which level supplies the reload.
 *   PRESSURE_SOURCE_HELPER  the discriminating condition described above.
 *
 * MEASUREMENT STRUCTURE (one "round")
 * --------------------------------------------------------------------------
 *   1. prime      walk the whole target cycle once, untimed, so every target
 *                 line is private-resident.
 *   2. baseline   walk the identical cycle again, timing groups of
 *                 accesses_per_sample dependent loads.  This is the
 *                 calibrated "private hit" class, measured with the same code
 *                 path as the probe, so constant loop/timer overhead cancels
 *                 in the comparison.
 *   3. pressure   apply the selected pressure source.
 *   4. probe      walk the identical cycle a third time, from the same start
 *                 node, timing the same groups.  This is the "after pressure"
 *                 class.
 *   5. overhead   one empty timer pair per sample so fence/timer cost is
 *                 characterized rather than blindly subtracted.
 *
 * Every timed group is a true dependency chain (p = p->next), so no memory
 * level parallelism can hide the latency, and the cycle is randomized so no
 * stride prefetcher can rebuild the target set during the probe.
 *
 * The code assigns NO policy label.  It emits the two latency distributions
 * and the parameters; the inference rule lives in the analysis scripts.
 */

#include "affinity.h"
#include "pointer_chase.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Where the LLC occupancy pressure is generated. */
enum cross_level_pressure_source {
    CROSS_LEVEL_PRESSURE_NONE,
    CROSS_LEVEL_PRESSURE_SELF,
    CROSS_LEVEL_PRESSURE_HELPER
};

struct cross_level_config {
    /* Target (probe) working set: sized to stay private-resident. */
    size_t target_bytes;
    size_t target_line_spacing_bytes;

    /* Pressure working set: swept across the suspected LLC capacity. */
    size_t pressure_bytes;
    size_t pressure_line_spacing_bytes;
    enum pointer_chase_order pressure_order;
    size_t pressure_passes_per_round;

    enum cross_level_pressure_source pressure_source;
    int helper_cpu;            /* ignored unless pressure_source is HELPER */
    bool allow_smt_sibling;    /* helper may share the measuring core */

    /* Dependent loads per timed interval.  1 gives the maximum number of
     * samples per round; larger values amortize timer/fence overhead and are
     * required on architectures whose timer ticks slowly (AArch64). */
    size_t accesses_per_sample;

    size_t requested_sample_count;   /* at least 1,000,000 */
    size_t warmup_round_count;
    uint64_t seed;
};

struct cross_level_topology {
    int logical_cpu;
    int physical_core_id;
    int physical_package_id;
};

struct cross_level_results {
    /* One entry per timed sample, in execution order.  Sample i of the
     * baseline array and sample i of the after-pressure array cover the same
     * target addresses in the same order within the same round. */
    uint64_t *baseline_ticks;
    uint64_t *after_pressure_ticks;
    uint64_t *timer_overhead_ticks;

    size_t sample_count;         /* rounds * samples_per_round */
    size_t round_count;
    size_t samples_per_round;
    size_t target_node_count;
    size_t pressure_node_count;

    size_t zero_baseline_count;
    size_t zero_after_pressure_count;
    size_t zero_overhead_count;

    /* Evidence that the pressure actually executed. */
    uint64_t pressure_pass_count;
    uint64_t helper_pass_count;

    struct cross_level_topology measuring;
    struct cross_level_topology helper;
    bool helper_used;
    bool helper_is_smt_sibling;
    bool helper_same_package;
};

/*
 * Read Linux topology IDs for one logical CPU.  Only core/package identity is
 * read; no cache-size or cache-topology file is opened, so this stays inside
 * the Phase-I rules.  Missing files yield -1 rather than an error.
 */
int cross_level_read_topology(int logical_cpu,
                              struct cross_level_topology *topology);

/*
 * Run the experiment.  The calling thread must already be pinned and the
 * architecture timer must already be initialized.  Allocation happens after
 * pinning so first-touch keeps the target pages local to the measuring core.
 */
int cross_level_run(const struct cross_level_config *config,
                    struct cross_level_results *results);

void cross_level_results_destroy(struct cross_level_results *results);

const char *cross_level_pressure_source_name(
    enum cross_level_pressure_source source);

#endif
