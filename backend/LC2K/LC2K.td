// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
include "llvm/Target/Target.td"
class LCReg<bits<3> n, string name> : Register<name> {
  let Namespace = "LC2K";
  let HWEncoding{2-0} = n;
}
foreach i = 0-7 in { def R#i : LCReg<i, !cast<string>(i)>; }
def GPR : RegisterClass<"LC2K", [i32], 32,
  (add R1, R2, R3, R4, R6, R0, R5, R7)>;
def brtarget : Operand<OtherVT>;
class LCInst<dag outs, dag ins, string text, list<dag> pattern = []>
    : Instruction {
  let Namespace = "LC2K";
  let OutOperandList = outs;
  let InOperandList = ins;
  let AsmString = text;
  let Pattern = pattern;
  let Size = 4;
  let hasSideEffects = 0;
  let mayLoad = 0;
  let mayStore = 0;
}
def ADD : LCInst<(outs GPR:$d), (ins GPR:$a, GPR:$b),
  "add $a $b $d", [(set i32:$d, (add i32:$a, i32:$b))]> {
  let isCommutable = 1;
}
def NOR : LCInst<(outs GPR:$d), (ins GPR:$a, GPR:$b),
  "nor $a $b $d", [(set i32:$d, (not (or i32:$a, i32:$b)))]> {
  let isCommutable = 1;
}
def : Pat<(not GPR:$a), (NOR GPR:$a, GPR:$a)>;
// Each LDC emits exactly one LW from a real literal pool word.
def LDC : LCInst<(outs GPR:$d), (ins i32imm:$value), "literal $d $value"> {
  let mayLoad = 1;
  let Uses = [R0];
  let isReMaterializable = 1;
}
def LDG : LCInst<(outs GPR:$d), (ins i32imm:$addr), "global-load $d $addr"> {
  let mayLoad = 1;
  let Uses = [R0];
}
def STG : LCInst<(outs), (ins GPR:$s, i32imm:$addr), "global-store $s $addr"> {
  let mayStore = 1;
  let Uses = [R0];
}
def LD : LCInst<(outs GPR:$d), (ins GPR:$base, i32imm:$off), "lw $base $d $off"> {
  let mayLoad = 1;
}
def ST : LCInst<(outs), (ins GPR:$s, GPR:$base, i32imm:$off), "sw $base $s $off"> {
  let mayStore = 1;
}
def BEQ : LCInst<(outs), (ins GPR:$a, GPR:$b, brtarget:$dst), "beq $a $b $dst"> {
  let isBranch = 1; let isTerminator = 1;
}
// BNE has no temporaries: emission is BEQ a,b,+1 followed by BEQ 0,0,dst.
def BNE : LCInst<(outs), (ins GPR:$a, GPR:$b, brtarget:$dst), "bne $a $b $dst"> {
  let isBranch = 1; let isTerminator = 1; let Size = 8;
}
def JMP : LCInst<(outs), (ins brtarget:$dst), "beq 0 0 $dst"> {
  let isBranch = 1; let isTerminator = 1; let isBarrier = 1; let Uses = [R0];
}
def RET : LCInst<(outs), (ins), "jalr 7 4"> {
  let isReturn = 1; let isTerminator = 1; let isBarrier = 1;
  let Uses = [R1, R7]; let Defs = [R4];
}
def LC2KInstrInfo : InstrInfo;
def : Processor<"generic", NoItineraries, []>;
def LC2K : Target { let InstructionSet = LC2KInstrInfo; }
