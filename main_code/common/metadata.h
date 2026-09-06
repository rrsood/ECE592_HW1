#ifndef ECE592_METADATA_H
#define ECE592_METADATA_H

#include <stdio.h>

#define ECE592_METADATA_TEXT_LENGTH 256
#define ECE592_CPU_LIST_LENGTH 128

struct system_metadata {
    char timestamp_utc[ECE592_METADATA_TEXT_LENGTH];
    char hostname[ECE592_METADATA_TEXT_LENGTH];
    char kernel_release[ECE592_METADATA_TEXT_LENGTH];
    char isa[ECE592_METADATA_TEXT_LENGTH];
    char cpu_model[ECE592_METADATA_TEXT_LENGTH];
    char cpu_model_source[ECE592_METADATA_TEXT_LENGTH];
    char affinity_cpu_list[ECE592_CPU_LIST_LENGTH];
    char thread_siblings_list[ECE592_CPU_LIST_LENGTH];
    long page_size_bytes;
    int logical_cpu;
    int affinity_allowed_cpu_count;
    int physical_core_id;
    int physical_package_id;
    int numa_node;
};

/* Collect only Phase-I-safe Linux identity and CPU-topology information. */
int metadata_collect(struct system_metadata *metadata);

/* Write metadata as machine-readable key=value records. */
int metadata_write(FILE *stream, const struct system_metadata *metadata);

#endif
