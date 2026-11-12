"""Command-line assembly and structured execution.

python -m harness assemble input.as output.mc [--map output.json]
python -m harness run input.mc [--max-steps N] [--observe ADDRESS ...]
python -m harness exec input.as [--max-steps N] [--observe ADDRESS ...]

Machine-code files use one 0xXXXXXXXX word per line (Fall 2026 course format).
Run/exec print a JSON result and return nonzero for timeout or machine fault.
Only explicitly observed memory is serialized; Python callers get full memory.
"""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from . import AssemblyError, SimulationError, assemble, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assembler = commands.add_parser("assemble")
    assembler.add_argument("source", type=Path)
    assembler.add_argument("output", type=Path)
    assembler.add_argument("--map", type=Path)
    for name in ("run", "exec"):
        runner = commands.add_parser(name)
        runner.add_argument("source", type=Path)
        runner.add_argument("--max-steps", type=int, default=100000)
        runner.add_argument("--observe", nargs="*", type=int, default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "assemble":
            program = assemble(args.source.read_text())
            args.output.write_text("".join(f"0x{word:08X}\n" for word in program.words))
            if args.map:
                args.map.write_text(json.dumps(asdict(program), indent=2) + "\n")
            return 0
        if args.command == "exec":
            words = assemble(args.source.read_text()).words
        else:
            words = [int(line.strip(), 0) for line in args.source.read_text().splitlines() if line.strip()]
        outcome = run(words, max_steps=args.max_steps)
        if any(not 0 <= address < 65536 for address in args.observe):
            raise SimulationError("observed address outside [0,65535]")
        output = {key: value for key, value in vars(outcome).items() if key != "memory"}
        output["memory"] = {str(address): outcome.memory[address] for address in args.observe}
        output["result"] = outcome.registers[1]
        print(json.dumps(output, sort_keys=True))
        return 0 if outcome.halted else 1
    except (AssemblyError, SimulationError, OSError, ValueError) as error:
        print(f"lc2k: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
