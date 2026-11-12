// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "llvm/MC/TargetRegistry.h"
using namespace llvm;
namespace llvm { Target &getTheLC2KTarget() { static Target T; return T; } }
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeLC2KTargetInfo() {
  RegisterTarget<Triple::UnknownArch> X(getTheLC2KTarget(), "lc2k",
                                       "LC2K (small leaf subset)", "LC2K");
}
