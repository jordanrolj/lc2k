add_llvm_component_library(LLVMLC2KDesc LC2KMCTargetDesc.cpp
  LINK_COMPONENTS LC2KInfo MC Support TargetParser ADD_TO_COMPONENT LC2K)
