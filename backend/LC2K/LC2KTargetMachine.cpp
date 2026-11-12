// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "LC2K.h"
#include "LC2KValidate.h"
#include "llvm/CodeGen/Passes.h"
#include "llvm/CodeGen/TargetLoweringObjectFileImpl.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/LegacyPassManager.h"
#include "llvm/MC/TargetRegistry.h"
using namespace llvm;
#define DEBUG_TYPE "lc2k-subtarget"
#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "LC2KGenSubtargetInfo.inc"
LC2KSubtarget::LC2KSubtarget(const Triple &T, StringRef CPU, StringRef FS,
                           const TargetMachine &TM)
    : LC2KGenSubtargetInfo(T, "generic", "generic", FS), TL(TM, &II.getRegisterInfo()) {
  ParseSubtargetFeatures("generic", "generic", FS);
}
LC2KTargetMachine::LC2KTargetMachine(const Target &T, const Triple &TT,
    StringRef CPU, StringRef FS, const TargetOptions &O,
    std::optional<Reloc::Model> RM, std::optional<CodeModel::Model> CM,
    CodeGenOptLevel OL, bool)
    : CodeGenTargetMachineImpl(T, "e-p:32:32-i32:32-n32-S32", TT,
          CPU, FS, O, Reloc::Static, CodeModel::Small, OL),
      ST(TT, CPU, FS, *this), TLOF(new TargetLoweringObjectFileELF) {
  initAsmInfo();
}
LC2KTargetMachine::~LC2KTargetMachine() = default;
namespace {
struct LC2KValidatePass : ModulePass {
  static char ID;
  LC2KValidatePass() : ModulePass(ID) {}
  bool runOnModule(Module &M) override { validateLC2KModule(M); return false; }
  StringRef getPassName() const override { return "LC2K supported subset validation"; }
};
char LC2KValidatePass::ID;
class LC2KPassConfig : public TargetPassConfig {
public:
  LC2KPassConfig(LC2KTargetMachine &T, PassManagerBase &P) : TargetPassConfig(T, P) {}
  void addIRPasses() override {
    addPass(new LC2KValidatePass());
    TargetPassConfig::addIRPasses();
  }
  bool addInstSelector() override {
    addPass(createLC2KISel(getTM<LC2KTargetMachine>(), getOptLevel()));
    return false;
  }
};
}
TargetPassConfig *LC2KTargetMachine::createPassConfig(PassManagerBase &P) {
  return new LC2KPassConfig(*this, P);
}
// LC2K has an assembly-only course toolchain. Reuse LLVM's entire codegen
// pipeline, then print allocated MachineInstrs directly. No ELF directives,
// linker, object emitter or text parsing of LLVM IR is involved.
bool LC2KTargetMachine::addAsmPrinter(PassManagerBase &P, raw_pwrite_stream &OS,
    raw_pwrite_stream *, CodeGenFileType F, MCContext &) {
  if (F == CodeGenFileType::Null) return false;
  if (F != CodeGenFileType::AssemblyFile) return true;
  P.add(createLC2KAsmPrinter(OS));
  return false;
}
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeLC2KTarget() {
  RegisterTargetMachine<LC2KTargetMachine> X(getTheLC2KTarget());
}
// Assembly registration is supplied by TargetMachine::addAsmPrinter.
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeLC2KAsmPrinter() {}
