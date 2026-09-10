#!/usr/bin/env python3
"""
=============================================================================
process_capacity.py

Turns the raw per-sample capacity sweep data into the summary statistics the
spec requires, plus a retained subsample for box plots.

ECE 592 Homework I -- Phase I.

SPEC REQUIREMENTS IMPLEMENTED
-----------------------------
  "Distribution, not only an average: Preserve enough data to reconstruct the
   latency distribution. Report median, mean, standard deviation, Q1, Q3,
   5th/95th percentiles, and the number of outliers."
      -> every one of those statistics appears as a column in the summary CSV.

  "Box plots: For every major test, include box plots of the measured
   distribution."
      -> a bounded random subsample of each point's raw ticks/access values is
         written to a companion file so the plotting script can draw true box
         plots without re-reading gigabytes of raw data.

  Traceability (section 12): every summary row carries the raw filename it was
  derived from, so a grader can walk from any plotted point back to its data.

WHAT IT READS
    <raw_dir>/capacity_ws<BYTES>_sp<SPACING>_<rand|seq>_<machine>_<ts>.csv.gz
    <raw_dir>/*.meta                    (metadata auto-emitted by cache_bench)

WHAT IT WRITES
    <out_dir>/capacity_summary.csv      one row per (working set, traversal mode)
    <out_dir>/capacity_boxdata.csv.gz   subsampled ticks/access for box plots
    <out_dir>/timer_overhead_summary.csv  empty-bracket distribution

USAGE
    python3 process_capacity.py <raw_dir> <out_dir> [--box-subsample N]
=============================================================================
"""

import argparse
import glob
import gzip
import os
import re
import sys

import numpy as np


# -----------------------------------------------------------------------------
# Metadata parsing
# -----------------------------------------------------------------------------
def read_meta(path):
    """Parse the '# key=value' metadata lines cache_bench writes to stderr.

    Reading the metadata rather than re-deriving values from the filename means
    the summary always reflects what the benchmark actually did -- for example
    actual_footprint_bytes, which is the quantity that belongs on the x-axis.
    """
    meta = {}
    if not os.path.exists(path):
        return meta
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("#") or "=" not in line:
                continue
            key, _, val = line[1:].strip().partition("=")
            meta[key.strip()] = val.strip()
    return meta


# -----------------------------------------------------------------------------
# Statistics
# -----------------------------------------------------------------------------
def summarize(ticks_per_access):
    """Compute the full statistic set the spec enumerates.

    OUTLIER DEFINITION: the standard Tukey rule -- a sample is an outlier if it
    lies more than 1.5 x IQR below Q1 or above Q3. We report the COUNT and never
    remove them. Outliers here are real events (interrupts, contention from
    other users, TLB or page-walk excursions) and the spec is explicit that they
    should be reported rather than deleted: "report outliers instead of deleting
    them". The median is used as the representative statistic precisely because
    it is insensitive to this tail.
    """
    a = np.asarray(ticks_per_access, dtype=np.float64)

    q1, med, q3 = np.percentile(a, [25, 50, 75])
    p5, p95 = np.percentile(a, [5, 95])
    iqr = q3 - q1

    lo_fence = q1 - 1.5 * iqr
    hi_fence = q3 + 1.5 * iqr
    n_outliers = int(np.count_nonzero((a < lo_fence) | (a > hi_fence)))

    return {
        "n_samples": a.size,
        "median": med,
        "mean": float(a.mean()),
        "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "p5": p5,
        "p95": p95,
        "min": float(a.min()),
        "max": float(a.max()),
        "n_outliers": n_outliers,
        "outlier_fraction": n_outliers / a.size if a.size else 0.0,
    }


