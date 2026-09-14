# Inclusion / Exclusion Behavior (Homework I, Section 8.2 item 7)

This document covers the experiment that classifies whether the last-level
cache is inclusive, exclusive/victim-like, or non-inclusive with respect to the
private caches. It explains the design, the files, how to run it, and the
inference rule that turns the measurement into the reported answer.

---

## 1. What the handout asks for

> Design an experiment that tests whether evicting a line from a lower cache
> level also invalidates the corresponding copy in an upper level. Use
> controlled cross-level occupancy/eviction and reload timing to classify the
> observed behavior as inclusive, exclusive/victim-like, or
> non-inclusive/non-exclusive/uncertain, as supported by the data. Do not infer
> policy from capacity ratios alone.

And the required figure:

> cross-level eviction/reload evidence for inclusion/exclusion behavior,
> showing the condition that distinguishes whether an upper-level copy survives
> or is invalidated after lower-level eviction pressure.

Read "lower level" as the level further from the core (the shared LLC) and
"upper level" as the level closer to the core (private L1D/L2). That is the
classic back-invalidation question.

---

## 2. The concepts, restated

A line **X** has been read by our core, so it sits in our private L1D. Under
different policies it may or may not also sit in the shared LLC, and the two
copies may or may not be coupled.

| Policy | Is X also in the LLC? | What happens to the private copy when the LLC evicts X? |
| --- | --- | --- |
| **Inclusive** | Always. The LLC is a superset of every private cache in its domain. | It must be invalidated. The LLC sends a back-invalidation so the superset property holds. |
| **Exclusive / victim-like** | No, not while it is private. Lines move *down* into the LLC when they are evicted from L2. | Nothing. There was no LLC copy to evict. |
| **Non-inclusive, non-exclusive (NINE)** | Usually yes on fill, but the LLC is not obliged to keep it. | Nothing is required. The LLC may drop its copy silently and the private copy survives. |

The observable difference is therefore a single question: **after the shared
LLC is put under enough occupancy pressure to displace X, is X still a private
hit?**

- Still fast → the private copy survived → **non-inclusive or exclusive**
- Now DRAM-slow → the private copy was destroyed → **inclusive**

Two practical consequences worth remembering for the report:

- Inclusion costs effective capacity. An inclusive hierarchy's total capacity
  is roughly the LLC alone, because private contents are duplicates. Exclusive
  and non-inclusive hierarchies get roughly LLC + L2 + L1.
- Inclusion buys coherence simplicity. An LLC that is a guaranteed superset can
  filter snoops: if a line is absent from the LLC, no core in the domain has
  it, so no private cache needs to be probed.

---

## 3. Why the obvious single-threaded test cannot work

The natural first design is: touch a probe set, walk a big array, re-touch the
probe set, see if it got slower. The repository already contains that design
(`inclusion_chase.c`, `inclusion_measurement.c`), and its own header comment
correctly warns that it "does not guarantee eviction or identify an inclusion
policy."

Here is the reason, and it is worth stating explicitly in the report because it
is the interesting methodological point of this section.

Any array the measuring core walks is loaded **through its own L1 and L2**.
Walking something larger than the LLC therefore evicts the probe set from L1,
from L2, *and* from the LLC, all at once. Afterwards the reload is slow. But:

- under an inclusive LLC, the reload is slow;
- under a non-inclusive LLC, the reload is *also* slow.

Both hypotheses predict the same measurement. The experiment has no
discriminating power, no matter how many samples are collected.

There is a second tempting approach: build an address set that is congruent in
the LLC but not in L1/L2, so the pressure hits only LLC sets. On a conventional
hierarchy this cannot be done. The L1 set index uses bits [11:6] of the
address, L2 uses a superset such as [15:6], and the LLC a larger superset still.
Addresses that agree in the LLC index bits automatically agree in the L2 and L1
index bits, so an LLC eviction set is always also an L1/L2 eviction set.

**The pressure has to come from a different core.** A helper thread pinned to
another physical core in the same package competes for the shared LLC while our
private L1D and L2 are never touched, because they are private to our core.
That is the only condition that separates the hypotheses, and it is why this
experiment uses a second thread even though every other experiment in the suite
is strictly single-threaded. Record both logical CPUs in the report; the
deviation is deliberate and necessary.

Two placements must be avoided:

- An **SMT sibling** shares L1D and L2 with the measuring thread, so its
  pressure evicts the private copies directly and proves nothing. The tools
  refuse this placement unless `--allow-smt-sibling` is passed explicitly, in
  which case it becomes a useful control showing what direct private eviction
  looks like.
- A **different package** drives a different LLC entirely, so nothing happens.
  The tools refuse it unless `--allow-remote-package` is passed, in which case
  it is an excellent negative control on a dual-socket machine such as Sunbird
  or Skylark: pressure from the other socket must *not* evict, and if it does,
  something about the setup is wrong.

On AMD Zen parts such as Skylark's EPYC 7532 the L3 is per-CCX, not per-socket.
A helper on the same socket but a different CCX drives a different L3 and will
produce a false "non-inclusive" answer. Sweep several helper CPUs and use the
result to identify the sharing domain empirically. That extra evidence also
answers the "private or shared, and what is the sharing scope" part of item 1
of the same section.

