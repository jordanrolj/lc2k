"""Two-pass assembler based on EECS370 Project 1, Fall 2026.

No course implementation is reused. Known instruction bit fields and the public
countdown example are tested separately in tests/isa. In addition to ordinary
course syntax, blank/comment lines, opcodes in column zero, hex integer literals,
and unsigned .fill bit patterns through 0xffffffff are accepted conveniences.
The backend should emit signed decimal .fill values for course-tool portability.
"""

from dataclasses import dataclass
import re


class AssemblyError(ValueError):
    """Assembly cannot be encoded without truncation or unresolved symbols."""


@dataclass
class Program:
    words: list[int]
    symbols: dict[str, int]
    source_lines: list[int]
    code_addresses: list[int]
    data_addresses: list[int]


_OPCODES = {"add": 0, "nor": 1, "lw": 2, "sw": 3,
            "beq": 4, "jalr": 5, "halt": 6, "noop": 7}
_ARITY = {"add": 3, "nor": 3, "lw": 3, "sw": 3, "beq": 3,
          "jalr": 2, "halt": 0, "noop": 0, ".fill": 1, "b": 1, "jump": 1}
_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9]{0,5}\Z")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+|0[xX][0-9a-fA-F]+)\Z")


def _integer(token: str) -> int | None:
    if not _NUMBER.fullmatch(token):
        return None
    return int(token, 16 if "x" in token.lower() else 10)


def _register(token: str) -> int:
    # Registers use decimal integers rather than labels or hex conveniences.
    if not re.fullmatch(r"[0-7]", token):
        raise AssemblyError(f"register must be an integer in [0,7], got {token!r}")
    return int(token)


def assemble(source: str) -> Program:
    """Encode source; labels identify word addresses and BEQ uses PC+1.

    One word is produced for every instruction/.fill, with parallel source-line
    and code/data maps for diagnostics and later measurement. Trailing text after
    the required operand count is the LC2K comment field, not an extra operand.
    """
    symbols: dict[str, int] = {}
    statements: list[tuple[int, str, list[str]]] = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        tokens = raw.split()
        if not tokens or tokens[0].startswith(("#", ";")):
            continue
        try:
            # Normal LC2K unlabeled lines start with whitespace; accept a known
            # opcode at column zero too. Labels must accompany an instruction.
            if not raw[0].isspace() and tokens[0] not in _ARITY:
                label = tokens.pop(0)
                if not _LABEL.fullmatch(label):
                    raise AssemblyError(f"invalid label {label!r}; use 1-6 alphanumerics starting with a letter")
                if label in symbols:
                    raise AssemblyError(f"duplicate label {label!r}")
                symbols[label] = len(statements)
            if not tokens:
                raise AssemblyError("label requires an instruction or .fill on the same line")
            opcode = tokens.pop(0)
            if opcode not in _ARITY:
                raise AssemblyError(f"unknown opcode {opcode!r}")
            arity = _ARITY[opcode]
            if len(tokens) < arity:
                raise AssemblyError(f"{opcode} requires {arity} operands")
            statements.append((lineno, opcode, tokens[:arity]))
            if len(statements) > 65536:
                raise AssemblyError("program exceeds 65536-word memory")
        except AssemblyError as error:
            raise AssemblyError(f"line {lineno}: {error}") from error

    words: list[int] = []
    source_lines: list[int] = []
    code_addresses: list[int] = []
    data_addresses: list[int] = []
    for address, (lineno, opcode, args) in enumerate(statements):
        try:
            if opcode == "b":
                opcode, args = "beq", ["0", "0", args[0]]
            elif opcode == "jump":
                opcode, args = "jalr", [args[0], "0"]
            if opcode == ".fill":
                value = _integer(args[0])
                if value is None:
                    if args[0] not in symbols:
                        raise AssemblyError(f"undefined label {args[0]!r}")
                    value = symbols[args[0]]
                if not -(1 << 31) <= value <= (1 << 32) - 1:
                    raise AssemblyError(".fill value does not fit a 32-bit bit pattern")
                words.append(value & 0xFFFFFFFF)
                data_addresses.append(address)
            else:
                word = _OPCODES[opcode] << 22
                if opcode in ("add", "nor", "lw", "sw", "beq", "jalr"):
                    word |= _register(args[0]) << 19
                    word |= _register(args[1]) << 16
                if opcode in ("add", "nor"):
                    word |= _register(args[2])
                elif opcode in ("lw", "sw", "beq"):
                    offset = _integer(args[2])
                    if offset is None:
                        if args[2] not in symbols:
                            raise AssemblyError(f"undefined label {args[2]!r}")
                        offset = symbols[args[2]]
                        if opcode == "beq":
                            offset -= address + 1
                    if not -(1 << 15) <= offset < (1 << 15):
                        raise AssemblyError(f"{opcode} offset {offset} does not fit signed 16 bits")
                    word |= offset & 0xFFFF
                words.append(word)
                code_addresses.append(address)
            source_lines.append(lineno)
        except AssemblyError as error:
            raise AssemblyError(f"line {lineno}: {error}") from error
    return Program(words, symbols, source_lines, code_addresses, data_addresses)
