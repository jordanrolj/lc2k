# LLVM LC2K Backend

## Overview

This project adds LC2K as an experimental target in LLVM 20.1.8. It compiles a
small, explicitly validated subset of LLVM IR into LC2K assembly using LLVM's
real SelectionDAG instruction selector, virtual registers, register allocator,
and spill/reload pipeline. The repository also includes a standalone assembler,
simulator, execution wrapper, and end-to-end correctness tests.

LC2K is a compact 32-bit teaching architecture with eight registers and a small
instruction set built around ADD, NOR, loads/stores, branches, JALR, HALT, and
NOOP. The backend focuses on understandable code generation and explicit
failure for operations outside the supported subset.

```text
Restricted C ──► Clang ──► validated LLVM IR ──► LLVM LC2K backend
                                                        │
                                                        ▼
                                              LC2K assembly
                                                        │
                                                        ▼
                                          assembler + simulator
```

The current implementation supports leaf `i32` kernels with up to three
arguments, modular addition, NOR/NOT, constants, EQ/NE branches, PHI nodes,
simple loops, register spills, and aligned constant-index global memory.
Unsupported operations are rejected with diagnostics instead of being silently
lowered incorrectly. The C route is intentionally restricted and is not a
general-purpose C compiler.

Week 1 smoke and full acceptance pass 20 test groups. See
[docs/SUPPORT.md](docs/SUPPORT.md) for the exact boundary,
[docs/STATUS.md](docs/STATUS.md) for current evidence, and
[docs/FILE_GUIDE.md](docs/FILE_GUIDE.md) for a file-by-file explanation.

## Build

Dependencies: Python 3.10+, CMake 3.20+, Ninja, Git, curl, tar, and a C++17-capable
Clang toolchain with platform SDK/system development headers. There are no
third-party Python packages. The initial build needs network access, several
GiB of disk, and time to compile LLVM and Clang. Use a low job count on small
machines. The verified development host and executed results are in STATUS.md;
other environments must run the same checks before being called supported.

```sh
python3 scripts/doctor.py --setup-only
bash scripts/build.sh                 # default two jobs
# Alternatively: LC2K_JOBS=4 bash scripts/build.sh
python3 scripts/doctor.py
python3 scripts/test.py --suite smoke
python3 scripts/test.py --suite full
```

The build downloads an immutable source archive and checks its SHA256 against
[configs/toolchain.json](configs/toolchain.json). It overlays `backend/LC2K`
as an experimental target without patching upstream LLVM registration. It
builds `llc`, `opt`, `clang`, `llvm-config`, and `lc2k-prepare` from that source.
One small hash-checked patch guards llc's original input triple/layout before
its normal DataLayout replacement; the patch is in `backend/patches/`.
An existing source tree must match the pin; it is never reset or replaced.
After setup, `bash scripts/build.sh --no-fetch` builds without network.
`bash scripts/reproduce.sh` performs setup checks, build, doctor, and full tests.
Commands, exit codes, generated assembly, and manifests live under ignored
`build/logs/`. Keep any run evidence you need before removing build artifacts.

## Run one program

```sh
build/llvm/bin/llc -march=lc2k -verify-machineinstrs \
  tests/backend/add.ll -o build/add.as
python3 scripts/run.py build/add.as --args 5 7
```

The runner prepends a handwritten wrapper, loads runtime arguments, initializes
r5, enters through JALR, observes the complete unsigned result in r1, and halts.
The intended result for this source is 12; executed evidence is in STATUS.md.
The recorded demo returns 12 (and 0 for 4294967295 + 1); see
[docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) for the emitted instructions.
Neither a host process exit code nor assembly text alone establishes correctness.

For the restricted C route:

```sh
python3 scripts/compile_c.py tests/frontend/add.c -o build/c-add.as
python3 scripts/run.py build/c-add.as --args 4294967295 1
```

This uses the pinned Clang RV32I freestanding frontend to produce IR, then
`lc2k-prepare` validates the exact frontend envelope, every instruction, type,
attribute, and address through LLVM APIs before explicitly setting the LC2K
triple/layout. Arbitrary host/RISC-V IR is rejected. This adapter is separate
from instruction selection; all generated instructions go through the real
LC2K backend. Temporary frontend/prepared IR and pipeline logs are retained.

## Contract and source map

The initial ABI and memory boundary are specified in
[docs/CONTRACT.md](docs/CONTRACT.md). One `kernel` takes up to three i32 inputs
in r1/r2/r3, returns i32 in r1, and reserves r0, r5, r7. There are five allocatable
registers. r5 is a fixed word-addressed leaf-frame base; LLVM spill objects use
byte offsets, explicitly divided by four in frame-index elimination. No calls
or recursion are admitted. Aligned i32 globals and constant-index addresses
use the same checked byte-offset-to-word-offset rule. Images must fit 32768
words, and leaf frames must fit 4096 words without overlapping the image.

Important files:

- `backend/LC2K/LC2K.td`: registers, instructions, ADD/NOR/NOT selection patterns.
- `LC2KTargetMachine.cpp`: target/subtarget, validation, LLVM codegen pipeline.
- `LC2KISelLowering.cpp`, `LC2KISelDAGToDAG.cpp`: ABI, branches, selection,
  explicit global byte/word conversion.
- `LC2KInstrInfo.cpp`: physical copies, spill/reload, branch and frame hooks.
- `LC2KAsmPrinter.cpp`: allocated machine instructions → ordinary LC2K text.
- `LC2KValidate.cpp`: closed supported-IR boundary and explicit diagnostics.
- `backend/tools/lc2k-prepare.cpp`: LLVM-API frontend validation/retargeting.
- `harness/`: original assembler, checked simulator, wrapper, independent runner.
- `tests/backend/`, `tests/frontend/`, `tests/isa/`: acceptance and negative cases.
- `docs/SOURCES.md`: source provenance and licensing information.

Candidate Week 1 operations are modular i32 ADD, raw NOR/NOT, constants/copies,
EQ/NE branches/PHIs/simple loops, and aligned constant-index i32 globals.
Consult STATUS.md for which acceptance checks have actually passed. Unsupported
operations fail explicitly. General AND/OR, multiply/divide, shifts, dynamic
indexing, arbitrary pointers, byte loads/stores, local allocas, calls, libc,
floating point, vectors, atomics, object output and broad C are outside this
Week 1 implementation. The exact IR/C matrix is in
[docs/SUPPORT.md](docs/SUPPORT.md).

The test suite compares full 32-bit results against independent Python source
expressions. Smoke uses edge patterns plus 100 seeded random tuples per scalar
kernel; full uses 1000. Bounded loop inputs are tested separately. Memory tests
check changed elements and unchanged neighbors; the pressure case must show
actual allocator spill stores/reloads and save MIR. Intentional wrong outputs,
corrupt programs, rejected IR/C and nonterminating execution exercise failures.
Tests establish observed correctness for this subset, not formal compiler proof
or hardware performance.
