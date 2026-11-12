set(LLVM_LINK_COMPONENTS Core IRReader Support)
add_llvm_tool(lc2k-prepare lc2k-prepare.cpp ../LC2K/LC2KValidate.cpp)
