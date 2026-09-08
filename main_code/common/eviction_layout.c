#define _POSIX_C_SOURCE 200809L
#include "eviction_layout.h"

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static uint64_t next_random(uint64_t *state)
{
    uint64_t z = (*state += UINT64_C(0x9e3779b97f4a7c15));
    z = (z ^ (z >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)) * UINT64_C(0x94d049bb133111eb);
    return z ^ (z >> 31);
}

static struct chase_node *at(void *arena, size_t offset)
{
    return (struct chase_node *)(void *)((unsigned char *)arena + offset);
}

void eviction_layout_destroy(struct eviction_layout *layout)
{
    if (layout != NULL) {
        free(layout->allocation);
        free(layout->target_offsets);
        free(layout->pressure_offsets);
        memset(layout, 0, sizeof(*layout));
    }
}

int eviction_layout_create(struct eviction_layout *layout,
                           size_t target_offset,
                           const size_t *pressure_offsets,
                           size_t pressure_count, uint64_t seed)
{
    return eviction_layout_create_targets(layout, &target_offset, 1,
        pressure_offsets, pressure_count, seed);
}

int eviction_layout_create_targets(struct eviction_layout *layout,
    const size_t *target_offsets, size_t target_count,
    const size_t *pressure_offsets, size_t pressure_count, uint64_t seed)
{
    const size_t node_bytes = sizeof(struct chase_node);
    size_t maximum = 0;
    size_t *order;
    long page;
    int error;
    if (layout == NULL) { errno = EINVAL; return -1; }
    memset(layout, 0, sizeof(*layout));
    if (pressure_offsets == NULL || pressure_count < 2 ||
        target_offsets == NULL || target_count == 0) { errno = EINVAL; return -1; }
    if (pressure_count > SIZE_MAX / sizeof(*order) ||
        target_count > SIZE_MAX / sizeof(*order)) {
        errno = EOVERFLOW; return -1;
    }
    for (size_t i = 0; i < target_count; ++i) {
        size_t offset = target_offsets[i];
        if (offset % node_bytes != 0) { errno = EINVAL; return -1; }
        for (size_t j = 0; j < i; ++j)
            if (offset == target_offsets[j]) { errno = EINVAL; return -1; }
        if (offset > maximum) maximum = offset;
    }
    for (size_t i = 0; i < pressure_count; ++i) {
        size_t offset = pressure_offsets[i];
        if (offset % node_bytes != 0) {
            errno = EINVAL; return -1;
        }
        for (size_t j = 0; j < target_count; ++j)
            if (offset == target_offsets[j]) { errno = EINVAL; return -1; }
        for (size_t j = 0; j < i; ++j) {
            if (offset == pressure_offsets[j]) { errno = EINVAL; return -1; }
        }
        if (offset > maximum) maximum = offset;
    }
    if (maximum > SIZE_MAX - node_bytes) { errno = EOVERFLOW; return -1; }
    page = sysconf(_SC_PAGESIZE);
    if (page <= 0 || ((size_t)page & ((size_t)page - 1)) != 0 ||
        (size_t)page % sizeof(void *) != 0) { errno = EINVAL; return -1; }
    size_t order_count = pressure_count > target_count ? pressure_count : target_count;
    order = malloc(order_count * sizeof(*order));
    if (order == NULL) return -1;
    layout->target_offsets = malloc(target_count * sizeof(*layout->target_offsets));
    layout->pressure_offsets =
        malloc(pressure_count * sizeof(*layout->pressure_offsets));
    if (layout->target_offsets == NULL || layout->pressure_offsets == NULL) {
        free(order);
        eviction_layout_destroy(layout);
        return -1;
    }
    memcpy(layout->target_offsets, target_offsets,
           target_count * sizeof(*layout->target_offsets));
    memcpy(layout->pressure_offsets, pressure_offsets,
           pressure_count * sizeof(*layout->pressure_offsets));
    layout->seed = seed;
    error = posix_memalign(&layout->allocation, (size_t)page, maximum + node_bytes);
    if (error != 0) {
        free(order);
        eviction_layout_destroy(layout);
        errno = error;
        return -1;
    }
    layout->allocation_bytes = maximum + node_bytes;
    /* First touch must happen after caller affinity is established. */
    memset(layout->allocation, 0, layout->allocation_bytes);
    memcpy(order, pressure_offsets, pressure_count * sizeof(*order));
    for (size_t remaining = pressure_count; remaining > 1; --remaining) {
        uint64_t bound = (uint64_t)remaining;
        uint64_t threshold = (UINT64_C(0) - bound) % bound;
        uint64_t value;
        do { value = next_random(&seed); } while (value < threshold);
        size_t chosen = (size_t)(value % bound);
        size_t temporary = order[remaining - 1];
        order[remaining - 1] = order[chosen];
        order[chosen] = temporary;
    }
    layout->pressure_start = at(layout->allocation, order[0]);
    layout->pressure_count = pressure_count;
    for (size_t i = 0; i < pressure_count; ++i) {
        at(layout->allocation, order[i])->next =
            at(layout->allocation, order[(i + 1) % pressure_count]);
    }
    memcpy(order, target_offsets, target_count * sizeof(*order));
    for (size_t remaining = target_count; remaining > 1; --remaining) {
        uint64_t bound = (uint64_t)remaining;
        uint64_t threshold = (UINT64_C(0) - bound) % bound;
        uint64_t value;
        do { value = next_random(&seed); } while (value < threshold);
        size_t chosen = (size_t)(value % bound);
        size_t temporary = order[remaining - 1];
        order[remaining - 1] = order[chosen];
        order[chosen] = temporary;
    }
    layout->target = at(layout->allocation, order[0]);
    layout->target_count = target_count;
    for (size_t i = 0; i < target_count; ++i)
        at(layout->allocation, order[i])->next =
            at(layout->allocation, order[(i + 1) % target_count]);
    free(order);
    return 0;
}

