#include "eviction_measurement.h"
#include "measurement.h"
#include "timer.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>

static struct chase_node *volatile endpoint;

static __attribute__((noinline)) struct chase_node *walk(
    struct chase_node *node, size_t count)
{
    for (size_t i = 0; i < count; ++i) node = node->next;
    __asm__ __volatile__("" : "+r"(node) : : "memory");
    return node;
}

static int reload(const struct eviction_layout *layout, int pressure,
                  uint64_t *ticks)
{
    /* Prime outside the timed interval, for both conditions. */
    endpoint = walk(layout->target, layout->target_count);
    if (pressure) endpoint = walk(layout->pressure_start, layout->pressure_count);
    uint64_t begin = timer_start();
    struct chase_node *result = walk(layout->target, layout->target_count);
    uint64_t end = timer_stop();
    endpoint = result;
    if (end < begin) { errno = ERANGE; return -1; }
    *ticks = end - begin;
    return 0;
}

void eviction_measurement_destroy(struct eviction_measurement_results *results)
{
    if (results == NULL) return;
    free(results->baseline_ticks);
    free(results->pressure_ticks);
    free(results->overhead_ticks);
    memset(results, 0, sizeof(*results));
}

int eviction_measurement_run(const struct eviction_layout *layout,
    const struct eviction_measurement_config *config,
    struct eviction_measurement_results *results)
{
    if (results == NULL) { errno = EINVAL; return -1; }
    memset(results, 0, sizeof(*results));
    if (layout == NULL || config == NULL || layout->target == NULL ||
        layout->target_count < 2 || layout->pressure_start == NULL ||
        layout->pressure_count < 2 || config->warmup_pairs == 0 ||
        config->sample_count < ECE592_MINIMUM_TIMED_SAMPLES ||
        config->reloads_per_sample != layout->target_count) { errno = EINVAL; return -1; }
    size_t count = config->sample_count;
    if (count > SIZE_MAX / sizeof(uint64_t)) { errno = EOVERFLOW; return -1; }
    results->baseline_ticks = calloc(count, sizeof(uint64_t));
    results->pressure_ticks = calloc(count, sizeof(uint64_t));
    results->overhead_ticks = calloc(count, sizeof(uint64_t));
    if (!results->baseline_ticks || !results->pressure_ticks || !results->overhead_ticks)
        goto fail;
    /* Fault in output pages before timing. */
    for (size_t i = 0; i < count; ++i) {
        ((volatile uint64_t *)results->baseline_ticks)[i] = 0;
        ((volatile uint64_t *)results->pressure_ticks)[i] = 0;
        ((volatile uint64_t *)results->overhead_ticks)[i] = 0;
    }
    for (size_t i = 0; i < config->warmup_pairs; ++i) {
        uint64_t ignored;
        if (reload(layout, 0, &ignored) || reload(layout, 1, &ignored)) goto fail;
    }
    for (size_t i = 0; i < count; ++i) {
        uint64_t baseline, pressured;
        if (i % 2 == 0) {
            if (reload(layout, 0, &baseline) || reload(layout, 1, &pressured)) goto fail;
        } else {
            if (reload(layout, 1, &pressured) || reload(layout, 0, &baseline)) goto fail;
        }
        uint64_t begin = timer_start();
        uint64_t end = timer_stop();
        if (end < begin) { errno = ERANGE; goto fail; }
        results->baseline_ticks[i] = baseline;
        results->pressure_ticks[i] = pressured;
        results->overhead_ticks[i] = end - begin;
        if (baseline == 0u) ++results->zero_baseline_count;
        if (pressured == 0u) ++results->zero_pressure_count;
        if (results->overhead_ticks[i] == 0u) ++results->zero_overhead_count;
    }
    results->event_count = count;
    return 0;
fail:
    {
        int saved_errno = errno;
        eviction_measurement_destroy(results);
        errno = saved_errno;
        return -1;
    }
}

#ifdef ECE592_EVICTION_MEASUREMENT_SELF_TEST
#include "affinity.h"
#include <stdio.h>
int main(int argc, char **argv)
{
    char *end;
    if (argc != 2) return 2;
    long cpu = strtol(argv[1], &end, 10);
    if (*end || end == argv[1] || cpu < 0 || cpu > 2147483647L) return 2;
    struct affinity_info affinity;
    struct timer_info timer;
    struct eviction_layout layout;
    struct eviction_measurement_results results;
    size_t targets[] = {0, sizeof(struct chase_node)};
    size_t offsets[] = {2 * sizeof(struct chase_node), 3 * sizeof(struct chase_node)};
    struct eviction_measurement_config config = {1000000, 2, 100};
    if (affinity_pin_current_thread((int)cpu, &affinity) || timer_init(&timer) ||
        eviction_layout_create_targets(&layout, targets, 2, offsets, 2, 592)) return 1;
    if (eviction_measurement_run(&layout, &config, &results)) {
        perror("eviction_measurement_run"); eviction_layout_destroy(&layout); return 1;
    }
    printf("sample_count=%zu\nraw_batch_pairs=%zu\nstatus=ok\n",
           config.sample_count, results.event_count);
    eviction_measurement_destroy(&results);
    eviction_layout_destroy(&layout);
    return 0;
}
#endif
