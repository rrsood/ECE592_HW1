/* ============================================================================
 * cache_bench.c
 *
 * Timing-only cache capacity / hierarchy reverse engineering -- x86-64 path
 * (Intel and AMD; a separate AArch64 source implements the Arm timer path.)
 *
 * ECE 592 Homework I -- PHASE I (timing only).
 * No performance counters, no sysfs cache fields, no published cache
 * specifications were consulted to produce or adjust any value this program
 * reports.
 *
 * ============================================================================
 * 1. WHAT THIS PROGRAM MEASURES
 * ============================================================================
 *
 * One invocation measures the average latency of a single *dependent* memory
 * load for ONE working-set size. You invoke it once per x-axis point; sweeping
 * the working-set size across many invocations produces the capacity /
 * hierarchy curve.
 *
 * The underlying physics: a cache level can only service an access at its own
 * latency if the data being accessed actually resides in it. Build a working
 * set of W bytes, traverse all of it repeatedly, and the observed latency per
 * access tells you which level of the hierarchy is servicing those accesses.
 * Sweeping W upward should therefore produce a STAIRCASE:
 *
 *      latency/access
 *          ^
 *          |                                     ________ DRAM
 *          |                          __________/
 *          |               __________/  LLC
 *          |    __________/  L2
 *          |___/  L1
 *          +--------------------------------------------> working-set size W
 *
 * Every flat plateau is one residency class. Every step up marks a capacity
 * boundary: the working set just stopped fitting in the previous level.
 * Counting plateaus counts cache levels; locating each step locates each
 * level's capacity.
 *
 * WHY THE PLATEAUS ARE FLAT (the steady-state argument):
 *   - If W fits in some level, warm-up makes the whole ring resident there and
 *     every subsequent access hits at that level's latency. Latency does not
 *     depend on W within the plateau, so the curve is flat.
 *   - If W exceeds that level, the ring can never be resident. Because the ring
 *     is a SINGLE cycle, a given node is only revisited after every other node
 *     has been touched. With more distinct lines in flight than the level can
 *     hold, that node is always evicted before we return to it -- on lap 1 and
 *     equally on lap 1000. The miss behaviour is therefore also steady, just at
 *     the next level's latency, producing the next flat plateau.
 *
 * ============================================================================
 * 2. THE THREE METHODOLOGICAL PILLARS
 * ============================================================================
 *
 * PILLAR 1 -- DEPENDENCY CHAIN (pointer chasing).
 *   A modern out-of-order core keeps many loads in flight at once
 *   ("memory-level parallelism", MLP). Timing N *independent* loads would let
 *   the core overlap their latencies, so the per-load figure would measure
 *   THROUGHPUT and look far better than the true latency. We defeat MLP by
 *   making the address of load i+1 be the value returned by load i (p = *p).
 *   The core physically cannot issue the next load early: until the current
 *   load returns, it does not know where to load from. Spec: "A cache-latency
 *   benchmark must contain a true dependency chain ... so that the next
 *   measured load cannot start before the previous one completes."
 *
 * PILLAR 2 -- RANDOMIZED ORDER (defeating the hardware prefetcher).
 *   A dependency chain alone is not enough. If the chain walked memory with a
 *   regular stride, the hardware prefetcher would learn the pattern and fetch
 *   lines before they are demanded, hiding true latency and making a large
 *   working set look deceptively cache-resident. We therefore link nodes in a
 *   random permutation, so consecutive addresses have no exploitable
 *   relationship. A SEQUENTIAL mode is provided as the required control: if
 *   sequential is much faster than randomized at large W, that gap is
 *   prefetching, not a larger cache. The final inference uses the randomized
 *   traversal -- the method least influenced by prefetching.
 *
 * PILLAR 3 -- BATCHING (amortizing instrumentation overhead).
 *   The LFENCE + RDTSCP sequence costs on the order of tens of cycles. An L1
 *   hit is roughly 4-5 cycles. Timing a single access would therefore mostly
 *   measure our own instrumentation and could never separate an L1 hit from an
 *   L2 hit. We instead time N dependent accesses between ONE start/stop pair
 *   and divide by N in post-processing: the fixed overhead is divided by N and
 *   becomes negligible, while the per-access cost does not shrink. Spec:
 *   "time N dependent accesses between a single start/stop pair and divide
 *   by N ... Keep single-access timing only as a diagnostic."
 *
 * ============================================================================
 * 3. MEMORY LAYOUT -- WHY NODE SPACING IS A PARAMETER, NOT A CONSTANT
 * ============================================================================
 *
 * A tempting implementation is a padded struct:
 *
 *     struct Node { struct Node *next; char pad[56]; };   /· 64 bytes ·/
 *
 * That hardcodes a 64-byte node, silently ASSUMING a 64-byte cache line --
 * one of the very quantities this assignment requires us to discover
 * experimentally. The spec forbids it explicitly: "Make node spacing/alignment
 * a benchmark parameter rather than silently assuming the cache-line size you
 * are trying to discover" and "Do not hard-code the cache-line size you are
 * trying to discover."
 *
 * We therefore treat the allocation as a flat byte buffer and place one
 * pointer every `spacing` bytes:
 *
 *   offset:   0                spacing          2*spacing        3*spacing
 *             |                |                |                |
 *   memory:   [ptr][--unread--][ptr][--unread--][ptr][--unread--][ptr]...
 *             \_______________/
 *              one "node" = one 8-byte pointer + dead space out to `spacing`
 *
 * ONLY the 8-byte pointer at each node's start is ever read. The bytes between
 * pointers are never touched; they exist purely to control how far apart
 * consecutive pointer fields sit in the address space.
 *
 * ---- WHY SPACING MUST MATCH THE LINE SIZE ----------------------------------
 *
 * Let S = spacing, B = the true (unknown) line size, W = working-set bytes.
 * The cache stores LINES, and only lines we actually touch ever enter it.
 * With S >= B, each node contributes exactly one touched line, so:
 *
 *       lines_touched  = W / S
 *       cache_footprint = (W / S) * B
 *
 * A capacity step occurs when cache_footprint reaches the level's capacity C:
 *
 *       (W / S) * B = C   =>   W_step = C * (S / B)
 *
 * So the working-set size at which the step APPEARS is the true capacity
 * scaled by S/B:
 *
 *   - S == B : W_step = C. The x-axis means what it claims. Correct.
 *   - S >  B : W_step = C * (S/B) > C. OVERESTIMATE by exactly the
 *              over-spacing ratio. Concretely, at S=256 and B=64 you would
 *              report a cache 4x larger than reality -- and the staircase
 *              would look perfectly clean while doing so, because nothing
 *              about the plot's SHAPE reveals that the x-axis is miscalibrated.
 *              The mechanism: 3 of every 4 lines in the allocation are dead
 *              space that never enters the cache, so you must allocate 4x more
 *              to touch the same number of lines.
 *   - S <  B : several pointers share one fetched line, so some accesses are
 *              cheap spatial hits riding along with a neighbour. The boundary
 *              location stays roughly right, but each level's clean latency is
 *              diluted and the plateaus blur -- a different failure mode with a
 *              different visual signature.
 *
 * Neither error direction is safe, which is why spacing is swept rather than
 * assumed. Our procedure is iterative and disclosed in the report:
 *   (i)   coarse capacity pass at a provisional spacing, to locate boundaries
 *         approximately;
 *   (ii)  line-size experiment (hold W fixed, sweep S) to measure B;
 *   (iii) refined capacity pass with S = B -- these are the REPORTED values.
 * Step (i) is scaffolding; only step (iii) enters the inference. Note also
 * that sweeping S with W fixed IS the line-size experiment, so this same
 * program implements Experiment 2 with no code change.
 *
 * ---- ALIGNMENT: WHY NO POINTER EVER STRADDLES A LINE BOUNDARY --------------
 *
 * A naturally aligned object of size k never straddles a boundary of size B
 * whenever B is a multiple of k. Our pointers are sizeof(void*) = 8 bytes on
 * any 64-bit target (we use sizeof rather than the literal 8 so the reasoning
 * stays honest). We align the whole buffer to a 4096-byte page and require
 * `spacing` to be a multiple of 8, so every pointer field lands on an 8-byte
 * boundary. Every plausible line size (32/64/128/256) is a multiple of 8, so a
 * pointer can never be split across two lines. That matters because a
 * split-line load forces the hardware to fetch and stitch together TWO lines,
 * injecting a latency artifact unrelated to cache capacity. Page alignment
 * additionally guarantees node 0 begins exactly at a line boundary whatever the
 * true line size turns out to be -- so the offset of every node relative to its
 * line is determined by `spacing` alone, not by an arbitrary malloc address.
 *
 * ============================================================================
 * 4. USAGE
 * ============================================================================
 *
 *   ./cache_bench <working_set_bytes> <node_spacing_bytes> <N_per_batch>
 *                 <num_samples> <seed> [sequential]
 *
 *     working_set_bytes   footprint to allocate and traverse (must be an exact
 *                         multiple of node_spacing_bytes -- see validation)
 *     node_spacing_bytes  bytes between consecutive pointer fields
 *     N_per_batch         dependent loads timed per sample (Pillar 3)
 *     num_samples         timed batches to collect (spec requires >= 1,000,000)
 *     seed                RNG seed for the shuffle; recorded for reproducibility
 *     sequential          optional: 0 = randomized (default, primary method)
 *                                   1 = sequential  (prefetcher control)
 *
 *   stdout : raw CSV -- sample_index,ticks_elapsed,N_per_batch
 *   stderr : run metadata as '#'-prefixed key=value lines (manifest source)
 *
 *   Metadata goes to stderr specifically so that `./cache_bench ... > data.csv`
 *   captures pure CSV while the metadata can be redirected to its own file.
 *
 *   Example (pinned to logical CPU 4, as the spec requires):
 *     taskset -c 4 ./cache_bench 32768 64 1000 1000000 12345 0 \
 *         > capacity_ws32768.csv 2> capacity_ws32768.meta
 *
 * ============================================================================
 * 5. BUILD  (spec mandates -O0 for the Phase-I baseline)
 * ============================================================================
 *
 *   gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer \
 *       -o cache_bench cache_bench.c
 *
 * -O0 is required so the intended access pattern survives into the binary: no
 * dead-code elimination of the chase, no vectorization, no unrolling into a
 * different access pattern, no hoisting of the timer reads. The cost is the
 * "-O0 tax" documented at the chase loop below. Do NOT add -flto for the
 * baseline. The generated assembly must be inspected and archived; see the
 * build script, which emits cache_bench.s and the objdump listings.
 * ==========================================================================*/

