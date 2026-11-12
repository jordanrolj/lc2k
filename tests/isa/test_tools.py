"""Acceptance cases derived by hand, independent of tool implementation.

The countdown words are the public EECS370 Fall 2026 specification example.
Other constants are derived directly from its instruction bit fields.
"""

import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from harness import AssemblyError, assemble, run


class AssemblerTests(unittest.TestCase):
    def test_public_countdown_example(self):
        source = """        lw 0 1 five
        lw 1 2 3
start   add 1 2 1
        beq 0 1 2
        beq 0 0 start
        noop
done    halt
five    .fill 5
neg1    .fill -1
stAddr  .fill start
"""
        expected = [0x00810007, 0x008A0003, 0x000A0001, 0x01010002,
                    0x0100FFFD, 0x01C00000, 0x01800000, 5, 0xFFFFFFFF, 2]
        program = assemble(source)
        self.assertEqual(program.words, expected)
        self.assertEqual(program.symbols["five"], 7)
        self.assertEqual(program.code_addresses, list(range(7)))
        self.assertEqual(program.data_addresses, [7, 8, 9])
        result = run(expected)
        self.assertTrue(result.halted)
        self.assertEqual(result.registers[1:3], [0, 0xFFFFFFFF])
        self.assertEqual(result.pc, 7)
        self.assertEqual(result.steps, 17)

    def test_every_opcode_and_signed_offsets(self):
        program = assemble("""        add 1 2 3
        nor 4 5 6
        lw 7 6 -32768
        sw 3 2 32767
        beq 1 2 -1
        jalr 7 6
        halt
        noop
""")
        self.assertEqual(program.words, [0x000A0003, 0x00650006,
                                         0x00BE8000, 0x00DA7FFF,
                                         0x010AFFFF, 0x017E0000,
                                         0x01800000, 0x01C00000])

    def test_fill_bitpatterns_and_short_pseudos(self):
        p = assemble("""        b done
        jump 7
done    halt
one     .fill 4294967295
high    .fill -2147483648
""")
        self.assertEqual(p.words, [0x01000001, 0x01780000, 0x01800000,
                                   0xFFFFFFFF, 0x80000000])

    def test_empty_and_comment_lines(self):
        p = assemble("\n# comment\n; comment\nhalt trailing text\n")
        self.assertEqual(p.words, [0x01800000])
        self.assertEqual(p.source_lines, [4])

    def test_rejections(self):
        cases = ["        lw 0 1 missing", "a halt\na noop", "abc1234 halt",
                 "1abc halt", "        add 8 0 1", "        add -1 0 1",
                 "        add x 0 1", "        add 1 2", "        xyz 0 0 0",
                 "        lw 0 1 32768", "        beq 0 0 -32769",
                 "        .fill 4294967296", "        .fill -2147483649",
                 "        .fill no", "a", "        .fill 1.5", "        jalr 1"]
        for source in cases:
            with self.subTest(source=source):
                with self.assertRaises(AssemblyError):
                    assemble(source)

    def test_label_offset_range_and_program_size(self):
        source = "        lw 0 1 far\n" + "        noop\n" * 32767 + "far .fill 1\n"
        with self.assertRaises(AssemblyError):
            assemble(source)
        with self.assertRaises(AssemblyError):
            assemble("        noop\n" * 65537)


