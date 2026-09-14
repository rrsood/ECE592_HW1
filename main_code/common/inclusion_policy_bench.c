#define _POSIX_C_SOURCE 200809L

/*
 * ECE 592 Homework I -- Section 8.2 item 7, inclusion/exclusion behavior.
 *
 * One measured point = one (target footprint, pressure source, pressure
 * footprint, helper CPU) configuration.  The program emits one self-describing
 * TSV file holding every raw timed sample, using the same header/row layout as
 * the rest of the Phase-I suite so the existing processing conventions apply.
 *
 * Build with scripts/build_inclusion_policy.sh (adds -pthread).
 */

#include "affinity.h"
#include "cross_level.h"
#include "metadata.h"
#include "pointer_chase.h"
#include "timer.h"

#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define ECE592_MINIMUM_TIMED_SAMPLES ((size_t)1000000)

struct program_options {
    int logical_cpu;
    int helper_cpu;
    enum cross_level_pressure_source pressure_source;
    enum pointer_chase_order pressure_order;
    size_t target_bytes;
    size_t target_spacing_bytes;
    size_t pressure_bytes;
    size_t pressure_spacing_bytes;
    size_t accesses_per_sample;
    size_t pressure_passes;
    size_t timed_sample_count;
    size_t warmup_round_count;
    uint64_t seed;
    bool allow_smt_sibling;
    const char *experiment_name;
    const char *output_path;
    const char *build_command;
    const char *smt_siblings_idle;
    const char *environment_variables;
};

static void print_usage(FILE *stream, const char *program)
{
    fprintf(stream,
            "usage: %s --cpu N --pressure-source none|self|helper "
            "[--helper-cpu N] [--allow-smt-sibling] "
            "--target-bytes N --target-spacing BYTES "
            "[--pressure-bytes N --pressure-spacing BYTES "
            "--pressure-order sequential|randomized --pressure-passes N] "
            "--accesses-per-sample N --samples N --warmup N --seed N "
            "--experiment NAME --output PATH --build-command COMMAND "
            "--smt-siblings-idle yes|no|not-applicable "
            "--environment-variables DESCRIPTION\n",
            program);
}

/* ------------------------------------------------------------------------ */
/* Option parsing                                                            */
/* ------------------------------------------------------------------------ */

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

static bool is_single_line(const char *text)
{
    return text != NULL && text[0] != '\0' &&
           strpbrk(text, "\r\n\t") == NULL;
}

enum option_identifier {
    OPTION_CPU = 1,
    OPTION_HELPER_CPU,
    OPTION_PRESSURE_SOURCE,
    OPTION_PRESSURE_ORDER,
    OPTION_TARGET_BYTES,
    OPTION_TARGET_SPACING,
    OPTION_PRESSURE_BYTES,
    OPTION_PRESSURE_SPACING,
    OPTION_ACCESSES_PER_SAMPLE,
    OPTION_PRESSURE_PASSES,
    OPTION_SAMPLES,
    OPTION_WARMUP,
    OPTION_SEED,
    OPTION_ALLOW_SMT_SIBLING,
    OPTION_EXPERIMENT,
    OPTION_OUTPUT,
    OPTION_BUILD_COMMAND,
    OPTION_SMT_SIBLINGS_IDLE,
    OPTION_ENVIRONMENT_VARIABLES
};

