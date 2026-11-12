// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "LC2K.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineRegisterInfo.h"
#include "llvm/CodeGen/SelectionDAG.h"
using namespace llvm;
LC2KTargetLowering::LC2KTargetLowering(const TargetMachine &TM, const TargetRegisterInfo *RI) : TargetLowering(TM) {
  addRegisterClass(MVT::i32, &LC2K::GPRRegClass);
  setStackPointerRegisterToSaveRestore(LC2K::R5);
  setBooleanContents(ZeroOrOneBooleanContent);
  setOperationAction(ISD::BR_CC, MVT::i32, Custom);
  setOperationAction(ISD::BRCOND, MVT::Other, Expand);
  setOperationAction(ISD::SETCC, MVT::i32, Expand);
  setOperationAction(ISD::SELECT, MVT::i32, Expand);
  setOperationAction(ISD::SELECT_CC, MVT::i32, Expand);
  setOperationAction(ISD::GlobalAddress, MVT::i32, Custom);
  setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i1, Expand);
  computeRegisterProperties(RI);
}
SDValue LC2KTargetLowering::LowerFormalArguments(SDValue Chain,
    CallingConv::ID CC, bool VarArg, const SmallVectorImpl<ISD::InputArg> &Ins,
    const SDLoc &DL, SelectionDAG &DAG, SmallVectorImpl<SDValue> &Vals) const {
  if (CC != CallingConv::C || VarArg || Ins.size() > 3)
    report_fatal_error("LC2K: expected leaf C convention, at most three i32 arguments");
  const MCPhysReg Args[] = {LC2K::R1, LC2K::R2, LC2K::R3};
  auto &MRI = DAG.getMachineFunction().getRegInfo();
  for (unsigned I = 0; I < Ins.size(); ++I) {
    if (Ins[I].VT != MVT::i32) report_fatal_error("LC2K: argument must be i32");
    Register V = MRI.createVirtualRegister(&LC2K::GPRRegClass);
    MRI.addLiveIn(Args[I], V);
    Vals.push_back(DAG.getCopyFromReg(Chain, DL, V, MVT::i32));
  }
  return Chain;
}
SDValue LC2KTargetLowering::LowerReturn(SDValue Chain, CallingConv::ID,
    bool, const SmallVectorImpl<ISD::OutputArg> &Outs,
    const SmallVectorImpl<SDValue> &Vals, const SDLoc &DL, SelectionDAG &DAG) const {
  if (Outs.size() != 1 || Outs[0].VT != MVT::i32)
    report_fatal_error("LC2K: return must be one i32");
  Chain = DAG.getCopyToReg(Chain, DL, LC2K::R1, Vals[0], SDValue());
  return DAG.getNode(LC2KISD::RET, DL, MVT::Other, Chain,
      DAG.getRegister(LC2K::R1, MVT::i32), Chain.getValue(1));
}
SDValue LC2KTargetLowering::LowerOperation(SDValue Op, SelectionDAG &DAG) const {
  SDLoc DL(Op);
  if (Op.getOpcode() == ISD::GlobalAddress) {
    auto *G = cast<GlobalAddressSDNode>(Op);
    // Preserve bytes until a recognized LOAD/STORE consumes this wrapper.
    return DAG.getNode(LC2KISD::ADDR, DL, MVT::i32,
        DAG.getTargetGlobalAddress(G->getGlobal(), DL, MVT::i32, G->getOffset()));
  }
  if (Op.getOpcode() == ISD::BR_CC) {
    auto CC = cast<CondCodeSDNode>(Op.getOperand(1))->get();
    if (CC != ISD::SETEQ && CC != ISD::SETNE)
      report_fatal_error("LC2K: only equality/inequality branches are supported");
    return DAG.getNode(LC2KISD::BR_CC, DL, MVT::Other, Op.getOperand(0),
        Op.getOperand(2), Op.getOperand(3),
        DAG.getTargetConstant(CC == ISD::SETNE, DL, MVT::i32), Op.getOperand(4));
  }
  report_fatal_error("LC2K: unsupported custom lowering");
}
const char *LC2KTargetLowering::getTargetNodeName(unsigned O) const {
  switch (O) {
  case LC2KISD::RET: return "LC2KISD::RET";
  case LC2KISD::BR_CC: return "LC2KISD::BR_CC";
  case LC2KISD::ADDR: return "LC2KISD::ADDR";
  default: return nullptr;
  }
}
