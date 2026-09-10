#!/usr/bin/env bash
# =============================================================================
# build.sh
#
# Builds the Phase-I benchmarks and archives the artifacts the spec requires for
# assembly inspection and build traceability.
#
# ECE 592 Homework I -- Phase I.
#
# WHY THE DISASSEMBLY ARTIFACTS ARE MANDATORY
# -------------------------------------------
# Spec: "Keep the compiler optimizations turned off by -O0: Inspect generated
# assembly for critical loops ... State compiler, version, optimization flags,
# and relevant source annotations."
# Submission checklist: "...and the inspected disassembly excerpt for critical
# loops."
#
# This script produces .s, .dis, .source.dis, and .intel.dis for every binary,
# plus a build log recording the exact compiler, version, and flags used.
#
# USAGE
#   ./build.sh <source_dir> <output_dir>
#
# Example:
#   ./scripts/build.sh main_code/x86_64 data_raw/sunbird/build
# =============================================================================

set -euo pipefail

SRC_DIR="${1:-main_code/x86_64}"
OUT_DIR="${2:-build}"

# Spec-mandated Phase-I baseline flags. Do NOT add -O2/-O3 or -flto here.
# -O0        : required baseline; preserves the intended access pattern
# -g         : symbols for readable disassembly with -S interleaving
# -std=c11   : aligned_alloc and the fixed-width integer types
# -Wall -Wextra : catch mistakes early; the sources build warning-free
# -fno-omit-frame-pointer : keeps stack frames intact for readable listings
CFLAGS="-O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer"

mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/build_log.txt"

{
    echo "# ============================================================"
    echo "# Build log -- ECE 592 HW1 Phase I"
    echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) (UTC)"
    echo "# Host: $(hostname)"
    echo "# ============================================================"
    echo
    echo "## Compiler version"
    gcc --version
    echo
    echo "## Flags"
    echo "CFLAGS = $CFLAGS"
    echo
    echo "## Git commit (if the tree is a git repo)"
    git rev-parse HEAD 2>/dev/null || echo "(not a git repository)"
    git status --porcelain 2>/dev/null | head -20 || true
    echo
} > "$LOG"

for src in "$SRC_DIR"/*.c; do
    base="$(basename "$src" .c)"
    echo "Building $base ..."

    # --- the binary ---------------------------------------------------------
    # shellcheck disable=SC2086
    gcc $CFLAGS -o "$OUT_DIR/$base" "$src"

    # --- compiler-emitted assembly -----------------------------------------
    # shellcheck disable=SC2086
    gcc $CFLAGS -S -o "$OUT_DIR/$base.s" "$src"

    # --- disassembly of the linked binary ----------------------------------
    # Plain, source-interleaved, and Intel-syntax variants. The spec's example
    # command list includes all three; source-interleaved is the most useful
    # for confirming the chase loop, Intel syntax the most readable for x86.
    objdump -d           "$OUT_DIR/$base" > "$OUT_DIR/$base.dis"
    objdump -d -S        "$OUT_DIR/$base" > "$OUT_DIR/$base.source.dis"
    objdump -d -Mintel   "$OUT_DIR/$base" > "$OUT_DIR/$base.intel.dis"

    {
        echo "## Built: $base"
        echo "   source:   $src"
        echo "   command:  gcc $CFLAGS -o $OUT_DIR/$base $src"
        echo "   sha256:   $(sha256sum "$src" | awk '{print $1}')"
        echo
    } >> "$LOG"
done

# --- extract the critical loop for quick inspection -------------------------
# The spec requires the disassembly EXCERPT of the critical loop to be kept in
# experimental notes. This pulls the chase() function out of the Intel-syntax
# listing so it can be pasted directly into the report.
if [ -f "$OUT_DIR/cache_bench.intel.dis" ]; then
    echo "Extracting chase() critical loop ..."
    awk '/<chase>:/{flag=1} flag{print} flag&&/ret/{exit}' \
        "$OUT_DIR/cache_bench.intel.dis" > "$OUT_DIR/critical_loop_chase.asm"

    {
        echo "## Critical loop (chase) -- Intel syntax"
        echo "   Extracted to: $OUT_DIR/critical_loop_chase.asm"
        echo "   VERIFY MANUALLY (spec checklist):"
        echo "     1. the intended load exists (mov reg, QWORD PTR [reg])"
        echo "     2. the dependency chain is intact (loaded value feeds next address)"
        echo "     3. timer reads bracket the intended region (check main, not chase)"
        echo "     4. loop not removed / vectorized / unrolled into another pattern"
        echo "     5. no unexpected stores to the traversed buffer inside the loop"
        echo "        (the stack spill of 'p' at -O0 is expected and is NOT a violation)"
        echo
    } >> "$LOG"
fi

echo
echo "Build complete."
echo "  Binaries and listings: $OUT_DIR"
echo "  Build log:             $LOG"
echo "  Critical loop excerpt: $OUT_DIR/critical_loop_chase.asm"