static int parse_options(int argc, char **argv, struct program_options *options)
{
    static const struct option long_options[] = {
        {"cpu", required_argument, NULL, OPTION_CPU},
        {"helper-cpu", required_argument, NULL, OPTION_HELPER_CPU},
        {"pressure-source", required_argument, NULL, OPTION_PRESSURE_SOURCE},
        {"pressure-order", required_argument, NULL, OPTION_PRESSURE_ORDER},
        {"target-bytes", required_argument, NULL, OPTION_TARGET_BYTES},
        {"target-spacing", required_argument, NULL, OPTION_TARGET_SPACING},
        {"pressure-bytes", required_argument, NULL, OPTION_PRESSURE_BYTES},
        {"pressure-spacing", required_argument, NULL, OPTION_PRESSURE_SPACING},
        {"accesses-per-sample", required_argument, NULL,
         OPTION_ACCESSES_PER_SAMPLE},
        {"pressure-passes", required_argument, NULL, OPTION_PRESSURE_PASSES},
        {"samples", required_argument, NULL, OPTION_SAMPLES},
        {"warmup", required_argument, NULL, OPTION_WARMUP},
        {"seed", required_argument, NULL, OPTION_SEED},
        {"allow-smt-sibling", no_argument, NULL, OPTION_ALLOW_SMT_SIBLING},
        {"experiment", required_argument, NULL, OPTION_EXPERIMENT},
        {"output", required_argument, NULL, OPTION_OUTPUT},
        {"build-command", required_argument, NULL, OPTION_BUILD_COMMAND},
        {"smt-siblings-idle", required_argument, NULL,
         OPTION_SMT_SIBLINGS_IDLE},
        {"environment-variables", required_argument, NULL,
         OPTION_ENVIRONMENT_VARIABLES},
        {NULL, 0, NULL, 0}
    };

    bool have_cpu = false;
    bool have_source = false;
    bool have_target_bytes = false;
    bool have_target_spacing = false;
    bool have_samples = false;
    bool have_warmup = false;
    bool have_seed = false;
    bool have_accesses = false;
    int option;

    memset(options, 0, sizeof(*options));
    options->helper_cpu = -1;
    options->pressure_order = POINTER_CHASE_SEQUENTIAL;
    options->pressure_passes = 1u;
    options->pressure_spacing_bytes = 0u;

    while ((option = getopt_long(argc, argv, "", long_options, NULL)) != -1) {
        switch (option) {
        case OPTION_CPU:
            if (parse_cpu(optarg, &options->logical_cpu) != 0) {
                return -1;
            }
            have_cpu = true;
            break;
        case OPTION_HELPER_CPU:
            if (parse_cpu(optarg, &options->helper_cpu) != 0) {
                return -1;
            }
            break;
        case OPTION_PRESSURE_SOURCE:
            if (strcmp(optarg, "none") == 0) {
                options->pressure_source = CROSS_LEVEL_PRESSURE_NONE;
            } else if (strcmp(optarg, "self") == 0) {
                options->pressure_source = CROSS_LEVEL_PRESSURE_SELF;
            } else if (strcmp(optarg, "helper") == 0) {
                options->pressure_source = CROSS_LEVEL_PRESSURE_HELPER;
            } else {
                return -1;
            }
            have_source = true;
            break;
        case OPTION_PRESSURE_ORDER:
            if (strcmp(optarg, "sequential") == 0) {
                options->pressure_order = POINTER_CHASE_SEQUENTIAL;
            } else if (strcmp(optarg, "randomized") == 0) {
                options->pressure_order = POINTER_CHASE_RANDOMIZED;
            } else {
                return -1;
            }
            break;
        case OPTION_TARGET_BYTES:
            if (parse_size(optarg, &options->target_bytes) != 0) {
                return -1;
            }
            have_target_bytes = true;
            break;
        case OPTION_TARGET_SPACING:
            if (parse_size(optarg, &options->target_spacing_bytes) != 0) {
                return -1;
            }
            have_target_spacing = true;
            break;
        case OPTION_PRESSURE_BYTES:
            if (parse_size(optarg, &options->pressure_bytes) != 0) {
                return -1;
            }
            break;
        case OPTION_PRESSURE_SPACING:
            if (parse_size(optarg, &options->pressure_spacing_bytes) != 0) {
                return -1;
            }
            break;
        case OPTION_ACCESSES_PER_SAMPLE:
            if (parse_size(optarg, &options->accesses_per_sample) != 0) {
                return -1;
            }
            have_accesses = true;
            break;
        case OPTION_PRESSURE_PASSES:
            if (parse_size(optarg, &options->pressure_passes) != 0) {
                return -1;
            }
            break;
        case OPTION_SAMPLES:
            if (parse_size(optarg, &options->timed_sample_count) != 0) {
                return -1;
            }
            have_samples = true;
            break;
        case OPTION_WARMUP:
            if (parse_size(optarg, &options->warmup_round_count) != 0) {
                return -1;
            }
            have_warmup = true;
            break;
        case OPTION_SEED:
            if (parse_u64(optarg, &options->seed) != 0) {
                return -1;
            }
            have_seed = true;
            break;
        case OPTION_ALLOW_SMT_SIBLING:
            options->allow_smt_sibling = true;
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
        case OPTION_SMT_SIBLINGS_IDLE:
            options->smt_siblings_idle = optarg;
            break;
        case OPTION_ENVIRONMENT_VARIABLES:
            options->environment_variables = optarg;
            break;
        default:
            return -1;
        }
    }

    if (optind != argc || !have_cpu || !have_source || !have_target_bytes ||
        !have_target_spacing || !have_samples || !have_warmup ||
        !have_seed || !have_accesses) {
        return -1;
    }
    if (!is_single_line(options->experiment_name) ||
        !is_single_line(options->output_path) ||
        !is_single_line(options->build_command) ||
        !is_single_line(options->environment_variables) ||
        options->smt_siblings_idle == NULL) {
        return -1;
    }
    if (strcmp(options->smt_siblings_idle, "yes") != 0 &&
        strcmp(options->smt_siblings_idle, "no") != 0 &&
        strcmp(options->smt_siblings_idle, "not-applicable") != 0) {
        return -1;
    }
    if (options->timed_sample_count < ECE592_MINIMUM_TIMED_SAMPLES) {
        fprintf(stderr,
                "error: --samples must be at least %zu\n",
                ECE592_MINIMUM_TIMED_SAMPLES);
        return -1;
    }
    if (options->pressure_source != CROSS_LEVEL_PRESSURE_NONE &&
        options->pressure_bytes == 0u) {
        return -1;
    }
    /* The pressure arena defaults to the same line spacing as the target set
     * so a single --target-spacing controls both unless overridden.  It is
     * always set, even for the no-pressure control, so the configuration
     * validator sees a well-formed value in every mode. */
    if (options->pressure_spacing_bytes == 0u) {
        options->pressure_spacing_bytes = options->target_spacing_bytes;
    }
    if (options->pressure_source == CROSS_LEVEL_PRESSURE_HELPER &&
        options->helper_cpu < 0) {
        return -1;
    }
    if (options->helper_cpu == options->logical_cpu &&
        options->pressure_source == CROSS_LEVEL_PRESSURE_HELPER) {
        fprintf(stderr,
                "error: --helper-cpu must differ from --cpu\n");
        return -1;
    }

    return 0;
}

