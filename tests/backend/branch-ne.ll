target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
define i32 @kernel(i32 %x, i32 %y, i32 %z) {
entry:
  %ne = icmp ne i32 %x, %y
  br i1 %ne, label %different, label %same
different:
  %r = xor i32 %z, -1
  ret i32 %r
same:
  %s = add i32 %z, 23
  ret i32 %s
}
