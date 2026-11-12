#!/usr/bin/env python3
"""Fetch, validate, configure and build the pinned LLVM plus the LC2K overlay.

The first run needs network access; subsequent builds are local. Existing source
trees are never reset or deleted. Each subprocess is recorded with its actual
argument vector, working directory, output log, and exit code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class BuildError(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fetch", action="store_true", help="require existing pinned source")
    parser.add_argument("--configure-only", action="store_true")
    parser.add_argument("--core-only", action="store_true", help="bootstrap LLVM tools before LC2K sources exist; does not validate LC2K")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--source", type=Path, default=ROOT / "_deps/llvm-project")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/llvm")
    args = parser.parse_args()
    lock = json.loads((ROOT / "configs/toolchain.json").read_text())
    pin = lock["llvm"]
    try:
        jobs = args.jobs if args.jobs is not None else int(os.environ.get("LC2K_JOBS", lock["build"]["default_jobs"]))
    except ValueError:
        parser.error("LC2K_JOBS must be an integer")
    if jobs < 1:
        parser.error("--jobs / LC2K_JOBS must be positive")
    source, build = args.source.resolve(), args.build_dir.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    logdir = ROOT / "build/logs" / ("build-" + stamp)
    logdir.mkdir(parents=True)
    print(f"Build evidence: {logdir}", flush=True)
    manifest = logdir / "commands.jsonl"
    sequence = 0

    def run(command: list[str], cwd: Path = ROOT, capture: bool = False) -> str:
        nonlocal sequence
        sequence += 1
        output_path = logdir / f"{sequence:02d}-{Path(command[0]).name}.log"
        print(f"$ {shlex.join(command)}", flush=True)
        output = []
        with output_path.open("w") as logfile:
            process = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
            assert process.stdout is not None
            for line in process.stdout:
                logfile.write(line)
                logfile.flush()
                if capture:
                    output.append(line)
                if not capture:
                    print(line, end="", flush=True)
            code = process.wait()
        with manifest.open("a") as stream:
            stream.write(json.dumps({"command": command, "cwd": str(cwd), "exit_code": code,
                                     "output": str(output_path.relative_to(ROOT))}) + "\n")
        if code:
            raise BuildError(f"command exited {code}; see {output_path}")
        return "".join(output).strip()

    try:
        for executable in ("cmake", "ninja", "git", "clang", "clang++", "curl", "tar"):
            if shutil.which(executable) is None:
                raise BuildError(f"required executable not found: {executable}")
        if not source.exists():
            if args.no_fetch:
                raise BuildError(f"missing source {source}; rerun without --no-fetch for network setup")
            source.parent.mkdir(parents=True, exist_ok=True)
            archive = source.parent / "llvm-project-20.1.8.tar.gz"
            if not archive.exists():
                run(["curl", "--fail", "--location", "--retry", "2", "--output", str(archive), pin["archive_url"]])
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
            if digest != pin["archive_sha256"]:
                raise BuildError(f"archive SHA256 {digest} differs from pin; leaving source uncreated")
            source.mkdir()
            run(["tar", "-xzf", str(archive), "--strip-components=1", "-C", str(source)])
            (source / ".lc2k-source.json").write_text(json.dumps({"commit": pin["commit"], "archive_sha256": digest}, indent=2) + "\n")
        if not (source / "llvm/CMakeLists.txt").is_file():
            raise BuildError(f"{source} is not an LLVM monorepo; refusing to replace it")
        if (source / ".git").exists():
            commit = run(["git", "rev-parse", "HEAD"], source, capture=True)
        else:
            marker = source / ".lc2k-source.json"
            if not marker.is_file():
                raise BuildError(f"archive source needs provenance marker {marker}")
            provenance = json.loads(marker.read_text())
            commit = provenance.get("commit")
            if provenance.get("archive_sha256") != pin["archive_sha256"]:
                raise BuildError("archive provenance SHA256 differs from pinned archive")
        if commit != pin["commit"]:
            raise BuildError(f"LLVM source commit {commit!r} differs from pinned {pin['commit']}")
        run([sys.executable, str(ROOT / "scripts/apply_llvm_patches.py"), str(source)])
        if not args.core_only:
            overlay = ROOT / "backend/LC2K"
            if not (overlay / "CMakeLists.txt").is_file():
                raise BuildError("backend/LC2K/CMakeLists.txt is missing (W1-03 not implemented)")
            destination = source / "llvm/lib/Target/LC2K"
            if destination.is_symlink():
                if destination.resolve() != overlay.resolve():
                    raise BuildError(f"{destination} links elsewhere; refusing to replace it")
            elif destination.exists():
                raise BuildError(f"{destination} already exists; refusing to overwrite target files")
            else:
                destination.symlink_to(overlay, target_is_directory=True)
        configure = [
            "cmake", "-G", "Ninja", "-S", str(source / "llvm"), "-B", str(build),
            "-DCMAKE_BUILD_TYPE=Release", "-DLLVM_ENABLE_ASSERTIONS=ON",
            "-DLLVM_ENABLE_PROJECTS=clang", "-DLLVM_TARGETS_TO_BUILD=",
            "-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=" + ("" if args.core_only else "LC2K"), "-DLLVM_INCLUDE_TESTS=OFF",
            "-DLLVM_INCLUDE_EXAMPLES=OFF", "-DLLVM_INCLUDE_BENCHMARKS=OFF",
            "-DLLVM_ENABLE_BINDINGS=OFF", "-DLLVM_ENABLE_ZSTD=OFF", "-DLLVM_ENABLE_ZLIB=OFF",
            "-DLLVM_ENABLE_LIBXML2=OFF", "-DLLVM_ENABLE_LIBEDIT=OFF",
            "-DLLVM_PARALLEL_LINK_JOBS=1", "-DPython3_EXECUTABLE=" + sys.executable,
            "-DLLVM_FORCE_VC_REVISION=" + pin["commit"],
            "-DLLVM_FORCE_VC_REPOSITORY=" + pin["repository"],
        ]
        run(configure)
        if not args.configure_only:
            # Make the pinned generator available early for target bring-up.
            run(["cmake", "--build", str(build), "--parallel", str(jobs), "--target", "llvm-tblgen"])
            if not args.core_only:
                run(["cmake", "--build", str(build), "--parallel", str(jobs), "--target", "LC2KCommonTableGen"])
            first_tools = ["llc", "llvm-config"]
            if not args.core_only:
                first_tools.append("lc2k-prepare")
            run(["cmake", "--build", str(build), "--parallel", str(jobs), "--target", *first_tools])
            version = run([str(build / "bin/llc"), "--version"], capture=True)
            print(version, flush=True)
            if pin["version"] not in version or (not args.core_only and "lc2k" not in version.lower()):
                raise BuildError("built llc does not report pinned LLVM and LC2K registration")
            print("Backend tools built; now compiling opt and clang.", flush=True)
            run(["cmake", "--build", str(build), "--parallel", str(jobs), "--target", "opt", "clang"])
        print(("CORE BUILD PASSED (LC2K not configured)" if args.core_only else "BUILD PASSED") if not args.configure_only else "CONFIGURE PASSED", flush=True)
        return 0
    except (BuildError, OSError, ValueError) as error:
        (logdir / "failure.txt").write_text(str(error) + "\n")
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
