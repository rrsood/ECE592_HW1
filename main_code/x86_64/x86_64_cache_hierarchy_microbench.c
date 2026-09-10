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
save the build command ([1] pg. 6, 7): 

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

  - <working_set_bytes> - The size, in bytes, of the load chain. ([1] pg. 6, 14)

  - <line_size_bytes> - The block size of the memory hierarchy. ([1] pg. 9)

  - <N_per_batch> - The number of loads per one timed batch. Setting this parameter to zero can be 
    used to measure an empty batch, which is useful for gauging time lost to microbenchmark 
    overhead. ([2], pg. 7, 11)

  - <num_samples> - The number of timed batches. ([2] pg. 11)

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

/* ------------------ MACROS ------------------ */
/* The first node of the load chain (i.e., the first pointer) must be block aligned. Using an
   alignment value that is much larger than any plausible line size ensures that the first node is 
   block aligned regardless of the actual line size. ([1] pg.22) */
#define BUFFER_ALIGNMENT 4096u
/* -------------------------------------------- */

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
      the effective access time shorter than it truly is. ([1] pg. 8) */
   struct load_link * next;
};

/* This function is used to record the processor's timestamp counter before an N-batch of loads are
   executed. It ensures that the counter is not read before prior loads (e.g., from a previous batch)
   have finished executing, and that subsequent loads (i.e., the loads from the batch) are not
   issued before the timestamp counter can be read. By enforcing a serial execution order, this 
   function ensures the microbenchmarks timing measurements are accurate. ([2] pg. 5) */
static inline uint64_t x86_tsc_start (unsigned * log_cpu) {
   /* A function that forces all prior load instructions to execute before any subsequent load
      instructions are issued. Note, this function is largely redundant when using RDTSCP, which 
      already waits for prior loads to finish executing before it reads the processor's timestamp 
      counter. This structure was kept to maintain the one presented in the homework materials. 
      ([1] pg. 7) */
   _mm_lfence();

   /* __rdtscp() waits for all prior loads to finish executing and then returns the processor's 
      64-bit timestamp counter value and the logical CPU ID. The ID can be used to verify that the 
      OS did not migrate the running microbenchmark to a different core, which could contaminate 
      the measurements. ([1] pg. 7) */
   uint64_t timestamp = __rdtscp(log_cpu);

   /* _mm_lfence() is called again to ensure that no subsequent load instructions are issued
      before the processor's timestamp counter is read. */
   _mm_lfence();

   return timestamp;
}

/* This function is used to record the processor's timestamp counter after an N-batch of loads are 
   executed. ([2] pg. 5) */
static inline uint64_t x86_tsc_stop (unsigned * log_cpu) {
   /* No redundant _mm_lfence() is used for the recording the processor's timestamp counter after 
      an N batch of loads. This is purely to match the structure presented in the homework 
      materials. ([1] pg. 7) */
   uint64_t timestamp = __rdtscp(log_cpu);

   /* Load instructions from the next batch should not execute before the timestamp counter for the 
      end of the current batch can be read. */
   _mm_lfence();
}

/* ([1] pg. 8) */
static uint32_t xorshift32 (uint32_t * state) {
   uint32_t x = *state;
   x ^= x << 13;
   x ^= x >> 17;
   x ^= x << 5;
   return (*state = x);
}

/* This function builds a randomized dependent load chain that is the size, in bytes, of the 
   user-specified working set. Each node in the chain is a pointer (i.e., an instantiated load link
   structure) followed by some spacing, in bytes, determined such that the size of the node is equal
   to the user-specified line/block size for the memory hierarchy. It is important that the
   specified line size, which determines the size of each node, is accurate (i.e., equals the 
   actual, undetermined line size) to maintain microbenchmark accuracy. There are three possible 
   cases for how the specified line size / node size can relate to the actual line size, each having
   its own implications for the microbenchmark's accuracy.
   
   Case 1: Node Size < Line Size
   ----------------------------- 
   If the node size is less than the line size, then when the value of a node's pointer (i.e., the 
   address of the memory item to which it points to) is loaded from memory, the memory block it is
   in will contain another pointer or pointers. If these pointers happen to belong to the next node
   in the sequence, their respective loads from memory will be faster due to unintentionally being 
   in the cache because of spatial locality. 
   
   Timing is used to determine what level of the memory hierarchy a given working set is a resident 
   in. When timing measurements are unintentionally faster due to a not-of-interest cache 
   characteristic, like spatial locality, it can make working sets that are too large for a certain 
   level in the hierarchy, appear as if they have access times that map to that level.
   
   Case 2: Node Size = Line Size
   -----------------------------
   When the node size equals the line size, each node's load only maps to one memory block. 
   Therefore, each timing measurement accurately reflects the location of the block within the 
   memory hierarchy.
   
   Case 3: Node Size > Line Size
   -----------------------------
   When the node size is greater than the line size, fewer pointers can fit in the same working set
   than when the node size equals the line size because more bytes are used for spacing. The extra
   spacing never gets placed in the cache because only memory blocks with pointers are ever
   accessed. While a working set may be too large to fit in a given level of the cache hierarchy,
   there may be enough capacity for the number of pointer-corresponding memory blocks in the working
   set. Since these memory blocks are the only items ever accessed, the timing reflects whichever 
   level the footprint actually fits in, not the level implied by the working-set size. This will 
   cause the microbenchmark to overestimate the capacity of a given cache level. 
   
   For a given working set of W bytes and node size of N bytes, in a system with a block size of B
   bytes, the number of bytes actually stored in a given level of the memory hierarchy (i.e., the
   footprint of the microbenchmark) is W * B/N. The ratio of block size to node size comes from the 
   fact that only the bytes of a node that correspond to the memory block containing the pointer 
   will ever be stored in the cache. Therfore, only this fraction of the working set is ever brought 
   into the cache hierarchy. The footprint of a given working set is the actual capacity test, and 
   when the node size equals the block size, the footprint is equal to the size of the working set. 
   When the footprint is smaller than the working set, the cache capacity is overestimated because
   an oversized working set can appear as if it fits within a certain level of the cache hierarchy,
   when in reality it is the working set's footprint that fits within said level. */
static void build_load_chain (struct load_link * node, size_t working_set_bytes, 
                              size_t line_size_bytes) {
   /* The first node of the load chain must be aligned to the start of a block. The aligned allocate
      function (aligned_alloc(alignment, size)) allocates the specified size, in bytes, of storage
      starting at an address of the specified alignment. However, the C11 standard states the align
      allocate function does not work if the size argument is not an integer multiple of the
      alignment argument. For this reason, a copy of the working set size is rounded up to the 
      nearest multiple of the alignment argument. */
// =================================================================================================
}

// ========================================= References ========================================= //
/* [1] ECE 592 - Homework 1: Specifications - Ajorpaz, Samira */
/* [2] ECE 592 - Reverse Engineering the CPU Cache Hierarchy Problem Session: Slide Deck - 
       Ajorpaz, Samira */
// ============================================================================================== // 