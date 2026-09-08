/* =================================================================================================
Project: ECE 592 - Homework 1: Cache Reverse Engineering C Microbenchmark Suite 
File: x86-64 Cache Hierarchy Microbenchmark
Author:
    1. Devanshi Jariwala (djariwa@ncsu.edu) - Developer
    2. Rohit Sood (rrsood@ncsu.edu) - Developer

Description:
A parameterizable C microbenchmark that creates a randomized pointer-chase dependent load chain for 
measuring the true latency of loads to a given CPU core's cache hierarchy. The user-configurable 
working set can be swept to determine the number of levels in a hierarchy and the capcity of each
level. 

The following are the commands required to build the microbenchmark, save the compiler version, and 
save the build command ([1], pg. 6, 7): 

  (1) gcc --version

  (2) gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer -S -o 
      x86_64_cache_hierarchy_microbench x86_64_cache_hierarchy_microbench.c.

  (3) objdump -d ./x86_64_cache_hierarchy_microbench > x86_64_cache_hierarchy_microbench.dis

  (4) objdump -d -S ./x86_64_cache_hierarchy_microbench > 
      x86_64_cache_hierarchy_microbench.source.dis

Note, the use of level zero optimization is a requirement set by the assignment specifications.

The following is the command required to run the executable built with the above command:

  (1) ./x86_64_cache_hierarchy_microbench <working_set_bytes> <line_size> <N_per_batch>
      <num_samples> <seed> [sequential].

Note, this command assumes the shell environment's current working directory is the one that
that contains the executable file. The chevron placeholders for the command-line arguments are 
replaced with user-defined values in an actual run command. The Sequential argument is either 
included (without the brackets), or excluded, if the user wants to issue a non-randomized 
pointer-chase dependent load chain (to guage the effects of the prefetcher). Below is an overview of 
each command-line argument:

  - <working_set_bytes> - The size, in bytes, of the load chain. ([1], pg. 6, 14)

  - <line_size_bytes> - The block size of the memory hierarchy. ([1], pg. 9)

  - <N_per_batch> - The number of loads per one timed batch. Setting this parameter to zero can be 
    used to measure an empty batch, which is useful for gauging time lost to microbenchmark 
    overhead. ([2], pg. 7, 11)

  - <num_samples> - The number of timed batches. ([2], pg. 11)

  - <seed> - A number used to pseudo-randomize the order of the load chain, allowing results to be 
    reproducible when the same seed and other command-line arguments are reused. ([1], pg. 8-9)

  - [sequential] - If this command-line argument is included, the load chain is non-randomized. This
    allows the user to guage the effects of a core's prefetcher.

Version Log:
Date         Version #   Description
----------   ---------   --------------------------------------------------
2026-09-05   01.00       Initial implementation of microbench specs
2026-09-06   01.01       Improved documentation & code + corrected spec compliance issues
================================================================================================= */

// ------------- Included File(s) ------------- //
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
/* The x86intrin.h is a header filed that provides access to x86-specific functions, such as RDTSC 
   ([2], pg. 5). */
#include <x86intrin.h>>
// -------------------------------------------- //

/* The structure used for the nodes in the load chain. */
struct load_link {
    /* A pointer-chase dependent load chain is a singly linked list of nodes, where each node
       points to the next node in the list. Traversing through the list generates a load for each
       node that reads the next node's address. The next load cannot execute until the current load
       has resolved, as the CPU core cannot determine the address of the next node's next node 
       before it has yet to even determine the address of the next node. This dependency between
       loads prevents the CPU core from issuing loads in parallel, which can contaminate the 
       microbenchmarks timing measurements. The microbenchmark functions by tracking the access time 
       for a N sized batch of loads, and dividing the total batch access time by the batch's size to 
       find the average time per load. Note, that batching is used to amortize the cost of the 
       microbenchmark's own overhead over the N loads. If multiple loads within a batch issue in 
       parallel, the average access time will be lower than the true time it would takes to load a 
       single item from the memory hierarchy. A working set that is actually too large to be in a 
       certain cache level, may report access times that correspond to said level, not because the 
       memory accesses are actually in that level, but because memory-level parallelism is making 
       the effective access time shorter than it truly is. ([1], pg. 8) */
    struct load_link * next;
};

