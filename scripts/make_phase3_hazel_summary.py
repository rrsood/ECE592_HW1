#!/usr/bin/env python3
"""Build compact Phase III Hazel summary tables from processed artifacts.

This intentionally uses only processed TSV/PDF artifacts. It does not read raw
timing samples and it does not use PMU or system cache files to "fix" timing
results.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MACHINES = ("haswell", "broadwell", "cascadelake", "genoa", "skylake")


SYSTEM_GEOMETRY = {
    "haswell": {
        "generation": "Intel Haswell",
        "line_bytes": "64",
        "l1d_bytes": "32768",
        "l2_bytes": "262144",
        "llc_bytes": "26214400",
        "l1d_ways": "8",
        "l2_ways": "8",
        "llc_ways": "20",
    },
    "broadwell": {
        "generation": "Intel Broadwell",
        "line_bytes": "64",
        "l1d_bytes": "32768",
        "l2_bytes": "262144",
        "llc_bytes": "31457280",
        "l1d_ways": "8",
        "l2_ways": "8",
        "llc_ways": "20",
    },
    "cascadelake": {
        "generation": "Intel Cascade Lake",
        "line_bytes": "64",
        "l1d_bytes": "32768",
        "l2_bytes": "1048576",
        "llc_bytes": "23068672",
        "l1d_ways": "8",
        "l2_ways": "16",
        "llc_ways": "11",
    },
    "genoa": {
        "generation": "AMD Zen 4 / Genoa",
        "line_bytes": "64",
        "l1d_bytes": "32768",
        "l2_bytes": "1048576",
        "llc_bytes": "33554432",
        "l1d_ways": "8",
        "l2_ways": "8",
        "llc_ways": "16",
    },
    "skylake": {
        "generation": "Intel Skylake-SP",
        "line_bytes": "64",
        "l1d_bytes": "32768",
        "l2_bytes": "1048576",
        "llc_bytes": "23068672",
        "l1d_ways": "8",
        "l2_ways": "16",
        "llc_ways": "11",
    },
}


def read_processed_tsv(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    meta: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line == "data_begin":
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    if row and next(iter(row.values())) == "data_end":
                        break
                    rows.append({k: (v or "") for k, v in row.items() if k is not None})
                break
            if "=" in line:
                key, value = line.split("=", 1)
                meta[key] = value
    return meta, rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def latest_dir(root: Path, machine: str, stage: str) -> Path | None:
    dirs = sorted(p for p in root.glob(f"{machine}_{stage}_*") if p.is_dir())
    return dirs[-1] if dirs else None


def stage_file(root: Path, machine: str, stage: str, rel: str) -> Path | None:
    d = latest_dir(root, machine, stage)
    if not d:
        return None
    p = d / rel
    return p if p.exists() else None


def all_stage_files(root: Path, machine: str, stage: str, rel: str) -> list[Path]:
    out: list[Path] = []
    for d in sorted(p for p in root.glob(f"{machine}_{stage}_*") if p.is_dir()):
        p = d / rel
        if p.exists():
            out.append(p)
    return out


def format_path(path: Path | None) -> str:
    return "" if path is None else str(path)


def median_latency_summary(path: Path | None) -> str:
    if not path:
        return ""
    _, rows = read_processed_tsv(path)
    vals = []
    for row in rows:
        role = row.get("point_role", "")
        span = row.get("actual_span_bytes", "")
        med = row.get("elapsed_raw_ticks_per_access_unadjusted_median", "")
        if role in {"below_refined_interval", "above_refined_interval"} and span and med:
            vals.append(f"{span}:{med}")
    return ";".join(vals[:8])


def software_rows(path: Path, machine: str) -> list[dict[str, str]]:
    case = path.stem
    meta, rows = read_processed_tsv(path)
    if not rows:
        return []
    row = rows[0]
    return [{
        "machine": machine,
        "case": case,
        "estimated_hit_rate": row.get("estimated_hit_rate", ""),
        "wilson_95_low": row.get("wilson_95_low", ""),
        "wilson_95_high": row.get("wilson_95_high", ""),
        "target_median_ticks_per_access": row.get("target_median_ticks_per_access", ""),
        "balanced_calibration_accuracy": meta.get("balanced_calibration_accuracy", ""),
        "source_file": str(path),
    }]


def inclusion_summary(path: Path, machine: str, llc_bytes: int) -> dict[str, str]:
    _, rows = read_processed_tsv(path)
    groups = {
        "none": [],
        "self": [],
        "helper_below_llc": [],
        "helper_at_or_above_llc": [],
        "helper_all": [],
    }
    for row in rows:
        try:
            pressure = int(row.get("pressure_bytes", "0"))
            prob = float(row.get("eviction_probability", "nan"))
            delta = float(row.get("delta_median_ticks_per_access", "nan"))
        except ValueError:
            continue
        src = row.get("pressure_source", "")
        item = (prob, delta, pressure, row.get("target_bytes", ""))
        if src == "none":
            groups["none"].append(item)
        elif src == "self":
            groups["self"].append(item)
        elif src == "helper":
            groups["helper_all"].append(item)
            if pressure >= llc_bytes:
                groups["helper_at_or_above_llc"].append(item)
            else:
                groups["helper_below_llc"].append(item)

    def best(name: str) -> tuple[float, float, int, str]:
        vals = groups[name]
        if not vals:
            return (0.0, 0.0, 0, "")
        return max(vals, key=lambda x: x[0])

    none = best("none")
    selfb = best("self")
    helper_below = best("helper_below_llc")
    helper_above = best("helper_at_or_above_llc")
    helper_all = best("helper_all")

    if helper_above[0] >= 0.25 and none[0] <= 0.05:
        classification = "inclusive_or_back_invalidation_observed"
    elif helper_above[0] < 0.10 and selfb[0] >= 0.20:
        classification = "non_inclusive_or_uncertain_no_strong_helper_back_invalidation"
    else:
        classification = "uncertain_mixed_behavior"

    return {
        "machine": machine,
        "processed_point_count": str(len(rows)),
        "max_none_eviction_probability": f"{none[0]:.6g}",
        "max_self_eviction_probability": f"{selfb[0]:.6g}",
        "max_helper_below_llc_eviction_probability": f"{helper_below[0]:.6g}",
        "max_helper_at_or_above_llc_eviction_probability": f"{helper_above[0]:.6g}",
        "max_helper_all_eviction_probability": f"{helper_all[0]:.6g}",
        "pressure_bytes_at_max_helper": str(helper_all[2]),
        "target_bytes_at_max_helper": helper_all[3],
        "behavioral_classification": classification,
        "source_file": str(path),
    }


def write_tsv(path: Path, meta: dict[str, str], rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        for k, v in meta.items():
            f.write(f"{k}={v}\n")
        f.write("data_begin\n")
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        f.write("data_end\n")


def main() -> int:
    root = Path("data_processed/phase3")
    out_dir = Path("data_processed/phase3_validation")
    plots_root = Path("plots/phase3")
    if not root.exists():
        raise SystemExit(f"missing extracted Phase III root: {root}")

    meta = {
        "generated_by": "scripts/make_phase3_hazel_summary.py",
        "source_root": str(root),
        "scope": "Hazel Phase III five-CPU processed timing artifacts",
    }

    geometry_rows: list[dict[str, str]] = []
    capacity_rows: list[dict[str, str]] = []
    software_out: list[dict[str, str]] = []
    inclusion_out: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []

    for machine in MACHINES:
        geom = dict(SYSTEM_GEOMETRY[machine])
        cap = stage_file(root, machine, "capacity", "processed/capacity/evidence_summary.tsv")
        line = stage_file(root, machine, "line_size", "processed/line_size/spatial_randomized.tsv")
        lat = stage_file(root, machine, "capacity", "processed/latency/hit_representatives.tsv")
        miss = stage_file(root, machine, "capacity", "processed/latency/miss_next_level_evidence.tsv")
        evict = stage_file(root, machine, "eviction", "processed/eviction/cross_level_randomized.tsv")
        incls = sorted((root / "inclusion_policy" / machine).glob(f"{machine}_inclusion_policy_*.tsv"))
        incl = incls[-1] if incls else None
        assoc_files = all_stage_files(root, machine, "associativity", "processed/associativity/conflict_randomized.tsv")
        sw_dir = latest_dir(root, machine, "software")

        geometry_rows.append({
            "machine": machine,
            **geom,
            "timing_capacity_evidence_file": format_path(cap),
            "timing_line_size_file": format_path(line),
            "timing_associativity_files": ";".join(str(p) for p in assoc_files),
            "timing_latency_file": format_path(lat),
            "timing_miss_next_level_file": format_path(miss),
            "timing_eviction_file": format_path(evict),
            "inclusion_policy_file": format_path(incl),
            "software_hit_rate_dir": format_path(sw_dir / "processed/software_hit_rate" if sw_dir else None),
            "representative_latency_medians_span_bytes_to_ticks": median_latency_summary(lat),
        })

        if cap:
            _, rows = read_processed_tsv(cap)
            for row in rows:
                capacity_rows.append({
                    "machine": machine,
                    "evidence_rank": row.get("evidence_rank", ""),
                    "coarse_interval_bytes": row.get("coarse_interval_bytes", ""),
                    "coarse_relative_increase": row.get("coarse_relative_increase", ""),
                    "dense_refined_interval_bytes": row.get("dense_refined_interval_bytes", ""),
                    "dense_relative_increase": row.get("dense_relative_increase", ""),
                    "dense_support_status": row.get("dense_support_status", ""),
                    "source_file": str(cap),
                })

        if sw_dir:
            for p in sorted((sw_dir / "processed/software_hit_rate").glob("*.tsv")):
                software_out.extend(software_rows(p, machine))

        if incl:
            inclusion_out.append(inclusion_summary(incl, machine, int(geom["llc_bytes"])))

    for p in sorted(root.rglob("*")) + sorted(plots_root.rglob("*")):
        if p.is_file() and ("/processed/" in str(p) or p.suffix == ".pdf" or "inclusion_policy" in str(p)):
            kind = "plot_pdf" if p.suffix == ".pdf" else "processed_tsv" if p.suffix == ".tsv" else "other"
            manifest_rows.append({
                "kind": kind,
                "path": str(p),
                "bytes": str(p.stat().st_size),
                "sha256": sha256_file(p),
            })

    write_tsv(
        out_dir / "phase3_hazel_geometry_and_evidence_summary_v1.tsv",
        meta,
        geometry_rows,
        [
            "machine", "generation", "line_bytes", "l1d_bytes", "l2_bytes", "llc_bytes",
            "l1d_ways", "l2_ways", "llc_ways", "timing_capacity_evidence_file",
            "timing_line_size_file", "timing_associativity_files", "timing_latency_file",
            "timing_miss_next_level_file", "timing_eviction_file", "inclusion_policy_file",
            "software_hit_rate_dir", "representative_latency_medians_span_bytes_to_ticks",
        ],
    )
    write_tsv(
        out_dir / "phase3_hazel_capacity_boundary_evidence_v1.tsv",
        meta,
        capacity_rows,
        [
            "machine", "evidence_rank", "coarse_interval_bytes", "coarse_relative_increase",
            "dense_refined_interval_bytes", "dense_relative_increase", "dense_support_status",
            "source_file",
        ],
    )
    write_tsv(
        out_dir / "phase3_hazel_software_hit_rate_summary_v1.tsv",
        meta,
        software_out,
        [
            "machine", "case", "estimated_hit_rate", "wilson_95_low", "wilson_95_high",
            "target_median_ticks_per_access", "balanced_calibration_accuracy", "source_file",
        ],
    )
    write_tsv(
        out_dir / "phase3_hazel_inclusion_policy_summary_v1.tsv",
        meta,
        inclusion_out,
        [
            "machine", "processed_point_count", "max_none_eviction_probability",
            "max_self_eviction_probability", "max_helper_below_llc_eviction_probability",
            "max_helper_at_or_above_llc_eviction_probability",
            "max_helper_all_eviction_probability", "pressure_bytes_at_max_helper",
            "target_bytes_at_max_helper", "behavioral_classification", "source_file",
        ],
    )
    write_tsv(
        out_dir / "phase3_hazel_artifact_manifest_v1.tsv",
        meta,
        manifest_rows,
        ["kind", "path", "bytes", "sha256"],
    )

    for p in sorted(out_dir.glob("phase3_hazel_*_v1.tsv")):
        print(f"{p} {p.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
