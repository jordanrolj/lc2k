// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Original project validator; APIs checked against llvmorg-20.1.8.
#include "LC2KValidate.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/ConstantRange.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Metadata.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Operator.h"
#include "llvm/Support/ErrorHandling.h"

using namespace llvm;

namespace {
[[noreturn]] void reject(const Twine &Reason) {
  report_fatal_error(Twine("LC2K unsupported IR: ") + Reason, false);
}

bool wordObject(Type *T) {
  if (T->isIntegerTy(32))
    return true;
  auto *A = dyn_cast<ArrayType>(T);
  return A && A->getNumElements() > 0 && A->getNumElements() <= 65536 &&
         A->getElementType()->isIntegerTy(32);
}

void initializer(const Constant *C) {
  if (auto *I = dyn_cast<ConstantInt>(C)) {
    if (!I->getType()->isIntegerTy(32))
      reject("global initializer must consist of i32 words");
    return;
  }
  if (isa<ConstantAggregateZero>(C) && wordObject(C->getType()))
    return;
  if (auto *D = dyn_cast<ConstantDataSequential>(C)) {
    if (!wordObject(D->getType()))
      reject("global initializer must consist of i32 words");
    return;
  }
  if (auto *A = dyn_cast<ConstantArray>(C)) {
    if (!wordObject(A->getType()))
      reject("only one-dimensional i32 arrays are admitted");
    for (const Use &U : A->operands())
      initializer(cast<Constant>(U.get()));
    return;
  }
  reject("global initializer is not a defined integer/array");
}

bool isNot(const Value *V) {
  auto *B = dyn_cast<BinaryOperator>(V);
  if (!B || B->getOpcode() != Instruction::Xor)
    return false;
  auto *C = dyn_cast<ConstantInt>(B->getOperand(1));
  return C && C->isMinusOne();
}

// Validate the structure, not just the pointer's integer bit pattern. In
// particular, accepting ptrtoint/inttoptr or blindly dividing a byte address
// would silently reinterpret arbitrary arithmetic as a machine word address.
const GlobalVariable *pointer(const Value *P) {
  if (!P->getType()->isPointerTy() || P->getType()->getPointerAddressSpace())
    reject("only address-space-zero global i32 addresses are admitted");
  if (auto *Global = dyn_cast<GlobalVariable>(P))
    return Global;
  auto *G = dyn_cast<GEPOperator>(P);
  if (!G || !isa<GlobalVariable>(G->getPointerOperand()))
    reject("address must be a global or a direct constant-index global GEP");
  if (G->getInRange() ||
      ((G->hasNoUnsignedWrap() || G->hasNoUnsignedSignedWrap()) &&
       !G->isInBounds()))
    reject("GEP range/nowrap flags outside the admitted inbounds form");
  auto *Base = cast<GlobalVariable>(G->getPointerOperand());
  SmallVector<const ConstantInt *, 2> Indices;
  for (const Use &U : G->indices()) {
    auto *C = dyn_cast<ConstantInt>(U.get());
    if (!C || C->isNegative() || C->getValue().getActiveBits() > 31)
      reject("GEP requires nonnegative constant indices");
    Indices.push_back(C);
  }
  // Clang O1 canonicalizes known i32 array elements to i8 GEPs. This
  // admits only a bounded, aligned constant byte displacement from the known
  // word object; it does not admit byte loads or arbitrary byte pointers.
  if (G->getSourceElementType()->isIntegerTy(8)) {
    if (Indices.size() != 1)
      reject("byte GEP requires one constant offset");
    uint64_t Bytes = Indices[0]->getZExtValue();
    uint64_t ObjectBytes = Base->getParent()->getDataLayout()
                               .getTypeAllocSize(Base->getValueType())
                               .getFixedValue();
    if (Bytes % 4 || Bytes + 4 > ObjectBytes)
      reject("byte GEP offset must identify one aligned in-range i32 word");
    return Base;
  }
  if (G->getSourceElementType() != Base->getValueType())
    reject("GEP source type must match its global object");
  if (Indices.empty() || !Indices[0]->isZero())
    reject("GEP must stay within its global object (first index zero)");
  if (Base->getValueType()->isIntegerTy(32)) {
    if (Indices.size() != 1)
      reject("invalid scalar global GEP");
    return Base;
  }
  auto *A = dyn_cast<ArrayType>(Base->getValueType());
  if (!A || Indices.size() != 2 ||
      Indices[1]->getZExtValue() >= A->getNumElements())
    reject("array GEP index outside the declared object");
  return Base;
}

void value(const Value *V) {
  if (isa<UndefValue>(V) || isa<PoisonValue>(V))
    reject("undef and poison values are not admitted");
  if (V->getType()->isPointerTy()) {
    pointer(V);
    return;
  }
  if (isa<BasicBlock>(V))
    return;
  if (!V->getType()->isIntegerTy(32) && !V->getType()->isIntegerTy(1))
    reject("only i32 data and i1 branch conditions are admitted");
  if (isa<Constant>(V) && !isa<ConstantInt>(V))
    reject("only literal integer data operands are admitted");
}

void attributes(const Function &F, bool Adapter) {
  for (unsigned I = 0; I < F.arg_size(); ++I) {
    for (Attribute A : F.getAttributes().getParamAttrs(I)) {
      if (A.isEnumAttribute() && A.getKindAsEnum() == Attribute::NoUndef)
        continue;
      if (A.isEnumAttribute() && A.getKindAsEnum() == Attribute::Returned) {
        // Pinned Clang annotates identity arguments with this semantic fact.
        // Check it directly instead of accepting arbitrary foreign ABI attrs.
        for (const BasicBlock &B : F)
          if (const auto *R = dyn_cast<ReturnInst>(B.getTerminator()))
            if (R->getReturnValue() != F.getArg(I))
              reject("returned parameter must be returned directly on every exit");
        continue;
      }
      reject("unsupported parameter attribute");
    }
  }
  for (Attribute A : F.getAttributes().getRetAttrs())
    if (!A.isEnumAttribute() || A.getKindAsEnum() != Attribute::NoUndef)
      reject("unsupported result attribute");
  for (Attribute A : F.getAttributes().getFnAttrs()) {
    if (A.isStringAttribute()) {
      StringRef K = A.getKindAsString(), V = A.getValueAsString();
      if (Adapter && K == "target-cpu" && V == "generic-rv32")
        continue;
      if (Adapter && K == "target-features") {
        SmallVector<StringRef, 128> Features;
        V.split(Features, ',');
        for (StringRef Feature : Features)
          if (Feature.empty() ||
              (Feature.front() != '-' && Feature != "+32bit" &&
               Feature != "+relax"))
            reject("adapter requires RV32I without extra enabled extensions");
        continue;
      }
      if ((K == "no-builtins" && V.empty()) ||
          (K == "no-trapping-math" && V == "true") ||
          (K == "stack-protector-buffer-size" && V == "8") ||
          (K == "frame-pointer" && (V == "all" || V == "none")))
        continue;
      reject(Twine("unsupported function attribute ") + K);
    }
    switch (A.getKindAsEnum()) {
    case Attribute::MustProgress:
    case Attribute::NoFree:
    case Attribute::NoRecurse:
    case Attribute::NoSync:
    case Attribute::NoUnwind:
    case Attribute::WillReturn:
    case Attribute::Memory:
    case Attribute::NoCallback:
      break;
    default:
      reject("unsupported function attribute");
    }
  }
}

void instruction(const Instruction &I) {
  SmallVector<std::pair<unsigned, MDNode *>, 4> MDs;
  I.getAllMetadata(MDs);
  for (const auto &MD : MDs)
    if (MD.first != LLVMContext::MD_tbaa)
      reject("only frontend TBAA instruction metadata is admitted");
  if (const auto *O = dyn_cast<OverflowingBinaryOperator>(&I))
    if (O->hasNoSignedWrap() || O->hasNoUnsignedWrap())
      reject("overflow flags are outside the modular arithmetic contract");
  if (const auto *D = dyn_cast<PossiblyDisjointInst>(&I))
    if (D->isDisjoint())
      reject("disjoint flag is outside the modular arithmetic contract");
  if (const auto *E = dyn_cast<PossiblyExactOperator>(&I))
    if (E->isExact())
      reject("exact flags are outside the modular arithmetic contract");
  if (!I.getType()->isVoidTy() && !I.getType()->isIntegerTy(32) &&
      !I.getType()->isIntegerTy(1) && !I.getType()->isPointerTy())
    reject("instruction result must be i32, i1, or an admitted global address");
  for (const Use &U : I.operands())
    // GEP index constants are compile-time displacements, not native data.
    // Their signed range and object bounds are checked structurally below.
    if (!isa<GetElementPtrInst>(I) || !isa<ConstantInt>(U.get()))
      value(U.get());
  switch (I.getOpcode()) {
  case Instruction::Add:
    if (!I.getType()->isIntegerTy(32))
      reject("ADD must operate on i32");
    break;
  case Instruction::Xor:
    if (!I.getType()->isIntegerTy(32) || !isNot(&I))
      reject("only xor i32 x, -1 (NOT) is admitted");
    break;
  case Instruction::Or:
    if (!I.getType()->isIntegerTy(32) || !I.hasOneUse() ||
        !isNot(*I.user_begin()))
      reject("OR is admitted only immediately under NOT as raw NOR");
    break;
  case Instruction::ICmp: {
    auto &C = cast<ICmpInst>(I);
    if (C.hasSameSign())
      reject("samesign flag is outside the modular arithmetic contract");
    if (!C.getOperand(0)->getType()->isIntegerTy(32) ||
        (C.getPredicate() != CmpInst::ICMP_EQ &&
         C.getPredicate() != CmpInst::ICMP_NE))
      reject("only i32 equality/inequality comparisons are admitted");
    for (const User *U : C.users())
      if (!isa<BranchInst>(U))
        reject("i1 comparison results may only control branches");
    break;
  }
  case Instruction::Br: {
    auto &B = cast<BranchInst>(I);
    if (B.isConditional() && !isa<ICmpInst>(B.getCondition()) &&
        !isa<ConstantInt>(B.getCondition()))
      reject("conditional branch requires an equality comparison");
    break;
  }
  case Instruction::PHI:
    if (!I.getType()->isIntegerTy(32))
      reject("only i32 PHIs are admitted");
    break;
  case Instruction::Ret:
    break;
  case Instruction::GetElementPtr:
    pointer(&I);
    for (const User *U : I.users())
      if (!isa<LoadInst>(U) && !isa<StoreInst>(U))
        reject("global GEPs may only be used by loads/stores");
    break;
  case Instruction::Load: {
    auto &L = cast<LoadInst>(I);
    if (!L.getType()->isIntegerTy(32) || L.isAtomic() || L.isVolatile() ||
        L.getAlign() != Align(4))
      reject("load must be nonvolatile, nonatomic, four-byte-aligned i32");
    pointer(L.getPointerOperand());
    break;
  }
  case Instruction::Store: {
    auto &S = cast<StoreInst>(I);
    if (!S.getValueOperand()->getType()->isIntegerTy(32) || S.isAtomic() ||
        S.isVolatile() || S.getAlign() != Align(4))
      reject("store must be nonvolatile, nonatomic, four-byte-aligned i32");
    if (pointer(S.getPointerOperand())->isConstant())
      reject("store to a constant global object");
    break;
  }
  default:
    reject(Twine("instruction '") + I.getOpcodeName() + "'");
  }
}

void metadata(const Module &M, bool Adapter) {
  for (const NamedMDNode &N : M.named_metadata())
    if (N.getName() != "llvm.ident" && N.getName() != "llvm.module.flags")
      reject(Twine("unsupported module metadata ") + N.getName());
  if (const NamedMDNode *Flags = M.getModuleFlagsMetadata()) {
    if (!Adapter && Flags->getNumOperands())
      reject("direct LC2K IR must not carry foreign target module flags");
    for (const MDNode *N : Flags->operands()) {
      if (N->getNumOperands() != 3)
        reject("malformed module flag");
      auto *Name = dyn_cast<MDString>(N->getOperand(1));
      if (!Name)
        reject("malformed module flag name");
      StringRef K = Name->getString();
      if (K == "target-abi") {
        auto *S = dyn_cast<MDString>(N->getOperand(2));
        if (!S || S->getString() != "ilp32")
          reject("adapter requires ilp32 ABI");
      } else if (K == "wchar_size" || K == "SmallDataLimit") {
        auto *V = mdconst::dyn_extract<ConstantInt>(N->getOperand(2));
        if (!V || V->getZExtValue() != (K == "wchar_size" ? 4 : 0))
          reject("unexpected frontend module flag value");
      } else if (K == "riscv-isa") {
        auto *Isa = dyn_cast<MDNode>(N->getOperand(2));
        auto *S = Isa && Isa->getNumOperands() == 1
                      ? dyn_cast<MDString>(Isa->getOperand(0))
                      : nullptr;
        if (!S || S->getString() != "rv32i2p1")
          reject("adapter requires rv32i2p1 frontend ISA");
      } else {
        reject(Twine("unsupported frontend module flag ") + K);
      }
    }
  }
  if (Adapter) {
    auto *Ident = M.getNamedMetadata("llvm.ident");
    if (!Ident || Ident->getNumOperands() != 1 ||
        Ident->getOperand(0)->getNumOperands() != 1)
      reject("adapter requires pinned Clang 20.1.8 producer identification");
    auto *S = dyn_cast<MDString>(Ident->getOperand(0)->getOperand(0));
    StringRef Producer = S ? S->getString() : StringRef();
    if (!Producer.consume_front("clang version 20.1.8") ||
        (!Producer.empty() && !Producer.starts_with(" ")))
      reject("adapter requires pinned Clang 20.1.8");
  }
}
} // namespace

