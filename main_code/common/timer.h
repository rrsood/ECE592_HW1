#ifndef ECE592_TIMER_H
#define ECE592_TIMER_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Describes the timer selected by the architecture-specific implementation.
 * A frequency is reported only when it is trustworthy for unit conversion.
 */
struct timer_info {
    const char *name;
    const char *unit;
    uint64_t frequency_hz;
    bool frequency_hz_valid;
};

/* Returns 0 when the required unprivileged timer is available. */
int timer_init(struct timer_info *info);

/* Read ordered start and stop timestamps around a measured region. */
uint64_t timer_start(void);
uint64_t timer_stop(void);

#endif