/* Reproduce the exact command line for the raw-file provenance header. */
static char *reconstruct_run_command(int argc, char **argv)
{
    size_t length = 1u;
    char *command;

    for (int argument = 0; argument < argc; ++argument) {
        length += strlen(argv[argument]) * 4u + 3u;
    }

    command = malloc(length);
    if (command == NULL) {
        return NULL;
    }
    command[0] = '\0';

    for (int argument = 0; argument < argc; ++argument) {
        if (argument != 0) {
            strcat(command, " ");
        }
        strcat(command, "'");
        for (const char *character = argv[argument]; *character != '\0';
             ++character) {
            char buffer[5];

            if (*character == '\'') {
                strcat(command, "'\\''");
            } else if (*character == '\n' || *character == '\r' ||
                       *character == '\t') {
                strcat(command, " ");
            } else {
                buffer[0] = *character;
                buffer[1] = '\0';
                strcat(command, buffer);
            }
        }
        strcat(command, "'");
    }

    return command;
}

static int verify_smt_status(const struct system_metadata *metadata,
                             const char *status)
{
    bool no_sibling = strcmp(metadata->thread_siblings_list, "unavailable") == 0;

    if ((no_sibling && strcmp(status, "not-applicable") != 0) ||
        (!no_sibling && strcmp(status, "not-applicable") == 0)) {
        return -1;
    }

    return 0;
}

/* ------------------------------------------------------------------------ */
/* Raw output                                                                */
/* ------------------------------------------------------------------------ */

