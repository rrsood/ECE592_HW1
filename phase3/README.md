# Phase III: frozen prediction and Hazel held-out workflow

This directory implements sections 8.6, 9, and 9.1 without mixing Hazel
observations into the lab-only training set.

## Scientific ordering

1. Copy `lab_observations_template.tsv` to a versioned input and fill all eight
   ECE lab rows using timing-only inferences. Keep PMU/published values in
   separate verification columns outside the timing-only fields.
2. Run `scripts/freeze_phase3_predictions.py`. It refuses incomplete metric
   series, fewer than three observations, extra/missing lab machines, and any
   apparent Hazel row.
3. Commit the generated freeze directory. The commit containing it is the
   freeze commit. Do not run a Hazel cache benchmark before this commit.
4. On Hazel, record live `si`/`sinfo` output. Generate jobs only for constraints
   actually visible to the course project with
   `scripts/generate_hazel_slurm_jobs.py`.
5. Submit from the repository root. Each generated job requests one CPU,
   binds the suite through `srun`, verifies the committed freeze, rejects login
   nodes, records Slurm/topology/build provenance, uses one million timed
   samples per point, processes the results, and losslessly compresses raw
   samples.
6. Freeze each Hazel timing-only inference before consulting cache topology,
   published cache specifications, or cache PMUs for that target.
7. Add held-out values to the chronological master data, preserving the frozen
   predictions. Hazel observations must never refit the dashed prediction.

The target catalog mirrors the project specification. Live scheduler output is
authoritative; do not submit blindly to every listed constraint. At least five
distinct generations are required, spanning the oldest and newest accessible
targets and including Genoa or newer when accessible.

## Example commands (after the eight-machine lab table is complete)

```bash
python3 scripts/freeze_phase3_predictions.py \
  --lab-table phase3/lab_observations_v1.tsv \
  --targets phase3/hazel_targets.tsv \
  --capacity-law-name 'LASTNAME1-LASTNAME2 Capacity Law' \
  --cost-law-name 'LASTNAME1-LASTNAME2 Latency Law' \
  --output-directory phase3/frozen_predictions_v1

git add phase3/lab_observations_v1.tsv phase3/frozen_predictions_v1
git commit -m "Freeze lab-only Hazel cache predictions"
freeze_commit=$(git rev-parse HEAD)

mkdir -p phase3/slurm_logs phase3/results
python3 scripts/generate_hazel_slurm_jobs.py \
  --targets phase3/hazel_targets.tsv \
  --availability-file phase3/scheduler_availability/sinfo_YYYYMMDD.txt \
  --visible-constraints haswell,cascadelake,sapphirerapids,genoa,turin \
  --freeze-directory phase3/frozen_predictions_v1 \
  --freeze-commit "$freeze_commit" \
  --result-root /PERSISTENT/PROJECT/PATH/ece592_phase3_results \
  --output-directory phase3/slurm_jobs_v1
```

Review the generated resource requests, then submit each generated `.sbatch`
file. The suite is intentionally long because every point has one million
samples. Never invoke `run_hazel_phase3_suite.sh` on a login node.

```bash
for job in phase3/slurm_jobs_v1/*.sbatch; do
  sbatch "$job"
done
squeue -u "$USER"
```

Each successful result directory contains job/topology provenance, saved build
commands and disassembly, plans, processed summaries, plots (when `gnuplot` is
available on the compute image), and a SHA-256-protected compressed raw-data
archive. Keep the raw archive outside Git but include it in the final submitted
data archive. If plotting was deferred, run the existing plot scripts against
the copied `processed/` files on a host with `gnuplot`.

After committing the timing-only Hazel inference table, build the final
chronological table and figures as follows. The optional uncertainty table is
long-form so bounds can be supplied only where the measurement supports them.

```bash
python3 scripts/build_phase3_chronological_master.py \
  --lab phase3/lab_observations_v1.tsv \
  --hazel phase3/hazel_observations_v1.tsv \
  --output phase3/chronological_master_v1.tsv

python3 scripts/plot_phase3_chronology.py \
  --master phase3/chronological_master_v1.tsv \
  --frozen-predictions phase3/frozen_predictions_v1/frozen_hazel_predictions.tsv \
  --uncertainty phase3/uncertainty_v1.tsv \
  --output-directory phase3/chronological_plots_v1
```

The plotting command creates 16 vector PDFs: the specification's 15 required
categories, with the two semantically comparable normalized PMU metrics split
into separate figures. Capacities use log-base-2 axes; lab observations use
solid vendor-specific series; frozen future predictions are dashed with
prediction intervals; and Hazel observations use distinct held-out markers.