/* This function is used to record the processor's timestamp counter before an N-batch of loads are
   executed. It ensures that the counter is not read before prior loads (e.g., from a previous batch)
   have finished executing, and that subsequent loads (i.e., the loads from the batch) are not
   issued before the timestamp counter can be read. By enforcing a serial execution order, this 
   function ensures the microbenchmarks timing measurements are accurate. ([2], pg. 5) */
static inline uint64_t x86_tsc_start (unsigned * log_cpu) {
    /* A function that forces all prior load instructions to execute before any subsequent load
       instructions are issued. Note, this function is largely redundant when using RDTSCP, which 
       already waits for prior loads to finish executing before it reads the processor's timestamp 
       counter. This structure was kept to maintain the one presented in the homework materials. 
       ([1], pg. 7) */
    _mm_lfence();

    /* __rdtscp() waits for all prior loads to finish executing and then returns the processor's 
       64-bit timestamp counter value and the logical CPU ID. The ID can be used to verify that the 
       OS did not migrate the running microbenchmark to a different core, which could contaminate 
       the measurements. ([1], pg. 7) */
    uint64_t timestamp = __rdtscp(log_cpu);

    /* _mm_lfence() is called again to ensure that no subsequent load instructions are issued
       before the processor's timestamp counter is read. */
    _mm_lfence();

    return timestamp;
}

/* This function is used to record the processor's timestamp counter after an N-batch of loads are 
   executed. ([2], pg. 5) */
static inline uint64_t x86_tsc_stop (unsigned * log_cpu) {
    /* No redundant _mm_lfence() is used for the recording the processor's timestamp counter after 
       an N batch of loads. This is purely to match the structure presented in the homework 
       materials. ([1], pg. 7) */
    uint64_t timestamp = __rdtscp(log_cpu);

    /* Load instructions from the next batch should not execute before the timestamp counter for the 
       end of the current batch can be read. */
    _mm_lfence();
}

/* Passes in a pointer to an unsigned 32 bit integer called seed. Sets the local unsigned 32 bit int
   x to the value pointed to by seed. Does some shifting and xoring that makes X difficult to track
   (pseudo-randomization). sets the value at the pointer to x and also returns said value. */
static uint32_t xorshift32 (uint32_t * state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return (*state = x);
}

/* Load Chain Building Function Skeleton from Project Specs */
// static void make_random_cycle(struct node * nodes, size_t n, uint32_t seed) {
//     size_t * order = malloc(n * sizeof(*order));
//     if (!order || n < 2) exit(1);

//     for (size_t i = 0; i < n; i++) order[i] = i;

//     uint32_t state = seed ? seed : 1u;

//     for (size_t i = n - 1; i > 0; i--) {
//         size_t j = (size_t)(xorshift32(&state) % (uint32_t)(i + 1));
//         size_t tmp = order[i];
//         order[i] = order[j];
//         order[j] = tmp;
//     }

//     for (size_t i = 0; i < n; i++)
//         nodes[order[i]].next = &nodes[order[(i + 1) % n]];

//     free(order);
// }

/* My goal is to build the load chain as a series of pointers seperated by bytes such that each
   pointer spacing pair is a node. I need to determine the size of a pointer (practically will 
   always be 8 bytes for a 64-bit system but ill still use robust checking) and then i get the user
   provided line size. I'll create these "nodes" and first link them in order and then randomize
   them */
static void build_load_chain (struct load_link * node, size_t working_set_bytes, size_t line_size_bytes) {
    /* find the size of a pointer for the system */
    uintmax_t padding = line_size_bytes - sizeof(node);
    /* malloc the load link, add the spacing, repeat, making sure to connect the pointers, also save first pointer address to have it link to the last load (chain) */
}

// =================================================================================================
// ========================================= References ========================================= //
/* [1] ECE 592 - Homework 1: Specifications - Ajorpaz, Samira */
/* [2] ECE 592 - Reverse Engineering the CPU Cache Hierarchy Problem Session: Slide Deck - 
       Ajorpaz, Samira */
// ============================================================================================== // 