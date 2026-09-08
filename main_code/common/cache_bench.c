#define _POSIX_C_SOURCE 200809L

#include "affinity.h"
#include "conflict_chase.h"
#include "eviction_layout.h"
#include "eviction_measurement.h"
#include "inclusion_chase.h"
#include "inclusion_measurement.h"
#include "measurement.h"
#include "metadata.h"
#include "pointer_chase.h"
#include "raw_output.h"
#include "spatial_chase.h"
#include "timer.h"

#include <errno.h>
#include <getopt.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum benchmark_mode {
    BENCHMARK_MODE_CAPACITY,
    BENCHMARK_MODE_SPATIAL,
    BENCHMARK_MODE_CONFLICT,
    BENCHMARK_MODE_INCLUSION,
    BENCHMARK_MODE_EVICTION
};

struct program_options {
    enum benchmark_mode mode;
    int logical_cpu;
    size_t node_count;
    size_t node_spacing_bytes;
    size_t region_count;
    size_t region_spacing_bytes;
    size_t probe_offset_bytes;
    size_t conflict_line_count;
    size_t conflict_stride_bytes;
    size_t probe_node_count;
    size_t pressure_node_count;
    size_t *target_offsets;
    size_t target_offset_count;
    size_t *pressure_offsets;
    size_t pressure_offset_count;
    size_t dependent_accesses_per_sample;
    size_t pressure_accesses_per_sample;
    size_t warmup_batch_count;
    size_t timed_sample_count;
    uint64_t seed;
    enum pointer_chase_order traversal_order;
    const char *experiment_name;
    const char *output_path;
    const char *build_command;
    const char *smt_siblings_idle;
    const char *environment_variables;
};

static void print_usage(FILE *stream, const char *program)
{
    fprintf(stream,
            "usage: %s [--mode capacity|spatial|conflict|inclusion] "
            "[--mode eviction] "
            "--cpu N --batch N "
            "--warmup N --samples N --seed N "
            "[capacity: --nodes N --spacing BYTES "
            "--traversal randomized|sequential] "
            "[spatial: --regions N --region-spacing BYTES "
            "--probe-offset BYTES] "
            "[conflict: --lines N --conflict-stride BYTES] "
            "[inclusion: --probe-nodes N --pressure-nodes N "
            "--spacing BYTES --pressure-batch N] "
            "[eviction: --target-offsets CSV --pressure-offsets CSV] "
            "--experiment NAME "
            "--output PATH --build-command COMMAND "
            "--smt-siblings-idle yes|no|not-applicable "
            "--environment-variables DESCRIPTION\n",
            program);
}

static int parse_u64(const char *text, uint64_t *value)
{
    char *end;
    unsigned long long parsed;

    if (text == NULL || value == NULL || text[0] == '-') {
        return -1;
    }

    errno = 0;
    end = NULL;
    parsed = strtoull(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0') {
        return -1;
    }

    *value = (uint64_t)parsed;
    return 0;
}

static int parse_size(const char *text, size_t *value)
{
    uint64_t parsed;

    if (parse_u64(text, &parsed) != 0 || parsed > SIZE_MAX) {
        return -1;
    }

    *value = (size_t)parsed;
    return 0;
}

static int parse_cpu(const char *text, int *logical_cpu)
{
    uint64_t parsed;

    if (parse_u64(text, &parsed) != 0 || parsed > INT_MAX) {
        return -1;
    }

    *logical_cpu = (int)parsed;
    return 0;
}

static int parse_size_list(const char *text, size_t **values_out,
                           size_t *count_out)
{
    size_t count = 1u;
    size_t index = 0u;
    const char *start;
    size_t *values;

    if (text == NULL || text[0] == '\0' || values_out == NULL ||
        count_out == NULL) {
        errno = EINVAL;
        return -1;
    }
    for (const char *character = text; *character != '\0'; ++character) {
        if (*character == ',') {
            if (character == text || character[1] == '\0') {
                errno = EINVAL;
                return -1;
            }
            ++count;
        }
    }
    if (count > SIZE_MAX / sizeof(*values)) {
        errno = EOVERFLOW;
        return -1;
    }
    values = malloc(count * sizeof(*values));
    if (values == NULL) {
        return -1;
    }

    start = text;
    while (*start != '\0') {
        char token[64];
        const char *comma = strchr(start, ',');
        size_t length = comma == NULL ? strlen(start) : (size_t)(comma - start);

        if (length == 0u || length >= sizeof(token)) {
            free(values);
            errno = EINVAL;
            return -1;
        }
        memcpy(token, start, length);
        token[length] = '\0';
        if (parse_size(token, &values[index]) != 0) {
            int saved_errno = errno == 0 ? EINVAL : errno;
            free(values);
            errno = saved_errno;
            return -1;
        }
        ++index;
        if (comma == NULL) {
            break;
        }
        start = comma + 1;
    }

    *values_out = values;
    *count_out = count;
    return 0;
}

