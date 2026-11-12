# LC2K assembler and simulator

These are small original Python implementations of the [EECS370 Project 1
Fall 2026 specification](https://eecs370.github.io/project_1_spec/), consulted
2026-11-10. No course solution or starter implementation is copied. The public
countdown input and machine words are reproduced as an authoritative fixture in
`tests/isa/test_tools.py`; other cases have hand-calculated results. This
interpreter is a tested reference implementation, not a formal correctness proof.

Run from the project root with Python 3.10 or newer; there are no pip dependencies.

```sh
python3 -m harness assemble program.as program.mc --map program.map.json
python3 -m harness run program.mc --max-steps 100000 --observe 20 21
python3 -m harness exec program.as --max-steps 100000
python3 -m unittest discover -s tests/isa -v
```

Machine-code files contain one hexadecimal `0xXXXXXXXX` word per line. Execution
prints JSON with `status`, `halted`, `registers`, `result` (r1), `pc`, `steps`,
`loads`, `stores`, `error`, and explicitly requested `memory` words. A successful
halt exits 0; timeout, invalid encoding, out-of-range address, or assembly error
exits 1. HALT is included in the instruction count and advances the PC. The API
exposes all 65536 memory words rather than only CLI observations.

```python
from harness import assemble, run

program = assemble("        add 1 2 1\n        halt\n")
result = run(program.words, initial_registers={1: 5, 2: 7})
assert result.halted and result.registers[1] == 12
```

`assemble` raises `AssemblyError` on malformed input and returns `Program` with
`words`, `symbols`, `source_lines` (one-based source lines parallel to words),
`code_addresses`, and `data_addresses`. Labels have 1–6 ASCII letters/digits and
start with a letter; labels share a line with their word. Offset overflow and
undefined or duplicate labels fail explicitly. Trailing text after the required
operand count is the LC2K comment field. The `b` and `jump` pseudos follow the
selected course specification.

The assembler accepts these documented conveniences: blank and `#`/`;` comment
lines; known opcodes starting in column zero; hexadecimal integer literals; and
unsigned `.fill` bit patterns through 4294967295 in addition to signed32 values.
For portable compiler output, use signed decimal `.fill` values as in the course
specification. Instructions/data may be interleaved, though generated compiler
assembly should place data after instructions.

`run` starts at PC 0, with zeroed registers and memory. Optional
`initial_registers` accepts eight words or a register-number mapping;
`initial_memory` is an address-to-word mapping applied after the program image.
Invalid invocation parameters raise `SimulationError`; machine faults return
`Result(status="error", halted=False, error=...)`; exhausting `max_steps` returns
`status="timeout"`. Register and memory values are exposed as unsigned 32-bit
patterns. ADD wraps modulo 2^32. Effective addresses use the signed register
value plus the signed16 offset and require 0–65535 without wrapping. JALR writes
the link before reading its target, including the same-register case. R0 always
reads zero and ignores writes, following the selected Fall 2026 specification.
There is no architectural protection between code, data, and stack; the compiler
and its runner are responsible for arranging disjoint regions.