---

## 4. How one measurement is taken

One **round**:

1. **Prime** — walk the whole target cycle once, untimed, so every target line
   is private-resident.
2. **Baseline** — walk the identical cycle again, timing groups of
   `accesses_per_sample` dependent loads. This is the calibrated *private hit*
   class.
3. **Pressure** — apply the selected pressure source and wait for it to finish.
   With the helper source, the measuring thread spins on a single
   synchronization word and touches nothing else, so its private caches are
   left alone.
4. **Probe** — walk the identical cycle a third time, from the same start node,
   timing the same groups. This is the *after pressure* class.
5. **Overhead** — empty timer start/stop pairs, one per sample.

Rounds repeat until at least 1,000,000 timed samples have been collected for
the point.

Design points that matter:

- **Dependent chain.** Every timed group is `p = p->next`, so the address of
  each load depends on the value returned by the previous one. Memory-level
  parallelism cannot hide the latency. A loop of independent loads would
  measure throughput instead.
- **Randomized cycle.** The target order is a recorded Fisher-Yates shuffle, so
  no stride or stream prefetcher can rebuild the target set during the probe
  walk.
- **Baseline and probe share the code path.** Both walks are the same function
  over the same addresses in the same order. Every constant additive cost — the
  `-O0` loop overhead, the LFENCE/RDTSCP overhead — appears in both, so it
  cancels in the comparison. This is why the inference does not depend on a
  fragile overhead subtraction.
- **Read-only.** No stores in the timed region, so store-to-load forwarding and
  address-aliasing effects cannot masquerade as a cache result.
- **Node spacing is a parameter.** `--target-spacing` takes the team's already
  inferred line size rather than assuming one.

### Choosing `--accesses-per-sample`

`1` on x86: the empty LFENCE/RDTSCP pair costs tens of ticks, which is more
than an L1 hit, but the contrast this experiment needs is private-hit versus
DRAM — hundreds of ticks — so a single-access interval separates the classes
easily and yields the most samples per round.

On AArch64 (Thunderbird) the generic timer can tick far more slowly than a
single load, so a single-access interval is unusable. Set
`--accesses-per-sample` to something like 256 there. Note the cost: samples per
round equal `target_nodes / accesses_per_sample`, and fewer samples per round
means more rounds, and each round pays for a full pressure episode. Compensate
by enlarging `--target-bytes` so one lap still contains many groups.

---

## 5. The conditions collected

| Source | Role | What it proves |
| --- | --- | --- |
| `none` | Negative control | The round structure by itself leaves the targets private-resident. The eviction probability here is the floor. |
| `self` | Positive control and latency ladder | The measuring thread walks the pressure set. This *must* slow the reload down; if it does not, the probe is broken. Swept from below L1 to above the LLC it also shows which level answered each reload. |
| `helper` | The discriminating condition | Shared-cache pressure with the private caches untouched. |

The helper footprint is swept across the inferred LLC capacity, densely near
1x, out to 4x, which is what produces the sharp edge the handout asks for.

---

## 6. Inference rule

For each point, the classification threshold is a high quantile of *that
point's own baseline distribution* — by default the 99.9th percentile. This
fixes the false-positive rate of the classifier at 0.1% by construction, so no
latency number has to be chosen by hand and the reported probability is
directly interpretable.

    eviction probability = fraction of after-pressure samples above the
                           baseline's 99.9th percentile

The processor also reports the empirical false-positive rate recomputed from
the baseline, as a check that the rule behaved as designed.

> A note on the alternative: the suite's usual Tukey fence, Q3 + 1.5 x IQR, is
> also reported, but it is *not* used for the primary number. When the
> private-hit distribution is very tight the interquartile range collapses to
> zero, the fence lands on the median, and roughly 20% of the hit mode is
> misclassified. A tight hit distribution is the good case, so a rule that
> fails on it is the wrong rule. This is worth a sentence in the report.

Reading the resulting curve:

| Observation | Conclusion |
| --- | --- |
| Helper eviction probability rises sharply toward 1 as the helper footprint passes the inferred LLC capacity, while the no-pressure control stays at the floor | **Inclusive.** LLC eviction back-invalidates the private copy. |
| Helper eviction probability stays at the floor out to several times the LLC capacity, *and* the same-core positive control does show eviction, *and* the helper is confirmed same-package/different-core with a nonzero completed pass count | **Non-inclusive or exclusive.** The private copy survives independent LLC pressure. |
| Probability rises only partially, or is not repeatable across trials and helper CPUs | **Uncertain.** Report the behavioral bound and the limitation rather than forcing a textbook label. |

Separating exclusive from non-inclusive needs one more piece of evidence, and
timing alone supports only a bound. Two supporting arguments, both of which
should be labelled as supporting rather than decisive:

1. **Aggregate capacity.** From the existing capacity sweep, find the footprint
   at which latency transitions to DRAM. An inclusive hierarchy's total is
   about the LLC alone; exclusive and non-inclusive hierarchies get roughly
   LLC + L2. The handout explicitly forbids inferring policy from capacity
   ratios alone, so use this only to support the back-invalidation result.
