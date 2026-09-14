#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "cross_level.h"

#include "timer.h"

#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdbool.h>
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

/*
 * Padding that is comfortably larger than any plausible cache line, used so
 * the two synchronization words cannot land in one line.  The benchmark must
 * not assume the line size it is helping to validate, so this is deliberately
 * generous rather than "one line".
 */
#define ECE592_SYNC_PADDING_BYTES 256

/* Architecture hint that shortens a spin-wait without doing memory traffic. */
static inline void cpu_relax(void)
{
#if defined(__x86_64__) || defined(__i386__)
    __builtin_ia32_pause();
#elif defined(__aarch64__)
    __asm__ __volatile__("yield" ::: "memory");
#else
    __asm__ __volatile__("" ::: "memory");
#endif
}

/* ------------------------------------------------------------------------ */
/* Dependent traversal primitives                                            */
/* ------------------------------------------------------------------------ */

static struct chase_node *volatile cross_level_sink;

/*
 * One dependent batch.  Marked noinline so the traversal cannot be folded
 * into a caller at any optimization level, and the inline asm keeps the final
 * pointer live so the loop cannot be discarded as dead code.
 */
static ECE592_NOINLINE struct chase_node *
run_dependent_batch(struct chase_node *current, size_t access_count)
{
    for (size_t access = 0; access < access_count; ++access) {
        current = current->next;
    }

    __asm__ __volatile__("" : "+r"(current) : : "memory");
    return current;
}

/*
 * Walk group_count groups of group_size dependent loads, timing each group.
 * Every group starts where the previous one stopped, so the whole walk is one
 * uninterrupted dependency chain over the cycle.
 */
static int walk_timed(struct chase_node *start, size_t group_count,
                      size_t group_size, uint64_t *output,
                      size_t *zero_count, struct chase_node **end)
{
    struct chase_node *current = start;

    for (size_t group = 0; group < group_count; ++group) {
        uint64_t started;
        uint64_t stopped;

        started = timer_start();
        current = run_dependent_batch(current, group_size);
        stopped = timer_stop();

        if (stopped < started) {
            errno = ERANGE;
            return -1;
        }

        output[group] = stopped - started;
        if (output[group] == 0u) {
            ++*zero_count;
        }
    }

    cross_level_sink = current;
    if (end != NULL) {
        *end = current;
    }
    return 0;
}

/* Empty start/stop pairs so timer and fence cost is recorded, not assumed. */
static int sample_timer_overhead(size_t count, uint64_t *output,
                                 size_t *zero_count)
{
    for (size_t index = 0; index < count; ++index) {
        uint64_t started = timer_start();
        uint64_t stopped = timer_stop();

        if (stopped < started) {
            errno = ERANGE;
            return -1;
        }

        output[index] = stopped - started;
        if (output[index] == 0u) {
            ++*zero_count;
        }
    }

    return 0;
}

/* ------------------------------------------------------------------------ */
/* Linux topology identity (Phase-I safe: no cache files are opened)         */
/* ------------------------------------------------------------------------ */

static int read_topology_integer(int logical_cpu, const char *leaf, int *value)
{
    char path[256];
    FILE *stream;
    long parsed;
    int written;

    written = snprintf(path, sizeof(path),
                       "/sys/devices/system/cpu/cpu%d/topology/%s",
                       logical_cpu, leaf);
    if (written < 0 || (size_t)written >= sizeof(path)) {
        return -1;
    }

    stream = fopen(path, "r");
    if (stream == NULL) {
        return -1;
    }
    if (fscanf(stream, "%ld", &parsed) != 1) {
        (void)fclose(stream);
        return -1;
    }
    (void)fclose(stream);

    *value = (int)parsed;
    return 0;
}

int cross_level_read_topology(int logical_cpu,
                              struct cross_level_topology *topology)
{
    if (topology == NULL || logical_cpu < 0) {
        errno = EINVAL;
        return -1;
    }

    topology->logical_cpu = logical_cpu;
    topology->physical_core_id = -1;
    topology->physical_package_id = -1;

    (void)read_topology_integer(logical_cpu, "core_id",
                                &topology->physical_core_id);
    (void)read_topology_integer(logical_cpu, "physical_package_id",
                                &topology->physical_package_id);
    return 0;
}

/* ------------------------------------------------------------------------ */
/* Helper thread that generates shared-cache occupancy pressure              */
/* ------------------------------------------------------------------------ */

enum helper_state {
    HELPER_STATE_STARTING = 0,
    HELPER_STATE_READY = 1,
    HELPER_STATE_FAILED = -1
};

