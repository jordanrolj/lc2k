#!/usr/bin/env python3
"""Apply the exact pinned llc input-contract change, without fuzz or overwrite."""
import hashlib
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv) != 2:
        print("usage: apply_llvm_patches.py <llvm-project-source>", file=sys.stderr)
        return 2
    patches = Path(__file__).resolve().parents[1] / "backend/patches"
    lock = json.loads((patches / "manifest.json").read_text())
    if lock["path"] != "llvm/tools/llc/llc.cpp":
        raise ValueError("unexpected patch destination")
    destination = Path(sys.argv[1]) / lock["path"]
    original = destination.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest == lock["patched_sha256"]:
        print(f"PASS exact llc patch already applied: {digest}")
        return 0
    if digest != lock["original_sha256"]:
        print(f"refusing modified LLVM source {destination}: {digest}", file=sys.stderr)
        return 1
    anchor = lock["anchor"].encode()
    insertion = (patches / "llc-input-contract.inc").read_bytes() + b"\n"
    if original.count(anchor) != 1:
        raise ValueError("patch anchor must be unique")
    patched = original.replace(anchor, insertion + anchor)
    if hashlib.sha256(patched).hexdigest() != lock["patched_sha256"]:
        raise ValueError("patch data differs from its pinned manifest")
    destination.write_bytes(patched)
    print(f"PASS applied exact llc input-contract patch: {lock['patched_sha256']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
