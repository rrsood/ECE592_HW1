#include "inclusion_measurement.h"

#include "measurement.h"
#include "timer.h"

#include <errno.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__GNUC__)
#define ECE592_NOINLINE __attribute__((noinline))
#else
#define ECE592_NOINLINE
#endif

static struct chase_node *volatile final_probe_node_sink;
static struct chase_node *volatile final_pressure_node_sink;

static ECE592_NOINLINE struct chase_node *
run_dependent_batch(struct chase_node *current, size_t access_count)
{
    for (size_t access = 0; access < access_count; ++access) {
        current = current->next;
    }

    __asm__ __volatile__("" : "+r"(current) : : "memory");
    return current;
}

static int allocate_array(uint64_t **array, size_t count)
{
    if (count > SIZE_MAX / sizeof(**array)) {
        errno = EOVERFLOW;
        return -1;
    }

    *array = malloc(count * sizeof(**array));
    return *array == NULL ? -1 : 0;
}

void inclusion_measurement_results_destroy(
    struct inclusion_measurement_results *results)
{
    if (results == NULL) {
        return;
    }

    free(results->probe_before_ticks);
    free(results->pressure_ticks);
    free(results->probe_after_ticks);
    free(results->timer_overhead_ticks);
    memset(results, 0, sizeof(*results));
}

int inclusion_measurement_run(
    const struct inclusion_chase *chase,
    const struct inclusion_measurement_config *config,
    struct inclusion_measurement_results *results)
{
    struct chase_node *probe_current;
    struct chase_node *pressure_current;

    if (chase == NULL || chase->probe.start == NULL ||
        chase->pressure.start == NULL || config == NULL || results == NULL ||
        config->timed_sample_count < ECE592_MINIMUM_TIMED_SAMPLES ||
        config->warmup_batch_count == 0u ||
        config->probe_accesses_per_sample == 0u ||
        chase->pressure.node_count == 0u ||
        config->pressure_accesses_per_sample < chase->pressure.node_count) {
        errno = EINVAL;
        return -1;
    }

    memset(results, 0, sizeof(*results));
    if (allocate_array(&results->probe_before_ticks,
                       config->timed_sample_count) != 0 ||
        allocate_array(&results->pressure_ticks,
                       config->timed_sample_count) != 0 ||
        allocate_array(&results->probe_after_ticks,
                       config->timed_sample_count) != 0 ||
        allocate_array(&results->timer_overhead_ticks,
                       config->timed_sample_count) != 0) {
        inclusion_measurement_results_destroy(results);
        return -1;
    }

    probe_current = chase->probe.start;
    pressure_current = chase->pressure.start;
    for (size_t warmup = 0; warmup < config->warmup_batch_count; ++warmup) {
        probe_current = run_dependent_batch(
            probe_current, config->probe_accesses_per_sample);
        pressure_current = run_dependent_batch(
            pressure_current, config->pressure_accesses_per_sample);
    }

    for (size_t sample = 0; sample < config->timed_sample_count; ++sample) {
        struct chase_node *probe_sample_start = probe_current;
        uint64_t before_start;
        uint64_t before_stop;
        uint64_t pressure_start;
        uint64_t pressure_stop;
        uint64_t after_start;
        uint64_t after_stop;
        uint64_t overhead_start;
        uint64_t overhead_stop;

        /* Prime exactly the segment that both timed probes will revisit.
         * Keep its result observable without adding stores inside timing. */
        final_probe_node_sink = run_dependent_batch(
            probe_sample_start, config->probe_accesses_per_sample);

        before_start = timer_start();
        probe_current = run_dependent_batch(
            probe_sample_start, config->probe_accesses_per_sample);
        before_stop = timer_stop();
        final_probe_node_sink = probe_current;

        pressure_start = timer_start();
        pressure_current = run_dependent_batch(
            pressure_current, config->pressure_accesses_per_sample);
        pressure_stop = timer_stop();

        after_start = timer_start();
        probe_current = run_dependent_batch(
            probe_sample_start, config->probe_accesses_per_sample);
        after_stop = timer_stop();

        overhead_start = timer_start();
        overhead_stop = timer_stop();

        if (before_stop < before_start ||
            pressure_stop < pressure_start ||
            after_stop < after_start ||
            overhead_stop < overhead_start) {
            inclusion_measurement_results_destroy(results);
            errno = ERANGE;
            return -1;
        }

        results->probe_before_ticks[sample] = before_stop - before_start;
        results->pressure_ticks[sample] = pressure_stop - pressure_start;
        results->probe_after_ticks[sample] = after_stop - after_start;
        results->timer_overhead_ticks[sample] =
            overhead_stop - overhead_start;

        if (results->probe_before_ticks[sample] == 0u) {
            ++results->zero_probe_before_count;
        }
        if (results->pressure_ticks[sample] == 0u) {
            ++results->zero_pressure_count;
        }
        if (results->probe_after_ticks[sample] == 0u) {
            ++results->zero_probe_after_count;
        }
        if (results->timer_overhead_ticks[sample] == 0u) {
            ++results->zero_overhead_count;
        }
    }

