// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Explicit, narrow frontend adapter. No instruction translation happens here.
#include "../LC2K/LC2KValidate.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/ToolOutputFile.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;
static cl::opt<std::string> Input(cl::Positional, cl::desc("input LLVM IR"), cl::Required);
static cl::opt<std::string> Output("o", cl::desc("output LC2K IR"), cl::init("-"));
static cl::opt<bool> Adapter("from-rv32i-c", cl::desc("validate the pinned restricted C frontend route"));
int main(int Argc, char **Argv) {
  InitLLVM Init(Argc, Argv);
  cl::SetVersionPrinter([](raw_ostream &OS) {
    OS << "lc2k-prepare LLVM " << LLVM_VERSION_STRING << '\n';
  });
  cl::ParseCommandLineOptions(Argc, Argv, "LC2K supported-subset validator\n");
  LLVMContext Context;
  SMDiagnostic Error;
  std::unique_ptr<Module> M = parseIRFile(Input, Error, Context);
  if (!M) {
    Error.print(Argv[0], errs());
    return 1;
  }
  if (verifyModule(*M, &errs()))
    return 1;
  validateLC2KModule(*M, Adapter);
  if (Adapter) {
    // These attributes/module flags described the admitted source frontend.
    // The validator has checked them and every operation/type/address first.
    for (Function &F : *M) {
      F.removeFnAttr("target-cpu");
      F.removeFnAttr("target-features");
    }
    if (auto *Flags = M->getModuleFlagsMetadata())
      M->eraseNamedMetadata(Flags);
    M->setTargetTriple(LC2KTriple);
    M->setDataLayout(LC2KDataLayout);
    validateLC2KModule(*M);
  }
  std::error_code EC;
  ToolOutputFile Out(Output, EC, sys::fs::OF_Text);
  if (EC) {
    errs() << EC.message() << '\n';
    return 1;
  }
  M->print(Out.os(), nullptr);
  Out.keep();
  return 0;
}
