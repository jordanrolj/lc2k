# Week 1 support boundary

This matrix names acceptance coverage; final execution status/evidence are in
STATUS.md. `C` means only the pinned validated frontend route, not arbitrary C.

| Feature | Direct LLVM IR acceptance | C acceptance |
|---|---|---|
| One leaf kernel, <=3 i32 arguments, i32 return | identity/add fixtures | identity/add fixtures |
| Modular ADD, full-width constants/copies | boundary/random values, overflow | unsigned add |
| Raw NOR / NOT | `nor.ll`, pressure tree | nor.c / not.c |
| LLVM register allocation and real spills/reloads | pressure.ll + saved MIR, random globals, wrong-spill negative | not claimed for C pressure workloads |
| EQ/NE branches, i32 PHIs | branch.ll / branch-ne.ll | C control-flow coverage not claimed |
| Simple bounded loops | loop.ll: 0, 1, 2, 7, 31 iterations | C loop coverage not claimed |
| Nonvolatile aligned i32 globals and constant-index arrays | memory.ll and pressure.ll | globals.c; neighbor isolation |
| Recognized direct-global constant byte-offset GEP | structural bounds/alignment tests | Clang's canonical memory shape |
| Rejection boundary | foreign triple/layout, bytes, multiply, invalid pointers/flags | multiply/byte/pointer source rejection |

Unsupported: generic AND/OR, multiplication/division/shifts, variable array
indices, pointer arguments, ptrtoint/inttoptr and other casts, user allocas,
dynamic stack frames, function calls/recursion/varargs, libc/I/O, vectors,
floating point, atomics/volatile accesses, narrow/wide integer data, arbitrary
intrinsics, undefined/poison values, unmodeled flags, object emission/linking.
Unsigned source arithmetic avoids C signed-overflow assumptions. Nontermination
is diagnosed by the simulator instruction limit.

The project has one fixed-base leaf frame: r0/r5/r7 reserved, five allocatable
registers, stack base 61440 and maximum 4096 stack words. Images must fit 32768
words. Native LC2K has larger memory, but this explicit project image envelope
keeps absolute addresses and branch fields checked and stack regions separate.
