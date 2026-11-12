// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "LC2K.h"
#include "llvm/CodeGen/SelectionDAGISel.h"
#include "llvm/CodeGen/SelectionDAG.h"
using namespace llvm;
namespace {
class LC2KISel : public SelectionDAGISel {
  #include "LC2KGenDAGISel.inc"
public:
  LC2KISel(LC2KTargetMachine &TM, CodeGenOptLevel OL) : SelectionDAGISel(TM, OL) {}
  SDValue globalAddress(SDValue P, const SDLoc &DL, int64_t Bytes = 0) {
    if (P.getOpcode() == ISD::ADD) {
      if (auto *C = dyn_cast<ConstantSDNode>(P.getOperand(1)))
        return globalAddress(P.getOperand(0), DL, Bytes + C->getSExtValue());
    }
    if (P.getOpcode() != LC2KISD::ADDR)
      report_fatal_error("LC2K: unrecognized memory address; expected aligned constant global offset");
    auto *G = cast<GlobalAddressSDNode>(P.getOperand(0));
    Bytes += G->getOffset();
    if (Bytes % 4 || Bytes < 0) report_fatal_error("LC2K: invalid byte-to-word offset");
    return CurDAG->getTargetGlobalAddress(G->getGlobal(), DL, MVT::i32, Bytes / 4);
  }
  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) { N->setNodeId(-1); return; }
    SDLoc DL(N);
    switch (N->getOpcode()) {
    case ISD::Constant: {
      int64_t V = cast<ConstantSDNode>(N)->getSExtValue();
      if (V == 0) { ReplaceNode(N, CurDAG->getRegister(LC2K::R0, MVT::i32).getNode()); return; }
      CurDAG->SelectNodeTo(N, LC2K::LDC, MVT::i32,
          CurDAG->getSignedTargetConstant(V, DL, MVT::i32)); return;
    }
    case ISD::BR:
      CurDAG->SelectNodeTo(N, LC2K::JMP, MVT::Other, N->getOperand(1), N->getOperand(0)); return;
    case LC2KISD::RET:
      CurDAG->SelectNodeTo(N, LC2K::RET, MVT::Other, N->getOperand(0), N->getOperand(2)); return;
    case LC2KISD::BR_CC: {
      unsigned O = N->getOperand(3)->getAsZExtVal() ? LC2K::BNE : LC2K::BEQ;
      SDValue Ops[] = {N->getOperand(1), N->getOperand(2), N->getOperand(4), N->getOperand(0)};
      CurDAG->SelectNodeTo(N, O, MVT::Other, Ops); return;
    }
    case ISD::LOAD: {
      auto *L = cast<LoadSDNode>(N);
      if (L->getMemoryVT() != MVT::i32 || L->getExtensionType() != ISD::NON_EXTLOAD)
        report_fatal_error("LC2K: only i32 loads are supported");
      SDNode *M = CurDAG->getMachineNode(LC2K::LDG, DL, MVT::i32, MVT::Other,
          globalAddress(L->getBasePtr(), DL), L->getChain());
      CurDAG->setNodeMemRefs(cast<MachineSDNode>(M), {L->getMemOperand()});
      ReplaceNode(N, M); return;
    }
    case ISD::STORE: {
      auto *S = cast<StoreSDNode>(N);
      if (S->getMemoryVT() != MVT::i32) report_fatal_error("LC2K: only i32 stores are supported");
      SDNode *M = CurDAG->getMachineNode(LC2K::STG, DL, MVT::Other,
          S->getValue(), globalAddress(S->getBasePtr(), DL), S->getChain());
      CurDAG->setNodeMemRefs(cast<MachineSDNode>(M), {S->getMemOperand()});
      ReplaceNode(N, M); return;
    }
    default: SelectCode(N); return;
    }
  }
};
class LC2KISelLegacy : public SelectionDAGISelLegacy {
public:
  static char ID;
  LC2KISelLegacy(LC2KTargetMachine &TM, CodeGenOptLevel OL)
      : SelectionDAGISelLegacy(ID, std::make_unique<LC2KISel>(TM, OL)) {}
  StringRef getPassName() const override { return "LC2K SelectionDAG instruction selection"; }
};
char LC2KISelLegacy::ID;
}
FunctionPass *llvm::createLC2KISel(LC2KTargetMachine &TM, CodeGenOptLevel OL) {
  return new LC2KISelLegacy(TM, OL);
}
