#ifndef ECE592_AFFINITY_H
#define ECE592_AFFINITY_H

/* Results recorded after the calling thread has been pinned. */
struct affinity_info {
    int requested_cpu;
    int running_cpu;
    int allowed_cpu_count;
};

/*
 * Pin the calling thread to one Linux logical CPU and verify the result.
 * Returns 0 on success and -1 on failure, with errno describing the error.
 */
int affinity_pin_current_thread(int logical_cpu, struct affinity_info *info);

#endif