struct helper_control {
    pthread_t thread;

    /* Written by the measuring thread, read by the helper. */
    _Atomic unsigned long request;
    char request_padding[ECE592_SYNC_PADDING_BYTES];

    /* Written by the helper, read by the measuring thread. */
    _Atomic unsigned long completed;
    char completed_padding[ECE592_SYNC_PADDING_BYTES];

    _Atomic int state;
    _Atomic int stop;
    char state_padding[ECE592_SYNC_PADDING_BYTES];

    int cpu;
    size_t node_count;
    size_t node_spacing_bytes;
    enum pointer_chase_order order;
    size_t passes_per_round;
    uint64_t seed;

    struct pointer_chase chase;
    struct affinity_info affinity;
    uint64_t passes_done;
    int start_errno;
};

static void *helper_main(void *argument)
{
    struct helper_control *control = argument;
    unsigned long served = 0u;

    /*
     * Pin first, then allocate, so the pressure buffer is first-touched on
     * the helper's own NUMA node and never migrates.
     */
    if (affinity_pin_current_thread(control->cpu, &control->affinity) != 0) {
        control->start_errno = errno;
        atomic_store_explicit(&control->state, HELPER_STATE_FAILED,
                              memory_order_release);
        return NULL;
    }
    if (pointer_chase_create(&control->chase, control->node_count,
                             control->node_spacing_bytes, control->seed,
                             control->order) != 0) {
        control->start_errno = errno;
        atomic_store_explicit(&control->state, HELPER_STATE_FAILED,
                              memory_order_release);
        return NULL;
    }

    atomic_store_explicit(&control->state, HELPER_STATE_READY,
                          memory_order_release);

    for (;;) {
        unsigned long requested;

        /* Idle spin on one word: no traffic that could disturb the LLC. */
        for (;;) {
            requested = atomic_load_explicit(&control->request,
                                             memory_order_acquire);
            if (requested != served) {
                break;
            }
            if (atomic_load_explicit(&control->stop,
                                     memory_order_acquire) != 0) {
                return NULL;
            }
            cpu_relax();
        }

        for (size_t pass = 0; pass < control->passes_per_round; ++pass) {
            cross_level_sink = run_dependent_batch(control->chase.start,
                                                   control->node_count);
            ++control->passes_done;
        }

        served = requested;
        atomic_store_explicit(&control->completed, served,
                              memory_order_release);
    }
}

static int helper_start(struct helper_control *control)
{
    int state;

    atomic_store_explicit(&control->request, 0u, memory_order_relaxed);
    atomic_store_explicit(&control->completed, 0u, memory_order_relaxed);
    atomic_store_explicit(&control->state, HELPER_STATE_STARTING,
                          memory_order_relaxed);
    atomic_store_explicit(&control->stop, 0, memory_order_relaxed);

    if (pthread_create(&control->thread, NULL, helper_main, control) != 0) {
        return -1;
    }

    do {
        state = atomic_load_explicit(&control->state, memory_order_acquire);
        cpu_relax();
    } while (state == HELPER_STATE_STARTING);

    if (state != HELPER_STATE_READY) {
        (void)pthread_join(control->thread, NULL);
        errno = control->start_errno != 0 ? control->start_errno : EIO;
        return -1;
    }

    return 0;
}

static void helper_stop(struct helper_control *control)
{
    atomic_store_explicit(&control->stop, 1, memory_order_release);
    (void)pthread_join(control->thread, NULL);
    pointer_chase_destroy(&control->chase);
}

/* Request one pressure episode and wait until the helper reports completion. */
static void helper_run_round(struct helper_control *control,
                             unsigned long ticket)
{
    atomic_store_explicit(&control->request, ticket, memory_order_release);
    while (atomic_load_explicit(&control->completed,
                                memory_order_acquire) != ticket) {
        cpu_relax();
    }
}

/* ------------------------------------------------------------------------ */
/* Experiment driver                                                         */
/* ------------------------------------------------------------------------ */

const char *cross_level_pressure_source_name(
    enum cross_level_pressure_source source)
{
    switch (source) {
    case CROSS_LEVEL_PRESSURE_NONE:
        return "none";
    case CROSS_LEVEL_PRESSURE_SELF:
        return "self";
    case CROSS_LEVEL_PRESSURE_HELPER:
        return "helper";
    default:
        return "invalid";
    }
}

