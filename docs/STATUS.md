# Status

Week 1 is implemented and tested; W1-01–08 are ready for review. G1 human
approval and independent reproduction remain pending.

Passed (exit 0):

- Pinned LLVM 20.1.8 build with assertions and registered LC2K; doctor all five tools.
  `build/logs/build-20261111T045216.688418Z/commands.jsonl`.
- Smoke 20 groups: `build/logs/test-20261111T045236.887059Z/manifest.json`.
- Full 20 groups: `build/logs/test-20261111T045243.890030Z/manifest.json`.
  19 ISA + 7 wrapper + 25 frontend tests; 1049 vectors per IR/C kernel;
  1071 pressure cases, 35 loop cases, constants and deliberate negatives.
- Real 45 spill stores / 45 reloads; 14 colored slots, byte/word offsets audited.
  `build/logs/independent-w1-review/`; tracked summary `results/week1/evidence.json`.

Current failures: none. Corrected failures (signed constants, llc input-layout
normalization, pinned C metadata/attributes) retained in evidence.json/logs.
Unrun: independent second-host/final clean-checkout rebuild, hosted CI, human
contract/milestone review. No synthesis or Week 2 implementation started.

Supported: leaf i32 ADD/NOR/NOT/constants, allocation/spills, IR EQ/NE/PHIs/loops,
constant-index i32 globals; validated C identity/add/NOT/NOR/globals. See
SUPPORT.md for exact exclusions. Machine-specific host details are omitted from
the public repository.

Documentation follow-up: [FILE_GUIDE.md](FILE_GUIDE.md) explains every maintained
file, generated outputs, and an addition example. Documentation checks are
recorded in `build/logs/file-guide-check.json`; compiler suites were not rerun
for this documentation-only change.

Next review action: independently reproduce add/loop/memory and review
CONTRACT.md before approving the ABI/support matrix and G1.
