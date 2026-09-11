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

static struct chase_node *volatile final_node_sink;
static struct chase_node *volatile independent_final_node_sinks[8];

static ECE592_NOINLINE struct chase_node *
run_dependent_batch(struct chase_node *current, size_t access_count)
{
    for (size_t access = 0; access < access_count; ++access) {
        current = current->next;
    }

    /* Keep the returned dependency-chain state observable to the compiler. */
    __asm__ __volatile__("" : "+r"(current) : : "memory");
    return current;
}

void measurement_results_destroy(struct measurement_results *results)
{
    if (results == NULL) {
        return;
    }

    free(results->elapsed_ticks);
    free(results->timer_overhead_ticks);
    memset(results, 0, sizeof(*results));
}

int measurement_run_from_start(struct chase_node *start,
                               const struct measurement_config *config,
                               struct measurement_results *results)
{
    struct chase_node *current;

    if (start == NULL || config == NULL ||
        results == NULL ||
        config->timed_sample_count < ECE592_MINIMUM_TIMED_SAMPLES ||
        config->dependent_accesses_per_sample == 0u ||
        config->timed_sample_count > SIZE_MAX / sizeof(uint64_t)) {
        errno = EINVAL;
        return -1;
    }

    memset(results, 0, sizeof(*results));
    results->elapsed_ticks =
        malloc(config->timed_sample_count * sizeof(*results->elapsed_ticks));
    if (results->elapsed_ticks == NULL) {
        return -1;
    }

    results->timer_overhead_ticks =
        malloc(config->timed_sample_count *
               sizeof(*results->timer_overhead_ticks));
    if (results->timer_overhead_ticks == NULL) {
        measurement_results_destroy(results);
        return -1;
    }

    current = start;
    for (size_t warmup = 0; warmup < config->warmup_batch_count; ++warmup) {
        current = run_dependent_batch(
            current, config->dependent_accesses_per_sample);
    }

    for (size_t sample = 0; sample < config->timed_sample_count; ++sample) {
        uint64_t measured_start;
        uint64_t measured_stop;
        uint64_t overhead_start;
        uint64_t overhead_stop;

        measured_start = timer_start();
        current = run_dependent_batch(
            current, config->dependent_accesses_per_sample);
        measured_stop = timer_stop();

        overhead_start = timer_start();
        overhead_stop = timer_stop();

        if (measured_stop < measured_start || overhead_stop < overhead_start) {
            measurement_results_destroy(results);
            errno = ERANGE;
            return -1;
        }

        results->elapsed_ticks[sample] = measured_stop - measured_start;
        results->timer_overhead_ticks[sample] =
            overhead_stop - overhead_start;

        if (results->elapsed_ticks[sample] == 0u) {
            ++results->zero_elapsed_count;
        }
        if (results->timer_overhead_ticks[sample] == 0u) {
            ++results->zero_overhead_count;
        }
    }

    results->sample_count = config->timed_sample_count;
    results->final_node = current;
    final_node_sink = current;
    return 0;
}

int measurement_run(const struct pointer_chase *chase,
                    const struct measurement_config *config,
                    struct measurement_results *results)
{
    if (chase == NULL) {
        errno = EINVAL;
        return -1;
    }

    return measurement_run_from_start(chase->start, config, results);
}

static ECE592_NOINLINE void
run_independent_rounds(struct chase_node **current, size_t round_count)
{
    for (size_t round = 0; round < round_count; ++round) {
        current[0] = current[0]->next;
        current[1] = current[1]->next;
        current[2] = current[2]->next;
        current[3] = current[3]->next;
        current[4] = current[4]->next;
        current[5] = current[5]->next;
        current[6] = current[6]->next;
        current[7] = current[7]->next;
    }

    __asm__ __volatile__("" : "+r"(current[0]), "+r"(current[1]),
                         "+r"(current[2]), "+r"(current[3]),
                         "+r"(current[4]), "+r"(current[5]),
                         "+r"(current[6]), "+r"(current[7]) : : "memory");
}

int measurement_run_independent_eight_lane(
    const struct pointer_chase *chase,
    const struct measurement_config *config,
    struct measurement_results *results)
{
    struct chase_node *current[8];
    struct chase_node *position;
    size_t next_lane = 0u;

    if (chase == NULL || chase->start == NULL || chase->node_count < 8u ||
        config == NULL || results == NULL ||
        config->timed_sample_count < ECE592_MINIMUM_TIMED_SAMPLES ||
        config->dependent_accesses_per_sample == 0u ||
        config->dependent_accesses_per_sample % 8u != 0u ||
        config->timed_sample_count > SIZE_MAX / sizeof(uint64_t)) {
        errno = EINVAL;
        return -1;
    }

    memset(results, 0, sizeof(*results));
    results->elapsed_ticks =
        malloc(config->timed_sample_count * sizeof(*results->elapsed_ticks));
    if (results->elapsed_ticks == NULL) {
        return -1;
    }
    results->timer_overhead_ticks =
        malloc(config->timed_sample_count *
               sizeof(*results->timer_overhead_ticks));
    if (results->timer_overhead_ticks == NULL) {
        measurement_results_destroy(results);
        return -1;
    }

    /* Select eight evenly separated starting positions in one cycle. */
    position = chase->start;
    for (size_t step = 0; step < chase->node_count && next_lane < 8u;
         ++step) {
        if (step == (next_lane * chase->node_count) / 8u) {
            current[next_lane++] = position;
        }
        position = position->next;
    }
    if (next_lane != 8u) {
        measurement_results_destroy(results);
        errno = EINVAL;
        return -1;
    }