static int write_raw_tsv(const struct program_options *options,
                         const char *run_command,
                         const struct system_metadata *metadata,
                         const struct timer_info *timer,
                         const struct cross_level_config *config,
                         const struct cross_level_results *results)
{
    FILE *stream;
    int descriptor;
    int saved_errno;

    descriptor = open(options->output_path, O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (descriptor < 0) {
        return -1;
    }
    stream = fdopen(descriptor, "w");
    if (stream == NULL) {
        saved_errno = errno;
        (void)close(descriptor);
        (void)unlink(options->output_path);
        errno = saved_errno;
        return -1;
    }

    if (fprintf(stream, "ece592_raw_format_version=1\n") < 0 ||
        fprintf(stream, "output_filename=%s\n", options->output_path) < 0 ||
        fprintf(stream, "experiment_name=%s\n",
                options->experiment_name) < 0 ||
        metadata_write(stream, metadata) != 0 ||
        fprintf(stream, "build_command=%s\n", options->build_command) < 0 ||
        fprintf(stream, "run_command=%s\n", run_command) < 0 ||
        fprintf(stream, "environment_variables=%s\n",
                options->environment_variables) < 0 ||
        fprintf(stream,
                "locality_method=pin-before-allocation plus first-touch memset "
                "in each thread\n") < 0 ||
        fprintf(stream, "smt_siblings_idle=%s\n",
                options->smt_siblings_idle) < 0 ||
        fprintf(stream, "timer_name=%s\n", timer->name) < 0 ||
        fprintf(stream, "timer_unit=%s\n", timer->unit) < 0 ||
        fprintf(stream, "timer_frequency_hz=%" PRIu64 "\n",
                timer->frequency_hz) < 0 ||
        fprintf(stream, "timer_frequency_hz_valid=%s\n",
                timer->frequency_hz_valid ? "true" : "false") < 0) {
        goto failure;
    }

    /* Experiment identity and construction. */
    if (fprintf(stream,
                "traversal=randomized-private-target-cycle-with-"
                "external-shared-cache-pressure\n") < 0 ||
        fprintf(stream,
                "inclusion_policy_method_version=1\n") < 0 ||
        fprintf(stream,
                "measurement_goal=8.2.7_inclusion_exclusion_behavior\n") < 0 ||
        fprintf(stream,
                "round_structure=prime-baseline-pressure-probe-overhead\n") < 0 ||
        fprintf(stream,
                "baseline_condition=private-resident-reload-before-pressure\n") < 0 ||
        fprintf(stream,
                "after_pressure_condition=same-addresses-reloaded-after-"
                "pressure-episode\n") < 0 ||
        fprintf(stream, "cache_policy_labels_assigned=false\n") < 0 ||
        fprintf(stream, "random_seed_applicable=true\n") < 0 ||
        fprintf(stream, "random_seed=%" PRIu64 "\n", options->seed) < 0 ||
        fprintf(stream, "target_bytes=%zu\n", config->target_bytes) < 0 ||
        fprintf(stream, "target_line_spacing_bytes=%zu\n",
                config->target_line_spacing_bytes) < 0 ||
        fprintf(stream, "target_node_count=%zu\n",
                results->target_node_count) < 0 ||
        fprintf(stream, "pressure_source=%s\n",
                cross_level_pressure_source_name(
                    config->pressure_source)) < 0 ||
        fprintf(stream, "pressure_bytes=%zu\n",
                config->pressure_source == CROSS_LEVEL_PRESSURE_NONE
                    ? (size_t)0u
                    : config->pressure_bytes) < 0 ||
        fprintf(stream, "pressure_line_spacing_bytes=%zu\n",
                config->pressure_line_spacing_bytes) < 0 ||
        fprintf(stream, "pressure_node_count=%zu\n",
                results->pressure_node_count) < 0 ||
        fprintf(stream, "pressure_order=%s\n",
                pointer_chase_order_name(config->pressure_order)) < 0 ||
        fprintf(stream, "pressure_passes_per_round=%zu\n",
                config->pressure_passes_per_round) < 0 ||
        fprintf(stream, "pressure_pass_count=%" PRIu64 "\n",
                results->pressure_pass_count) < 0 ||
        fprintf(stream, "helper_pass_count=%" PRIu64 "\n",
                results->helper_pass_count) < 0) {
        goto failure;
    }

    /* Topology of both participating CPUs. */
    if (fprintf(stream, "measuring_logical_cpu=%d\n",
                results->measuring.logical_cpu) < 0 ||
        fprintf(stream, "measuring_physical_core_id=%d\n",
                results->measuring.physical_core_id) < 0 ||
        fprintf(stream, "measuring_physical_package_id=%d\n",
                results->measuring.physical_package_id) < 0 ||
        fprintf(stream, "helper_used=%s\n",
                results->helper_used ? "true" : "false") < 0 ||
        fprintf(stream, "helper_logical_cpu=%d\n",
                results->helper_used ? results->helper.logical_cpu : -1) < 0 ||
        fprintf(stream, "helper_physical_core_id=%d\n",
                results->helper_used ? results->helper.physical_core_id
                                     : -1) < 0 ||
        fprintf(stream, "helper_physical_package_id=%d\n",
                results->helper_used ? results->helper.physical_package_id
                                     : -1) < 0 ||
        fprintf(stream, "helper_same_package=%s\n",
                results->helper_used && results->helper_same_package
                    ? "true" : "false") < 0 ||
        fprintf(stream, "helper_is_smt_sibling=%s\n",
                results->helper_used && results->helper_is_smt_sibling
                    ? "true" : "false") < 0) {
        goto failure;
    }

    /* Sampling structure. */
    if (fprintf(stream, "requested_timed_sample_count=%zu\n",
                options->timed_sample_count) < 0 ||
        fprintf(stream, "timed_sample_count=%zu\n",
                results->sample_count) < 0 ||
        fprintf(stream, "round_count=%zu\n", results->round_count) < 0 ||
        fprintf(stream, "samples_per_round=%zu\n",
                results->samples_per_round) < 0 ||
        fprintf(stream, "accesses_per_sample=%zu\n",
                config->accesses_per_sample) < 0 ||
        fprintf(stream, "warmup_round_count=%zu\n",
                config->warmup_round_count) < 0 ||
        fprintf(stream, "zero_baseline_count=%zu\n",
                results->zero_baseline_count) < 0 ||
        fprintf(stream, "zero_after_pressure_count=%zu\n",
                results->zero_after_pressure_count) < 0 ||
        fprintf(stream, "zero_overhead_count=%zu\n",
                results->zero_overhead_count) < 0 ||
        fprintf(stream, "timer_overhead_subtracted=false\n") < 0 ||
        fprintf(stream, "data_encoding=tab-separated-decimal-integers\n") < 0 ||
        fprintf(stream, "data_begin\n") < 0 ||
        fprintf(stream,
                "sample_index\tbaseline_raw_ticks\t"
                "after_pressure_raw_ticks\ttimer_overhead_raw_ticks\n") < 0) {
        goto failure;
    }

    for (size_t sample = 0; sample < results->sample_count; ++sample) {
        if (fprintf(stream, "%zu\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64 "\n",
                    sample, results->baseline_ticks[sample],
                    results->after_pressure_ticks[sample],
                    results->timer_overhead_ticks[sample]) < 0) {
            goto failure;
        }
    }

    if (fprintf(stream, "data_end\n") < 0 || fflush(stream) != 0 ||
        fsync(descriptor) != 0 || fclose(stream) != 0) {
        goto failure;
    }

    return 0;

failure:
    saved_errno = errno;
    (void)fclose(stream);
    (void)unlink(options->output_path);
    errno = saved_errno;
    return -1;
}

/* ------------------------------------------------------------------------ */

int main(int argc, char **argv)
{
    struct affinity_info affinity;
    struct cross_level_config config;
    struct cross_level_results results;
    struct program_options options;
    struct system_metadata metadata;
    struct timer_info timer;
    char *run_command = NULL;
    int status = 1;

    memset(&results, 0, sizeof(results));

    if (parse_options(argc, argv, &options) != 0) {
        print_usage(stderr, argv[0]);
        return 2;
    }

    /* Pin before any allocation so first touch is local to this core. */
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

    config.target_bytes = options.target_bytes;
    config.target_line_spacing_bytes = options.target_spacing_bytes;
    config.pressure_bytes = options.pressure_bytes;
    config.pressure_line_spacing_bytes = options.pressure_spacing_bytes;
    config.pressure_order = options.pressure_order;
    config.pressure_passes_per_round = options.pressure_passes;
    config.pressure_source = options.pressure_source;
    config.helper_cpu = options.helper_cpu;
    config.allow_smt_sibling = options.allow_smt_sibling;
    config.accesses_per_sample = options.accesses_per_sample;
    config.requested_sample_count = options.timed_sample_count;
    config.warmup_round_count = options.warmup_round_count;
    config.seed = options.seed;

    if (cross_level_run(&config, &results) != 0) {
        perror("cross_level_run");
        goto cleanup;
    }
    if (write_raw_tsv(&options, run_command, &metadata, &timer, &config,
                      &results) != 0) {
        perror("write_raw_tsv");
        goto cleanup;
    }

    printf("output_filename=%s\n", options.output_path);
    printf("pressure_source=%s\n",
           cross_level_pressure_source_name(options.pressure_source));
    printf("target_node_count=%zu\n", results.target_node_count);
    printf("pressure_node_count=%zu\n", results.pressure_node_count);
    printf("round_count=%zu\n", results.round_count);
    printf("samples_per_round=%zu\n", results.samples_per_round);
    printf("timed_sample_count=%zu\n", results.sample_count);
    printf("helper_used=%s\n", results.helper_used ? "true" : "false");
    printf("helper_same_package=%s\n",
           results.helper_used && results.helper_same_package
               ? "true" : "false");
    printf("helper_is_smt_sibling=%s\n",
           results.helper_used && results.helper_is_smt_sibling
               ? "true" : "false");
    printf("timer_unit=%s\n", timer.unit);
    printf("status=ok\n");
    status = 0;

cleanup:
    cross_level_results_destroy(&results);
    free(run_command);
    return status;
}
