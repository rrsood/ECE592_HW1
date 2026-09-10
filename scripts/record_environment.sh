#!/usr/bin/env bash
# =============================================================================
# record_environment.sh
#
# Captures the machine environment required by the spec's "Record the
# environment" bullet, using ONLY Phase-I-safe commands.
#
# ECE 592 Homework I -- Phase I.
#
# PHASE-I SAFETY
# --------------
# The spec permits identifying the machine and topology, but forbids anything
# that reports cache sizes/ways/topology until timing-only results are frozen:
#   "do not use commands/files whose purpose is to report cache sizes, cache
#    ways, or cache topology (for example, cache entries in sysfs)"
#
# Commands used here are exactly those the spec lists as Phase-I safe:
#   hostname, uname -a, grep model name /proc/cpuinfo, lscpu -e=CPU,CORE,SOCKET,NODE
#
# DELIBERATELY NOT USED (would break the Phase-I wall):
#   lscpu            (unfiltered -- prints L1d/L1i/L2/L3 cache size fields)
#   lscpu -C         (cache table)
#   /sys/devices/system/cpu/cpu*/cache/*
#   getconf -a | grep CACHE
#   dmidecode, cpuid, hwloc-ls, likwid-topology
#
# The lscpu invocation is field-restricted with -e=CPU,CORE,SOCKET,NODE so it
# emits only the topology columns and no cache columns.
#
# USAGE
#   ./record_environment.sh <output_file>
# =============================================================================

set -euo pipefail

OUT="${1:-environment.txt}"

{
    echo "# ============================================================"
    echo "# Environment record -- ECE 592 HW1 Phase I"
    echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) (UTC)"
    echo "# NOTE: Phase-I-safe commands only; no cache-size fields queried."
    echo "# ============================================================"
    echo

    echo "## hostname"
    hostname
    echo

    echo "## uname -a"
    uname -a
    echo

    echo "## CPU model (/proc/cpuinfo, first match only)"
    grep -m1 -E 'model name|Hardware|Processor' /proc/cpuinfo || echo "(not found)"
    echo

    echo "## Topology (lscpu -e=CPU,CORE,SOCKET,NODE -- no cache fields)"
    lscpu -e=CPU,CORE,SOCKET,NODE 2>/dev/null || echo "(lscpu unavailable)"
    echo

    echo "## Page size (getconf PAGESIZE)"
    getconf PAGESIZE
    echo

    echo "## Compiler version"
    gcc --version | head -1
    echo

    echo "## Kernel version"
    cat /proc/version
    echo

    echo "## Load average at capture time (interference indicator)"
    cat /proc/loadavg
    echo

    echo "## Logged-in users (other users may perturb measurements)"
    who 2>/dev/null || echo "(who unavailable)"
    echo

    echo "## NUMA nodes present"
    ls -d /sys/devices/system/node/node* 2>/dev/null | wc -l
    echo

    echo "## Transparent hugepage setting (affects TLB reach; not a cache field)"
    cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo "(unavailable)"
    echo

} > "$OUT"

echo "Environment recorded to: $OUT"
