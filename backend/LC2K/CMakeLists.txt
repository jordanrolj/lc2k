add_llvm_component_group(LC2K)
set(LLVM_TARGET_DEFINITIONS LC2K.td)
tablegen(LLVM LC2KGenRegisterInfo.inc -gen-register-info)
tablegen(LLVM LC2KGenInstrInfo.inc -gen-instr-info)
tablegen(LLVM LC2KGenSubtargetInfo.inc -gen-subtarget)
tablegen(LLVM LC2KGenDAGISel.inc -gen-dag-isel)
add_public_tablegen_target(LC2KCommonTableGen)
add_llvm_target(LC2KCodeGen
  LC2KTargetMachine.cpp
  LC2KInstrInfo.cpp
  LC2KISelLowering.cpp
  LC2KISelDAGToDAG.cpp
  LC2KAsmPrinter.cpp
  LC2KValidate.cpp
  LINK_COMPONENTS Analysis CodeGen CodeGenTypes Core LC2KDesc LC2KInfo MC
    SelectionDAG Support Target TargetParser TransformUtils
  ADD_TO_COMPONENT LC2K)
add_subdirectory(TargetInfo)
add_subdirectory(MCTargetDesc)
get_filename_component(LC2K_REAL_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}" REALPATH)
add_subdirectory("${LC2K_REAL_SOURCE}/../tools" ${CMAKE_CURRENT_BINARY_DIR}/tools)
