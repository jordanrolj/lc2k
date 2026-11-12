# LC2K file guide

This guide explains every maintained file in this repository. Start with the
pipeline below, then use the linked filenames to read the implementation.
Generated build files and the downloaded LLVM tree are explained as groups at
the end; they are not additional project source files to maintain.

The exact supported language is defined in [SUPPORT.md](SUPPORT.md), the ABI in
[CONTRACT.md](CONTRACT.md), and the current verification state in
[STATUS.md](STATUS.md).

## How the pieces fit together

```text
Restricted C                         Handwritten LC2K LLVM IR
     |                                          |
compile_c.py → pinned Clang                      |
     |                                          |
lc2k-prepare: validate and explicitly retarget    |
     +---------------------+--------------------+
                           |
                      llc -march=lc2k
                           |
                Validate → Lower → Select instructions
                           |
                 LLVM register allocation
                           |
                  LC2K assembly printer
                           |
                      assembly (.as)
                           |
             execution wrapper → Python assembler
                           |
                    Python simulator
                           |
              result, state, instruction counts
```

The `.td` files describe the target at **build time**. LLVM's TableGen tool
turns those descriptions into C++ includes used by the backend. They are not
read by the simulator.

Useful vocabulary:

| Term | Meaning here |
|---|---|
| LLVM IR | Typed operations such as `add i32`, before LC2K instruction selection. |
| SelectionDAG | LLVM's graph representation used while lowering and selecting instructions. |
| Lowering | Converting an operation into a form the target can implement. |
| Virtual register | A temporary value before LLVM assigns a physical register. |
| Register allocation | Assigning values to real registers and spilling some to memory if necessary. |
| Spill / reload | Saving a register value to a stack slot / reading it back. |
| ABI | Rules for arguments, return values, reserved registers, and stack memory. |
| Pseudo-instruction | A compiler instruction expanded into actual LC2K instructions before output. |
| MC | LLVM's machine-code metadata layer; this project still uses its Python assembler for encoding. |
| CMake target | A build artifact such as a library; distinct from the LC2K processor target. |

## Backend: build and registration

### [backend/LC2K/CMakeLists.txt](../backend/LC2K/CMakeLists.txt)

This is the backend's main build recipe. It asks TableGen to generate register,
instruction, subtarget, and instruction-selection definitions from `LC2K.td`.
It builds the C++ implementation into `LLVMLC2KCodeGen` and includes the
`TargetInfo` and `MCTargetDesc` subdirectories. It also connects the preparation
tool's build. The source path handling supports the backend being linked into
the downloaded LLVM tree.

Read this file to see **which implementation files are compiled together**.
Adding a new C++ implementation file normally requires adding it here.
CMake does not define the behavior of an ADD instruction.

### [backend/LC2K/TargetInfo/CMakeLists.txt](../backend/LC2K/TargetInfo/CMakeLists.txt)

Builds the small `LLVMLC2KInfo` library from `LC2KTargetInfo.cpp` and declares its
LLVM dependencies. `ADD_TO_COMPONENT LC2K` associates the library with the
LC2K build component. This separate library lets LLVM discover the target
without putting all instruction-selection code into the registration layer.

### [backend/LC2K/TargetInfo/LC2KTargetInfo.cpp](../backend/LC2K/TargetInfo/LC2KTargetInfo.cpp)

Defines `getTheLC2KTarget()`, which provides a shared target object, and
`LLVMInitializeLC2KTargetInfo()`, which registers the name `lc2k` and its
description with LLVM. This is part of how `llc` knows LC2K exists.

Registration uses `Triple::UnknownArch`; the project does not add a new enum to
upstream LLVM's architecture parser. The documented invocation uses
`-march=lc2k`, together with the explicitly validated LC2K input contract.
This file registers the target; it does not translate instructions.

### [backend/LC2K/MCTargetDesc/CMakeLists.txt](../backend/LC2K/MCTargetDesc/CMakeLists.txt)

Builds `LLVMLC2KDesc`, the library supplying machine metadata, with its LLVM
and target-info dependencies.

### [backend/LC2K/MCTargetDesc/LC2KMCTargetDesc.cpp](../backend/LC2K/MCTargetDesc/LC2KMCTargetDesc.cpp)

Registers factories for LLVM's instruction, register, subtarget, and assembly
metadata through `LLVMInitializeLC2KTargetMC()`. It consumes TableGen-generated
metadata and sets assembly properties such as the comment syntax.

