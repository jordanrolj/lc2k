# Week 1 contract (initial implementation)

This adopts a small leaf-function ABI as a project convention, not an LC2K
standard. Human review of this initial contract and G1 remains pending.
No calls, synthesis, or Week 2 recipes are enabled.

## ISA and ABI

The ISA reference is the EECS 370 Project 1 Fall 2026 specification, retrieved
2026-11-10: https://eecs370.github.io/project_1_spec/ . Eight 32-bit registers,
65536 word addresses, ADD modulo 2^32, bitwise NOR, LW/SW, BEQ relative to PC+1,
JALR (link written before target read), HALT and NOOP. r0 remains zero.
Generated assembly uses signed decimal .fill values and six-character labels.

One leaf function `kernel`, up to three i32 arguments in r1/r2/r3, result r1.
r0, r5 (stack base), r7 (return address) are reserved; r1/r2/r3/r4/r6
are allocatable and caller-clobbered. The wrapper initializes a word-addressed
stack base and uses JALR to enter/return. There is no libc, recursion, varargs,
user function call, object writer, or linker. Stack and program size limits
must be checked by the harness, never silently wrapped.

## Intended Week 1 subset and acceptance

Only i32 modular ADD, raw NOR/NOT, constants, copies, i32 return, equality and
inequality branches, PHIs, bounded simple loops, aligned i32 globals and
constant-index i32 GEPs are candidates for support. Each needs an executed
test before it is claimed. Generic AND/OR/multiply recipes wait for Week 2.
Floating point, vectors, division, shifts, arbitrary calls, pointer casts,
byte accesses, dynamic indexing and arbitrary host IR are rejected.

## Byte/word boundary

LLVM IR retains byte sizes and alignment: i32 is four bytes, pointers are 32
bits. Machine addresses denote words. Only recognized global + constant,
four-byte-aligned offsets may become global word labels plus offset/4.
Frame objects remain byte-sized in LLVM and are divided by four explicitly
when frame indices become stack-relative machine operands. No arbitrary
integer expression may be treated as a pointer or divided opportunistically.
Clang's canonical direct-global `getelementptr i8` form is admitted only with
one nonnegative constant byte offset divisible by four, and offset+4 inside
the known i32 object. It does not admit byte loads/stores. Inbounds offsets
are checked structurally; arbitrary pointer arithmetic remains rejected.

The runtime wrapper initializes r5 to 61440 and reserves 4096 words below it.
Images are limited to 32768 words, so code, literals and globals cannot overlap
the stack and all absolute LW/SW labels fit a signed 16-bit offset. The observed
pressure test uses 14 colored four-byte slots (56-byte frame); this is evidence
of LLVM allocation, not a claim that local liveness equals spill count.

## Frontend

Direct IR must explicitly opt in to the project target and layout. A separate
validated C adapter may accept only its documented pinned freestanding Clang
configuration; arbitrary RISC-V/host IR is never silently retargeted.
Unsigned 32-bit C is the reference computation. Features and limitations
actually demonstrated will be recorded in STATUS.md and README.md.
