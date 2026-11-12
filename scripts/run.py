#!/usr/bin/env python3
"""Run LC2K backend assembly in the documented startup wrapper."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.backend import execute

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("assembly", type=Path)
    p.add_argument("--args", nargs="*", type=lambda s: int(s, 0), default=[])
    p.add_argument("--max-steps", type=int, default=100000)
    args = p.parse_args()
    try:
        for value in args.args:
            if not -(1 << 31) <= value < (1 << 32):
                raise ValueError("arguments must be 32-bit bit patterns")
        result, program = execute(args.assembly.read_text(), args.args, max_steps=args.max_steps)
        print(json.dumps({"status": result.status, "result_u32": result.registers[1],
            "registers": result.registers, "dynamic_instructions": result.steps,
            "loads": result.loads, "stores": result.stores,
            "static_instructions": len(program.code_addresses),
            "data_words": len(program.data_addresses)}))
        return 0
    except (OSError, ValueError, AssertionError) as e:
        print(json.dumps({"status":"error", "error":str(e)}))
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