This is not an object-file writer or the LC2K assembler. Actual instruction
encoding is implemented in `harness/assembler.py`.

## Backend: definitions and compilation

### [backend/LC2K/LC2K.h](../backend/LC2K/LC2K.h)

The shared declarations for the backend: register information, instruction
information, frame lowering, target lowering, subtarget, target machine, and
pass factories. It also declares custom DAG node kinds such as return,
conditional branch, and address nodes.

A declaration describes the interface; the corresponding `.cpp` provides the
behavior. Several classes deliberately share an implementation file:

| Declaration | Implementation |
|---|---|
| Register, instruction, and frame information | `LC2KInstrInfo.cpp` |
| Target lowering | `LC2KISelLowering.cpp` |
| Subtarget and target machine | `LC2KTargetMachine.cpp` |
| Instruction-selector factory | `LC2KISelDAGToDAG.cpp` |
| Assembly-printer factory | `LC2KAsmPrinter.cpp` |

The `GET_*` macros select portions of TableGen-generated include files.

### [backend/LC2K/LC2K.td](../backend/LC2K/LC2K.td)

The declarative target description used by TableGen. It defines the eight
registers, the general-purpose register class, instruction operands, and
selection patterns. For example, the ADD pattern connects an LLVM DAG addition
to an LC2K ADD with two inputs and one result.

All eight registers can appear in the register descriptions; C++ register-info
code separately reserves registers that allocation must not use.

Some instructions in this file are compiler conveniences:

| Compiler instruction | Final output idea |
|---|---|
| `LDC` | Load a constant from a literal pool. |
| `LDG` / `STG` | Load/store using a global label. |
| `LD` / `ST` | Load/store using a register and an offset. |
| `BNE` | Implement inequality using a sequence of BEQ instructions. |
| `JMP` | Use an always-taken `beq 0 0 ...`. |
| `RET` | Return with `jalr 7 4`. |

Thus, seeing `BNE` or `LDC` here does not mean the hardware has those opcodes.
The handwritten assembly printer implements their output. The assembly strings
in this description do not replace that printer, and binary encoding lives in
the Python assembler.

### [backend/LC2K/LC2KTargetMachine.cpp](../backend/LC2K/LC2KTargetMachine.cpp)

Connects the target to LLVM's compilation pipeline. It constructs the subtarget
and data layout, installs validation before the normal IR pipeline, adds the
LC2K instruction selector, and supplies the assembly printer. It registers the
target-machine implementation with LLVM.

The supported output is assembly; object emission is explicitly rejected. An
LLVM object-lowering helper in this file does not imply object-file support.

### [backend/LC2K/LC2KValidate.h](../backend/LC2K/LC2KValidate.h)

Declares the shared module validator and the target's triple/data-layout
constants. Both the C adapter and backend use this interface so they agree on
the accepted input contract.

### [backend/LC2K/LC2KValidate.cpp](../backend/LC2K/LC2KValidate.cpp)

Examines LLVM objects to reject unsupported programs before code generation.
Checks include function shape, types, instructions, attributes, metadata,
global initializers, and permitted memory accesses. The admitted kernel has
an `i32` return and at most three `i32` arguments.

Constant-index accesses to supported globals are checked; arbitrary pointer
arguments and dynamic addressing are outside the contract. Offset validation
checks alignment and bounds. The selector later performs the actual conversion
from LLVM byte offsets to LC2K word offsets.

`llvm::Twine`, used in diagnostics, is LLVM's temporary string-concatenation
helper. It helps build error messages; it is not part of LC2K execution.

### [backend/LC2K/LC2KISelLowering.cpp](../backend/LC2K/LC2KISelLowering.cpp)

Defines how supported DAG operations and the calling convention are lowered.
Arguments enter through `r1`, `r2`, and `r3`; the result returns in `r1`.
Custom nodes represent returns, conditional branches, and global addresses.

This stage establishes how values and operations enter the target pipeline.
It does not assign every temporary to a physical register; LLVM's allocator
performs that job later.

### [backend/LC2K/LC2KISelDAGToDAG.cpp](../backend/LC2K/LC2KISelDAGToDAG.cpp)

Selects LC2K machine instructions from the lowered DAG. Simple patterns use the
TableGen-generated selector. Handwritten cases handle constants, branches,
returns, and supported memory addresses.

Zero can use the reserved zero register; other constants use a constant-load
instruction. Address selection explicitly converts byte offsets to word
offsets: an aligned offset of 8 bytes becomes 2 LC2K words. Memory dependencies
must be preserved while choosing the instructions.