class SimulatorTests(unittest.TestCase):
    def execute(self, source, **kwargs):
        return run(assemble(source).words, **kwargs)

    def test_modular_arithmetic_and_operand_alias(self):
        r = self.execute("""        add 1 2 1
        add 3 3 3
        nor 4 5 4
        halt
""", initial_registers=[0, 0xFFFFFFFF, 1, 0x80000000,
                           0xAAAAAAAA, 0x55555555, 0, 0])
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[1], 0)
        self.assertEqual(r.registers[3], 0)
        self.assertEqual(r.registers[4], 0)
        self.assertEqual(r.steps, 4)

    def test_nor_is_bitwise(self):
        r = self.execute("        nor 1 2 3\n        halt\n",
                         initial_registers=[0, 0x80000001, 0x00000100, 0, 0, 0, 0, 0])
        self.assertEqual(r.registers[3], 0x7FFFFEFE)

    def test_load_store_signed_offset_and_neighbor(self):
        r = self.execute("""        lw 1 2 -1
        sw 1 2 1
        halt
""", initial_registers=[0, 100, 0, 0, 0, 0, 0, 0],
                         initial_memory={99: 0xFFFFFFFF, 100: 42, 101: 1, 102: 23})
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[2], 0xFFFFFFFF)
        self.assertEqual(r.memory[99:103], [0xFFFFFFFF, 42, 0xFFFFFFFF, 23])
        self.assertEqual((r.loads, r.stores), (1, 1))

    def test_address_boundaries_do_not_wrap(self):
        r = self.execute("        lw 1 2 1\n        halt\n",
                         initial_registers={1: 0xFFFFFFFF})
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[2], 0x008A0001)
        r = self.execute("        lw 1 2 0\n        halt\n",
                         initial_registers={1: 65535}, initial_memory={65535: 31})
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[2], 31)
        r = self.execute("        lw 1 2 1\n        halt\n",
                         initial_registers={1: 65535})
        self.assertEqual(r.status, "error")
        # A final HALT increments PC past the last address, then halts normally.
        r = self.execute("        jalr 1 7\n", initial_registers={1: 65535},
                         initial_memory={65535: 0x01800000})
        self.assertTrue(r.halted)
        self.assertEqual(r.pc, 65536)

    def test_branch_taken_untaken_and_backwards(self):
        source = """        beq 1 2 equal
        add 0 0 3
        beq 0 0 done
equal   add 1 2 3
done    halt
"""
        r = self.execute(source, initial_registers=[0, 7, 7, 99, 0, 0, 0, 0])
        self.assertEqual((r.registers[3], r.steps), (14, 3))
        r = self.execute(source, initial_registers=[0, 7, 8, 99, 0, 0, 0, 0])
        self.assertEqual((r.registers[3], r.steps), (0, 4))

    def test_emitted_bne_then_false_jump(self):
        # The target emitter's two-instruction BNE must skip its own jump on
        # equality and then execute the following false-path unconditional jump.
        source = """        beq 1 2 1
        beq 0 0 yes
        beq 0 0 no
yes     add 0 3 1
        beq 0 0 done
no      add 0 4 1
done    halt
"""
        r = self.execute(source, initial_registers={1: 7, 2: 7, 3: 100, 4: 200,
                                                     5: 60000, 7: 1234})
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[1], 200)
        self.assertEqual((r.registers[0], r.registers[5], r.registers[7]), (0, 60000, 1234))
        r = self.execute(source, initial_registers={1: 7, 2: 8, 3: 100, 4: 200,
                                                     5: 60000, 7: 1234})
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[1], 100)
        self.assertEqual((r.registers[0], r.registers[5], r.registers[7]), (0, 60000, 1234))

    def test_jalr_link_alias_and_zero(self):
        r = self.execute("""        jalr 1 7
        halt
        jalr 7 6
""", initial_registers=[0, 2, 0, 0, 0, 0, 0, 0])
        self.assertTrue(r.halted)
        self.assertEqual((r.registers[7], r.registers[6], r.pc), (1, 3, 2))
        r = self.execute("        jalr 1 1\n        halt\n",
                         initial_registers=[0, 60000, 0, 0, 0, 0, 0, 0])
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[1], 1)
        r = self.execute("        jalr 1 0\n        noop\n        halt\n",
                         initial_registers=[0, 2, 0, 0, 0, 0, 0, 0])
        self.assertTrue(r.halted)
        self.assertEqual(r.registers[0], 0)
        self.assertEqual(r.steps, 2)

    def test_r0_fixed_zero(self):
        r = self.execute("        add 1 1 0\n        nor 0 0 0\n        lw 0 0 x\n        halt\nx .fill 123\n",
                         initial_registers=[0, 9, 0, 0, 0, 0, 0, 0])
        self.assertEqual(r.registers[0], 0)
        self.assertTrue(r.halted)

    def test_runtime_failures_are_structured(self):
        cases = [("        lw 1 2 -1\n        halt", [0] * 8),
                 ("        sw 1 2 0\n        halt", [0, 65536, 0, 0, 0, 0, 0, 0]),
                 ("        beq 0 0 -2", [0] * 8),
                 ("        jalr 1 7", [0, 65536, 0, 0, 0, 0, 0, 0])]
        for source, registers in cases:
            with self.subTest(source=source):
                r = self.execute(source, initial_registers=registers)
                self.assertEqual(r.status, "error")
                self.assertFalse(r.halted)
                self.assertTrue(r.error)

    def test_invalid_encodings(self):
        for word in [0x80000000, 0x00000008, 0x01400001, 0x01800001, 0x01C10000]:
            with self.subTest(word=word):
                r = run([word])
                self.assertEqual(r.status, "error")
                self.assertIn("encoding", r.error)

    def test_timeout_and_noop(self):
        r = self.execute("        noop\nagain   beq 0 0 again", max_steps=5)
        self.assertEqual(r.status, "timeout")
        self.assertFalse(r.halted)
        self.assertEqual(r.steps, 5)
        self.assertEqual(r.pc, 1)

    def test_checker_rejects_deliberate_corruption(self):
        # The reference expected result is 12. Mutating ADD to NOR is rejected.
        correct = [0x000A0003, 0x01800000]
        mutated = [0x004A0003, 0x01800000]
        registers = [0, 5, 7, 0, 0, 0, 0, 0]
        self.assertEqual(run(correct, initial_registers=registers).registers[3], 12)
        with self.assertRaises(AssertionError):
            self.assertEqual(run(mutated, initial_registers=registers).registers[3], 12)
        # Likewise an off-by-one BEQ encoding bypasses the expected ADD.
        wrong_branch = [0x01000001, 0x000A0003, 0x01800000]
        with self.assertRaises(AssertionError):
            self.assertEqual(run(wrong_branch, initial_registers=registers).registers[3], 12)


class CommandLineTests(unittest.TestCase):
    def test_assemble_run_json_and_timeout_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, machine, mapping = root / "tiny.as", root / "tiny.mc", root / "tiny.json"
            source.write_text("        lw 0 1 value\n        halt\nvalue .fill -1\n")
            command = [sys.executable, "-m", "harness"]
            p = subprocess.run(command + ["assemble", str(source), str(machine), "--map", str(mapping)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(machine.read_text(), "0x00810002\n0x01800000\n0xFFFFFFFF\n")
            self.assertEqual(json.loads(mapping.read_text())["symbols"], {"value": 2})
            p = subprocess.run(command + ["run", str(machine), "--observe", "2"],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            output = json.loads(p.stdout)
            self.assertEqual(output["result"], 0xFFFFFFFF)
            self.assertEqual(output["memory"], {"2": 0xFFFFFFFF})
            source.write_text("again beq 0 0 again\n")
            p = subprocess.run(command + ["exec", str(source), "--max-steps", "3"],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertEqual(json.loads(p.stdout)["status"], "timeout")
            source.write_text("        lw 0 1 absent\n")
            p = subprocess.run(command + ["assemble", str(source), str(machine)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertIn("undefined label", p.stderr)


if __name__ == "__main__":
    unittest.main()