    results->sample_count = config->timed_sample_count;
    results->final_probe_node = probe_current;
    results->final_pressure_node = pressure_current;
    final_probe_node_sink = probe_current;
    final_pressure_node_sink = pressure_current;
    return 0;
}

#if defined(ECE592_INCLUSION_MEASUREMENT_SELF_TEST)

#include "affinity.h"

#include <limits.h>

static int parse_logical_cpu(const char *text, int *logical_cpu)
{
    char *end;
    long parsed;

    errno = 0;
    end = NULL;
    parsed = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        parsed < 0 || parsed > INT_MAX) {
        return -1;
    }

    *logical_cpu = (int)parsed;
    return 0;
}

static void range(const uint64_t *values, size_t count,
                  uint64_t *minimum, uint64_t *maximum)
{
    *minimum = values[0];
    *maximum = values[0];
    for (size_t index = 1; index < count; ++index) {
        if (values[index] < *minimum) {
            *minimum = values[index];
        }
        if (values[index] > *maximum) {
            *maximum = values[index];
        }
    }
}

int main(int argc, char **argv)
{
    const struct inclusion_measurement_config config = {
        ECE592_MINIMUM_TIMED_SAMPLES,
        1000u,
        64u,
        17u
    };
    struct affinity_info affinity;
    struct inclusion_chase chase;
    struct inclusion_measurement_results results;
    uint64_t before_minimum;
    uint64_t before_maximum;
    uint64_t after_minimum;
    uint64_t after_maximum;
    int logical_cpu;

    if (argc != 2 || parse_logical_cpu(argv[1], &logical_cpu) != 0) {
        fprintf(stderr, "usage: %s <logical-cpu>\n", argv[0]);
        return 2;
    }

    if (affinity_pin_current_thread(logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (timer_init(&(struct timer_info){0}) != 0) {
        fprintf(stderr, "error: timer initialization failed\n");
        return 1;
    }
    if (inclusion_chase_create(&chase, 257u, 17u,
                               sizeof(struct chase_node),
                               UINT64_C(592)) != 0) {
        perror("inclusion_chase_create");
        return 1;
    }
    struct inclusion_measurement_config invalid_config = config;
    invalid_config.pressure_accesses_per_sample = 16u;
    if (inclusion_measurement_run(&chase, &invalid_config, &results) != -1 ||
        errno != EINVAL) {
        fprintf(stderr, "error: incomplete pressure traversal accepted\n");
        inclusion_chase_destroy(&chase);
        return 1;
    }
    if (inclusion_measurement_run(&chase, &config, &results) != 0) {
        perror("inclusion_measurement_run");
        inclusion_chase_destroy(&chase);
        return 1;
    }

    struct chase_node *expected_probe = chase.probe.start;
    size_t expected_steps = (config.timed_sample_count +
        config.warmup_batch_count) * config.probe_accesses_per_sample;
    expected_probe = run_dependent_batch(expected_probe,
                                        expected_steps % chase.probe.node_count);
    if (results.final_probe_node != expected_probe ||
        results.final_pressure_node != chase.pressure.start) {
        fprintf(stderr, "error: unexpected traversal endpoint\n");
        inclusion_measurement_results_destroy(&results);
        inclusion_chase_destroy(&chase);
        return 1;
    }
    printf("incomplete_pressure_rejected=true\n");
    printf("traversal_endpoints_verified=true\n");
    range(results.probe_before_ticks, results.sample_count,
          &before_minimum, &before_maximum);
    range(results.probe_after_ticks, results.sample_count,
          &after_minimum, &after_maximum);

    printf("timed_sample_count=%zu\n", results.sample_count);
    printf("probe_accesses_per_sample=%zu\n",
           config.probe_accesses_per_sample);
    printf("pressure_accesses_per_sample=%zu\n",
           config.pressure_accesses_per_sample);
    printf("probe_before_min=%" PRIu64 "\n", before_minimum);
    printf("probe_before_max=%" PRIu64 "\n", before_maximum);
    printf("probe_after_min=%" PRIu64 "\n", after_minimum);
    printf("probe_after_max=%" PRIu64 "\n", after_maximum);
    printf("zero_probe_before_count=%zu\n", results.zero_probe_before_count);
    printf("zero_probe_after_count=%zu\n", results.zero_probe_after_count);
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);
    printf("raw_sample_arrays_populated=true\n");
    printf("status=ok\n");

    inclusion_measurement_results_destroy(&results);
    inclusion_chase_destroy(&chase);
    return 0;
}

#endif