static bool valid_smt_status(const char *status)
{
    return status != NULL &&
           (strcmp(status, "yes") == 0 || strcmp(status, "no") == 0 ||
            strcmp(status, "not-applicable") == 0);
}

static int parse_options(int argc, char **argv, struct program_options *options)
{
    enum {
        OPTION_CPU = 1000,
        OPTION_MODE,
        OPTION_NODES,
        OPTION_SPACING,
        OPTION_REGIONS,
        OPTION_REGION_SPACING,
        OPTION_PROBE_OFFSET,
        OPTION_LINES,
        OPTION_CONFLICT_STRIDE,
        OPTION_PROBE_NODES,
        OPTION_PRESSURE_NODES,
        OPTION_TARGET_OFFSETS,
        OPTION_PRESSURE_OFFSETS,
        OPTION_BATCH,
        OPTION_PRESSURE_BATCH,
        OPTION_WARMUP,
        OPTION_SAMPLES,
        OPTION_SEED,
        OPTION_TRAVERSAL,
        OPTION_EXPERIMENT,
        OPTION_OUTPUT,
        OPTION_BUILD_COMMAND,
        OPTION_SMT_IDLE,
        OPTION_ENVIRONMENT
    };
    static const struct option long_options[] = {
        {"mode", required_argument, NULL, OPTION_MODE},
        {"cpu", required_argument, NULL, OPTION_CPU},
        {"nodes", required_argument, NULL, OPTION_NODES},
        {"spacing", required_argument, NULL, OPTION_SPACING},
        {"regions", required_argument, NULL, OPTION_REGIONS},
        {"region-spacing", required_argument, NULL, OPTION_REGION_SPACING},
        {"probe-offset", required_argument, NULL, OPTION_PROBE_OFFSET},
        {"lines", required_argument, NULL, OPTION_LINES},
        {"conflict-stride", required_argument, NULL, OPTION_CONFLICT_STRIDE},
        {"probe-nodes", required_argument, NULL, OPTION_PROBE_NODES},
        {"pressure-nodes", required_argument, NULL, OPTION_PRESSURE_NODES},
        {"target-offsets", required_argument, NULL, OPTION_TARGET_OFFSETS},
        {"pressure-offsets", required_argument, NULL, OPTION_PRESSURE_OFFSETS},
        {"batch", required_argument, NULL, OPTION_BATCH},
        {"pressure-batch", required_argument, NULL, OPTION_PRESSURE_BATCH},
        {"warmup", required_argument, NULL, OPTION_WARMUP},
        {"samples", required_argument, NULL, OPTION_SAMPLES},
        {"seed", required_argument, NULL, OPTION_SEED},
        {"traversal", required_argument, NULL, OPTION_TRAVERSAL},
        {"experiment", required_argument, NULL, OPTION_EXPERIMENT},
        {"output", required_argument, NULL, OPTION_OUTPUT},
        {"build-command", required_argument, NULL, OPTION_BUILD_COMMAND},
        {"smt-siblings-idle", required_argument, NULL, OPTION_SMT_IDLE},
        {"environment-variables", required_argument, NULL, OPTION_ENVIRONMENT},
        {NULL, 0, NULL, 0}
    };
    bool seen_cpu = false;
    bool seen_nodes = false;
    bool seen_spacing = false;
    bool seen_regions = false;
    bool seen_region_spacing = false;
    bool seen_probe_offset = false;
    bool seen_lines = false;
    bool seen_conflict_stride = false;
    bool seen_probe_nodes = false;
    bool seen_pressure_nodes = false;
    bool seen_target_offsets = false;
    bool seen_pressure_offsets = false;
    bool seen_batch = false;
    bool seen_pressure_batch = false;
    bool seen_warmup = false;
    bool seen_samples = false;
    bool seen_seed = false;
    bool seen_traversal = false;
    int option;

    memset(options, 0, sizeof(*options));
    options->mode = BENCHMARK_MODE_CAPACITY;
    while ((option = getopt_long(argc, argv, "", long_options, NULL)) != -1) {
        switch (option) {
        case OPTION_MODE:
            if (strcmp(optarg, "capacity") == 0) {
                options->mode = BENCHMARK_MODE_CAPACITY;
            } else if (strcmp(optarg, "spatial") == 0) {
                options->mode = BENCHMARK_MODE_SPATIAL;
            } else if (strcmp(optarg, "conflict") == 0) {
                options->mode = BENCHMARK_MODE_CONFLICT;
            } else if (strcmp(optarg, "inclusion") == 0) {
                options->mode = BENCHMARK_MODE_INCLUSION;
            } else if (strcmp(optarg, "eviction") == 0) {
                options->mode = BENCHMARK_MODE_EVICTION;
            } else {
                return -1;
            }
            break;
        case OPTION_TARGET_OFFSETS:
            free(options->target_offsets);
            options->target_offsets = NULL;
            options->target_offset_count = 0u;
            seen_target_offsets =
                parse_size_list(optarg, &options->target_offsets,
                                &options->target_offset_count) == 0;
            if (!seen_target_offsets) {
                return -1;
            }
            break;
        case OPTION_PRESSURE_OFFSETS:
            free(options->pressure_offsets);
            options->pressure_offsets = NULL;
            options->pressure_offset_count = 0u;
            seen_pressure_offsets =
                parse_size_list(optarg, &options->pressure_offsets,
                                &options->pressure_offset_count) == 0;
            if (!seen_pressure_offsets) {
                return -1;
            }
            break;
        case OPTION_CPU:
            seen_cpu = parse_cpu(optarg, &options->logical_cpu) == 0;
            if (!seen_cpu) {
                return -1;
            }
            break;
        case OPTION_NODES:
            seen_nodes = parse_size(optarg, &options->node_count) == 0;
            if (!seen_nodes) {
                return -1;
            }
            break;
        case OPTION_SPACING:
            seen_spacing =
                parse_size(optarg, &options->node_spacing_bytes) == 0;
            if (!seen_spacing) {
                return -1;
            }
            break;
        case OPTION_REGIONS:
            seen_regions = parse_size(optarg, &options->region_count) == 0;
            if (!seen_regions) {
                return -1;
            }
            break;
        case OPTION_REGION_SPACING:
            seen_region_spacing =
                parse_size(optarg, &options->region_spacing_bytes) == 0;
            if (!seen_region_spacing) {
                return -1;
            }
            break;
        case OPTION_PROBE_OFFSET:
            seen_probe_offset =
                parse_size(optarg, &options->probe_offset_bytes) == 0;
            if (!seen_probe_offset) {
                return -1;
            }
            break;
        case OPTION_LINES:
            seen_lines =
                parse_size(optarg, &options->conflict_line_count) == 0;
            if (!seen_lines) {
                return -1;
            }
            break;
        case OPTION_CONFLICT_STRIDE:
            seen_conflict_stride =
                parse_size(optarg, &options->conflict_stride_bytes) == 0;
            if (!seen_conflict_stride) {
                return -1;
            }
            break;
        case OPTION_PROBE_NODES:
            seen_probe_nodes =
                parse_size(optarg, &options->probe_node_count) == 0;
            if (!seen_probe_nodes) {
                return -1;
            }
            break;
        case OPTION_PRESSURE_NODES:
            seen_pressure_nodes =
                parse_size(optarg, &options->pressure_node_count) == 0;
            if (!seen_pressure_nodes) {
                return -1;
            }
            break;
        case OPTION_BATCH:
            seen_batch = parse_size(
                optarg, &options->dependent_accesses_per_sample) == 0;
            if (!seen_batch) {
                return -1;
            }
            break;
        case OPTION_PRESSURE_BATCH:
            seen_pressure_batch = parse_size(
                optarg, &options->pressure_accesses_per_sample) == 0;
            if (!seen_pressure_batch) {
                return -1;
            }
            break;
        case OPTION_WARMUP:
            seen_warmup =
                parse_size(optarg, &options->warmup_batch_count) == 0;
            if (!seen_warmup) {
                return -1;
            }
            break;
        case OPTION_SAMPLES:
            seen_samples =
                parse_size(optarg, &options->timed_sample_count) == 0;
            if (!seen_samples) {
                return -1;
            }
            break;
        case OPTION_SEED:
            seen_seed = parse_u64(optarg, &options->seed) == 0;
            if (!seen_seed) {
                return -1;
            }
            break;
        case OPTION_TRAVERSAL:
            if (strcmp(optarg, "randomized") == 0) {
                options->traversal_order = POINTER_CHASE_RANDOMIZED;
                seen_traversal = true;
            } else if (strcmp(optarg, "sequential") == 0) {
                options->traversal_order = POINTER_CHASE_SEQUENTIAL;
                seen_traversal = true;
            } else {
                return -1;
            }
            break;
        case OPTION_EXPERIMENT:
            options->experiment_name = optarg;
            break;
        case OPTION_OUTPUT:
            options->output_path = optarg;
            break;
        case OPTION_BUILD_COMMAND:
            options->build_command = optarg;
            break;
        case OPTION_SMT_IDLE:
            options->smt_siblings_idle = optarg;
            break;
        case OPTION_ENVIRONMENT:
            options->environment_variables = optarg;
            break;
        default:
            return -1;
        }
    }

    if (optind != argc || !seen_cpu ||
        !seen_batch || !seen_warmup || !seen_samples || !seen_seed ||
        options->experiment_name == NULL || options->output_path == NULL ||
        options->build_command == NULL ||
        !valid_smt_status(options->smt_siblings_idle) ||
        options->environment_variables == NULL) {
        return -1;
    }

    if (options->mode == BENCHMARK_MODE_CAPACITY &&
        (!seen_nodes || !seen_spacing || !seen_traversal ||
         seen_regions || seen_region_spacing || seen_probe_offset ||
         seen_lines || seen_conflict_stride ||
         seen_probe_nodes || seen_pressure_nodes || seen_pressure_batch ||
         seen_target_offsets || seen_pressure_offsets)) {
        return -1;
    }
    if (options->mode == BENCHMARK_MODE_SPATIAL &&
        (!seen_regions || !seen_region_spacing || !seen_probe_offset ||
         seen_nodes || seen_spacing || seen_traversal ||
         seen_lines || seen_conflict_stride ||
         seen_probe_nodes || seen_pressure_nodes || seen_pressure_batch ||
         seen_target_offsets || seen_pressure_offsets)) {
        return -1;
    }
    if (options->mode == BENCHMARK_MODE_CONFLICT &&
        (!seen_lines || !seen_conflict_stride ||
         seen_nodes || seen_spacing || seen_traversal ||
         seen_regions || seen_region_spacing || seen_probe_offset ||
         seen_probe_nodes || seen_pressure_nodes || seen_pressure_batch ||
         seen_target_offsets || seen_pressure_offsets)) {
        return -1;
    }
    if (options->mode == BENCHMARK_MODE_INCLUSION &&
        (!seen_probe_nodes || !seen_pressure_nodes || !seen_spacing ||
         !seen_pressure_batch ||
         seen_nodes || seen_traversal ||
         seen_regions || seen_region_spacing || seen_probe_offset ||
         seen_lines || seen_conflict_stride ||
         seen_target_offsets || seen_pressure_offsets)) {
        return -1;
    }
    if (options->mode == BENCHMARK_MODE_EVICTION &&
        (!seen_target_offsets || !seen_pressure_offsets ||
         options->target_offset_count < 2u ||
         options->pressure_offset_count < 2u ||
         options->dependent_accesses_per_sample !=
             options->target_offset_count ||
         seen_nodes || seen_spacing || seen_traversal ||
         seen_regions || seen_region_spacing || seen_probe_offset ||
         seen_lines || seen_conflict_stride ||
         seen_probe_nodes || seen_pressure_nodes || seen_pressure_batch)) {
        return -1;
    }

    return 0;
}