#define _ISOC11_SOURCE          /* expose C11 aligned_alloc() */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <inttypes.h>           /* PRIu64: portable printf formats */
#include <x86intrin.h>          /* __rdtscp, _mm_lfence */


/* ---------------------------------------------------------------------------
 * Types and constants
 * ------------------------------------------------------------------------ */

/* We walk memory as a chain of pointers-to-pointers. `void **p` reads as: p is
 * an address, and the 8 bytes stored there are themselves an address. Hence
 * `p = (void **)(*p)` loads the pointer at p and makes THAT the new p -- one
 * dependent step of the chase. */
typedef void ** chain_ptr;

/* Buffer alignment. A 4 KiB page is a deliberately generous choice: it is a
 * multiple of every plausible cache line size, so node 0 always starts exactly
 * at a line boundary regardless of what the real line size turns out to be. */
#define BUFFER_ALIGNMENT 4096u

/* Sentinel marking a sample discarded because the thread migrated mid-batch.
 * UINT64_MAX is safe as a sentinel: a real batch would need ~2^64 ticks
 * (millennia at any real clock rate) to produce this value legitimately. */
#define SAMPLE_MIGRATED UINT64_MAX


/* ============================================================================
 * SECTION A -- THE FENCED TIMER PAIR
 * ============================================================================
 *
 * x86 exposes the time-stamp counter via RDTSC / RDTSCP. The subtlety is that
 * RDTSC is NOT serializing: the out-of-order engine may execute it earlier or
 * later relative to surrounding code. Without explicit ordering, the start
 * timestamp can be taken while earlier work is still in flight, or the first
 * loads of the timed region can begin before the timestamp is read. Either way
 * the measured interval is wrong. Intel's SDM documents this and prescribes
 * fence sequences; the course slides give the same skeleton.
 *
 * WHAT EACH INSTRUCTION CONTRIBUTES:
 *
 *   RDTSCP  -- reads the counter, but only after all prior instructions have
 *              executed and all prior loads are globally visible. This is a
 *              BACKWARD ordering guarantee. It also returns IA32_TSC_AUX.
 *   LFENCE  -- on Intel, waits for prior instructions to complete locally
 *              (retire); on AMD it is dispatch-serializing under the default
 *              microcode Linux configures. Either way it is the tool for
 *              preventing LATER instructions from starting early.
 *
 * WHY tsc_stop MUST USE RDTSCP RATHER THAN PLAIN RDTSC:
 *   The stop timestamp must not be taken until the FINAL dependent load has
 *   returned. Plain RDTSC could be executed while that load was still
 *   outstanding, truncating the measured interval. RDTSCP's backward guarantee
 *   is exactly the property needed.
 *
 * WHY BOTH ROUTINES USE RDTSCP:
 *   RDTSCP additionally returns the IA32_TSC_AUX MSR, which Linux populates
 *   with the logical CPU number. Reading it at BOTH ends of a batch is what
 *   makes migration detection possible (see the timed loop). tsc_start does
 *   not strictly need RDTSCP's ordering property, but harvesting aux costs
 *   essentially nothing.
 *
 * AMD NOTE (relevant to Skylark / EPYC 7532): LFENCE is dispatch-serializing
 * under default microcode, so this identical sequence is correct on AMD too --
 * no separate vendor code path is required. In any case the ordering this
 * measurement actually relies on comes from RDTSCP waiting for the prior load,
 * not from LFENCE serialization.
 *
 * UNIT DISCIPLINE: the returned value is TSC TICKS, not core clock cycles. The
 * TSC advances at a fixed reference rate that does NOT track the core's actual
 * frequency under turbo/DVFS. Phase I therefore reports "TSC ticks/access".
 * Converting to true cycles requires a PMU cycle event, which is Phase II. We
 * never convert using a nominal GHz figure.
 * ==========================================================================*/

