#define _POSIX_C_SOURCE 200809L

#include "affinity.h"
#include "measurement.h"
#include "metadata.h"
#include "pointer_chase.h"
#include "raw_output.h"
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

struct program_options {
    int logical_cpu;
    size_t node_count;
    size_t node_spacing_bytes;
    size_t dependent_accesses_per_sample;
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
            "usage: %s --cpu N --nodes N --spacing BYTES --batch N "
            "--warmup N --samples N --seed N "
            "--traversal randomized|sequential --experiment NAME "
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
        OPTION_NODES,
        OPTION_SPACING,
        OPTION_BATCH,
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
        {"cpu", required_argument, NULL, OPTION_CPU},
        {"nodes", required_argument, NULL, OPTION_NODES},
        {"spacing", required_argument, NULL, OPTION_SPACING},
        {"batch", required_argument, NULL, OPTION_BATCH},
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
    bool seen_batch = false;
    bool seen_warmup = false;
    bool seen_samples = false;
    bool seen_seed = false;
    bool seen_traversal = false;
    int option;

    memset(options, 0, sizeof(*options));
    while ((option = getopt_long(argc, argv, "", long_options, NULL)) != -1) {
        switch (option) {
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
        case OPTION_BATCH:
            seen_batch = parse_size(
                optarg, &options->dependent_accesses_per_sample) == 0;
            if (!seen_batch) {
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

    if (optind != argc || !seen_cpu || !seen_nodes || !seen_spacing ||
        !seen_batch || !seen_warmup || !seen_samples || !seen_seed ||
        !seen_traversal ||
        options->experiment_name == NULL || options->output_path == NULL ||
        options->build_command == NULL ||
        !valid_smt_status(options->smt_siblings_idle) ||
        options->environment_variables == NULL) {
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
    struct pointer_chase chase;
    struct program_options options;
    struct raw_output_context output_context;
    struct system_metadata metadata;
    struct timer_info timer;
    char *run_command = NULL;
    int status = 1;

    memset(&results, 0, sizeof(results));
    memset(&chase, 0, sizeof(chase));

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
    if (pointer_chase_create(&chase, options.node_count,
                             options.node_spacing_bytes,
                             options.seed, options.traversal_order) != 0) {
        perror("pointer_chase_create");
        goto cleanup;
    }

    config.timed_sample_count = options.timed_sample_count;
    config.warmup_batch_count = options.warmup_batch_count;
    config.dependent_accesses_per_sample =
        options.dependent_accesses_per_sample;

    if (measurement_run(&chase, &config, &results) != 0) {
        perror("measurement_run");
        goto cleanup;
    }

    output_context.experiment_name = options.experiment_name;
    output_context.build_command = options.build_command;
    output_context.run_command = run_command;
    output_context.locality_method =
        "pin-before-allocation plus first-touch memset";
    output_context.smt_siblings_idle = options.smt_siblings_idle;
    output_context.environment_variables = options.environment_variables;

    if (raw_output_write_tsv(options.output_path, &output_context, &metadata,
                             &timer, &chase, &config, &results) != 0) {
        perror("raw_output_write_tsv");
        goto cleanup;
    }

    printf("output_filename=%s\n", options.output_path);
    printf("timed_sample_count=%zu\n", results.sample_count);
    printf("timer_unit=%s\n", timer.unit);
    printf("status=ok\n");
    status = 0;

cleanup:
    measurement_results_destroy(&results);
    pointer_chase_destroy(&chase);
    free(run_command);
    return status;
}