2. **Same-core ladder.** With `self` pressure sized between L2 and the LLC, the
   target is evicted from the private caches but not from the LLC. If the
   reload lands at LLC-hit latency rather than DRAM latency, the LLC held a
   copy after the line left L2. That is consistent with both non-inclusive fill
   and exclusive victim fill, so it bounds rather than decides.

For the final per-machine table, state what the experiment *proves*: whether
LLC eviction pressure from another core in the same sharing domain invalidates
the private copy. If the answer is no, report "non-inclusive or
exclusive/victim-like, not separated by timing alone" rather than guessing, and
resolve it in Phase II against documentation and counters.

---

## 7. Files

### Benchmark (`main_code/`)

| File | Contents |
| --- | --- |
| `common/cross_level.h` | Public API and the full design rationale as comments. |
| `common/cross_level.c` | Helper-thread lifecycle and synchronization, the round loop, timed dependent traversal, Phase-I-safe topology reads. |
| `common/inclusion_policy_bench.c` | `main`, option parsing, metadata capture, raw TSV writer. |
| `common/pointer_chase.c` | Reused unchanged. Builds both the target cycle and the pressure arena. |
| `common/affinity_linux.c`, `common/metadata_linux.c` | Reused unchanged. |
| `x86_64/timer_x86_64.c`, `aarch64/timer_aarch64.c` | Reused unchanged. |

The raw file header and the data columns
(`sample_index`, `baseline_raw_ticks`, `after_pressure_raw_ticks`,
`timer_overhead_raw_ticks`) match the existing eviction writer, so the raw
format is consistent with the rest of the suite.

### Scripts (`scripts/`)

| File | Role |
| --- | --- |
| `build_inclusion_policy.sh` | Builds at `-O0` with the same warning set as `build_phase1.sh`, plus `-pthread`. Writes the `.build-command.txt` sidecar. |
| `generate_inclusion_policy_plan.py` | Emits the randomized execution plan and per-point seeds. Prints a wall-clock estimate. Executes nothing. |
| `run_inclusion_policy_plan.py` | Validates the plan, pre-flights CPU topology, runs every row, writes the manifest, optionally gzips each raw file, supports `--resume`. |
| `process_inclusion_policy_run.py` | Validates every raw file against the plan, computes full distributions, derives the eviction probability. Reads `.tsv` and `.tsv.gz`. |
| `plot_inclusion_policy_curve.py` | Three vector PDFs plus a provenance sidecar. |
| `run_inclusion_policy_all.sh` | Build → plan → collect → process → plot in one command. |

---

## 8. Running it

Per machine, after logging in and reserving a core:

```bash
scripts/run_inclusion_policy_all.sh \
    --machine sunbird --cpu 4 --helper-cpus 6,8 \
    --line-bytes 64 --l1-bytes 32768 --l2-bytes 262144 \
    --llc-bytes 31457280 \
    --smt-siblings-idle yes --trials 2 --seed 592
```

All four size arguments are the team's own Phase-I timing-only inferences.
Nothing in this pipeline reads a cache specification file.

Check the plan first without collecting anything:

```bash
scripts/run_inclusion_policy_all.sh ... --dry-run
```

The plan generator prints `estimated_wall_clock_minutes` before any data is
collected, which is the number to check before launching four machines in
parallel. If a run is interrupted, repeat the same command with `--resume` and
the same `--seed`.

### Choosing helper CPUs

Use `lscpu -e=CPU,CORE,SOCKET,NODE`, which the handout lists as a Phase-I-safe
topology command. Pick logical CPUs with the **same SOCKET** and a **different
CORE** than the measuring CPU. On Skylark also vary the helper across the
socket so the L3 sharing domain shows up in the data. The runner prints the
topology of every CPU involved and refuses placements that cannot answer the
question.

### Outputs

```
data_raw/<machine>/inclusion_policy/raw/<run>/     raw TSVs, plan, manifest
data_processed/<machine>/inclusion_policy/<run>.tsv
plots/<machine>/<run>_eviction_probability.pdf
plots/<machine>/<run>_reload_latency.pdf
plots/<machine>/<run>_reload_boxplots.pdf
plots/<machine>/<run>_plots.provenance.tsv
```

---

## 9. Limitations to state in the report

- The classification is about the LLC sharing domain visible to the pinned
  core, not about every cache in the machine.
- The experiment establishes back-invalidation behavior. It does not separate
  exclusive from non-inclusive by itself; timing supports a bound.
- Modern LLCs are sliced and hashed. Occupancy pressure rather than a
  constructed eviction set is used precisely because slice hashing makes a
  clean per-set eviction construction impractical from virtual addresses, which
  also means the transition can be broader than a textbook capacity edge.
- The helper thread is a documented deviation from the otherwise strict
  one-logical-CPU rule, and is necessary: no single-threaded design can
  separate the hypotheses.
- Both CPUs are shared lab resources. Record the reservation window, and note
  that interference from other users inflates the tails of both conditions
  roughly equally, which is one more reason the comparison rather than the
  absolute latency carries the inference.
