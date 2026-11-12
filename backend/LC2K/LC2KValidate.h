// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#ifndef LLVM_LIB_TARGET_LC2K_VALIDATE_H
#define LLVM_LIB_TARGET_LC2K_VALIDATE_H
namespace llvm {
class Module;
inline constexpr const char *LC2KTriple = "lc2k-unknown-none";
inline constexpr const char *LC2KDataLayout = "e-p:32:32-i32:32-n32-S32";
/// Reject IR outside the tested project contract before SelectionDAG lowering.
/// Adapter=true admits only the pinned freestanding RV32I frontend envelope;
/// it does not change the module. Retargeting is a separate, explicit action.
void validateLC2KModule(const Module &M, bool Adapter = false);
}
#endif