void cross_level_results_destroy(struct cross_level_results *results)
{
    if (results == NULL) {
        return;
    }

    free(results->baseline_ticks);
    free(results->after_pressure_ticks);
    free(results->timer_overhead_ticks);
    memset(results, 0, sizeof(*results));
}

static int allocate_sample_array(uint64_t **array, size_t count)
{
    if (count == 0u || count > SIZE_MAX / sizeof(**array)) {
        errno = EOVERFLOW;
        return -1;
    }

    *array = malloc(count * sizeof(**array));
    return *array == NULL ? -1 : 0;
}

static int validate_config(const struct cross_level_config *config,
                           size_t *target_nodes, size_t *pressure_nodes)
{
    size_t targets;
    size_t pressure;

    if (config == NULL ||
        config->target_line_spacing_bytes < sizeof(struct chase_node) ||
        config->target_line_spacing_bytes % _Alignof(struct chase_node) != 0u ||
        config->pressure_line_spacing_bytes < sizeof(struct chase_node) ||
        config->pressure_line_spacing_bytes %
            _Alignof(struct chase_node) != 0u ||
        config->target_bytes < 2u * config->target_line_spacing_bytes ||
        config->accesses_per_sample == 0u ||
        config->requested_sample_count == 0u) {
        errno = EINVAL;
        return -1;
    }

    targets = config->target_bytes / config->target_line_spacing_bytes;
    if (targets < 2u || targets % config->accesses_per_sample != 0u) {
        /* One lap must divide evenly into timed groups so that every sample
         * covers a whole number of distinct target lines. */
        errno = EINVAL;
        return -1;
    }

    pressure = 0u;
    if (config->pressure_source != CROSS_LEVEL_PRESSURE_NONE) {
        pressure = config->pressure_bytes /
                   config->pressure_line_spacing_bytes;
        if (pressure < 2u || config->pressure_passes_per_round == 0u) {
            errno = EINVAL;
            return -1;
        }
    }

    if (config->pressure_source == CROSS_LEVEL_PRESSURE_HELPER &&
        config->helper_cpu < 0) {
        errno = EINVAL;
        return -1;
    }

    *target_nodes = targets;
    *pressure_nodes = pressure;
    return 0;
}

int cross_level_run(const struct cross_level_config *config,
                    struct cross_level_results *results)
{
    struct pointer_chase targets;
    struct helper_control helper;
    struct pointer_chase self_pressure;
    struct chase_node *start;
    size_t target_nodes;
    size_t pressure_nodes;
    size_t samples_per_round;
    size_t rounds;
    size_t sample_count;
    size_t cursor;
    bool helper_started = false;
    bool self_pressure_created = false;
    int saved_errno;

    if (results == NULL) {
        errno = EINVAL;
        return -1;
    }

    memset(results, 0, sizeof(*results));
    memset(&targets, 0, sizeof(targets));
    memset(&self_pressure, 0, sizeof(self_pressure));
    memset(&helper, 0, sizeof(helper));

    if (validate_config(config, &target_nodes, &pressure_nodes) != 0) {
        return -1;
    }

    samples_per_round = target_nodes / config->accesses_per_sample;
    rounds = (config->requested_sample_count + samples_per_round - 1u) /
             samples_per_round;
    if (rounds == 0u || rounds > SIZE_MAX / samples_per_round) {
        errno = EOVERFLOW;
        return -1;
    }
    sample_count = rounds * samples_per_round;

    /* Record identity before doing anything that could fail late. */
    (void)cross_level_read_topology(sched_getcpu(), &results->measuring);

    if (allocate_sample_array(&results->baseline_ticks, sample_count) != 0 ||
        allocate_sample_array(&results->after_pressure_ticks,
                              sample_count) != 0 ||
        allocate_sample_array(&results->timer_overhead_ticks,
                              sample_count) != 0) {
        saved_errno = errno;
        cross_level_results_destroy(results);
        errno = saved_errno;
        return -1;
    }

    /*
     * The target cycle is randomized so no stride prefetcher can reconstruct
     * the set during the probe walk, and it is allocated after pinning so
     * first touch keeps it on the measuring core's NUMA node.
     */
    if (pointer_chase_create(&targets, target_nodes,
                             config->target_line_spacing_bytes,
                             config->seed,
                             POINTER_CHASE_RANDOMIZED) != 0) {
        saved_errno = errno;
        cross_level_results_destroy(results);
        errno = saved_errno;
        return -1;
    }
    start = targets.start;

