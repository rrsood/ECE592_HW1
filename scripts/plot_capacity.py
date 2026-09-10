#!/usr/bin/env python3
"""
=============================================================================
plot_capacity.py

Produces the Experiment 1 figures: the latency-vs-working-set staircase and the
box plots around each inferred boundary.

ECE 592 Homework I -- Phase I.

FIGURE STYLE REQUIREMENTS IMPLEMENTED
-------------------------------------
The spec's "Required figure style (conference/old-ISCA style)" bullet is
prescriptive, and every item below is enforced in STYLE / the plotting calls:

  "large readable fonts"                -> font sizes 13-16
  "white background"                    -> figure.facecolor / axes.facecolor white
  "black/grayscale lines and markers"   -> only black and gray levels used
  "clearly distinguishable marker
   shapes and line styles"              -> filled circle vs. open square,
                                           solid vs. dash-dot
  "no background grid lines"            -> ax.grid(False), enforced explicitly
  "strong black axes"                   -> spine linewidth 1.6, black
  "line widths/marker sizes that remain
   readable when reduced to a column"   -> lw 2.0, markersize 8
  "Avoid rainbow palettes, thin hairline
   curves, tiny tick labels, decorative
   backgrounds"                         -> none used
  "Figures must remain interpretable
   when printed in grayscale"           -> already grayscale by construction
  "Vector plots are preferred"          -> PDF output (also PNG for quick view)

LINE-STYLE RULE
  The spec reserves DASHED lines for future-year extrapolation in the
  chronological/prediction plots ("use a dashed line only for future-year
  extrapolation/prediction beyond the last measured training-year point").
  These are measurement plots, not chronological ones, so every measured series
  here is drawn SOLID with solid markers. The sequential control uses dash-dot
  rather than dashed to stay clear of that reserved meaning while remaining
  distinguishable in grayscale.

USAGE
    python3 plot_capacity.py <processed_dir> <plots_dir> [--machine NAME]
                             [--boundaries B1,B2,B3]

    --boundaries  optional comma-separated byte values at which YOUR analysis
                  inferred a capacity edge. When given, dotted vertical markers
                  are drawn and box plots are emitted below/at/above each one.
                  The spec reserves dotted (not dashed) for inferred boundaries
                  in this kind of figure, matching its Figure 9.
=============================================================================
"""

import argparse
import csv
import gzip
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")           # headless: lab machines have no display
import matplotlib.pyplot as plt
import numpy as np


# -----------------------------------------------------------------------------
# Style
# -----------------------------------------------------------------------------
STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",

    "font.size": 13,
    "axes.labelsize": 15,
    "axes.titlesize": 15,
    "xtick.labelsize": 13,
    "ytick.labelsize": 13,
    "legend.fontsize": 12,

    # Strong black axes on all four sides, as in classic gnuplot figures.
    "axes.edgecolor": "black",
    "axes.linewidth": 1.6,
    "axes.grid": False,               # spec: no background grid lines

    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "xtick.major.size": 7,
    "xtick.minor.size": 4,
    "ytick.major.size": 7,
    "ytick.minor.size": 4,
    "xtick.major.width": 1.4,
    "ytick.major.width": 1.4,

    "lines.linewidth": 2.0,
    "lines.markersize": 8,

    "legend.frameon": True,
    "legend.edgecolor": "black",
    "legend.framealpha": 1.0,

    # Embed real fonts (Type 42) so the PDF is vector and text stays selectable.
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
}

# Grayscale-only series encoding. Distinguishable by SHAPE and LINE STYLE, not
# by colour, so the figures survive grayscale printing.
SERIES = {
    "randomized": dict(color="black", marker="o", markerfacecolor="black",
                       linestyle="-", label="Randomized chase (primary)"),
    "sequential": dict(color="0.45", marker="s", markerfacecolor="white",
                       markeredgecolor="0.45", linestyle="-.",
                       label="Sequential chase (prefetcher control)"),
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def human_bytes(n):
    """Format a byte count with binary (KiB/MiB) units for axis tick labels."""
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if n == int(n) else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.0f} GiB"


