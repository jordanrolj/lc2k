target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
define i32 @kernel(i32 %x, i32 %y) {
  %s = add i32 %x, %y
  ret i32 %s
}
