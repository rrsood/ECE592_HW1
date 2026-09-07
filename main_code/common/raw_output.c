#define _POSIX_C_SOURCE 200809L

#include "raw_output.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifndef ECE592_BUILD_COMMAND
#define ECE592_BUILD_COMMAND "not-supplied"
#endif

static bool is_single_line(const char *text)
{
    return text != NULL && strpbrk(text, "\r\n\t") == NULL;
}

static int validate_inputs(const char *path,
                           const struct raw_output_context *context,
                           const struct system_metadata *metadata,
                           const struct timer_info *timer,
                           const struct pointer_chase *chase,
                           const struct measurement_config *config,
                           const struct measurement_results *results)
{
    if (path == NULL || path[0] == '\0' || !is_single_line(path) ||
        context == NULL ||
        metadata == NULL || timer == NULL || chase == NULL || config == NULL ||
        results == NULL || results->elapsed_ticks == NULL ||
        results->timer_overhead_ticks == NULL ||
        results->sample_count != config->timed_sample_count ||
        results->sample_count < ECE592_MINIMUM_TIMED_SAMPLES ||
        !is_single_line(context->experiment_name) ||
        !is_single_line(context->build_command) ||
        !is_single_line(context->run_command) ||
        !is_single_line(context->locality_method) ||
        !is_single_line(context->smt_siblings_idle) ||
        !is_single_line(context->environment_variables) ||
        !is_single_line(timer->name) || !is_single_line(timer->unit)) {
        errno = EINVAL;
        return -1;
    }

    return 0;
}

static int write_header(FILE *stream, const char *path,
                        const struct raw_output_context *context,
                        const struct system_metadata *metadata,
                        const struct timer_info *timer,
                        const struct pointer_chase *chase,
                        const struct measurement_config *config,
                        const struct measurement_results *results)
{
    if (fprintf(stream, "ece592_raw_format_version=1\n") < 0 ||
        fprintf(stream, "output_filename=%s\n", path) < 0 ||
        fprintf(stream, "experiment_name=%s\n",
                context->experiment_name) < 0 ||
        metadata_write(stream, metadata) != 0 ||
        fprintf(stream, "build_command=%s\n", context->build_command) < 0 ||
        fprintf(stream, "run_command=%s\n", context->run_command) < 0 ||
        fprintf(stream, "environment_variables=%s\n",
                context->environment_variables) < 0 ||
        fprintf(stream, "locality_method=%s\n",
                context->locality_method) < 0 ||
        fprintf(stream, "smt_siblings_idle=%s\n",
                context->smt_siblings_idle) < 0 ||
        fprintf(stream, "timer_name=%s\n", timer->name) < 0 ||
        fprintf(stream, "timer_unit=%s\n", timer->unit) < 0 ||
        fprintf(stream, "timer_frequency_hz=%" PRIu64 "\n",
                timer->frequency_hz) < 0 ||
        fprintf(stream, "timer_frequency_hz_valid=%s\n",
                timer->frequency_hz_valid ? "true" : "false") < 0 ||
        fprintf(stream, "traversal=%s\n",
                pointer_chase_order_name(chase->order)) < 0 ||
        fprintf(stream, "random_seed_applicable=%s\n",
                chase->order == POINTER_CHASE_RANDOMIZED ? "true" : "false") < 0 ||
        fprintf(stream, "random_seed=%" PRIu64 "\n", chase->seed) < 0 ||
        fprintf(stream, "node_count=%zu\n", chase->node_count) < 0 ||
        fprintf(stream, "node_spacing_bytes=%zu\n",
                chase->node_spacing_bytes) < 0 ||
        fprintf(stream, "allocation_bytes=%zu\n",
                chase->allocation_bytes) < 0 ||
        fprintf(stream, "allocation_alignment_bytes=%zu\n",
                chase->allocation_alignment_bytes) < 0 ||
        fprintf(stream, "timed_sample_count=%zu\n",
                config->timed_sample_count) < 0 ||
        fprintf(stream, "warmup_batch_count=%zu\n",
                config->warmup_batch_count) < 0 ||
        fprintf(stream, "dependent_accesses_per_sample=%zu\n",
                config->dependent_accesses_per_sample) < 0 ||
        fprintf(stream, "zero_elapsed_count=%zu\n",
                results->zero_elapsed_count) < 0 ||
        fprintf(stream, "zero_overhead_count=%zu\n",
                results->zero_overhead_count) < 0 ||
        fprintf(stream, "data_encoding=tab-separated-decimal-integers\n") < 0 ||
        fprintf(stream, "data_begin\n") < 0 ||
        fprintf(stream,
                "sample_index\telapsed_raw_ticks\ttimer_overhead_raw_ticks\n") < 0) {
        return -1;
    }

    return 0;
}

