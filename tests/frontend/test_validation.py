"""Acceptance tests for the LLVM API boundary before target code generation.

Missing built tools are failures, so a backend suite cannot silently turn green
by skipping the validator. The repository's lightweight ISA suite can run alone.
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(os.environ.get("LC2K_BIN_DIR", ROOT / "build" / "llvm" / "bin"))
HEADER = ('target datalayout = "e-p:32:32-i32:32-n32-S32"\n'
          'target triple = "lc2k-unknown-none"\n')
IDENTITY = 'define i32 @kernel(i32 %x) { ret i32 %x }\n'


class ValidationTests(unittest.TestCase):
    def prepare(self, source, *, adapter=False):
        self.assertTrue((BIN / "lc2k-prepare").is_file(),
                        "build lc2k-prepare before running frontend tests")
        with tempfile.TemporaryDirectory(prefix="lc2k-validate-") as directory:
            input_file = Path(directory) / "input.ll"
            output_file = Path(directory) / "output.ll"
            input_file.write_text(source)
            command = [str(BIN / "lc2k-prepare"), str(input_file), "-o", str(output_file)]
            if adapter:
                command.append("--from-rv32i-c")
            result = subprocess.run(command, capture_output=True, text=True)
            return result, output_file.read_text() if output_file.exists() else ""

    def rejects(self, body, reason):
        result, output = self.prepare(HEADER + body)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("LC2K unsupported IR:", result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertEqual(output, "")

    def test_identity(self):
        result, output = self.prepare(HEADER + IDENTITY)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('target triple = "lc2k-unknown-none"', output)

    def test_raw_nor_and_global_constant_index(self):
        source = HEADER + '''
@a = global [3 x i32] [i32 5, i32 -7, i32 9], align 4
define i32 @kernel(i32 %x, i32 %y) {
  %o = or i32 %x, %y
  %n = xor i32 %o, -1
  %v = load i32, ptr getelementptr ([3 x i32], ptr @a, i32 0, i32 1), align 4
  %r = add i32 %n, %v
  ret i32 %r
}
'''
        result, _ = self.prepare(source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_host_triple_is_rejected(self):
        result, _ = self.prepare((HEADER + IDENTITY).replace("lc2k-unknown-none", "x86_64-unknown-linux-gnu"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target triple", result.stderr)

    def test_host_layout_is_rejected(self):
        result, _ = self.prepare((HEADER + IDENTITY).replace("p:32:32", "p:64:64"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data layout", result.stderr)

    def test_unadmitted_operations(self):
        for operation in ("mul", "udiv", "shl", "and"):
            with self.subTest(operation=operation):
                self.rejects(f'define i32 @kernel(i32 %x, i32 %y) {{\n'
                             f'%r = {operation} i32 %x, %y\nret i32 %r\n}}\n', "instruction")

    def test_overflow_flags_rejected(self):
        self.rejects('define i32 @kernel(i32 %x) { %r = add nsw i32 %x, 1\nret i32 %r }',
                     "overflow flags")

    def test_disjoint_nor_rejected(self):
        self.rejects('define i32 @kernel(i32 %x, i32 %y) {\n'
                     '%o = or disjoint i32 %x, %y\n%n = xor i32 %o, -1\nret i32 %n }',
                     "disjoint flag")

    def test_samesign_equality_rejected(self):
        self.rejects('define i32 @kernel(i32 %x, i32 %y) {\n'
                     '%c = icmp samesign eq i32 %x, %y\nbr i1 %c, label %a, label %b\n'
                     'a: ret i32 %x\nb: ret i32 %y }', "samesign flag")

    def test_cast_rejected(self):
        self.rejects('define i32 @kernel(i32 %x) { %p = inttoptr i32 %x to ptr\n'
                     '%r = load i32, ptr %p, align 4\nret i32 %r }', "inttoptr")

    def test_returned_parameter_checked(self):
        result, _ = self.prepare(HEADER +
                                 'define i32 @kernel(i32 returned %x) { ret i32 %x }')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.rejects('define i32 @kernel(i32 returned %x) { ret i32 0 }',
                     "returned parameter must be returned directly")

    def test_unsupported_return_attribute_rejected(self):
        self.rejects('define zeroext i32 @kernel(i32 %x) { ret i32 %x }',
                     "unsupported result attribute")

    def test_poison_rejected(self):
        self.rejects('define i32 @kernel() { ret i32 poison }', "poison")

    def test_pointer_abi_rejected(self):
        self.rejects('define i32 @kernel(ptr %p) { %x = load i32, ptr %p, align 4\nret i32 %x }',
                     "arguments must be i32")

    def test_byte_global_rejected(self):
        self.rejects('@b = global i8 7\n' + IDENTITY, "global must")

    def test_store_to_constant_global_rejected(self):
        self.rejects('@a = constant i32 7, align 4\n'
                     'define i32 @kernel(i32 %x) { store i32 %x, ptr @a, align 4\nret i32 %x }',
                     "store to a constant global")

    def test_dynamic_and_oob_array_indices_rejected(self):
        for index in ("%x", "3", "-1", "1073741824"):
            with self.subTest(index=index):
                self.rejects('@a = global [3 x i32] zeroinitializer, align 4\n'
                             'define i32 @kernel(i32 %x) {\n'
                             f'%p = getelementptr [3 x i32], ptr @a, i32 0, i32 {index}\n'
                             '%v = load i32, ptr %p, align 4\nret i32 %v\n}', "GEP")

    def test_known_aligned_byte_gep(self):
        source = HEADER + '@a = global [3 x i32] zeroinitializer, align 4\n' + (
            'define i32 @kernel() { %p = getelementptr inbounds nuw i8, ptr @a, i64 4\n'
            '%v = load i32, ptr %p, align 4\nret i32 %v }')
        result, _ = self.prepare(source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_byte_gep_offsets(self):
        for offset in (1, 12, 16):
            with self.subTest(offset=offset):
                self.rejects('@a = global [3 x i32] zeroinitializer, align 4\n'
                             'define i32 @kernel() {\n'
                             f'%p = getelementptr i8, ptr @a, i32 {offset}\n'
                             '%v = load i32, ptr %p, align 4\nret i32 %v }',
                             "aligned in-range i32 word")

    def test_unpaired_or_rejected(self):
        self.rejects('define i32 @kernel(i32 %x, i32 %y) { %o = or i32 %x, %y\nret i32 %o }',
                     "OR is admitted only")

    def test_foreign_target_attribute_rejected(self):
        self.rejects('define i32 @kernel(i32 %x) "target-cpu"="generic-rv32" { ret i32 %x }',
                     "unsupported function attribute")

    def test_restricted_adapter_accepts_after_validation(self):
        source = ('target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"\n'
                  'target triple = "riscv32-unknown-unknown-elf"\n'
                  'define i32 @kernel(i32 %x) "target-cpu"="generic-rv32" '
                  '"target-features"="+32bit,+relax,-m" { ret i32 %x }\n'
                  '!llvm.ident = !{!0}\n!0 = !{!"clang version 20.1.8"}\n')
        result, output = self.prepare(source, adapter=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('target triple = "lc2k-unknown-none"', output)
        self.assertIn('target datalayout = "e-p:32:32-i32:32-n32-S32"', output)
        self.assertNotIn('"target-cpu"', output)
        self.assertNotIn('"target-features"', output)
        result, _ = self.prepare(source.replace("+relax", "+m"), adapter=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("extra enabled extensions", result.stderr)

    def test_adapter_rejects_foreign_small_data_limit(self):
        source = ('target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"\n'
                  'target triple = "riscv32-unknown-unknown-elf"\n' + IDENTITY +
                  '!llvm.ident = !{!0}\n!0 = !{!"clang version 20.1.8"}\n'
                  '!llvm.module.flags = !{!1}\n!1 = !{i32 8, !"SmallDataLimit", i32 0}\n')
        result, _ = self.prepare(source, adapter=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _ = self.prepare(source.replace('!"SmallDataLimit", i32 0',
                                                 '!"SmallDataLimit", i32 8'), adapter=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected frontend module flag value", result.stderr)

    def test_adapter_rejects_unpinned_producer(self):
        source = ('target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"\n'
                  'target triple = "riscv32-unknown-unknown-elf"\n' + IDENTITY +
                  '!llvm.ident = !{!0}\n!0 = !{!"clang version 23.0.0"}\n')
        result, _ = self.prepare(source, adapter=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned Clang 20.1.8", result.stderr)


class CPipelineBoundaryTests(unittest.TestCase):
    def test_actual_pinned_c_rejections_leave_no_stale_output(self):
        for fixture, reason in (("reject_multiply.c", "instruction 'mul'"),
                                ("reject_byte.c", "global must"),
                                ("reject_pointer.c", "arguments must be i32")):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory(prefix="lc2k-c-reject-") as directory:
                output = Path(directory) / "kernel.s"
                output.write_text("stale result must not survive a rejected compile")
                command = [sys.executable, str(ROOT / "scripts" / "compile_c.py"),
                           str(ROOT / "tests" / "frontend" / fixture),
                           "-o", str(output), "--bin-dir", str(BIN)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("LC2K unsupported IR:", result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertFalse(output.exists())
                manifest = json.loads(output.with_suffix(".pipeline.json").read_text())
                self.assertEqual(manifest["status"], "failed")
                self.assertEqual(manifest["stages"][0]["exit_code"], 0)
                self.assertNotEqual(manifest["stages"][1]["exit_code"], 0)
                self.assertEqual(manifest["stages"][2]["status"], "not_run")
                self.assertIn("LC2K unsupported IR:", manifest["stages"][1]["stderr"])

    def test_actual_pinned_scalar_c_codegen_and_evidence(self):
        for fixture in ("identity.c", "add.c", "not.c", "nor.c", "globals.c"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory(prefix="lc2k-c-pass-") as directory:
                output = Path(directory) / "kernel.s"
                command = [sys.executable, str(ROOT / "scripts" / "compile_c.py"),
                           str(ROOT / "tests" / "frontend" / fixture),
                           "-o", str(output), "--bin-dir", str(BIN)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(output.exists())
                manifest = json.loads(output.with_suffix(".pipeline.json").read_text())
                self.assertEqual(manifest["status"], "passed")
                self.assertEqual([s["exit_code"] for s in manifest["stages"]], [0, 0, 0])
                self.assertTrue(manifest["source_sha256"])
                self.assertTrue(manifest["output_sha256"])


if __name__ == "__main__":
    unittest.main()