    for (size_t warmup = 0; warmup < config->warmup_batch_count; ++warmup) {
        run_independent_rounds(
            current, config->dependent_accesses_per_sample / 8u);
    }

    for (size_t sample = 0; sample < config->timed_sample_count; ++sample) {
        uint64_t measured_start = timer_start();
        uint64_t measured_stop;
        uint64_t overhead_start;
        uint64_t overhead_stop;

        run_independent_rounds(
            current, config->dependent_accesses_per_sample / 8u);
        measured_stop = timer_stop();
        overhead_start = timer_start();
        overhead_stop = timer_stop();

        if (measured_stop < measured_start || overhead_stop < overhead_start) {
            measurement_results_destroy(results);
            errno = ERANGE;
            return -1;
        }
        results->elapsed_ticks[sample] = measured_stop - measured_start;
        results->timer_overhead_ticks[sample] =
            overhead_stop - overhead_start;
        if (results->elapsed_ticks[sample] == 0u) {
            ++results->zero_elapsed_count;
        }
        if (results->timer_overhead_ticks[sample] == 0u) {
            ++results->zero_overhead_count;
        }
    }

    results->sample_count = config->timed_sample_count;
    results->final_node = current[0];
    for (size_t lane = 0; lane < 8u; ++lane) {
        independent_final_node_sinks[lane] = current[lane];
    }
    return 0;
}

#if defined(ECE592_MEASUREMENT_SELF_TEST)

#include "affinity.h"

#include <limits.h>

static int parse_logical_cpu(const char *text, int *logical_cpu)
{
    char *end;
    long value;

    errno = 0;
    end = NULL;
    value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        value < 0 || value > INT_MAX) {
        return -1;
    }

    *logical_cpu = (int)value;
    return 0;
}

static int parse_access_count(const char *text, size_t *access_count)
{
    char *end;
    unsigned long long value;

    if (text == NULL || access_count == NULL || text[0] == '-') {
        return -1;
    }

    errno = 0;
    end = NULL;
    value = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value == 0u ||
        value > SIZE_MAX) {
        return -1;
    }

    *access_count = (size_t)value;
    return 0;
}

static void find_range(const uint64_t *values, size_t count,
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
    struct measurement_config config;
    struct affinity_info affinity;
    struct measurement_results results;
    struct pointer_chase chase;
    struct timer_info timer;
    uint64_t elapsed_minimum;
    uint64_t elapsed_maximum;
    uint64_t overhead_minimum;
    uint64_t overhead_maximum;
    int logical_cpu;

    if (argc != 3 || parse_logical_cpu(argv[1], &logical_cpu) != 0 ||
        parse_access_count(argv[2],
                           &config.dependent_accesses_per_sample) != 0) {
        fprintf(stderr,
                "usage: %s <logical-cpu> <dependent-accesses-per-sample>\n",
                argv[0]);
        return 2;
    }

    config.timed_sample_count = ECE592_MINIMUM_TIMED_SAMPLES;
    config.warmup_batch_count = 1000u;

    if (affinity_pin_current_thread(logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (timer_init(&timer) != 0) {
        fprintf(stderr, "error: timer initialization failed\n");
        return 1;
    }
    if (pointer_chase_create(&chase, 4096u, sizeof(struct chase_node),
                             UINT64_C(592), POINTER_CHASE_RANDOMIZED) != 0) {
        perror("pointer_chase_create");
        return 1;
    }
    if (measurement_run(&chase, &config, &results) != 0) {
        perror("measurement_run");
        pointer_chase_destroy(&chase);
        return 1;
    }

    find_range(results.elapsed_ticks, results.sample_count,
               &elapsed_minimum, &elapsed_maximum);
    find_range(results.timer_overhead_ticks, results.sample_count,
               &overhead_minimum, &overhead_maximum);

    printf("timer_name=%s\n", timer.name);
    printf("timer_unit=%s\n", timer.unit);
    printf("timed_sample_count=%zu\n", results.sample_count);
    printf("warmup_batch_count=%zu\n", config.warmup_batch_count);
    printf("dependent_accesses_per_sample=%zu\n",
           config.dependent_accesses_per_sample);
    printf("raw_elapsed_min=%" PRIu64 "\n", elapsed_minimum);
    printf("raw_elapsed_max=%" PRIu64 "\n", elapsed_maximum);
    printf("raw_overhead_min=%" PRIu64 "\n", overhead_minimum);
    printf("raw_overhead_max=%" PRIu64 "\n", overhead_maximum);
    printf("zero_elapsed_count=%zu\n", results.zero_elapsed_count);
    printf("zero_overhead_count=%zu\n", results.zero_overhead_count);
    printf("affinity_allowed_cpu_count=%d\n", affinity.allowed_cpu_count);

    for (size_t sample = 0; sample < 5u; ++sample) {
        printf("sample_%zu_elapsed=%" PRIu64
               " overhead=%" PRIu64 "\n",
               sample, results.elapsed_ticks[sample],
               results.timer_overhead_ticks[sample]);
    }

    if (results.sample_count != ECE592_MINIMUM_TIMED_SAMPLES ||
        results.zero_elapsed_count != 0u || results.final_node == NULL) {
        fprintf(stderr, "error: measurement self-test invariant failed\n");
        measurement_results_destroy(&results);
        pointer_chase_destroy(&chase);
        return 1;
    }

    printf("raw_sample_arrays_populated=true\n");
    printf("status=ok\n");

    measurement_results_destroy(&results);
    pointer_chase_destroy(&chase);
    return 0;
}

#endif