static inline uint64_t tsc_start(unsigned *aux_out)
{
    uint64_t t;

    /* This leading LFENCE is LARGELY REDUNDANT and retained deliberately as
     * cheap conservatism, not as a correctness requirement. RDTSCP already
     * waits for prior instructions to have executed and prior loads to be
     * globally visible, which is the ordering this fence would otherwise
     * supply. (It was load-bearing in the classic skeleton, which uses plain
     * RDTSC here.) Two reasons to keep it: LFENCE's "retire" guarantee is
     * marginally stronger than RDTSCP's "execute" guarantee, and at a few
     * cycles ONCE PER BATCH of N loads its cost per access is ~0.005 ticks --
     * negligible against a ~4-tick L1 hit. */
    _mm_lfence();

    t = __rdtscp(aux_out);      /* counter + logical CPU id from IA32_TSC_AUX */

    /* This trailing LFENCE is NOT redundant. RDTSCP orders only what PRECEDES
     * it; it does nothing to stop later instructions from being hoisted above
     * it. Without this fence the first chase loads could begin executing before
     * the start timestamp was taken, shortening the measured interval. */
    _mm_lfence();

    return t;
}

static inline uint64_t tsc_stop(unsigned *aux_out)
{
    uint64_t t;

    /* RDTSCP waits for prior instructions -- crucially the final dependent
     * load of the chase -- to have executed before sampling the counter. */
    t = __rdtscp(aux_out);

    /* Prevent later work (the sink store, the next iteration's setup) from
     * being hoisted above the stop timestamp. */
    _mm_lfence();

    return t;
}