def load_summary(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    if not rows:
        raise SystemExit(f"no rows in {path}")
    return rows


def load_boxdata(path):
    """Load the subsampled per-point values, keyed by (footprint, order)."""
    data = defaultdict(list)
    if not os.path.exists(path):
        return data
    with gzip.open(path, "rt") as fh:
        next(fh)
        for line in fh:
            fp, order, v = line.strip().split(",")
            data[(int(fp), order)].append(float(v))
    return data


# -----------------------------------------------------------------------------
# Figure 1: the staircase
# -----------------------------------------------------------------------------
def plot_staircase(rows, out_base, machine, boundaries=None):
    """Median latency per access vs. working-set footprint.

    ERROR BARS: drawn from the 5th to the 95th percentile, which the spec asks
    for ("Include uncertainty/error bars where the inferred value or latency has
    measurable variability"). Percentiles rather than standard deviation,
    because the latency distributions are strongly right-skewed -- an
    interrupt-inflated tail makes sd a poor width descriptor while p5/p95
    describes the bulk honestly.
    """
    series = defaultdict(list)
    for r in rows:
        series[r["traversal_order"]].append((
            int(r["footprint_bytes"]),
            float(r["median"]),
            float(r["p5"]),
            float(r["p95"]),
        ))

    fig, ax = plt.subplots(figsize=(8.0, 5.2))

    for order in ("randomized", "sequential"):
        if order not in series:
            continue
        pts = sorted(series[order])
        x = np.array([p[0] for p in pts], dtype=float)
        med = np.array([p[1] for p in pts])
        p5 = np.array([p[2] for p in pts])
        p95 = np.array([p[3] for p in pts])

        style = SERIES[order]
        ax.errorbar(
            x, med,
            yerr=np.vstack([np.maximum(med - p5, 0), np.maximum(p95 - med, 0)]),
            capsize=3, elinewidth=1.0, capthick=1.0,
            ecolor=style["color"],
            **{k: v for k, v in style.items() if k != "label"},
            label=style["label"],
        )

    # Inferred boundaries as DOTTED verticals. Dotted, not dashed: the spec
    # reserves dashed for future-year prediction, and its own Figure 9 uses
    # dotted verticals for inferred boundaries.
    if boundaries:
        for b in boundaries:
            ax.axvline(b, color="0.3", linestyle=":", linewidth=1.4, zorder=0)
            ax.annotate(human_bytes(b), xy=(b, ax.get_ylim()[1]),
                        xytext=(0, -14), textcoords="offset points",
                        rotation=90, ha="right", va="top", fontsize=11,
                        color="0.2")

    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("Working-set footprint (bytes, log$_2$ scale)")
    ax.set_ylabel("Median latency (TSC ticks / access)")
    ax.set_title(f"Dependent-load latency vs. working-set size -- {machine}")

    # Readable binary tick labels rather than raw powers of two.
    xs = sorted({int(r["footprint_bytes"]) for r in rows})
    ticks = [v for v in xs if (v & (v - 1)) == 0] or xs[:: max(1, len(xs) // 8)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([human_bytes(t) for t in ticks], rotation=45, ha="right")

    ax.grid(False)                      # belt and braces: spec forbids grids
    ax.legend(loc="upper left")
    fig.tight_layout()

    fig.savefig(out_base + ".pdf")      # vector, preferred by the spec
    fig.savefig(out_base + ".png", dpi=200)
    plt.close(fig)
    print(f"  wrote {out_base}.pdf / .png")


# -----------------------------------------------------------------------------
# Figure 2: box plots around each boundary
# -----------------------------------------------------------------------------
def plot_boxes(boxdata, rows, out_base, machine, boundaries):
    """Box plots below / at / above every inferred boundary.

    Spec: "At minimum, show representative points immediately below, at/near,
    and above every inferred cache boundary."

    For each boundary we select the nearest measured footprint below it, the
    nearest at or just above it, and the next one beyond -- so each boundary
    contributes a below/at/above triple drawn from actual measured points rather
    than interpolated positions.
    """
    if not boundaries:
        print("  (no --boundaries given; skipping box plots)")
        return

    footprints = sorted({int(r["footprint_bytes"]) for r in rows
                         if r["traversal_order"] == "randomized"})
    if not footprints:
        return

    selected = []
    for b in boundaries:
        below = [f for f in footprints if f < b]
        at_above = [f for f in footprints if f >= b]
        if below:
            selected.append((below[-1], f"below\n{human_bytes(below[-1])}"))
        if at_above:
            selected.append((at_above[0], f"at\n{human_bytes(at_above[0])}"))
        if len(at_above) > 1:
            selected.append((at_above[1], f"above\n{human_bytes(at_above[1])}"))

    # De-duplicate while preserving order (adjacent boundaries can share points)
    seen = set()
    uniq = []
    for fp, lab in selected:
        if fp not in seen:
            seen.add(fp)
            uniq.append((fp, lab))

    data, labels = [], []
    for fp, lab in uniq:
        vals = boxdata.get((fp, "randomized"), [])
        if vals:
            data.append(vals)
            labels.append(lab)

    if not data:
        print("  (no box data matched the selected footprints)")
        return

    fig, ax = plt.subplots(figsize=(max(8.0, 1.1 * len(data)), 5.2))

    bp = ax.boxplot(
        data, labels=labels, showfliers=True, whis=(5, 95),
        patch_artist=True,
        boxprops=dict(facecolor="white", color="black", linewidth=1.4),
        medianprops=dict(color="black", linewidth=2.2),
        whiskerprops=dict(color="black", linewidth=1.2),
        capprops=dict(color="black", linewidth=1.2),
        flierprops=dict(marker=".", markersize=3, markerfacecolor="0.5",
                        markeredgecolor="0.5", alpha=0.4),
    )
    del bp

    ax.set_yscale("log")
    ax.set_ylabel("Latency (TSC ticks / access)")
    ax.set_xlabel("Working-set footprint, relative to each inferred boundary")
    ax.set_title(f"Latency distributions around inferred boundaries -- {machine}")
    ax.grid(False)

    # Whiskers are set to the 5th/95th percentiles to match the statistics
    # reported in the summary CSV, rather than matplotlib's default 1.5*IQR.
    ax.annotate("box: Q1-Q3, line: median, whiskers: p5-p95, dots: outliers",
                xy=(0.99, 0.02), xycoords="axes fraction",
                ha="right", va="bottom", fontsize=10, color="0.25")

    fig.tight_layout()
    fig.savefig(out_base + ".pdf")
    fig.savefig(out_base + ".png", dpi=200)
    plt.close(fig)
    print(f"  wrote {out_base}.pdf / .png")


# -----------------------------------------------------------------------------
# Figure 3: prefetcher-benefit ratio
# -----------------------------------------------------------------------------
def plot_prefetch_ratio(rows, out_base, machine):
    """Randomized-to-sequential median ratio vs. footprint.

    This is the quantitative form of the spec's prefetcher sanity check: "if it
    is much faster than the randomized chain at larger footprints, hardware
    prefetching is probably helping and should not be mistaken for a larger
    cache." A ratio near 1 means the two traversals agree and prefetching is not
    distorting the result; a ratio growing well above 1 at large footprints
    localizes exactly where prefetching starts to matter, and justifies using
    the randomized series for the final inference.
    """
    med = defaultdict(dict)
    for r in rows:
        med[int(r["footprint_bytes"])][r["traversal_order"]] = float(r["median"])

    xs, ys = [], []
    for fp in sorted(med):
        d = med[fp]
        if "randomized" in d and "sequential" in d and d["sequential"] > 0:
            xs.append(fp)
            ys.append(d["randomized"] / d["sequential"])

    if not xs:
        print("  (no paired randomized/sequential points; skipping ratio plot)")
        return

    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ax.plot(xs, ys, color="black", marker="o", markerfacecolor="black",
            linestyle="-", linewidth=2.0, markersize=7)
    ax.axhline(1.0, color="0.5", linestyle=":", linewidth=1.4)
    ax.annotate("ratio = 1: traversals agree\n(no prefetch benefit)",
                xy=(xs[0], 1.0), xytext=(6, 8), textcoords="offset points",
                fontsize=11, color="0.25")

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Working-set footprint (bytes, log$_2$ scale)")
    ax.set_ylabel("Median randomized / median sequential")
    ax.set_title(f"Prefetcher benefit vs. working-set size -- {machine}")
    ax.set_xticks([v for v in xs if (v & (v - 1)) == 0])
    ax.set_xticklabels([human_bytes(v) for v in xs if (v & (v - 1)) == 0],
                       rotation=45, ha="right")
    ax.grid(False)
    fig.tight_layout()

    fig.savefig(out_base + ".pdf")
    fig.savefig(out_base + ".png", dpi=200)
    plt.close(fig)
    print(f"  wrote {out_base}.pdf / .png")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("processed_dir")
    ap.add_argument("plots_dir")
    ap.add_argument("--machine", default=None,
                    help="machine name for titles (default: read from data)")
    ap.add_argument("--boundaries", default="",
                    help="comma-separated inferred capacity boundaries in bytes")
    args = ap.parse_args()

    os.makedirs(args.plots_dir, exist_ok=True)
    plt.rcParams.update(STYLE)

    rows = load_summary(os.path.join(args.processed_dir, "capacity_summary.csv"))
    boxdata = load_boxdata(os.path.join(args.processed_dir,
                                        "capacity_boxdata.csv.gz"))

    machine = args.machine or rows[0].get("machine", "unknown")
    boundaries = [int(b) for b in args.boundaries.split(",") if b.strip()]

    print(f"Plotting for machine: {machine}")
    plot_staircase(rows, os.path.join(args.plots_dir,
                                      f"capacity_staircase_{machine}"),
                   machine, boundaries)
    plot_boxes(boxdata, rows, os.path.join(args.plots_dir,
                                           f"capacity_boxplots_{machine}"),
               machine, boundaries)
    plot_prefetch_ratio(rows, os.path.join(args.plots_dir,
                                           f"prefetch_ratio_{machine}"),
                        machine)

    print("\nReminder for the report: label every figure with the machine, the "
          "units (TSC ticks/access, NOT cycles), the sample count, and the "
          "primary contributor, and cite the source raw files from "
          "capacity_summary.csv's source_raw_file column.")


if __name__ == "__main__":
    main()
