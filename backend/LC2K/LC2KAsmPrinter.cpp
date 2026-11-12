// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "LC2K.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineFrameInfo.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/raw_ostream.h"
#include <map>
using namespace llvm;
namespace {
class LC2KAsmPrinter : public MachineFunctionPass {
  raw_ostream &OS;
  std::map<int32_t, unsigned> Literals;
  DenseMap<const GlobalValue *, unsigned> GlobalBases;
  unsigned NextGlobal = 0;
  static unsigned reg(const MachineOperand &O) {
    if (!O.isReg() || !O.getReg().isPhysical())
      report_fatal_error("LC2K: unresolved virtual register in assembly emission");
    switch (O.getReg().id()) {
    case LC2K::R0: return 0; case LC2K::R1: return 1;
    case LC2K::R2: return 2; case LC2K::R3: return 3;
    case LC2K::R4: return 4; case LC2K::R5: return 5;
    case LC2K::R6: return 6; case LC2K::R7: return 7;
    default: report_fatal_error("LC2K: invalid physical register");
    }
  }
  void global(const MachineOperand &O) {
    if (!O.isGlobal() || !GlobalBases.count(O.getGlobal()) || O.getOffset() < 0)
      report_fatal_error("LC2K: invalid global operand");
    OS << 'g' << GlobalBases.lookup(O.getGlobal()) + O.getOffset();
  }
  void inst(const MachineInstr &MI) {
    if (MI.isDebugInstr()) return;
    if (MI.isPseudo()) report_fatal_error("LC2K: unresolved machine pseudo in assembly");
    const auto &A = MI.getOperand(0);
    switch (MI.getOpcode()) {
    case LC2K::ADD: case LC2K::NOR:
      OS << "        " << (MI.getOpcode() == LC2K::ADD ? "add " : "nor ")
         << reg(MI.getOperand(1)) << ' ' << reg(MI.getOperand(2)) << ' ' << reg(A) << '\n'; break;
    case LC2K::LDC: {
      int32_t V = MI.getOperand(1).getImm();
      auto [I, Added] = Literals.emplace(V, Literals.size());
      OS << "        lw 0 " << reg(A) << " c" << I->second << '\n'; break;
    }
    case LC2K::LDG:
      OS << "        lw 0 " << reg(A) << ' '; global(MI.getOperand(1)); OS << '\n'; break;
    case LC2K::STG:
      OS << "        sw 0 " << reg(A) << ' '; global(MI.getOperand(1)); OS << '\n'; break;
    case LC2K::LD:
      OS << "        lw " << reg(MI.getOperand(1)) << ' ' << reg(A) << ' '
         << MI.getOperand(2).getImm() << " # allocator reload\n"; break;
    case LC2K::ST:
      OS << "        sw " << reg(MI.getOperand(1)) << ' ' << reg(A) << ' '
         << MI.getOperand(2).getImm() << " # allocator spill\n"; break;
    case LC2K::BEQ: case LC2K::BNE:
      OS << "        beq " << reg(A) << ' ' << reg(MI.getOperand(1)) << ' ';
      if (MI.getOpcode() == LC2K::BNE) OS << "1\n        beq 0 0 ";
      OS << 'b' << MI.getOperand(2).getMBB()->getNumber() << '\n'; break;
    case LC2K::JMP:
      OS << "        beq 0 0 b" << A.getMBB()->getNumber() << '\n'; break;
    case LC2K::RET: OS << "        jalr 7 4\n"; break;
    default: report_fatal_error("LC2K: unhandled machine instruction in emitter");
    }
  }
public:
  static char ID;
  LC2KAsmPrinter(raw_ostream &O) : MachineFunctionPass(ID), OS(O) {}
  StringRef getPassName() const override { return "LC2K assembly printer"; }
  bool doInitialization(Module &M) override {
    Literals.clear(); GlobalBases.clear(); NextGlobal = 0;
    for (auto &G : M.globals()) {
      GlobalBases[&G] = NextGlobal;
      NextGlobal += M.getDataLayout().getTypeAllocSize(G.getValueType()).getFixedValue() / 4;
    }
    if (NextGlobal > 10000) report_fatal_error("LC2K: too many global words");
    return false;
  }
  bool runOnMachineFunction(MachineFunction &MF) override {
    OS << "kentry noop\n";
    OS << "        # frame_bytes " << MF.getFrameInfo().getStackSize() << '\n';
    for (auto &B : MF) {
      OS << 'b' << B.getNumber() << " noop\n";
      for (auto &MI : B) inst(MI);
    }
    return false;
  }
  bool doFinalization(Module &M) override {
    // Data are after all returns; the wrapper halts before entering this data.
    for (auto &G : M.globals()) {
      unsigned Base = GlobalBases.lookup(&G);
      auto *Init = G.getInitializer();
      uint64_t Words = M.getDataLayout().getTypeAllocSize(G.getValueType()).getFixedValue() / 4;
      for (unsigned I = 0; I < Words; ++I) {
        const Constant *C = Init;
        if (G.getValueType()->isArrayTy()) C = Init->getAggregateElement(I);
        if (!C || !isa<ConstantInt>(C)) report_fatal_error("LC2K: invalid global initializer");
        OS << 'g' << Base + I << " .fill " << cast<ConstantInt>(C)->getSExtValue() << '\n';
      }
    }
    for (auto [V, I] : Literals) OS << 'c' << I << " .fill " << V << '\n';
    return false;
  }
};
char LC2KAsmPrinter::ID;
}
FunctionPass *llvm::createLC2KAsmPrinter(raw_ostream &OS) { return new LC2KAsmPrinter(OS); }