/* ============================================================================
 * SECTION B -- SEEDED RNG (xorshift32)
 * ============================================================================
 *
 * Used only to shuffle the traversal order.
 *
 * WHY NOT rand()? Its underlying algorithm is implementation-defined: glibc,
 * musl, and the libc on the Arm lab machine can all produce different sequences
 * from the same seed. The spec requires the permutation to be reproducible from
 * a RECORDED SEED, which means the RNG's behaviour must be fully determined by
 * our own source, not by whichever libc a given machine ships. A self-contained
 * generator guarantees seed 12345 yields the identical traversal order on all
 * eight lab machines and on every Hazel node.
 *
 * xorshift32 is not cryptographically strong. That is irrelevant here: we need
 * reproducible, well-mixed ordering, not unpredictability against an adversary.
 *
 * PROVENANCE NOTE: the spec supplies an xorshift32 snippet in its starter-code
 * section, so the generator itself follows the handout. The SHUFFLE algorithm
 * built on top of it (Fisher-Yates) is our own choice -- see build_ring().
 *
 * FIXED POINT: state 0 maps to 0 under every shift-xor step, so a zero seed
 * would produce an all-zero "random" sequence and hence no shuffle at all.
 * main() coerces seed 0 to 1.
 * ==========================================================================*/

static uint32_t g_rng_state;

static uint32_t xorshift32(void)
{
    uint32_t x = g_rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    g_rng_state = x;
    return x;
}

/* Uniform value in [0, bound] inclusive.
 *
 * The naive `xorshift32() % (bound+1)` suffers modulo bias: when 2^32 is not an
 * exact multiple of the modulus, the low residues are slightly more likely. At
 * millions of nodes that bias is small, but eliminating it is free, so we use
 * rejection sampling -- discard any draw at or above the largest multiple of
 * the modulus that fits in 2^32. Expected retries are well under 2. */
static uint32_t rng_below_or_equal(uint32_t bound)
{
    uint32_t modulus = bound + 1u;
    if (modulus == 0u) return xorshift32();   /* bound == UINT32_MAX */

    uint32_t limit = UINT32_MAX - (UINT32_MAX % modulus);
    uint32_t r;
    do {
        r = xorshift32();
    } while (r >= limit);
    return r % modulus;
}


/* ============================================================================
 * SECTION C -- BUILDING THE POINTER-CHASE RING
 * ============================================================================
 *
 * Goal: lay out `num_nodes` pointer fields, `spacing` bytes apart, linked into
 * ONE SINGLE CYCLE visiting every node exactly once before repeating.
 *
 * WHY ONE CYCLE AND NOT SEVERAL DISJOINT LOOPS:
 * Assigning each node a random successor independently would almost certainly
 * produce multiple disjoint cycles (e.g. a 3-node loop and a 900-node loop).
 * The chase would then spin forever inside whichever loop it entered, touching
 * a tiny fraction of the allocated footprint. We would believe we were testing
 * W bytes while actually testing a few hundred, and the capacity curve would be
 * meaningless. Walking a PERMUTATION in order and linking each element to the
 * next -- wrapping the last back to the first -- guarantees exactly one cycle
 * of length num_nodes by construction.
 *
 * This property is also what makes the steady-state argument in Section 1 hold:
 * one full lap touches the entire footprint, so a node is only revisited after
 * every other node has been touched.
 * ==========================================================================*/

