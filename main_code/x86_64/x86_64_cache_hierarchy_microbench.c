/* =================================================================================================
Project: ECE 592 - Homework 1: Cache Reverse Engineering C Microbenchmark Suite 
File: x86-64 Cache Hierarchy Microbenchmark
Author:
    1. Devanshi Jariwala (djariwa@ncsu.edu) - Developer
    2. Rohit Sood (rrsood@ncsu.edu) - Developer

Description:
A parameterizable C microbenchmark that can allocate a linked list of nodes, each W bytes (the 
parameterizable working set), connecting the nodes into one randomized cycle, and then time batches
of N dependent pointer-chase loads. Because the order of the nodes in the linked list are 
randomized, and each next load is dependent on the current load resolving, the true latency is 
measured instead of throughput or memory-level parallelism contaminating the timing measurements.
Either a working set can fit in a cache level or it cannot. If it can't, when we access items and 
measure the time, we'll never be accessing an item that is in the cache because items will be too 
far apart from one another that they'll be evicted from the cache by the time we get back around to 
them. We do batching either because of counter granularity and/or because we don't want the overhead
of the timing to itself to add noise, that means limiting the overhead to well-sized batches 
decreases its overall effect to be negligible. 

Version Log:
Date         Version #   Description
----------   ---------   --------------------------------------------------
2026-09-05   01.00       Developed benchmark according to specs (compliance verification needed).
================================================================================================= */

/*
 * cache_bench.c -- Experiment 1: cache capacity / hierarchy detector
 *
 * Method: allocate a working set of W bytes as linked nodes, connect them
 * into ONE randomized cycle, then time batches of N dependent pointer-chase
 * steps. Because each load's address depends on the previous load's value,
 * the core cannot use memory-level parallelism to hide latency -- we are
 * measuring true latency, not throughput.
 *
 * Usage:
 *   ./cache_bench <working_set_bytes> <N_per_batch> <num_samples> <seed> [sequential]
 *
 * Output (to stdout): one CSV line per sample:
 *   sample_index,ticks_elapsed,N_per_batch
 *
 * Build (per spec, -O0 is required for Phase I):
 *   gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer -o cache_bench cache_bench.c
 */
 
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <x86intrin.h>
 
/* ---------- 1. The node type for the pointer-chase ring ---------- */
 
typedef struct Node {
    struct Node *next;
    char padding[56]; /* pad node to 64 bytes = typical cache line size,
                          so each node occupies exactly one line and we
                          control spacing precisely via node count, not
                          incidental struct size */
} Node;
 
/* ---------- 2. The fenced timer pair (x86-64) ---------- */
 
static inline uint64_t tsc_start(void) {
    _mm_lfence();              /* wait for all prior instructions to retire */
    uint64_t t = __rdtsc();    /* read the timestamp counter */
    _mm_lfence();              /* prevent later instructions from starting early */
    return t;
}
 
static inline uint64_t tsc_stop(void) {
    unsigned aux;
    uint64_t t = __rdtscp(&aux); /* waits for prior instructions (esp. loads)
                                     to execute before reading the counter */
    _mm_lfence();                /* stop later instructions from hoisting above this */
    return t;
}
 
/* ---------- 3. A small, fast, seedable RNG (xorshift32) ---------- */
/* We avoid rand()/random() because their internal state and quality vary
 * by libc and are not guaranteed reproducible across the 8 machines. A
 * self-contained RNG means the SAME seed produces the SAME shuffle on
 * every machine, which is required for reproducibility. */
 
static uint32_t xorshift_state;
 
static uint32_t xorshift32(void) {
    uint32_t x = xorshift_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    xorshift_state = x;
    return x;
}
 
/* ---------- 4. Build the pointer-chase ring ---------- */
 
/*
 * Allocates 'num_nodes' Node structs and links them into ONE cycle.
 * If 'sequential' is 0: the cycle visits nodes in RANDOM order (this is
 *   the primary method -- defeats stride prefetchers).
 * If 'sequential' is 1: the cycle visits nodes in ARRAY order (this is
 *   the control -- if this is much faster at large W, that speed
 *   difference is the prefetcher, not evidence of a bigger cache).
 */
