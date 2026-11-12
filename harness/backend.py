"""Compile real LLVM fixtures and enter a checked fixed-base leaf wrapper."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import subprocess
from . import assemble, run

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "build/llvm/bin"
TRIPLE = 'target triple = "lc2k-unknown-none"\n'
LAYOUT = 'target datalayout = "e-p:32:32-i32:32-n32-S32"\n'


def compile_ir(source: Path, output: Path, *, extra=()) -> str:
    command = [str(TOOLS / "llc"), "-march=lc2k", "-verify-machineinstrs",
               *extra, str(source), "-o", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    output.with_name(output.name + ".compile.json").write_text(json.dumps({
        "command": command, "exit_code": result.returncode,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest() if not result.returncode else None,
        "stdout": result.stdout, "stderr": result.stderr}, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(f"LLVM compilation failed ({result.returncode}): {result.stderr}")
    return output.read_text()


def execute(assembly: str, args=(), *, max_steps=100000, global_words=None):
    if len(args) > 3:
        raise ValueError("leaf ABI admits at most three arguments")
    arguments = list(args) + [0] * (3 - len(args))
    signed = lambda x: (x & 0xffffffff) - (0x100000000 if x & 0x80000000 else 0)
    wrapper = """        lw 0 1 in1
        lw 0 2 in2
        lw 0 3 in3
        lw 0 5 stack
        lw 0 4 entry
        jalr 4 7
        halt
entry   .fill kentry
stack   .fill 61440
"""
    wrapper += "".join(f"in{i+1} .fill {signed(v)}\n" for i, v in enumerate(arguments))
    program = assemble(wrapper + assembly)
    # Code/globals/literals fit signed16 absolute loads and cannot overlap the
    # fixed 4096-word stack [57344,61439]. All image addresses remain <32768.
    if len(program.words) > 32768:
        raise ValueError("LC2K image exceeds 32768-word absolute address envelope")
    for pc in program.code_addresses:
        if pc < program.symbols["kentry"]:
            continue
        word = program.words[pc]
        opcode = word >> 22 & 7
        destination = (word & 7) if opcode in (0,1) else ((word >> 16 & 7) if opcode in (2,5) else None)
        if destination in (0,5,7):
            raise AssertionError(f"kernel writes reserved register r{destination} at word {pc}")
    memory = {}
    for symbol, value in (global_words or {}).items():
        if not symbol.startswith("g") or symbol not in program.symbols or program.symbols[symbol] not in program.data_addresses:
            raise ValueError(f"not an emitted global word: {symbol}")
        memory[program.symbols[symbol]] = value
    result = run(program.words, max_steps=max_steps, initial_memory=memory)
    if not result.halted:
        raise AssertionError(f"execution {result.status}: {result.error}")
    if result.registers[0] != 0 or result.registers[5] != 61440 or result.registers[7] != 6:
        raise AssertionError("kernel violated reserved-register/leaf ABI contract")
    if result.pc != 7:
        raise AssertionError("kernel did not return to the wrapper HALT")
    return result, program


def check_result(actual: int, expected: int):
    if actual != expected & 0xffffffff:
        raise AssertionError(f"result 0x{actual:08x}, expected 0x{expected & 0xffffffff:08x}")
