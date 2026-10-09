#!/usr/bin/env python3
"""Compare two CLI files against the configured workspace with read-only commands.

python3 benchmark.py --before /path/to/base/linear --after ./linear --project NAME
Prints timings and output digests, never credentials or workspace contents.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

_SAMPLE = r'''
import contextlib, hashlib, io, json, runpy, sys
module = runpy.run_path(sys.argv[1], run_name="linear_benchmark")
main = module["main"]
globals_ = main.__globals__
original = globals_["gql"]
requests = []
def measured(*args, **kwargs):
    result = original(*args, **kwargs)
    requests.append({"bytes": len(json.dumps(result).encode()),
                     "error": bool(result.get("errors"))})
    return result
globals_["gql"] = measured
sys.argv = sys.argv[1:]
output = io.StringIO()
with contextlib.redirect_stdout(output):
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            raise
text = output.getvalue()
if "--json" in sys.argv:
    document = json.loads(text)
    if isinstance(document, dict):
        document.pop("generatedAt", None)
    text = json.dumps(document, sort_keys=True, separators=(",", ":"))
print(json.dumps({"requests": len(requests),
                  "response_bytes": sum(r["bytes"] for r in requests),
                  "errors": sum(r["error"] for r in requests),
                  "digest": hashlib.sha256(text.encode()).hexdigest()}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--project", required=True, help="Project name or UUID for scoped overview")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    scenarios = {
        "help": ["--help"],
        "tasks-active": ["tasks", "--all", "--cycle", "active", "--json"],
        "tasks-next": ["tasks", "--all", "--cycle", "next", "--json"],
        "board-active": ["tasks", "--board", "--all", "--cycle", "active", "--json"],
        "overview-all": ["projects", "overview", "--json"],
        "overview-project": ["projects", "overview", "--project", args.project, "--json"],
        "goals": ["goals", "--json"],
    }
    samples = {name: {"before": [], "after": []} for name in scenarios}
    for name, command in scenarios.items():
        for run in range(args.runs):
            # Alternate order to reduce systematic effects from server/machine load.
            order = ("before", "after") if run % 2 == 0 else ("after", "before")
            for version in order:
                start = time.perf_counter()
                proc = subprocess.run(
                    [sys.executable, "-c", _SAMPLE, str(getattr(args, version).resolve()), *command],
                    capture_output=True, text=True, timeout=120,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                elapsed = time.perf_counter() - start
                if proc.returncode:
                    raise RuntimeError(f"{name}/{version} exited {proc.returncode}; inspect the command privately")
                result = json.loads(proc.stdout)
                if result["errors"]:
                    raise RuntimeError(f"{name}/{version} returned API errors")
                result["seconds"] = round(elapsed, 6)
                samples[name][version].append(result)
                print(json.dumps({"scenario": name, "version": version, "run": run + 1, **result}), flush=True)
    for name, versions in samples.items():
        summary = {"scenario": name, "summary": True}
        for version, rows in versions.items():
            times = [r["seconds"] for r in rows]
            summary[version] = {"median_seconds": statistics.median(times),
                                "min_seconds": min(times), "max_seconds": max(times),
                                "requests": sorted({r["requests"] for r in rows})}
        summary["outputs_equal"] = len({r["digest"] for rows in versions.values() for r in rows}) == 1
        print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