def load_ticks_per_access(csv_gz_path):
    """Load a raw file and convert to ticks per access.

    The raw file stores ticks_elapsed for a BATCH of N_per_batch dependent
    loads. The division to per-access happens here, not in the benchmark, so
    the raw data remains exactly what the hardware reported and the conversion
    is always re-checkable.
    """
    with gzip.open(csv_gz_path, "rt") as fh:
        header = fh.readline().strip().split(",")
        try:
            i_ticks = header.index("ticks_elapsed")
            i_npb = header.index("N_per_batch")
        except ValueError:
            raise SystemExit(f"unexpected header in {csv_gz_path}: {header}")

        data = np.loadtxt(fh, delimiter=",", usecols=(i_ticks, i_npb),
                          dtype=np.float64, ndmin=2)

    if data.size == 0:
        return np.array([]), 0

    ticks = data[:, 0]
    npb = data[:, 1]
    return ticks / npb, int(npb[0])


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
FNAME_RE = re.compile(
    r"capacity_ws(?P<ws>\d+)_sp(?P<sp>\d+)_(?P<order>rand|seq)_"
    r"(?P<machine>[^_]+)_(?P<ts>[\d\-]+)\.csv\.gz$"
)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--box-subsample", type=int, default=20000,
                    help="max raw values retained per point for box plots "
                         "(default 20000; enough for a faithful box plot "
                         "without carrying 1e6 values per point into the "
                         "plotting stage)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(args.raw_dir, "capacity_ws*.csv.gz")))
    if not files:
        raise SystemExit(f"no capacity raw files found in {args.raw_dir}")

    rng = np.random.default_rng(12345)   # fixed seed: subsampling is reproducible

    summary_rows = []
    box_rows = []

    for path in files:
        m = FNAME_RE.search(os.path.basename(path))
        if not m:
            print(f"  skipping unrecognized file: {os.path.basename(path)}",
                  file=sys.stderr)
            continue

        meta = read_meta(path[:-len(".csv.gz")] + ".meta")
        tpa, npb = load_ticks_per_access(path)

        if tpa.size == 0:
            print(f"  WARNING: {os.path.basename(path)} contained no samples",
                  file=sys.stderr)
            continue

        stats = summarize(tpa)

        # Prefer the footprint the benchmark actually traversed over the
        # requested size. With the divisibility check they are equal, but the
        # traversed value is the defensible x-axis quantity.
        footprint = int(meta.get("actual_footprint_bytes", m.group("ws")))

        row = {
            "machine": m.group("machine"),
            "working_set_bytes": int(m.group("ws")),
            "footprint_bytes": footprint,
            "node_spacing_bytes": int(m.group("sp")),
            "traversal_order": "randomized" if m.group("order") == "rand" else "sequential",
            "N_per_batch": npb,
            "unit": "TSC_ticks_per_access",
            **stats,
            "num_nodes": meta.get("num_nodes", ""),
            "warmup_steps": meta.get("warmup_steps", ""),
            "warmup_laps": meta.get("warmup_laps", ""),
            "seed": meta.get("seed", ""),
            "migrated_excluded": meta.get("migrated_samples_excluded", ""),
            "logical_cpu": meta.get("logical_cpu_from_tsc_aux", ""),
            "source_raw_file": os.path.basename(path),
        }
        summary_rows.append(row)

        # Retain a bounded random subsample for box plots.
        k = min(args.box_subsample, tpa.size)
        keep = rng.choice(tpa, size=k, replace=False) if k < tpa.size else tpa
        for v in keep:
            box_rows.append((footprint, row["traversal_order"], v))

        print(f"  {os.path.basename(path)}: n={stats['n_samples']}, "
              f"median={stats['median']:.2f} ticks/access, "
              f"outliers={stats['n_outliers']}")

    # ---- write the summary --------------------------------------------------
    summary_rows.sort(key=lambda r: (r["traversal_order"], r["footprint_bytes"]))
    summary_path = os.path.join(args.out_dir, "capacity_summary.csv")

    cols = ["machine", "working_set_bytes", "footprint_bytes",
            "node_spacing_bytes", "traversal_order", "N_per_batch", "unit",
            "n_samples", "median", "mean", "sd", "q1", "q3", "iqr",
            "p5", "p95", "min", "max", "n_outliers", "outlier_fraction",
            "num_nodes", "warmup_steps", "warmup_laps", "seed",
            "migrated_excluded", "logical_cpu", "source_raw_file"]

    with open(summary_path, "w") as fh:
        fh.write(",".join(cols) + "\n")
        for r in summary_rows:
            fh.write(",".join(str(r.get(c, "")) for c in cols) + "\n")

    # ---- write the box-plot subsample --------------------------------------
    box_path = os.path.join(args.out_dir, "capacity_boxdata.csv.gz")
    with gzip.open(box_path, "wt") as fh:
        fh.write("footprint_bytes,traversal_order,ticks_per_access\n")
        for fp, order, v in box_rows:
            fh.write(f"{fp},{order},{v:.6f}\n")

    # ---- timer overhead -----------------------------------------------------
    ov_files = sorted(glob.glob(os.path.join(args.raw_dir,
                                             "timer_overhead_*.csv.gz")))
    if ov_files:
        ov_path = os.path.join(args.out_dir, "timer_overhead_summary.csv")
        with open(ov_path, "w") as fh:
            fh.write("source_raw_file,unit,n_samples,median,mean,sd,q1,q3,"
                     "p5,p95,min,max,n_outliers\n")
            for f in ov_files:
                with gzip.open(f, "rt") as g:
                    g.readline()
                    d = np.loadtxt(g, delimiter=",", usecols=(1,),
                                   dtype=np.float64, ndmin=1)
                s = summarize(d)
                fh.write(f"{os.path.basename(f)},TSC_ticks_per_empty_bracket,"
                         f"{s['n_samples']},{s['median']},{s['mean']},{s['sd']},"
                         f"{s['q1']},{s['q3']},{s['p5']},{s['p95']},"
                         f"{s['min']},{s['max']},{s['n_outliers']}\n")
        print(f"\nTimer overhead summary: {ov_path}")

    print(f"\nSummary:  {summary_path}  ({len(summary_rows)} rows)")
    print(f"Box data: {box_path}")


if __name__ == "__main__":
    main()
