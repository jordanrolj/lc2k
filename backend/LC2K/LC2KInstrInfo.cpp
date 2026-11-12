// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "LC2K.h"
#include "llvm/CodeGen/MachineFrameInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineInstrBuilder.h"
#include "llvm/CodeGen/MachineMemOperand.h"
#include "llvm/Support/MathExtras.h"
using namespace llvm;
#define GET_REGINFO_TARGET_DESC
#include "LC2KGenRegisterInfo.inc"
#define GET_INSTRINFO_CTOR_DTOR
#include "LC2KGenInstrInfo.inc"
LC2KRegisterInfo::LC2KRegisterInfo() : LC2KGenRegisterInfo(LC2K::R7) {}
LC2KInstrInfo::LC2KInstrInfo() : LC2KGenInstrInfo() {}
const MCPhysReg *LC2KRegisterInfo::getCalleeSavedRegs(const MachineFunction *) const {
  static const MCPhysReg None[] = {0}; return None;
}
BitVector LC2KRegisterInfo::getReservedRegs(const MachineFunction &) const {
  BitVector B(getNumRegs());
  B.set(LC2K::R0); B.set(LC2K::R5); B.set(LC2K::R7); return B;
}
Register LC2KRegisterInfo::getFrameRegister(const MachineFunction &) const { return LC2K::R5; }
bool LC2KRegisterInfo::eliminateFrameIndex(MachineBasicBlock::iterator I,
    int SPAdj, unsigned Op, RegScavenger *) const {
  auto &MI = *I;
  auto &MFI = MI.getMF()->getFrameInfo();
  int FI = MI.getOperand(Op).getIndex();
  // LLVM frame layout is in bytes; r5 is the fixed leaf frame's word base.
  int64_t Bytes = MFI.getObjectOffset(FI);
  if (SPAdj || Bytes % 4 || MFI.getObjectSize(FI) != 4)
    report_fatal_error("LC2K: unsupported frame object/alignment");
  int64_t Words = Bytes / 4 + MI.getOperand(Op + 1).getImm();
  if (!isInt<16>(Words) || Words >= 0 || Words < -4096)
    report_fatal_error("LC2K: stack offset exceeds fixed leaf stack");
  MI.getOperand(Op).ChangeToRegister(LC2K::R5, false);
  MI.getOperand(Op + 1).ChangeToImmediate(Words);
  return false;
}
void LC2KFrameLowering::emitPrologue(MachineFunction &MF, MachineBasicBlock &) const {
  // Calls and local allocas are rejected. No stack adjustment is needed for
  // this one fixed-base leaf frame; every allocator slot is below r5.
  if (MF.getFrameInfo().getStackSize() > 16384 || MF.getFrameInfo().hasVarSizedObjects())
    report_fatal_error("LC2K: leaf stack frame exceeds 4096 words");
}
void LC2KInstrInfo::copyPhysReg(MachineBasicBlock &B, MachineBasicBlock::iterator I,
    const DebugLoc &D, MCRegister Dst, MCRegister Src, bool Kill, bool, bool) const {
  if (Dst == LC2K::R0 || Dst == LC2K::R5 || Dst == LC2K::R7)
    report_fatal_error("LC2K: copy writes reserved register");
  BuildMI(B, I, D, get(LC2K::ADD), Dst).addReg(Src, getKillRegState(Kill)).addReg(LC2K::R0);
}
void LC2KInstrInfo::storeRegToStackSlot(MachineBasicBlock &B,
    MachineBasicBlock::iterator I, Register R, bool Kill, int FI,
    const TargetRegisterClass *, const TargetRegisterInfo *, Register,
    MachineInstr::MIFlag Flags) const {
  auto &MF = *B.getParent();
  auto *MMO = MF.getMachineMemOperand(MachinePointerInfo::getFixedStack(MF, FI),
      MachineMemOperand::MOStore, 4, Align(4));
  BuildMI(B, I, DebugLoc(), get(LC2K::ST)).addReg(R, getKillRegState(Kill))
      .addFrameIndex(FI).addImm(0).addMemOperand(MMO).setMIFlag(Flags);
}
void LC2KInstrInfo::loadRegFromStackSlot(MachineBasicBlock &B,
    MachineBasicBlock::iterator I, Register R, int FI,
    const TargetRegisterClass *, const TargetRegisterInfo *, Register,
    MachineInstr::MIFlag Flags) const {
  auto &MF = *B.getParent();
  auto *MMO = MF.getMachineMemOperand(MachinePointerInfo::getFixedStack(MF, FI),
      MachineMemOperand::MOLoad, 4, Align(4));
  BuildMI(B, I, DebugLoc(), get(LC2K::LD), R).addFrameIndex(FI).addImm(0)
      .addMemOperand(MMO).setMIFlag(Flags);
}
bool LC2KInstrInfo::analyzeBranch(MachineBasicBlock &B, MachineBasicBlock *&T,
    MachineBasicBlock *&F, SmallVectorImpl<MachineOperand> &C, bool) const {
  T = F = nullptr; C.clear();
  for (auto I = B.getFirstTerminator(); I != B.end(); ++I) {
    if (I->isDebugInstr()) continue;
    unsigned O = I->getOpcode();
    if (O == LC2K::JMP) {
      if (!T) T = I->getOperand(0).getMBB();
      else if (!C.empty() && !F) F = I->getOperand(0).getMBB();
      else return true;
    } else if ((O == LC2K::BEQ || O == LC2K::BNE) && !T) {
      T = I->getOperand(2).getMBB();
      C.push_back(MachineOperand::CreateImm(O == LC2K::BEQ ? 0 : 1));
      C.push_back(I->getOperand(0)); C.push_back(I->getOperand(1));
    } else return true;
  }
  return false;
}
unsigned LC2KInstrInfo::insertBranch(MachineBasicBlock &B, MachineBasicBlock *T,
    MachineBasicBlock *F, ArrayRef<MachineOperand> C, const DebugLoc &D, int *Bytes) const {
  if (!T) report_fatal_error("LC2K: branch requires destination");
  unsigned N = 1, Size = 4;
  if (C.empty()) BuildMI(&B, D, get(LC2K::JMP)).addMBB(T);
  else {
    unsigned O = C[0].getImm() ? LC2K::BNE : LC2K::BEQ;
    BuildMI(&B, D, get(O)).add(C[1]).add(C[2]).addMBB(T);
    Size = O == LC2K::BNE ? 8 : 4;
    if (F) { BuildMI(&B, D, get(LC2K::JMP)).addMBB(F); ++N; Size += 4; }
  }
  if (Bytes) *Bytes = Size;
  return N;
}
unsigned LC2KInstrInfo::removeBranch(MachineBasicBlock &B, int *Bytes) const {
  unsigned N = 0; int Size = 0;
  while (!B.empty()) {
    auto &MI = B.back();
    unsigned O = MI.getOpcode();
    if (O != LC2K::JMP && O != LC2K::BEQ && O != LC2K::BNE) break;
    Size += O == LC2K::BNE ? 8 : 4; MI.eraseFromParent(); ++N;
  }
  if (Bytes) *Bytes = Size;
  return N;
}
bool LC2KInstrInfo::reverseBranchCondition(SmallVectorImpl<MachineOperand> &C) const {
  C[0].setImm(!C[0].getImm()); return false;
}
