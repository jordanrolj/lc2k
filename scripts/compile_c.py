#!/usr/bin/env python3
"""Compile the restricted pinned RV32I C route to LC2K assembly.

Only the LLVM API validator in lc2k-prepare may retarget frontend IR. Source IR,
prepared IR and exact per-stage command/exit/output evidence are retained next
to the requested output. As with a compiler's -o option, an existing requested
assembly output is replaced; failed compilation leaves no assembly at that path.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--bin-dir", type=Path, default=ROOT / "build" / "llvm" / "bin")
    args = p.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    bin_dir = args.bin_dir.resolve()
    raw = output.with_suffix(".frontend.ll")
    prepared = output.with_suffix(".lc2k.ll")
    evidence = output.with_suffix(".pipeline.json")
    # Prevent -o from overwriting the supplied source or one of our own input
    # sidecars before any subprocess has had a chance to diagnose the mistake.
    paths = (source, output, raw, prepared, evidence)
    if len(set(paths)) != len(paths):
        p.error("source/output names collide with a pipeline evidence file")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": str(source),
        "source_sha256": None,
        "output": str(output),
        "output_sha256": None,
        "status": "failed",
        "stages": [],
    }
    # Explicit -o authorizes replacing these build artifacts.
    for artifact in (output, raw, prepared):
        artifact.unlink(missing_ok=True)
    try:
        manifest["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as e:
        manifest["error"] = str(e)
        evidence.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"cannot read source: {e}", file=sys.stderr)
        return 2

    # Explicit -o authorizes replacing this build artifact. Remove prior
    # artifacts up front, then atomically install only a newly successful result.
    # Keeping stale assembly after a rejected input would be misleading.
    with tempfile.TemporaryDirectory(prefix=".lc2k-c-", dir=output.parent) as temp:
        staged_output = Path(temp) / "output.s"
        commands = [
            ("clang", [str(bin_dir / "clang"),
                       "--target=riscv32-unknown-unknown-elf", "-march=rv32i",
                       "-mabi=ilp32", "-msmall-data-limit=0", "-ffreestanding", "-fno-builtin", "-O1",
                       "-S", "-emit-llvm", str(source), "-o", str(raw)]),
            ("validate", [str(bin_dir / "lc2k-prepare"), "--from-rv32i-c",
                          str(raw), "-o", str(prepared)]),
            ("llc", [str(bin_dir / "llc"), "-march=lc2k",
                     "-verify-machineinstrs", "-O0", str(prepared),
                     "-o", str(staged_output)]),
        ]
        exit_code = 0
        try:
            for name, command in commands:
                print("+ " + " ".join(command), flush=True)
                stage = {"name": name, "argv": command, "exit_code": None,
                         "stdout": "", "stderr": "", "status": "running"}
                manifest["stages"].append(stage)
                try:
                    result = subprocess.run(command, capture_output=True, text=True)
                except OSError as e:
                    stage.update(status="error", stderr=str(e))
                    print(f"cannot run {name}: {e}", file=sys.stderr)
                    exit_code = 2
                    break
                stage.update(exit_code=result.returncode, stdout=result.stdout,
                             stderr=result.stderr,
                             status="passed" if result.returncode == 0 else "failed")
                if result.stdout:
                    print(result.stdout, end="", flush=True)
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr, flush=True)
                if result.returncode:
                    exit_code = result.returncode if result.returncode > 0 else 1
                    break
            if exit_code == 0:
                staged_output.replace(output)
                manifest["status"] = "passed"
                manifest["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        finally:
            for name, command in commands[len(manifest["stages"]):]:
                manifest["stages"].append({"name": name, "argv": command,
                                           "exit_code": None, "stdout": "",
                                           "stderr": "", "status": "not_run"})
            manifest["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            evidence.write_text(json.dumps(manifest, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
