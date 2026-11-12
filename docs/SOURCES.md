# Sources and reuse log

- LLVM llvmorg-20.1.8, commit
  `87f0227cb60147a26a1eeb4fb06e3b505e9c7261`, annotated tag
  `023ec9011c9a92cfa8922030eb266d66a10f78f8`.
  https://github.com/llvm/llvm-project/releases/tag/llvmorg-20.1.8 .
  License: Apache-2.0 WITH LLVM-exception (upstream LICENSE.TXT).
  Pinned target sources and headers will be consulted for exact APIs.
  Structural/API references actually consulted: LanaiTargetMachine,
  LanaiSubtarget, LanaiMCTargetDesc, LanaiRegisterInfo.td, MSP430ISelDAGToDAG,
  MSP430ISelLowering, MSP430RegisterInfo, and the corresponding LLVM CodeGen
  headers. Target scaffolding is adapted under the same LLVM license; LC2K
  semantics, the closed validator and Python tools are project implementations.
  `backend/patches/llc-input-contract.patch` is the only upstream source edit.
- EECS 370 Project 1, Fall 2026:
  https://eecs370.github.io/project_1_spec/ (retrieved 2026-11-10).
  ISA facts are used; no student/course solution is copied. Harness is original.
  A local ignored snapshot and hash will record the exact consulted revision.
  Snapshot: `_deps/reference/eecs370-project1-fall2026.html`, SHA256
  `2d51899f90d21537d618fa1a614c7e86faa885cb4427f71a54e3e95248396190`;
  retrieval manifest `_deps/reference/manifest.json`.