void llvm::validateLC2KModule(const Module &M, bool Adapter) {
  if (M.getTargetTriple() != (Adapter ? "riscv32-unknown-unknown-elf" : LC2KTriple))
    reject("target triple does not match the explicitly selected input route");
  if (M.getDataLayoutStr() !=
      (Adapter ? "e-m:e-p:32:32-i64:64-n32-S128" : LC2KDataLayout))
    reject("data layout does not match the explicitly selected input route");
  if (!M.getModuleInlineAsm().empty() || !M.alias_empty() || !M.ifunc_empty())
    reject("inline assembly, aliases, and indirect functions are not admitted");
  metadata(M, Adapter);
  for (const GlobalVariable &G : M.globals()) {
    if (!wordObject(G.getValueType()) || G.getAddressSpace() ||
        G.isThreadLocal() || !G.hasInitializer() || G.hasSection() ||
        G.hasComdat() || G.isExternallyInitialized() ||
        (!G.hasExternalLinkage() && !G.hasLocalLinkage() && !G.hasCommonLinkage()))
      reject("global must be an initialized i32 or one-dimensional i32 array");
    if (G.getAlign().value_or(M.getDataLayout().getABITypeAlign(G.getValueType()))
        != Align(4))
      reject("global alignment must be four bytes");
    initializer(G.getInitializer());
  }
  if (M.size() != 1)
    reject("module must contain exactly one defined leaf function 'kernel'");
  for (const Function &F : M) {
    if (F.getName() != "kernel" || F.isDeclaration() || F.isVarArg() ||
        F.getCallingConv() != CallingConv::C || F.arg_size() > 3 ||
        !F.getReturnType()->isIntegerTy(32) || F.hasPersonalityFn() ||
        F.hasSection() || F.hasComdat() || !F.hasExternalLinkage() ||
        F.hasGC() || F.hasPrefixData() || F.hasPrologueData())
      reject("expected one nonvariadic C-convention i32 kernel with <=3 inputs");
    for (const Argument &A : F.args())
      if (!A.getType()->isIntegerTy(32))
        reject("kernel arguments must be i32");
    attributes(F, Adapter);
    for (const BasicBlock &B : F)
      for (const Instruction &I : B)
        instruction(I);
  }
}
