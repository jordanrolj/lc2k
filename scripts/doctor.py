#!/usr/bin/env python3
"""Report pinned dependencies and resources; exit nonzero for missing requirements."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def probe(command: list[str]) -> dict:
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=20)
        return {"command": command, "exit_code": result.returncode, "output": result.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "exit_code": None, "output": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-only", action="store_true", help="do not require built LLVM tools")
    args = parser.parse_args()
    pin = json.loads((ROOT / "configs/toolchain.json").read_text())["llvm"]
    minimum_python = (3, 10)
    checks = []
    failed = []
    for tool in ("cmake", "ninja", "git", "clang", "clang++", "curl", "tar"):
        executable = shutil.which(tool)
        result = probe([executable or tool, "--version"])
        checks.append({"name": tool, "path": executable, **result})
        if executable is None or result["exit_code"] != 0:
            failed.append(tool)
    if sys.version_info < minimum_python:
        failed.append("Python >= 3.10")
    backend = []
    for tool in ("llc", "opt", "clang", "llvm-config", "lc2k-prepare"):
        executable = ROOT / "build/llvm/bin" / tool
        result = probe([str(executable), "--version"])
        compatible = result["exit_code"] == 0 and pin["version"] in result["output"]
        if tool == "llc":
            compatible = compatible and "lc2k" in result["output"].lower()
        backend.append({"name": tool, "compatible": compatible, **result})
        if not args.setup_only and not compatible:
            failed.append(f"pinned {tool}")
    memory = None
    if platform.system() == "Darwin":
        result = probe(["sysctl", "-n", "hw.memsize"])
        if result["exit_code"] == 0:
            memory = int(result["output"])
    else:
        try:
            memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (OSError, ValueError):
            pass
    usage = shutil.disk_usage(ROOT)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "platform": platform.platform(), "architecture": platform.machine(),
        "python": sys.version, "cpu_count": os.cpu_count(), "memory_bytes": memory,
        "memory_note": None if memory else "resource probe unavailable in this environment",
        "disk_free_bytes": usage.free, "llvm_pin": pin, "setup_checks": checks,
        "backend_checks": backend, "git": probe(["git", "-C", str(ROOT), "status", "--short", "--branch"]),
        "failed_requirements": failed, "exit_code": int(bool(failed)),
    }
    logdir = ROOT / "build/logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = logdir / f"doctor-{stamp}.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Host: {report['platform']} ({report['architecture']}); Python {platform.python_version()}")
    print(f"Resources: {report['cpu_count']} CPUs; RAM {memory if memory else 'unavailable'} bytes; "
          f"free disk {usage.free // (1024**3)} GiB")
    print(f"LLVM pin: {pin['tag']} {pin['commit']}")
    for item in checks:
        first_line = item["output"].splitlines()[0] if item["output"] else "no output"
        print(f"{'PASS' if item['exit_code'] == 0 else 'FAIL'} {item['name']}: {first_line}")
    for item in backend:
        print(f"{'PASS' if item['compatible'] else 'MISSING/INCOMPATIBLE'} pinned {item['name']}")
    print(f"Evidence: {output}")
    if failed:
        print("DOCTOR FAILED: " + ", ".join(failed))
    else:
        print("DOCTOR PASSED" + (" (setup requirements only)" if args.setup_only else ""))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
