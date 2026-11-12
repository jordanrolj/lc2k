target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
define i32 @kernel(i32 %x, i32 %y) {
  %o = or i32 %x, %y
  %n = xor i32 %o, -1
  ret i32 %n
}
