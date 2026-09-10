/* ============================================================================
 * timer_overhead.c
 *
 * Characterizes the timer/fence overhead of the exact start/stop bracket used
 * by cache_bench.c, by timing an EMPTY bracket (no work between the reads).
 *
 * ECE 592 Homework I -- Phase I companion tool.
 *
 * WHY THIS EXISTS
 * ---------------
 * The spec requires it twice:
 *   "Measure the empty timing sequence as well so you know the timer/fence
 *    overhead distribution."
 *   "Still measure the empty pair. Report its distribution; do not blindly
 *    subtract one minimum from every sample."
 *
 * HOW THE RESULT IS USED (and how it is NOT used)
 * -----------------------------------------------
 * This overhead is NOT subtracted from cache_bench samples. Two reasons:
 *   (1) The spec explicitly warns against a fragile blind subtraction.
 *   (2) Batching already renders it negligible. If the empty bracket costs
 *       ~40 ticks and cache_bench uses N_per_batch = 1000, the overhead
 *       contributes 40/1000 = 0.04 ticks per access -- roughly 1% of a ~4-tick
 *       L1 hit, and utterly invisible against a ~250-tick DRAM access.
 *
 * Its actual purpose is to JUSTIFY the choice of N. Reporting the empty-bracket
 * distribution alongside the measurements demonstrates quantitatively that the
 * instrumentation is not what the staircase is made of, which is the claim the
 * spec asks us to be able to defend.
 *
 * The timer routines below are duplicated verbatim from cache_bench.c rather
 * than shared through a header, so that this tool measures exactly the bracket
 * under test with no possibility of divergence.
 *
 * USAGE
 * -----
 *   ./timer_overhead <num_samples>
 *   stdout : sample_index,ticks_elapsed   (ticks for one empty bracket)
 *   stderr : '#'-prefixed metadata
 *
 * Example:
 *   taskset -c 4 ./timer_overhead 1000000 \
 *       > timer_overhead.csv 2> timer_overhead.meta
 *
 * BUILD
 * -----
 *   gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer \
 *       -o timer_overhead timer_overhead.c
 * ==========================================================================*/

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>
#include <x86intrin.h>

#define SAMPLE_MIGRATED UINT64_MAX

/* Identical to cache_bench.c -- see that file for the full rationale on why
 * RDTSCP is used at both ends and why the leading LFENCE is retained despite
 * being largely redundant. */
static inline uint64_t tsc_start(unsigned *aux_out)
{
    uint64_t t;
    _mm_lfence();
    t = __rdtscp(aux_out);
    _mm_lfence();
    return t;
}

static inline uint64_t tsc_stop(unsigned *aux_out)
{
    uint64_t t;
    t = __rdtscp(aux_out);
    _mm_lfence();
    return t;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <num_samples>\n", argv[0]);
        return 1;
    }

    uint64_t num_samples = strtoull(argv[1], NULL, 10);
    if (num_samples == 0) {
        fprintf(stderr, "ERROR: num_samples must be > 0\n");
        return 1;
    }

    uint64_t *samples = malloc((size_t)num_samples * sizeof(*samples));
    if (!samples) {
        fprintf(stderr, "ERROR: malloc failed for %" PRIu64 " samples\n",
                num_samples);
        return 1;
    }

    /* Warm-up: run the bracket a few times untimed so that the instruction
     * cache, branch predictors, and any first-call effects have settled before
     * the recorded samples begin -- the same principle as cache_bench's
     * warm-up, applied to the instrumentation itself. */
    for (uint64_t i = 0; i < 1000; i++) {
        unsigned a, b;
        (void)tsc_start(&a);
        (void)tsc_stop(&b);
    }

    unsigned aux_first        = 0;
    uint64_t migrated_samples = 0;

    for (uint64_t r = 0; r < num_samples; r++) {
        unsigned aux_a, aux_b;

        /* THE EMPTY BRACKET: nothing whatsoever between the two reads. The
         * measured interval is therefore the cost of the instrumentation
         * itself -- two RDTSCPs and three LFENCEs -- and nothing else. */
        uint64_t t0 = tsc_start(&aux_a);
        uint64_t t1 = tsc_stop(&aux_b);

        if (r == 0) aux_first = aux_a;

        if (aux_a != aux_b) {
            samples[r] = SAMPLE_MIGRATED;
            migrated_samples++;
        } else {
            samples[r] = t1 - t0;
        }
    }

    fprintf(stderr, "# cache_bench_metadata_version=1\n");
    fprintf(stderr, "# experiment=timer_overhead\n");
    fprintf(stderr, "# num_samples_requested=%" PRIu64 "\n", num_samples);
    fprintf(stderr, "# num_samples_emitted=%" PRIu64 "\n",
            num_samples - migrated_samples);
    fprintf(stderr, "# timer_method=lfence;rdtscp;lfence / rdtscp;lfence\n");
    fprintf(stderr, "# timer_units=TSC_ticks\n");
    fprintf(stderr, "# bracket_contents=empty\n");
    fprintf(stderr, "# logical_cpu_from_tsc_aux=%u\n", aux_first);
    fprintf(stderr, "# migrated_samples_excluded=%" PRIu64 "\n",
            migrated_samples);

    printf("sample_index,ticks_elapsed\n");
    for (uint64_t r = 0; r < num_samples; r++) {
        if (samples[r] == SAMPLE_MIGRATED) continue;
        printf("%" PRIu64 ",%" PRIu64 "\n", r, samples[r]);
    }

    free(samples);
    return 0;
}