### [backend/LC2K/LC2KInstrInfo.cpp](../backend/LC2K/LC2KInstrInfo.cpp)

Implements instruction, register, and frame support used by LLVM's existing
allocator. It reserves `r0`, `r5`, and `r7`, supplies register copies and
spill/reload operations, resolves stack-frame references, and provides branch
analysis/editing hooks.

A register copy uses ADD with zero. Stack slots are described in bytes inside
LLVM and converted to word offsets for LC2K loads/stores. The wrapper establishes
the stack base in `r5`; the supported fixed frame follows the documented ABI.
This file supports allocation rather than implementing a new allocator.

### [backend/LC2K/LC2KAsmPrinter.cpp](../backend/LC2K/LC2KAsmPrinter.cpp)

Writes course-format LC2K assembly from the allocated machine instructions.
It emits function/block labels, actual instructions, global data, and constant
pools. It expands the output forms described above and rejects unexpected
unresolved instructions.

For an addition whose physical operands are `r1` and `r2` with result in `r1`,
the output is `add 1 2 1`. By this stage, IR validation, selection, and register
allocation have already happened. The printer neither executes the program
nor turns its textual instructions into binary words.

## Input preparation and the pinned LLVM patch

| File | Purpose |
|---|---|
| [backend/tools/CMakeLists.txt](../backend/tools/CMakeLists.txt) | Builds `lc2k-prepare` with LLVM parsing/support libraries and the shared validator. |
| [backend/tools/lc2k-prepare.cpp](../backend/tools/lc2k-prepare.cpp) | Reads and verifies IR. Its C-adapter mode validates the permitted RV32I frontend envelope, removes checked foreign attributes/flags, explicitly sets the LC2K triple/layout, validates again, and writes IR. It does not select instructions. |
| [backend/patches/llc-input-contract.patch](../backend/patches/llc-input-contract.patch) | Human-readable upstream change protecting the original input contract before `llc` can replace its data layout. |
| [backend/patches/llc-input-contract.inc](../backend/patches/llc-input-contract.inc) | Insertion fragment used to apply that guard; this is maintained source, not a generated TableGen include. |
| [backend/patches/manifest.json](../backend/patches/manifest.json) | Expected file hashes and insertion information so the patcher rejects an unknown source version. |

The guard matters because silently changing an arbitrary host module's layout
would not establish that the program obeys the LC2K memory contract.

## Build, run, and test commands

| File | Purpose |
|---|---|
| [configs/toolchain.json](../configs/toolchain.json) | Pins LLVM's version, source revision/archive hash, and build settings. |
| [scripts/build.sh](../scripts/build.sh) | Shell entry point that locates the repository and invokes the Python build driver. |
| [scripts/build_llvm.py](../scripts/build_llvm.py) | Obtains and verifies pinned sources, applies the patch, overlays LC2K, configures/builds LLVM, and records logs. `--no-fetch` reuses existing sources. |
| [scripts/apply_llvm_patches.py](../scripts/apply_llvm_patches.py) | Applies the declared change only to a recognized source state; recognizes the already-patched state too. |
| [scripts/doctor.py](../scripts/doctor.py) | Checks setup, tools, and environment. A healthy setup is not itself a compiler correctness test. |
| [scripts/compile_c.py](../scripts/compile_c.py) | Runs pinned Clang, preparation, and LC2K compilation. Saves frontend IR, LC2K IR, assembly, and pipeline evidence; removes stale assembly on failure. |
| [scripts/run.py](../scripts/run.py) | Wraps a compiled kernel, assembles it, and simulates it with runtime arguments. Reports result and execution information as JSON. |
| [scripts/test.py](../scripts/test.py) | Drives ISA, wrapper, frontend, backend, smoke, and full checks using independent expectations. Saves manifests and command evidence; missing tools are failures. |
| [scripts/reproduce.sh](../scripts/reproduce.sh) | Runs the reproduction sequence, including building/checking tools and the full suite, stopping on failure. |
| [.github/workflows/tests.yml](../.github/workflows/tests.yml) | CI jobs for project checks and LLVM integration, including caches and uploaded evidence. The file's existence does not prove hosted CI has run. |
| [.gitignore](../.gitignore) | Keeps downloaded dependencies, builds, logs, and caches out of version control. |

## Assembler, simulator, and execution harness

