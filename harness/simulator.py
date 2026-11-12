"""Checked instruction interpreter for the pinned LC2K ISA.

Registers and memory expose unsigned 32-bit bit patterns. ADD wraps at 32 bits.
Address calculation interprets the register as signed two's complement, adds
the signed offset mathematically, and checks 0..65535 without wrapping. HALT is
included in dynamic instruction count; the reported PC is already incremented.
R0 is fixed zero, as specified by the Fall 2026 course specification. There is
no assumption that code/data/stack are protected by the architectural machine.
"""

from dataclasses import dataclass
from collections.abc import Mapping, Sequence


class SimulationError(ValueError):
    """Malformed invocation (runtime machine faults instead return Result)."""


@dataclass
class Result:
    registers: list[int]
    memory: list[int]
    pc: int
    steps: int
    loads: int
    stores: int
    halted: bool
    status: str
    error: str | None = None


def _signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x100000000


def _word(value: int) -> int:
    if not isinstance(value, int) or not -(1 << 31) <= value < (1 << 32):
        raise SimulationError(f"not a 32-bit word: {value!r}")
    return value & 0xFFFFFFFF


def run(words: Sequence[int], *, max_steps: int = 100000,
        initial_registers: Sequence[int] | Mapping[int, int] | None = None,
        initial_memory: Mapping[int, int] | None = None) -> Result:
    """Run an image from PC=0, returning status ``halted``, ``timeout``, or ``error``.

    The default state is eight zero registers and 65536 zero words. Optional
    initial memory patches apply after loading the image; callers must use only
    defined addresses. The result includes the full final memory for exact
    observation. No output/result oracle is implemented in this interpreter.
    """
    if not isinstance(max_steps, int) or max_steps < 0:
        raise SimulationError("max_steps must be a nonnegative integer")
    if len(words) > 65536:
        raise SimulationError("program exceeds 65536-word memory")
    memory = [0] * 65536
    memory[:len(words)] = [_word(value) for value in words]
    registers = [0] * 8
    if initial_registers is not None:
        if isinstance(initial_registers, Mapping):
            items = initial_registers.items()
        else:
            if len(initial_registers) != 8:
                raise SimulationError("initial_registers must contain exactly eight words")
            items = enumerate(initial_registers)
        for register, value in items:
            if not isinstance(register, int) or not 0 <= register <= 7:
                raise SimulationError("invalid initial register number")
            registers[register] = _word(value)
    if registers[0] != 0:
        raise SimulationError("r0 must initially be zero")
    for address, value in (initial_memory or {}).items():
        if not isinstance(address, int) or not 0 <= address < 65536:
            raise SimulationError("initial memory address outside [0,65535]")
        memory[address] = _word(value)
    pc = steps = loads = stores = 0

    def result(status: str, error: str | None = None) -> Result:
        return Result(registers, memory, pc, steps, loads, stores,
                      status == "halted", status, error)

    while steps < max_steps:
        if not 0 <= pc < 65536:
            return result("error", f"PC {pc} outside [0,65535]")
        instruction = memory[pc]
        opcode = (instruction >> 22) & 7
        a, b = (instruction >> 19) & 7, (instruction >> 16) & 7
        if (instruction >> 25 or
            opcode in (0, 1) and instruction & 0xFFF8 or
            opcode == 5 and instruction & 0xFFFF or
            opcode in (6, 7) and instruction & 0x3FFFFF):
            return result("error", f"invalid instruction encoding 0x{instruction:08x} at PC {pc}")
        offset = instruction & 0xFFFF
        if offset >= 0x8000:
            offset -= 0x10000
        next_pc = pc + 1
        if opcode == 0:
            destination = instruction & 7
            if destination:
                registers[destination] = (registers[a] + registers[b]) & 0xFFFFFFFF
        elif opcode == 1:
            destination = instruction & 7
            if destination:
                registers[destination] = (~(registers[a] | registers[b])) & 0xFFFFFFFF
        elif opcode in (2, 3):
            address = _signed32(registers[a]) + offset
            if not 0 <= address < 65536:
                return result("error", f"memory address {address} outside [0,65535] at PC {pc}")
            if opcode == 2:
                if b:
                    registers[b] = memory[address]
                loads += 1
            else:
                memory[address] = registers[b]
                stores += 1
        elif opcode == 4:
            if registers[a] == registers[b]:
                next_pc += offset
        elif opcode == 5:
            if b:
                registers[b] = next_pc
            # This ordering is observable when a==b. R0 writes are ignored.
            next_pc = _signed32(registers[a])
        pc = next_pc
        steps += 1
        if opcode == 6:
            return result("halted")
    return result("timeout", f"instruction limit {max_steps} reached")