#ifdef ECE592_EVICTION_LAYOUT_SELF_TEST
#include <assert.h>
#include <stdio.h>
int main(void)
{
    /* Synthetic pointer-sized slots: no cache geometry is assumed. */
    size_t offsets[7];
    struct eviction_layout a, b;
    for (size_t i = 0; i < 7; ++i) offsets[i] = (i + 1) * sizeof(struct chase_node);
    assert(eviction_layout_create(&a, 0, offsets, 7, 592) == 0);
    assert(eviction_layout_create(&b, 0, offsets, 7, 592) == 0);
    struct chase_node *p = a.pressure_start, *q = b.pressure_start;
    unsigned seen = 0;
    for (size_t i = 0; i < 7; ++i) {
        size_t x = (size_t)((unsigned char *)p - (unsigned char *)a.allocation);
        size_t y = (size_t)((unsigned char *)q - (unsigned char *)b.allocation);
        assert(x == y && x % sizeof(*p) == 0);
        size_t index = x / sizeof(*p);
        assert(index >= 1 && index <= 7 && !(seen & (1u << index)));
        seen |= 1u << index;
        p = p->next; q = q->next;
    }
    assert(p == a.pressure_start && q == b.pressure_start);
    assert(a.target->next == a.target);
    eviction_layout_destroy(&a); eviction_layout_destroy(&b);
    size_t targets[] = {0, 8 * sizeof(struct chase_node), 9 * sizeof(struct chase_node)};
    assert(eviction_layout_create_targets(&a, targets, 3, offsets, 7, 592) == 0);
    assert(eviction_layout_create_targets(&b, targets, 3, offsets, 7, 592) == 0);
    p = a.target; q = b.target; seen = 0;
    for (size_t i = 0; i < 3; ++i) {
        size_t x = (size_t)((unsigned char *)p - (unsigned char *)a.allocation);
        size_t y = (size_t)((unsigned char *)q - (unsigned char *)b.allocation);
        assert(x == y);
        size_t j = 0;
        while (j < 3 && targets[j] != x) ++j;
        assert(j < 3 && !(seen & (1u << j)));
        seen |= 1u << j;
        p = p->next; q = q->next;
    }
    assert(seen == 7 && p == a.target && q == b.target);
    eviction_layout_destroy(&a); eviction_layout_destroy(&b);
    offsets[0] = 0;
    assert(eviction_layout_create(&a, 0, offsets, 7, 592) == -1 && errno == EINVAL);
    offsets[0] = offsets[1];
    assert(eviction_layout_create(&a, 0, offsets, 7, 592) == -1 && errno == EINVAL);
    puts("unique_target_cycle=true\nunique_pressure_cycle=true\nreproducible_order=true\n"
         "target_excluded=true\noverlap_rejected=true\nstatus=ok");
    return 0;
}
#endif
