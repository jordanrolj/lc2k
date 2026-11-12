// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "llvm/MC/MCAsmInfo.h"
#include "llvm/MC/MCInstrInfo.h"
#include "llvm/MC/MCRegisterInfo.h"
#include "llvm/MC/MCSubtargetInfo.h"
#include "llvm/MC/TargetRegistry.h"
using namespace llvm;
namespace llvm { Target &getTheLC2KTarget(); }
#define GET_REGINFO_ENUM
#include "LC2KGenRegisterInfo.inc"
#define GET_INSTRINFO_ENUM
#include "LC2KGenInstrInfo.inc"
#define GET_SUBTARGETINFO_ENUM
#include "LC2KGenSubtargetInfo.inc"
#define GET_REGINFO_MC_DESC
#include "LC2KGenRegisterInfo.inc"
#define GET_INSTRINFO_MC_DESC
#include "LC2KGenInstrInfo.inc"
#define GET_SUBTARGETINFO_MC_DESC
#include "LC2KGenSubtargetInfo.inc"
namespace {
class LC2KAsmInfo : public MCAsmInfo {
public:
  LC2KAsmInfo() {
    CodePointerSize = 4; CalleeSaveStackSlotSize = 4;
    MinInstAlignment = 4; MaxInstLength = 8;
    CommentString = "#"; SupportsDebugInformation = false;
  }
};
MCAsmInfo *asmInfo(const MCRegisterInfo &, const Triple &, const MCTargetOptions &) {
  return new LC2KAsmInfo();
}
MCInstrInfo *instrInfo() { auto *I = new MCInstrInfo; InitLC2KMCInstrInfo(I); return I; }
MCRegisterInfo *regInfo(const Triple &) {
  auto *R = new MCRegisterInfo; InitLC2KMCRegisterInfo(R, LC2K::R7); return R;
}
MCSubtargetInfo *subtargetInfo(const Triple &T, StringRef CPU, StringRef FS) {
  return createLC2KMCSubtargetInfoImpl(T, CPU.empty() ? "generic" : CPU,
                                      CPU.empty() ? "generic" : CPU, FS);
}
}
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeLC2KTargetMC() {
  auto &T = getTheLC2KTarget();
  TargetRegistry::RegisterMCAsmInfo(T, asmInfo);
  TargetRegistry::RegisterMCInstrInfo(T, instrInfo);
  TargetRegistry::RegisterMCRegInfo(T, regInfo);
  TargetRegistry::RegisterMCSubtargetInfo(T, subtargetInfo);
}