static void *build_ring(size_t num_nodes, size_t spacing, int sequential,
                        chain_ptr *entry_out, size_t *alloc_bytes_out)
{
    size_t bytes = num_nodes * spacing;

    /* C11 requires aligned_alloc's size to be an integer multiple of its
     * alignment; otherwise behaviour is undefined and a conforming
     * implementation may return NULL. glibc happens to be lenient, but "works
     * on this libc" is the wrong foundation for code that must behave
     * identically across 8 lab machines and 5+ Hazel node types. So round the
     * request up to the next whole page.
     *
     * The idiom `((x + N - 1) / N) * N` rounds x up to the next multiple of N
     * by exploiting integer-division truncation: adding N-1 pushes any
     * non-multiple past the next boundary while leaving exact multiples just
     * short of the following one (so they are returned unchanged).
     *
     * The extra tail bytes are allocated but never linked into the ring, hence
     * never read, hence never enter the cache -- they cost address space, not
     * measurement fidelity. */
    size_t rounded = ((bytes + BUFFER_ALIGNMENT - 1u) / BUFFER_ALIGNMENT)
                     * BUFFER_ALIGNMENT;

    unsigned char *buf = aligned_alloc(BUFFER_ALIGNMENT, rounded);
    if (!buf) {
        /* Checked because a large sweep point on a shared lab machine can
         * genuinely fail to allocate. Without this, `buf` would be NULL and the
         * memset below would segfault with no diagnostic. */
        fprintf(stderr, "ERROR: aligned_alloc failed for %zu bytes\n", rounded);
        exit(1);
    }

    /* ---- FIRST TOUCH -----------------------------------------------------
     * Linux maps pages lazily: the physical pages behind this allocation do not
     * exist until something writes to them. Skipping this would make the first
     * traversal fault on every page -- thousands of cycles of kernel work per
     * page, unrelated to cache latency, landing inside our measurements.
     * Writing the whole buffer now forces every page to be physically backed
     * BEFORE any timing occurs.
     *
     * This is also our NUMA locality mechanism, and the one the spec asks us to
     * report. Linux's default first-touch policy places each page in the memory
     * attached to the socket of the thread that first writes it. Because the
     * process is already pinned (taskset) when this executes, every page lands
     * local to the pinned core -- required on the multi-socket machines
     * (Sunbird, Skylark, Artemisia) so we measure local rather than remote
     * memory. No privileged tooling is involved. */
    memset(buf, 0, rounded);

    /* ---- build the visiting order ----------------------------------------
     * order[i] = index of the node visited at step i of one lap. */
    size_t *order = malloc(num_nodes * sizeof(*order));
    if (!order) {
        fprintf(stderr, "ERROR: malloc failed for %zu-entry permutation\n",
                num_nodes);
        exit(1);
    }
    for (size_t i = 0; i < num_nodes; i++) order[i] = i;

    if (!sequential) {
        /* ---- Fisher-Yates shuffle ----------------------------------------
         *
         * PROVENANCE: neither the spec nor the slides mandate a shuffling
         * algorithm; they require only that the order be "randomly permuted
         * with a recorded seed". Fisher-Yates is OUR choice, made because:
         *   (a) it produces a uniformly distributed permutation, so no residual
         *       ordering structure survives for a prefetcher to exploit;
         *   (b) it is O(n) with no auxiliary allocation, which matters at
         *       millions of nodes;
         *   (c) it is standard and straightforward to defend in the write-up.
         *
         * HOW IT WORKS: walk from the last element down to the second. At each
         * position i, draw a uniform j in [0, i] and swap order[i], order[j].
         * Once an element is placed at position i it is never moved again. The
         * invariant is that positions i..n-1 always hold a uniformly random
         * selection of the whole array, which is what makes the final
         * permutation uniform over all n! orderings. */
        for (size_t i = num_nodes - 1; i > 0; i--) {
            uint32_t j  = rng_below_or_equal((uint32_t)i);
            size_t   tmp = order[i];
            order[i]     = order[j];
            order[j]     = tmp;
        }
    }
    /* If `sequential`, order[] remains 0,1,2,... -- the prefetcher control.
     * This traverses ascending addresses with a constant stride of `spacing`,
     * the easiest possible pattern for a stride prefetcher to predict, which is
     * exactly what makes it a useful upper bound on prefetcher benefit. */

    /* ---- link the cycle ---------------------------------------------------
     * The node visited at step i points to the node visited at step i+1; the
     * final node wraps to the first, closing the ring.
     *
     * Address arithmetic: node k's pointer field lives at buf + k*spacing. We
     * cast that byte address to `void **` so the store writes an 8-byte pointer
     * and the chase can later load through it. */
    for (size_t i = 0; i < num_nodes; i++) {
        size_t cur  = order[i];
        size_t next = order[(i + 1u) % num_nodes];

        void **slot = (void **)(buf + cur * spacing);
        *slot       = (void *)(buf + next * spacing);
    }

    free(order);    /* the permutation now lives in the links themselves */

    /* Enter at node 0. Any node would serve -- it is a single cycle, so all
     * nodes are mutually reachable -- and buf+0 is valid regardless of how the
     * permutation came out. Using a fixed entry keeps randomized and sequential
     * modes structurally identical. */
    *entry_out       = (chain_ptr)(buf + 0 * spacing);
    *alloc_bytes_out = rounded;

    return buf;     /* returned so main() can free the original allocation */
}