static char *reconstruct_run_command(int argc, char **argv)
{
    size_t capacity = 1u;
    size_t used = 0u;
    char *command;

    for (int argument = 0; argument < argc; ++argument) {
        size_t length = strlen(argv[argument]);

        if (length > (SIZE_MAX - capacity - 4u) / 4u) {
            errno = EOVERFLOW;
            return NULL;
        }
        capacity += length * 4u + 4u;
    }

    command = malloc(capacity);
    if (command == NULL) {
        return NULL;
    }

    for (int argument = 0; argument < argc; ++argument) {
        if (argument != 0) {
            command[used++] = ' ';
        }
        command[used++] = '\'';
        for (const char *character = argv[argument]; *character != '\0';
             ++character) {
            if (*character == '\'') {
                memcpy(command + used, "'\\''", 4u);
                used += 4u;
            } else {
                command[used++] = *character;
            }
        }
        command[used++] = '\'';
    }
    command[used] = '\0';
    return command;
}

static int verify_smt_status(const struct system_metadata *metadata,
                             const char *status)
{
    char logical_cpu_text[32];
    int written;
    bool no_sibling;

    written = snprintf(logical_cpu_text, sizeof(logical_cpu_text), "%d",
                       metadata->logical_cpu);
    if (written < 0 || (size_t)written >= sizeof(logical_cpu_text)) {
        return -1;
    }

    no_sibling = strcmp(metadata->thread_siblings_list,
                        logical_cpu_text) == 0;
    if ((no_sibling && strcmp(status, "not-applicable") != 0) ||
        (!no_sibling && strcmp(status, "not-applicable") == 0)) {
        errno = EINVAL;
        return -1;
    }

    return 0;
}