    if (config->pressure_source == CROSS_LEVEL_PRESSURE_SELF) {
        if (pointer_chase_create(&self_pressure, pressure_nodes,
                                 config->pressure_line_spacing_bytes,
                                 config->seed ^ UINT64_C(0x5deece66d),
                                 config->pressure_order) != 0) {
            goto failure;
        }
        self_pressure_created = true;
    } else if (config->pressure_source == CROSS_LEVEL_PRESSURE_HELPER) {
        helper.cpu = config->helper_cpu;
        helper.node_count = pressure_nodes;
        helper.node_spacing_bytes = config->pressure_line_spacing_bytes;
        helper.order = config->pressure_order;
        helper.passes_per_round = config->pressure_passes_per_round;
        helper.seed = config->seed ^ UINT64_C(0x5deece66d);
        if (helper_start(&helper) != 0) {
            goto failure;
        }
        helper_started = true;

        (void)cross_level_read_topology(config->helper_cpu, &results->helper);
        results->helper_used = true;
        results->helper_same_package =
            results->helper.physical_package_id ==
            results->measuring.physical_package_id;
        results->helper_is_smt_sibling =
            results->helper_same_package &&
            results->helper.physical_core_id ==
                results->measuring.physical_core_id;

        if (results->helper_is_smt_sibling && !config->allow_smt_sibling) {
            /* An SMT sibling shares L1D and L2 with the measuring thread, so
             * its pressure would evict the private copies directly and the
             * result could not distinguish an inclusion policy. */
            errno = EINVAL;
            goto failure;
        }
    }

    cursor = 0u;
    for (size_t round = 0; round < rounds + config->warmup_round_count;
         ++round) {
        bool recording = round >= config->warmup_round_count;
        uint64_t *baseline_slot;
        uint64_t *after_slot;
        uint64_t *overhead_slot;

        /* 1. Prime: make every target line private-resident, untimed. */
        cross_level_sink = run_dependent_batch(start, target_nodes);

        baseline_slot = recording ? results->baseline_ticks + cursor : NULL;
        after_slot = recording ? results->after_pressure_ticks + cursor : NULL;
        overhead_slot = recording ? results->timer_overhead_ticks + cursor
                                  : NULL;

        /* 2. Baseline: the calibrated private-hit class. */
        if (recording) {
            if (walk_timed(start, samples_per_round,
                           config->accesses_per_sample, baseline_slot,
                           &results->zero_baseline_count, NULL) != 0) {
                goto failure;
            }
        } else {
            cross_level_sink = run_dependent_batch(start, target_nodes);
        }

        /* 3. Pressure. */
        switch (config->pressure_source) {
        case CROSS_LEVEL_PRESSURE_NONE:
            break;
        case CROSS_LEVEL_PRESSURE_SELF:
            for (size_t pass = 0; pass < config->pressure_passes_per_round;
                 ++pass) {
                cross_level_sink = run_dependent_batch(self_pressure.start,
                                                       pressure_nodes);
                ++results->pressure_pass_count;
            }
            break;
        case CROSS_LEVEL_PRESSURE_HELPER:
            helper_run_round(&helper, (unsigned long)(round + 1u));
            results->pressure_pass_count += config->pressure_passes_per_round;
            break;
        default:
            errno = EINVAL;
            goto failure;
        }

        /* 4. Probe: identical addresses, identical order, identical code. */
        if (recording) {
            if (walk_timed(start, samples_per_round,
                           config->accesses_per_sample, after_slot,
                           &results->zero_after_pressure_count, NULL) != 0) {
                goto failure;
            }
            /* 5. Timer/fence overhead for the same number of intervals. */
            if (sample_timer_overhead(samples_per_round, overhead_slot,
                                      &results->zero_overhead_count) != 0) {
                goto failure;
            }
            cursor += samples_per_round;
        } else {
            cross_level_sink = run_dependent_batch(start, target_nodes);
        }
    }

    results->sample_count = cursor;
    results->round_count = rounds;
    results->samples_per_round = samples_per_round;
    results->target_node_count = target_nodes;
    results->pressure_node_count = pressure_nodes;
    if (helper_started) {
        results->helper_pass_count = helper.passes_done;
    }

    if (helper_started) {
        helper_stop(&helper);
    }
    if (self_pressure_created) {
        pointer_chase_destroy(&self_pressure);
    }
    pointer_chase_destroy(&targets);
    return 0;

failure:
    saved_errno = errno;
    if (helper_started) {
        helper_stop(&helper);
    }
    if (self_pressure_created) {
        pointer_chase_destroy(&self_pressure);
    }
    pointer_chase_destroy(&targets);
    cross_level_results_destroy(results);
    errno = saved_errno;
    return -1;
}