/* ============================================================================
 * SECTION D -- THE CHASE (the measured critical loop)
 * ============================================================================
 *
 * Every iteration performs exactly one load whose address came from the
 * previous load's result. Neither the compiler nor the hardware can reorder or
 * overlap these: the address dependency is a genuine data dependency through
 * memory.
 *
 * EXPECTED -O0 CODE GENERATION (Intel syntax; verify against the archived
 * disassembly for each machine, as the spec's checklist requires):
 *
 *     .L3:
 *         mov  rax, QWORD PTR [rbp-8]    ; reload p from the stack
 *         mov  rax, QWORD PTR [rax]      ; p = *p    <-- THE dependent load
 *         mov  QWORD PTR [rbp-8], rax    ; spill p back to the stack
 *         add  QWORD PTR [rbp-16], 1     ; i++
 *         mov  rax, QWORD PTR [rbp-16]
 *         cmp  rax, QWORD PTR [rbp-24]   ; i < steps ?
 *         jb   .L3
 *
 * The five checks the spec requires of this listing: (1) the intended load
 * exists; (2) the dependency chain is intact (the loaded value feeds the next
 * load's address); (3) the timer reads bracket the intended region; (4) the
 * loop was not removed, vectorized, or unrolled into a different access
 * pattern; (5) no unexpected stores sit inside the read loop. Note the spill
 * store to [rbp-8] IS expected at -O0 and is not a violation of (5) -- it
 * targets the stack slot for `p`, not the traversed buffer, so the traversal
 * itself remains read-only.
 *
 * THE "-O0 TAX": because -O0 keeps `p` in a stack slot, every iteration adds a
 * store/reload round trip (satisfied by store-to-load forwarding) on top of the
 * real cache access. This inflates the ABSOLUTE latency figure by a few cycles.
 * Crucially it is a CONSTANT offset, identical at every working-set size, so
 * the STEPS between levels -- which are what the capacity inference actually
 * rests on -- remain fully visible. Per the spec we characterize this overhead
 * rather than subtracting a guess from every sample. The empty-bracket
 * measurement (see the build/run scripts) quantifies the timer half of it.
 * ==========================================================================*/

static chain_ptr chase(chain_ptr p, uint64_t steps)
{
    for (uint64_t i = 0; i < steps; i++) {
        p = (chain_ptr)(*p);        /* one dependent load */
    }
    return p;
}

/* Volatile sink. Assigning the chase's result here makes the loop's output
 * observably used, so no compiler can conclude the traversal is dead code and
 * delete it; `volatile` additionally forces the store to be emitted. The sink
 * store is deliberately placed OUTSIDE the timed bracket in the loop below. */
static volatile void *g_sink;


/* ============================================================================
 * SECTION E -- MAIN
 * ==========================================================================*/