int main(int argc, char **argv)
{
    struct affinity_info affinity;
    struct measurement_config config;
    struct measurement_results results;
    struct conflict_chase conflict_chase;
    struct eviction_layout eviction_layout;
    struct eviction_measurement_config eviction_config;
    struct eviction_measurement_results eviction_results;
    struct inclusion_chase inclusion_chase;
    struct inclusion_measurement_config inclusion_config;
    struct inclusion_measurement_results inclusion_results;
    struct pointer_chase chase;
    struct spatial_chase spatial_chase;
    struct program_options options;
    struct raw_output_context output_context;
    struct system_metadata metadata;
    struct timer_info timer;
    char *run_command = NULL;
    int status = 1;

    memset(&results, 0, sizeof(results));
    memset(&conflict_chase, 0, sizeof(conflict_chase));
    memset(&eviction_layout, 0, sizeof(eviction_layout));
    memset(&eviction_results, 0, sizeof(eviction_results));
    memset(&inclusion_chase, 0, sizeof(inclusion_chase));
    memset(&inclusion_results, 0, sizeof(inclusion_results));
    memset(&chase, 0, sizeof(chase));
    memset(&spatial_chase, 0, sizeof(spatial_chase));

    if (parse_options(argc, argv, &options) != 0) {
        print_usage(stderr, argv[0]);
        return 2;
    }

    if (affinity_pin_current_thread(options.logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        goto cleanup;
    }

    run_command = reconstruct_run_command(argc, argv);
    if (run_command == NULL) {
        perror("reconstruct_run_command");
        goto cleanup;
    }
    if (metadata_collect(&metadata) != 0) {
        perror("metadata_collect");
        goto cleanup;
    }
    if (verify_smt_status(&metadata, options.smt_siblings_idle) != 0) {
        fprintf(stderr,
                "error: --smt-siblings-idle conflicts with sibling list %s\n",
                metadata.thread_siblings_list);
        goto cleanup;
    }
    if (timer_init(&timer) != 0) {
        fprintf(stderr, "error: timer initialization failed\n");
        goto cleanup;
    }
    config.timed_sample_count = options.timed_sample_count;
    config.warmup_batch_count = options.warmup_batch_count;
    config.dependent_accesses_per_sample =
        options.dependent_accesses_per_sample;

    output_context.experiment_name = options.experiment_name;
    output_context.build_command = options.build_command;
    output_context.run_command = run_command;
    output_context.locality_method =
        "pin-before-allocation plus first-touch memset";
    output_context.smt_siblings_idle = options.smt_siblings_idle;
    output_context.environment_variables = options.environment_variables;

    if (options.mode == BENCHMARK_MODE_CAPACITY) {
        if (pointer_chase_create(&chase, options.node_count,
                                 options.node_spacing_bytes,
                                 options.seed, options.traversal_order) != 0) {
            perror("pointer_chase_create");
            goto cleanup;
        }
        if (measurement_run(&chase, &config, &results) != 0) {
            perror("measurement_run");
            goto cleanup;
        }
        if (raw_output_write_tsv(options.output_path, &output_context,
                                 &metadata, &timer, &chase, &config,
                                 &results) != 0) {
            perror("raw_output_write_tsv");
            goto cleanup;
        }
    } else if (options.mode == BENCHMARK_MODE_SPATIAL) {
        if (spatial_chase_create(&spatial_chase, options.region_count,
                                 options.region_spacing_bytes,
                                 options.probe_offset_bytes,
                                 options.seed) != 0) {
            perror("spatial_chase_create");
            goto cleanup;
        }
        if (measurement_run_from_start(spatial_chase.start, &config,
                                       &results) != 0) {
            perror("measurement_run_from_start");
            goto cleanup;
        }
        if (raw_output_write_spatial_tsv(options.output_path, &output_context,
                                         &metadata, &timer, &spatial_chase,
                                         &config, &results) != 0) {
            perror("raw_output_write_spatial_tsv");
            goto cleanup;
        }
    } else if (options.mode == BENCHMARK_MODE_CONFLICT) {
        if (conflict_chase_create(&conflict_chase,
                                  options.conflict_line_count,
                                  options.conflict_stride_bytes,
                                  options.seed) != 0) {
            perror("conflict_chase_create");
            goto cleanup;
        }
        if (measurement_run_from_start(conflict_chase.start, &config,
                                       &results) != 0) {
            perror("measurement_run_from_start");
            goto cleanup;
        }
        if (raw_output_write_conflict_tsv(options.output_path,
                                          &output_context, &metadata, &timer,
                                          &conflict_chase, &config,
                                          &results) != 0) {
            perror("raw_output_write_conflict_tsv");
            goto cleanup;
        }
    } else if (options.mode == BENCHMARK_MODE_INCLUSION) {
        inclusion_config.timed_sample_count = options.timed_sample_count;
        inclusion_config.warmup_batch_count = options.warmup_batch_count;
        inclusion_config.probe_accesses_per_sample =
            options.dependent_accesses_per_sample;
        inclusion_config.pressure_accesses_per_sample =
            options.pressure_accesses_per_sample;

        if (inclusion_chase_create(&inclusion_chase,
                                   options.probe_node_count,
                                   options.pressure_node_count,
                                   options.node_spacing_bytes,
                                   options.seed) != 0) {
            perror("inclusion_chase_create");
            goto cleanup;
        }
        if (inclusion_measurement_run(&inclusion_chase, &inclusion_config,
                                      &inclusion_results) != 0) {
            perror("inclusion_measurement_run");
            goto cleanup;
        }
        if (raw_output_write_inclusion_tsv(options.output_path,
                                           &output_context, &metadata,
                                           &timer, &inclusion_chase,
                                           &inclusion_config,
                                           &inclusion_results) != 0) {
            perror("raw_output_write_inclusion_tsv");
            goto cleanup;
        }
    } else {
        eviction_config.sample_count = options.timed_sample_count;
        eviction_config.reloads_per_sample =
            options.dependent_accesses_per_sample;
        eviction_config.warmup_pairs = options.warmup_batch_count;

        if (eviction_layout_create_targets(
                &eviction_layout, options.target_offsets,
                options.target_offset_count, options.pressure_offsets,
                options.pressure_offset_count, options.seed) != 0) {
            perror("eviction_layout_create_targets");
            goto cleanup;
        }
        if (eviction_measurement_run(&eviction_layout, &eviction_config,
                                     &eviction_results) != 0) {
            perror("eviction_measurement_run");
            goto cleanup;
        }
        if (raw_output_write_eviction_tsv(options.output_path,
                                          &output_context, &metadata,
                                          &timer, &eviction_layout,
                                          &eviction_config,
                                          &eviction_results) != 0) {
            perror("raw_output_write_eviction_tsv");
            goto cleanup;
        }
    }

    printf("output_filename=%s\n", options.output_path);
    if (options.mode == BENCHMARK_MODE_INCLUSION) {
        printf("timed_sample_count=%zu\n", inclusion_results.sample_count);
    } else if (options.mode == BENCHMARK_MODE_EVICTION) {
        printf("timed_sample_count=%zu\n", eviction_results.event_count);
    } else {
        printf("timed_sample_count=%zu\n", results.sample_count);
    }
    printf("timer_unit=%s\n", timer.unit);
    printf("status=ok\n");
    status = 0;

cleanup:
    measurement_results_destroy(&results);
    eviction_measurement_destroy(&eviction_results);
    eviction_layout_destroy(&eviction_layout);
    inclusion_measurement_results_destroy(&inclusion_results);
    inclusion_chase_destroy(&inclusion_chase);
    conflict_chase_destroy(&conflict_chase);
    pointer_chase_destroy(&chase);
    spatial_chase_destroy(&spatial_chase);
    free(options.target_offsets);
    free(options.pressure_offsets);
    free(run_command);
    return status;
}