static Node *build_ring(size_t num_nodes, int sequential) {
    Node *nodes = aligned_alloc(64, num_nodes * sizeof(Node));
    if (!nodes) {
        fprintf(stderr, "allocation failed for %zu nodes\n", num_nodes);
        exit(1);
    }
 
    /* First-touch every page NOW, right after allocation, so physical
     * pages are actually mapped before we start timing anything. */
    memset(nodes, 0, num_nodes * sizeof(Node));
 
    /* permutation[] will hold a random ordering of node indices 0..num_nodes-1 */
    size_t *permutation = malloc(num_nodes * sizeof(size_t));
    for (size_t i = 0; i < num_nodes; i++) permutation[i] = i;
 
    if (!sequential) {
        /* Fisher-Yates shuffle using our seeded RNG */
        for (size_t i = num_nodes - 1; i > 0; i--) {
            uint32_t r = xorshift32() % (uint32_t)(i + 1);
            size_t tmp = permutation[i];
            permutation[i] = permutation[r];
            permutation[r] = tmp;
        }
    }
    /* if sequential, permutation stays 0,1,2,...,num_nodes-1 */
 
    /* Link nodes[permutation[i]] -> nodes[permutation[i+1]], and wrap the
     * last one back to the first, forming a single cycle through every
     * node. Note we link the STRUCTS in permutation order; each node
     * still lives at its original array slot, so the memory ADDRESSES
     * visited over time follow the permutation, not the allocation order. */
    for (size_t i = 0; i < num_nodes; i++) {
        size_t cur  = permutation[i];
        size_t nxt  = permutation[(i + 1) % num_nodes];
        nodes[cur].next = &nodes[nxt];
    }
 
    free(permutation);
    return nodes;
}
 
/* ---------- 5. The timed chase: N dependent steps, batched ---------- */
 
/* Advances the pointer chain N times and returns the final pointer.
 * The caller times the call to this function; N loads happen inside,
 * each one dependent on the previous (p = p->next), so nothing here
 * can be parallelized by the core. */
static Node *chase(Node *p, size_t N) {
    for (size_t i = 0; i < N; i++) {
        p = p->next;
    }
    return p;
}
 
/* ---------- 6. main: parse args, warm up, run 1e6 timed samples ---------- */
 
int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr,
            "usage: %s <working_set_bytes> <N_per_batch> <num_samples> <seed> [sequential]\n",
            argv[0]);
        return 1;
    }
 
    size_t working_set_bytes = strtoull(argv[1], NULL, 10);
    size_t N_per_batch       = strtoull(argv[2], NULL, 10);
    size_t num_samples       = strtoull(argv[3], NULL, 10);
    xorshift_state           = (uint32_t)strtoul(argv[4], NULL, 10);
    int sequential            = (argc >= 6) ? atoi(argv[5]) : 0;
 
    if (xorshift_state == 0) xorshift_state = 1; /* xorshift breaks at seed 0 */
 
    size_t num_nodes = working_set_bytes / sizeof(Node);
    if (num_nodes < 2) num_nodes = 2;
 
    /* --- Build the ring --- */
    Node *nodes = build_ring(num_nodes, sequential);
    Node *p = &nodes[0];
 
    /* --- Warm-up: touch the working set before timing so page faults,
     *     TLB fills, and cold-cache effects don't pollute the first
     *     timed samples. 10x the batch size is a reasonable warm-up. */
    const size_t WARMUP_STEPS = (num_nodes > 10 * N_per_batch) ? num_nodes : 10 * N_per_batch;
    p = chase(p, WARMUP_STEPS);
 
    /* --- Timed loop: this is the required 1,000,000-sample method. --- */
    uint64_t *samples = malloc(num_samples * sizeof(uint64_t));
 
    for (size_t r = 0; r < num_samples; r++) {
        uint64_t t0 = tsc_start();
        p = chase(p, N_per_batch);
        uint64_t t1 = tsc_stop();
        samples[r] = t1 - t0;
    }
 
    /* Keep the final pointer value "live" so the compiler cannot decide
     * the entire chase loop was dead code and delete it. Printing to
     * stderr (not stdout) keeps this out of our CSV data stream. */
    fprintf(stderr, "sink (ignore): %p\n", (void *)p);
 
    /* --- Emit raw CSV: sample_index,ticks_elapsed,N_per_batch --- */
    for (size_t r = 0; r < num_samples; r++) {
        printf("%zu,%llu,%zu\n", r, (unsigned long long)samples[r], N_per_batch);
    }
 
    free(samples);
    free(nodes);
    return 0;
}