| File | Purpose |
|---|---|
| [harness/assembler.py](../harness/assembler.py) | Two-pass assembler: resolves labels, validates operands, and encodes assembly into 32-bit words. Retains source/code/data information for checks. |
| [harness/simulator.py](../harness/simulator.py) | Executes LC2K words with eight registers, bounded memory, 32-bit arithmetic, instruction semantics, and a step limit. Returns machine state and counts. |
| [harness/backend.py](../harness/backend.py) | Invokes real LLVM compilation and builds the execution wrapper. Sets arguments/stack/return state, checks execution invariants, and compares results with independent expected values. |
| [harness/__init__.py](../harness/__init__.py) | Exposes the package's public Python interfaces. |
| [harness/__main__.py](../harness/__main__.py) | Implements `python -m harness` commands for standalone assembly and simulation. Unlike the kernel runner, standalone execution does not automatically provide the kernel calling wrapper. |
| [harness/README.md](../harness/README.md) | Documents the harness API, assembly format, semantics, and provenance. |

A compiled kernel returns using `jalr`; the wrapper calls it and halts after
it returns. The simulator is tested independently, but no single simulator run
is a proof that the entire compiler is correct.

## Test files

### LLVM IR fixtures

These exercise the backend directly, without the C frontend.

| File | What it exercises |
|---|---|
| [tests/backend/identity.ll](../tests/backend/identity.ll) | Returning an argument and the calling convention. |
| [tests/backend/add.ll](../tests/backend/add.ll) | Addition, including modular overflow through test inputs. |
| [tests/backend/nor.ll](../tests/backend/nor.ll) | Bitwise NOR selection. |
| [tests/backend/branch.ll](../tests/backend/branch.ll) | Equality branches, constants, and PHI merging. |
| [tests/backend/branch-ne.ll](../tests/backend/branch-ne.ll) | Inequality branches and distinct results for the two paths. |
| [tests/backend/loop.ll](../tests/backend/loop.ll) | Loop control and loop-carried values. |
| [tests/backend/memory.ll](../tests/backend/memory.ll) | Supported global loads/stores and constant indexing. |
| [tests/backend/pressure.ll](../tests/backend/pressure.ll) | Enough simultaneously needed values to force spills/reloads; the runner checks varied inputs and frame behavior. |

### C fixtures and input validation

| File | What it exercises |
|---|---|
| [tests/frontend/identity.c](../tests/frontend/identity.c) | A C argument-to-result path through Clang and the adapter. |
| [tests/frontend/add.c](../tests/frontend/add.c) | C addition through the entire pipeline. |
| [tests/frontend/not.c](../tests/frontend/not.c) | Bitwise complement. |
| [tests/frontend/nor.c](../tests/frontend/nor.c) | C bitwise expression lowered to NOR. |
| [tests/frontend/globals.c](../tests/frontend/globals.c) | Fixed-index global array reads/writes and neighboring elements. |
| [tests/frontend/reject_byte.c](../tests/frontend/reject_byte.c) | Rejecting unsupported byte-oriented behavior. |
| [tests/frontend/reject_multiply.c](../tests/frontend/reject_multiply.c) | Rejecting unsupported multiplication. |
| [tests/frontend/reject_pointer.c](../tests/frontend/reject_pointer.c) | Rejecting an unsupported pointer interface. |
| [tests/frontend/test_validation.py](../tests/frontend/test_validation.py) | Positive/negative validation cases, C rejection reasons, and failure-output handling. |
| [tests/frontend/__init__.py](../tests/frontend/__init__.py) | Marks the frontend test directory as a Python package. |

### Independent tools and wrapper checks

| File | What it exercises |
|---|---|
| [tests/isa/test_tools.py](../tests/isa/test_tools.py) | Known encodings and instruction behavior, invalid inputs, and deliberate wrong behavior that the checks must detect. |
| [tests/isa/__init__.py](../tests/isa/__init__.py) | Marks the ISA test directory as a Python package. |
| [tests/runner/test_wrapper.py](../tests/runner/test_wrapper.py) | Valid kernel return and rejection of early halt, reserved-register corruption, limits, and wrong results. |

The test driver also creates temporary cases under `build/logs/`; not every
negative test or constant test has its own tracked fixture.

## Saved Week 1 evidence

These are snapshots for review, not inputs that implement the compiler.

| File | Contents |
|---|---|
| [results/week1/add.as](../results/week1/add.as) | Saved assembly from the IR addition example. |
| [results/week1/c-add.as](../results/week1/c-add.as) | Saved assembly from the C addition example. |
| [results/week1/demo.json](../results/week1/demo.json) | Recorded IR demonstration commands/results. |
| [results/week1/c-demo.json](../results/week1/c-demo.json) | Recorded C pipeline and execution demonstration. |
| [results/week1/evidence.json](../results/week1/evidence.json) | Summary of checks, source provenance, corrected failures, spill evidence, and outstanding review/reproduction work. |

