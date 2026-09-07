#ifndef ECE592_RAW_OUTPUT_H
#define ECE592_RAW_OUTPUT_H

#include "measurement.h"
#include "metadata.h"
#include "pointer_chase.h"
#include "timer.h"

struct raw_output_context {
    const char *experiment_name;
    const char *build_command;
    const char *run_command;
    const char *locality_method;
    const char *smt_siblings_idle;
    const char *environment_variables;
};

/*
 * Create a new, self-describing TSV file. An existing path is never
 * overwritten. Every measured and timer-overhead sample is written.
 */
int raw_output_write_tsv(const char *path,
                         const struct raw_output_context *context,
                         const struct system_metadata *metadata,
                         const struct timer_info *timer,
                         const struct pointer_chase *chase,
                         const struct measurement_config *config,
                         const struct measurement_results *results);

#endif
