"""Failure-path acceptance for the runtime ABI boundary; no compiler needed."""
import unittest
from harness.backend import execute, check_result

class WrapperTests(unittest.TestCase):
    def test_real_return(self):
        result, _ = execute('kentry add 1 2 1\n        jalr 7 4\n', (5,7))
        check_result(result.registers[1],12)
        self.assertEqual(result.pc,7)

    def test_early_halt_rejected(self):
        with self.assertRaisesRegex(AssertionError,"did not return"):
            execute('kentry halt\n',(123,))

    def test_ignored_write_to_zero_rejected(self):
        with self.assertRaisesRegex(AssertionError,"reserved register r0"):
            execute('kentry add 0 0 0\n        jalr 7 4\n',(123,))

    def test_restoring_reserved_register_still_rejected(self):
        with self.assertRaisesRegex(AssertionError,"reserved register r5"):
            execute('kentry add 5 0 5\n        jalr 7 4\n')

    def test_timeout_rejected(self):
        with self.assertRaisesRegex(AssertionError,"timeout"):
            execute('kentry beq 0 0 -1\n',max_steps=30)

    def test_bad_argument_count(self):
        with self.assertRaisesRegex(ValueError,"three"):
            execute('kentry jalr 7 4\n',(1,2,3,4))

    def test_wrong_output_rejected(self):
        result, _ = execute('kentry jalr 7 4\n',(123,))
        with self.assertRaisesRegex(AssertionError,"expected"):
            check_result(result.registers[1],124)
