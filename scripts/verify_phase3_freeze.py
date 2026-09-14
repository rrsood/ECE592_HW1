#!/usr/bin/env python3
"""Refuse Hazel cache runs unless the prediction bundle is committed intact."""

import argparse
import csv
import hashlib
import os
import subprocess
import sys


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-directory", required=True)
    parser.add_argument("--freeze-commit", required=True)
    args = parser.parse_args()
    directory = os.path.abspath(args.freeze_directory)
    manifest = os.path.join(directory, "freeze_manifest.tsv")
    if not os.path.isfile(manifest):
        parser.error("freeze_manifest.tsv is missing")
    subprocess.run(["git", "cat-file", "-e", args.freeze_commit + "^{commit}"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", args.freeze_commit, "HEAD"], check=True)
    relative = os.path.relpath(directory, subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip())
    if subprocess.run(["git", "diff", "--quiet", args.freeze_commit, "--", relative]).returncode != 0:
        raise ValueError("freeze directory differs from the supplied committed revision")
    with open(manifest, encoding="utf-8", newline="") as stream:
        for line in stream:
            if line.rstrip("\n") == "data_begin":
                break
        reader = csv.DictReader(stream, delimiter="\t")
        checked = 0
        for row in reader:
            if row["filename"] == "data_end":
                break
            path = os.path.join(directory, row["filename"])
            if not os.path.isfile(path) or sha256_file(path) != row["sha256"]:
                raise ValueError("freeze hash mismatch: {}".format(path))
            checked += 1
    if checked < 3:
        raise ValueError("freeze manifest has too few protected files")
    print("freeze_commit={}".format(args.freeze_commit))
    print("verified_file_count={}".format(checked))
    print("status=ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        sys.exit(1)
