"""Small independently implemented LC2K assembly/execution tools.

``assemble(source)`` raises AssemblyError for malformed assembly and returns a
Program whose words are uint32 bit patterns. ``run(program.words, ...)`` returns
a Result; runtime faults and instruction limits are explicit statuses rather
than successful halts. Arithmetic is modular; address arithmetic is checked.
"""

from .assembler import AssemblyError, Program, assemble
from .simulator import Result, SimulationError, run

__all__ = ["AssemblyError", "Program", "assemble", "Result", "SimulationError", "run"]
