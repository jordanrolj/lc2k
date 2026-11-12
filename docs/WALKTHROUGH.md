# Trace a real Week 1 kernel

`tests/backend/add.ll` receives runtime i32 arguments and returns their sum.
It declares the LC2K triple and byte-sized DataLayout explicitly. Validation
checks the input envelope, types and operations before LLVM instruction selection.

SelectionDAG turns the IR ADD into the target ADD defined in `LC2K.td`.
Arguments start as LLVM virtual registers with physical live-ins r1/r2. LLVM
allocates and coalesces them so the final sum can overwrite r1. The emitted
assembly from `build/demo/add.as` is:

```text
kentry noop
        # frame_bytes 0
b0 noop
        add 1 2 1
        jalr 7 4
```

The two NOOPs attach ordinary short labels to actual words, as required by the
course assembly format. The ADD reads both inputs before overwriting r1. The
return JALR reads the return address from reserved r7 and writes an unused
link into r4, so no additional reserved scratch is needed.

The handwritten wrapper in `harness/backend.py` loads 5 and 7 from data words,
initializes r5 to 61440, loads the address of kentry into r4 and executes
`jalr 4 7`. It saves return PC 6 in r7. The kernel returns there; the wrapper's
HALT advances PC to 7. The runner observes all 32 bits of r1, rather than using
a host process exit code.

Executed commands (both exit 0):

```sh
build/llvm/bin/llc -march=lc2k -verify-machineinstrs tests/backend/add.ll -o build/demo/add.as
python3 scripts/run.py build/demo/add.as --args 5 7
python3 scripts/run.py build/demo/add.as --args 4294967295 1
```

Results: respectively 12 and 0, with 11 dynamic instructions including the
wrapper HALT. The second demonstrates modular overflow. These instruction
counts describe the simulator, not measured hardware speed.

`tests/backend/loop.ll` has two PHIs: an iteration index and a sum. LLVM lowers
them to register transfers and loop-carried state. With the default backend
optimization level, the tested emitted loop counts down using a literal -1
and branches on equality to zero. No ADD-immediate is invented: the -1 lives
in a `.fill` pool word and is loaded with LW.

`tests/backend/memory.ll` loads/stores elements of a four-word array. LLVM's
third element has byte offset 8; selection explicitly converts 8/4 to word
offset 2, and assembly names that word g2. A store to g1 must leave g0,g2,g3 and
the separate g4 global intact. The test checks these observations independently.

`tests/backend/pressure.ll` keeps a balanced NOR computation across 64 runtime
global words. The actual tested assembly contains 45 allocator spill stores
and 45 reloads. LLVM frame objects are byte offsets; frame-index elimination
converts each to a negative word offset from r5. No free constant, implicit
extra register or unbounded virtual register reaches the final program.
The test uses random mutable globals and per-leaf sensitizing cases because
a NOR tree can otherwise mask incorrect intermediate values.