int raw_output_write_tsv(const char *path,
                         const struct raw_output_context *context,
                         const struct system_metadata *metadata,
                         const struct timer_info *timer,
                         const struct pointer_chase *chase,
                         const struct measurement_config *config,
                         const struct measurement_results *results)
{
    FILE *stream;
    int descriptor;
    int saved_errno;

    if (validate_inputs(path, context, metadata, timer, chase, config,
                        results) != 0) {
        return -1;
    }

    descriptor = open(path, O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (descriptor < 0) {
        return -1;
    }

    stream = fdopen(descriptor, "w");
    if (stream == NULL) {
        saved_errno = errno;
        (void)close(descriptor);
        (void)unlink(path);
        errno = saved_errno;
        return -1;
    }

    if (write_header(stream, path, context, metadata, timer, chase, config,
                     results) != 0) {
        goto write_failure;
    }

    for (size_t sample = 0; sample < results->sample_count; ++sample) {
        if (fprintf(stream, "%zu\t%" PRIu64 "\t%" PRIu64 "\n",
                    sample, results->elapsed_ticks[sample],
                    results->timer_overhead_ticks[sample]) < 0) {
            goto write_failure;
        }
    }

    if (fprintf(stream, "data_end\n") < 0 || fflush(stream) != 0 ||
        fsync(descriptor) != 0) {
        goto write_failure;
    }

    if (fclose(stream) != 0) {
        saved_errno = errno;
        (void)unlink(path);
        errno = saved_errno;
        return -1;
    }

    return 0;

write_failure:
    saved_errno = errno == 0 ? EIO : errno;
    (void)fclose(stream);
    (void)unlink(path);
    errno = saved_errno;
    return -1;
}

#if defined(ECE592_RAW_OUTPUT_SELF_TEST)

#include "affinity.h"

#include <limits.h>
#include <stdlib.h>

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

int main(int argc, char **argv)
{
    const struct measurement_config config = {
        ECE592_MINIMUM_TIMED_SAMPLES,
        1000u,
        256u
    };
    struct affinity_info affinity;
    struct measurement_results results;
    struct pointer_chase chase;
    struct raw_output_context context;
    struct system_metadata metadata;
    struct timer_info timer;
    char run_command[1024];
    int logical_cpu;
    int written;

    if (argc != 3 || parse_logical_cpu(argv[1], &logical_cpu) != 0) {
        fprintf(stderr, "usage: %s <logical-cpu> <new-output-path>\n", argv[0]);
        return 2;
    }

    written = snprintf(run_command, sizeof(run_command), "%s %s %s",
                       argv[0], argv[1], argv[2]);
    if (written < 0 || (size_t)written >= sizeof(run_command)) {
        fprintf(stderr, "error: run command is too long\n");
        return 2;
    }

    if (affinity_pin_current_thread(logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (metadata_collect(&metadata) != 0) {
        perror("metadata_collect");
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

    context.experiment_name = "raw-output-self-test";
    context.build_command = ECE592_BUILD_COMMAND;
    context.run_command = run_command;
    context.locality_method = "pin-before-allocation plus first-touch memset";
    context.smt_siblings_idle = "not-verified-by-this-test";
    context.environment_variables = "none required by self-test";

    if (raw_output_write_tsv(argv[2], &context, &metadata, &timer, &chase,
                             &config, &results) != 0) {
        perror("raw_output_write_tsv");
        measurement_results_destroy(&results);
        pointer_chase_destroy(&chase);
        return 1;
    }

    printf("output_filename=%s\n", argv[2]);
    printf("timed_sample_count=%zu\n", results.sample_count);
    printf("raw_rows_written=%zu\n", results.sample_count);
    printf("existing_files_overwritten=false\n");
    printf("status=ok\n");

    measurement_results_destroy(&results);
    pointer_chase_destroy(&chase);
    return 0;
}

#endif
