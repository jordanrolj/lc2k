// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#ifndef LLVM_LIB_TARGET_LC2K_H
#define LLVM_LIB_TARGET_LC2K_H
#include "llvm/CodeGen/CodeGenTargetMachineImpl.h"
#include "llvm/CodeGen/TargetFrameLowering.h"
#include "llvm/CodeGen/TargetInstrInfo.h"
#include "llvm/CodeGen/TargetLowering.h"
#include "llvm/CodeGen/TargetRegisterInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"
#define GET_REGINFO_ENUM
#include "LC2KGenRegisterInfo.inc"
#define GET_INSTRINFO_ENUM
#include "LC2KGenInstrInfo.inc"
#define GET_REGINFO_HEADER
#include "LC2KGenRegisterInfo.inc"
#define GET_INSTRINFO_HEADER
#include "LC2KGenInstrInfo.inc"
#define GET_SUBTARGETINFO_HEADER
#include "LC2KGenSubtargetInfo.inc"
namespace llvm {
Target &getTheLC2KTarget();
class LC2KTargetMachine;
FunctionPass *createLC2KISel(LC2KTargetMachine &TM, CodeGenOptLevel OL);
FunctionPass *createLC2KAsmPrinter(raw_ostream &OS);
namespace LC2KISD { enum { RET = ISD::BUILTIN_OP_END, BR_CC, ADDR }; }
class LC2KRegisterInfo : public LC2KGenRegisterInfo {
public:
  LC2KRegisterInfo();
  const MCPhysReg *getCalleeSavedRegs(const MachineFunction *) const override;
  BitVector getReservedRegs(const MachineFunction &) const override;
  Register getFrameRegister(const MachineFunction &) const override;
  bool eliminateFrameIndex(MachineBasicBlock::iterator, int, unsigned,
                           RegScavenger *) const override;
};
class LC2KInstrInfo : public LC2KGenInstrInfo {
  LC2KRegisterInfo RI;
public:
  LC2KInstrInfo();
  const LC2KRegisterInfo &getRegisterInfo() const { return RI; }
  void copyPhysReg(MachineBasicBlock &, MachineBasicBlock::iterator,
      const DebugLoc &, MCRegister, MCRegister, bool, bool = false, bool = false) const override;
  void storeRegToStackSlot(MachineBasicBlock &, MachineBasicBlock::iterator,
      Register, bool, int, const TargetRegisterClass *, const TargetRegisterInfo *,
      Register, MachineInstr::MIFlag = MachineInstr::NoFlags) const override;
  void loadRegFromStackSlot(MachineBasicBlock &, MachineBasicBlock::iterator,
      Register, int, const TargetRegisterClass *, const TargetRegisterInfo *,
      Register, MachineInstr::MIFlag = MachineInstr::NoFlags) const override;
  bool analyzeBranch(MachineBasicBlock &, MachineBasicBlock *&, MachineBasicBlock *&,
      SmallVectorImpl<MachineOperand> &, bool = false) const override;
  unsigned insertBranch(MachineBasicBlock &, MachineBasicBlock *, MachineBasicBlock *,
      ArrayRef<MachineOperand>, const DebugLoc &, int * = nullptr) const override;
  unsigned removeBranch(MachineBasicBlock &, int * = nullptr) const override;
  bool reverseBranchCondition(SmallVectorImpl<MachineOperand> &) const override;
};
class LC2KFrameLowering : public TargetFrameLowering {
public:
  LC2KFrameLowering() : TargetFrameLowering(StackGrowsDown, Align(4), 0) {}
  bool hasFPImpl(const MachineFunction &) const override { return true; }
  void emitPrologue(MachineFunction &, MachineBasicBlock &) const override;
  void emitEpilogue(MachineFunction &, MachineBasicBlock &) const override {}
};
class LC2KTargetLowering : public TargetLowering {
public:
  LC2KTargetLowering(const TargetMachine &, const TargetRegisterInfo *);
  SDValue LowerFormalArguments(SDValue, CallingConv::ID, bool,
      const SmallVectorImpl<ISD::InputArg> &, const SDLoc &, SelectionDAG &,
      SmallVectorImpl<SDValue> &) const override;
  SDValue LowerReturn(SDValue, CallingConv::ID, bool,
      const SmallVectorImpl<ISD::OutputArg> &, const SmallVectorImpl<SDValue> &,
      const SDLoc &, SelectionDAG &) const override;
  SDValue LowerOperation(SDValue, SelectionDAG &) const override;
  const char *getTargetNodeName(unsigned) const override;
};
class LC2KSubtarget : public LC2KGenSubtargetInfo {
  LC2KInstrInfo II;
  LC2KFrameLowering FL;
  LC2KTargetLowering TL;
public:
  LC2KSubtarget(const Triple &, StringRef, StringRef, const TargetMachine &);
  void ParseSubtargetFeatures(StringRef CPU, StringRef TuneCPU, StringRef FS);
  const LC2KInstrInfo *getInstrInfo() const override { return &II; }
  const LC2KRegisterInfo *getRegisterInfo() const override { return &II.getRegisterInfo(); }
  const LC2KFrameLowering *getFrameLowering() const override { return &FL; }
  const LC2KTargetLowering *getTargetLowering() const override { return &TL; }
};
class LC2KTargetMachine : public CodeGenTargetMachineImpl {
  LC2KSubtarget ST;
  std::unique_ptr<TargetLoweringObjectFile> TLOF;
public:
  LC2KTargetMachine(const Target &, const Triple &, StringRef, StringRef,
      const TargetOptions &, std::optional<Reloc::Model>,
      std::optional<CodeModel::Model>, CodeGenOptLevel, bool);
  ~LC2KTargetMachine() override;
  const LC2KSubtarget *getSubtargetImpl(const Function &) const override { return &ST; }
  TargetLoweringObjectFile *getObjFileLowering() const override { return TLOF.get(); }
  TargetPassConfig *createPassConfig(PassManagerBase &) override;
  bool addAsmPrinter(PassManagerBase &, raw_pwrite_stream &, raw_pwrite_stream *,
                    CodeGenFileType, MCContext &) override;
};
}
#endif