int main(int argc, char **argv)
{
    if (argc < 6) {
        fprintf(stderr,
            "usage: %s <working_set_bytes> <node_spacing_bytes> <N_per_batch> "
            "<num_samples> <seed> [sequential]\n"
            "  sequential: 0 = randomized order (default, primary method)\n"
            "              1 = sequential order  (prefetcher control)\n",
            argv[0]);
        return 1;
    }

    size_t   working_set_bytes = strtoull(argv[1], NULL, 10);
    size_t   spacing           = strtoull(argv[2], NULL, 10);
    uint64_t N_per_batch       = strtoull(argv[3], NULL, 10);
    uint64_t num_samples       = strtoull(argv[4], NULL, 10);
    uint32_t seed              = (uint32_t)strtoul(argv[5], NULL, 10);
    int      sequential        = (argc >= 7) ? atoi(argv[6]) : 0;

    /* ---- parameter validation -------------------------------------------
     *
     * (1) Spacing must hold a pointer and be a multiple of the pointer size, so
     *     every pointer field stays naturally aligned (Section 3). sizeof(void*)
     *     is used rather than a literal 8 so the constraint is derived, not
     *     assumed. */
    if (spacing < sizeof(void *) || (spacing % sizeof(void *)) != 0) {
        fprintf(stderr,
            "ERROR: node_spacing_bytes (%zu) must be >= %zu and a multiple "
            "of %zu\n", spacing, sizeof(void *), sizeof(void *));
        return 1;
    }

    /* (2) The working set must be an EXACT multiple of the spacing.
     *
     *     num_nodes = working_set_bytes / spacing uses integer division, which
     *     truncates silently. Requesting W = 100000 at spacing 64 would yield
     *     1562 nodes = 99968 bytes traversed: the x-axis label would claim one
     *     footprint while the traversal covered another. The drift grows with
     *     spacing (at spacing 4096, W=100000 traverses only 98304 bytes, 1.7%
     *     low) and is most damaging exactly where it matters most -- in the
     *     dense sampling used to locate a capacity edge precisely.
     *
     *     We REJECT rather than round: rounding would "fix" the mismatch
     *     invisibly, which is the same class of silent error we are trying to
     *     eliminate. The message reports the two nearest valid values so a
     *     sweep script is trivial to correct. */
    if ((working_set_bytes % spacing) != 0) {
        fprintf(stderr,
            "ERROR: working_set_bytes (%zu) must be an exact multiple of "
            "node_spacing_bytes (%zu).\n"
            "       Nearest valid values: %zu or %zu\n",
            working_set_bytes, spacing,
            (working_set_bytes / spacing) * spacing,
            ((working_set_bytes / spacing) + 1) * spacing);
        return 1;
    }

    if (N_per_batch == 0 || num_samples == 0) {
        fprintf(stderr, "ERROR: N_per_batch and num_samples must both be > 0\n");
        return 1;
    }

    /* xorshift32 has 0 as a fixed point; coerce so the shuffle is real. */
    g_rng_state = (seed == 0u) ? 1u : seed;

    size_t num_nodes = working_set_bytes / spacing;
    if (num_nodes < 2) {
        fprintf(stderr,
            "ERROR: working set too small -- %zu bytes at spacing %zu yields "
            "%zu node(s); at least 2 are needed to form a cycle\n",
            working_set_bytes, spacing, num_nodes);
        return 1;
    }

    /* ---- build the ring -------------------------------------------------- */
    chain_ptr entry;
    size_t    alloc_bytes;
    void     *buffer = build_ring(num_nodes, spacing, sequential,
                                  &entry, &alloc_bytes);
    chain_ptr p = entry;

    /* ---- WARM-UP ---------------------------------------------------------
     *
     * Purpose: pay every one-time cost BEFORE the first recorded sample, so all
     * samples reflect steady-state behaviour. The costs absorbed here are:
     *   - residual page-fault work (mostly handled by the first-touch memset,
     *     but the traversal order differs from memset's linear order);
     *   - TLB fills for the pages the traversal will visit;
     *   - the cold-cache transient: the first pass necessarily pulls data up
     *     the hierarchy, and those one-off misses must not be averaged into the
     *     numbers we keep.
     *
     * CRITICAL SIZING RULE -- warm-up must cover AT LEAST ONE FULL LAP of the
     * ring (num_nodes steps). A naive `10 * N_per_batch` is a bug at large
     * footprints: with a 64 MiB working set and N_per_batch = 100 it warms 1000
     * of ~1,000,000 nodes (0.1%), so the timed loop would spend most of its
     * early samples touching never-before-seen memory and folding first-touch
     * cost into the measurement. We therefore take the LARGER of one full lap
     * and 10 batches; the 10-batch floor still matters for small working sets,
     * where a lap may be only a handful of steps and extra settling helps.
     *
     * Warm-up steps are NOT recorded. Spec: "Warm-up samples do not count
     * toward the one million." */
    uint64_t warmup_by_lap   = (uint64_t)num_nodes;
    uint64_t warmup_by_batch = 10ull * N_per_batch;
    uint64_t warmup_steps    = (warmup_by_lap > warmup_by_batch)
                               ? warmup_by_lap : warmup_by_batch;

    p      = chase(p, warmup_steps);
    g_sink = (void *)p;             /* keep warm-up from being elided */

    /* ---- sample buffer ---------------------------------------------------
     *
     * Every individual sample is retained rather than accumulated into a
     * running average, because the spec requires reconstructing the full
     * DISTRIBUTION -- median, mean, sd, Q1, Q3, p5, p95, outlier count -- plus
     * box plots. An average would discard precisely the information graded.
     *
     * Cost: 8 bytes/sample, so the required 1,000,000 samples need 8 MB. That
     * is far cheaper than writing to disk inside the timed loop, which would
     * inject syscall latency directly into the measurement. All I/O happens
     * after timing completes. */
    uint64_t *samples = malloc((size_t)num_samples * sizeof(*samples));
    if (!samples) {
        fprintf(stderr, "ERROR: malloc failed for %" PRIu64 " samples "
                "(%zu bytes)\n",
                num_samples, (size_t)num_samples * sizeof(*samples));
        return 1;
    }

    /* ---- THE TIMED LOOP --------------------------------------------------
     *
     * One sample == elapsed TSC ticks for N_per_batch dependent loads.
     *
     * WHAT IS INSIDE THE BRACKET: only the chase. Allocation, shuffling,
     * warm-up, the sink store, the sample-array write, and all printing are
     * deliberately outside it.
     *
     * MIGRATION DETECTION: RDTSCP returns IA32_TSC_AUX, which Linux sets to the
     * logical CPU number. If that value differs between a batch's start and
     * stop, the OS moved this thread to another core mid-measurement -- which
     * can happen despite taskset pinning under cgroup or container policies.
     * Such a sample is contaminated: the new core's private caches hold none of
     * the state we warmed, so the timing reflects a locality discontinuity
     * rather than the working-set size under test. (Invariant TSC is
     * synchronized across cores on these machines, so the tick values remain
     * comparable; it is the cache state, not the clock, that invalidates the
     * sample.) We mark such samples, exclude them from the emitted data, and
     * report the count so it lands in the run manifest.
     *
     * GRANULARITY CHOICE: we check ONCE PER BATCH, not per step. Checking every
     * step would require an RDTSCP per load, reintroducing exactly the
     * per-access instrumentation overhead that batching exists to eliminate.
     * Per-batch granularity answers the question that actually matters: was
     * this measurement window interrupted by a migration? */
    unsigned aux_first        = 0;
    uint64_t migrated_samples = 0;

    for (uint64_t r = 0; r < num_samples; r++) {
        unsigned aux_a, aux_b;

        uint64_t t0 = tsc_start(&aux_a);
        p           = chase(p, N_per_batch);
        uint64_t t1 = tsc_stop(&aux_b);

        g_sink = (void *)p;         /* keep the chain live, outside the bracket */

        if (r == 0) aux_first = aux_a;

        if (aux_a != aux_b) {
            samples[r] = SAMPLE_MIGRATED;
            migrated_samples++;
        } else {
            samples[r] = t1 - t0;
        }
    }

    /* ---- run metadata (stderr) -------------------------------------------
     *
     * Emitted as '#'-prefixed key=value lines so the collection script can
     * capture them verbatim into a .meta file and a processing script can parse
     * them into the run manifest. Auto-emitting this is what keeps the
     * reproducibility record honest: nothing here is hand-transcribed.
     *
     * Note that actual_footprint_bytes is reported separately from
     * working_set_bytes. With the divisibility check above they are always
     * equal, but plots should be keyed to the footprint actually traversed --
     * that is the defensible quantity to put on an axis. */
    fprintf(stderr, "# cache_bench_metadata_version=1\n");
    fprintf(stderr, "# experiment=capacity\n");
    fprintf(stderr, "# working_set_bytes=%zu\n",        working_set_bytes);
    fprintf(stderr, "# node_spacing_bytes=%zu\n",       spacing);
    fprintf(stderr, "# num_nodes=%zu\n",                num_nodes);
    fprintf(stderr, "# actual_footprint_bytes=%zu\n",   num_nodes * spacing);
    fprintf(stderr, "# allocated_bytes=%zu\n",          alloc_bytes);
    fprintf(stderr, "# buffer_alignment_bytes=%u\n",    BUFFER_ALIGNMENT);
    fprintf(stderr, "# pointer_size_bytes=%zu\n",       sizeof(void *));
    fprintf(stderr, "# N_per_batch=%" PRIu64 "\n",      N_per_batch);
    fprintf(stderr, "# num_samples_requested=%" PRIu64 "\n", num_samples);
    fprintf(stderr, "# num_samples_emitted=%" PRIu64 "\n",
            num_samples - migrated_samples);
    fprintf(stderr, "# warmup_steps=%" PRIu64 "\n",     warmup_steps);
    fprintf(stderr, "# warmup_laps=%.3f\n",
            (double)warmup_steps / (double)num_nodes);
    fprintf(stderr, "# seed=%" PRIu32 "\n",             seed);
    fprintf(stderr, "# traversal_order=%s\n",
            sequential ? "sequential" : "randomized");
    fprintf(stderr, "# shuffle_algorithm=%s\n",
            sequential ? "none" : "fisher_yates_xorshift32");
    fprintf(stderr, "# timer_method=lfence;rdtscp;lfence / rdtscp;lfence\n");
    fprintf(stderr, "# timer_units=TSC_ticks\n");
    fprintf(stderr, "# units_note=TSC ticks are NOT core clock cycles; "
                    "no GHz conversion applied\n");
    fprintf(stderr, "# kernel_type=read_only_pointer_chase\n");
    fprintf(stderr, "# numa_locality_method=first_touch_after_pinning\n");
    fprintf(stderr, "# logical_cpu_from_tsc_aux=%u\n", aux_first);
    fprintf(stderr, "# migrated_samples_excluded=%" PRIu64 "\n",
            migrated_samples);
    fprintf(stderr, "# sink_ignore=%p\n", (void *)g_sink);

    /* ---- raw CSV (stdout) ------------------------------------------------
     *
     * Columns: sample_index,ticks_elapsed,N_per_batch
     *
     * We deliberately do NOT divide by N_per_batch here. The raw file records
     * exactly what the hardware reported alongside the batch size used, so the
     * conversion to ticks/access happens in processing and can always be
     * re-derived or re-checked. Baking the division into the raw data would
     * destroy that traceability.
     *
     * sample_index preserves the ORIGINAL loop index, so gaps in the sequence
     * identify precisely which samples were dropped for migration. */
    printf("sample_index,ticks_elapsed,N_per_batch\n");
    for (uint64_t r = 0; r < num_samples; r++) {
        if (samples[r] == SAMPLE_MIGRATED) continue;
        printf("%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
               r, samples[r], N_per_batch);
    }

    free(samples);
    free(buffer);
    return 0;
}