Rerun the relevant tests after changing code; saved successful results do not
establish that a later version works.

## Project documentation

| File | Why to read it |
|---|---|
| [README.md](../README.md) | Main entry point for setup, compilation, testing, and project scope. |
| [docs/STATUS.md](STATUS.md) | Current results, limitations, pending review, and next action. |
| [docs/CONTRACT.md](CONTRACT.md) | ISA/ABI/data-layout assumptions that implementation and tests must preserve. |
| [docs/SUPPORT.md](SUPPORT.md) | Exact supported input subset and exclusions. |
| [docs/SOURCES.md](SOURCES.md) | Reused/reference source provenance and licensing information. |
| [docs/WALKTHROUGH.md](WALKTHROUGH.md) | Practical walkthrough for building, running, and inspecting examples. |
| [docs/FILE_GUIDE.md](FILE_GUIDE.md) | This file-by-file explanation. |

## Downloaded and generated files

| Location | Meaning |
|---|---|
| `_deps/llvm-project/` | Pinned upstream LLVM/Clang source, with the declared input guard applied. Its thousands of files are upstream dependencies. |
| `_deps/llvm-project/llvm/lib/Target/LC2K` | Link to this project's backend. Edit the maintained `backend/LC2K/` sources. |
| `_deps/llvm-project-20.1.8.tar.gz` | Downloaded source archive checked against the pinned hash. |
| `_deps/llvm-project/.lc2k-source.json` | Source provenance recorded by the build driver. |
| `_deps/reference/` | Local reference material used during development, outside tracked project sources. |
| `build/llvm/bin/` | Built tools such as `clang`, `llc`, `opt`, `llvm-config`, and `lc2k-prepare`. |
| `build/llvm/lib/Target/LC2K/LC2KGenRegisterInfo.inc` | Generated register definitions and metadata. |
| `build/llvm/lib/Target/LC2K/LC2KGenInstrInfo.inc` | Generated instruction definitions and metadata. |
| `build/llvm/lib/Target/LC2K/LC2KGenSubtargetInfo.inc` | Generated subtarget metadata. |
| `build/llvm/lib/Target/LC2K/LC2KGenDAGISel.inc` | Generated selection code for the `.td` patterns. |
| `build/llvm/compile_commands.json` | Compiler invocations useful for IDE include paths and flags when generated by the configuration. |
| `build/llvm/CMakeCache.txt`, `build.ninja` | Generated build configuration and commands. Change maintained CMake/configuration files rather than hand-editing these. |
| `build/logs/` | Build/test logs, command records, generated cases, and intermediate evidence such as MIR. |
| `build/demo/`, `build/manual/` | Working outputs created by example commands. |
| `__pycache__/` | Python bytecode caches; not source. |

Do not fix generated `.inc` files directly: rebuilding regenerates them from
`LC2K.td`. MIR is LLVM's machine-instruction representation and is useful for
inspecting register allocation and spills.

## Follow one example yourself

From the repository root, after building the tools:

```sh
mkdir -p build/manual
python3 scripts/compile_c.py tests/frontend/add.c -o build/manual/add.as
cat build/manual/add.lc2k.ll
cat build/manual/add.as
python3 scripts/run.py build/manual/add.as --args 5 7
```

The returned result should be **12**. `compile_c.py` coordinates the tools;
`lc2k-prepare.cpp` validates/adapts the frontend IR; the backend validates,
lowers, selects, allocates, and prints; the harness wraps, assembles, and runs
it. Compare the IR addition with the emitted `add` instruction.

After a backend edit, rebuild before testing:

```sh
bash scripts/build.sh --no-fetch
python3 scripts/test.py --suite smoke
```

Use `python3 scripts/test.py --suite full` for the broader acceptance run. See
[WALKTHROUGH.md](WALKTHROUGH.md) for more examples and inspection commands.

Suggested reading order: `add.ll` → `LC2K.td` → `LC2K.h` → lowering/selection →
instruction info → assembly printer → assembler/simulator. Read the validation
and build files alongside those when you need to understand accepted inputs
or how LLVM discovers the target.

A useful review question: can you trace which file registers LC2K, which selects
ADD, which prints it, and which executes it? Those are four separate jobs.
