#ifndef ECE592_RAW_OUTPUT_H
#define ECE592_RAW_OUTPUT_H

#include "eviction_layout.h"
#include "eviction_measurement.h"
#include "measurement.h"
#include "metadata.h"
#include "conflict_chase.h"
#include "inclusion_chase.h"
#include "inclusion_measurement.h"
#include "pointer_chase.h"
#include "spatial_chase.h"
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

int raw_output_write_independent_tsv(
    const char *path,
    const struct raw_output_context *context,
    const struct system_metadata *metadata,
    const struct timer_info *timer,
    const struct pointer_chase *chase,
    const struct measurement_config *config,
    const struct measurement_results *results);

int raw_output_write_spatial_tsv(const char *path,
                                 const struct raw_output_context *context,
                                 const struct system_metadata *metadata,
                                 const struct timer_info *timer,
                                 const struct spatial_chase *chase,
                                 const struct measurement_config *config,
                                 const struct measurement_results *results);

int raw_output_write_conflict_tsv(const char *path,
                                  const struct raw_output_context *context,
                                  const struct system_metadata *metadata,
                                  const struct timer_info *timer,
                                  const struct conflict_chase *chase,
                                  const struct measurement_config *config,
                                  const struct measurement_results *results);

int raw_output_write_inclusion_tsv(
    const char *path,
    const struct raw_output_context *context,
    const struct system_metadata *metadata,
    const struct timer_info *timer,
    const struct inclusion_chase *chase,
    const struct inclusion_measurement_config *config,
    const struct inclusion_measurement_results *results);

int raw_output_write_eviction_tsv(
    const char *path,
    const struct raw_output_context *context,
    const struct system_metadata *metadata,
    const struct timer_info *timer,
    const struct eviction_layout *layout,
    const struct eviction_measurement_config *config,
    const struct eviction_measurement_results *results);

#endif
