target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
define i32 @kernel(i32 %x, i32 %y, i32 %z) {
entry:
  %eq = icmp eq i32 %x, %y
  br i1 %eq, label %same, label %different
same:
  %a = add i32 %x, %z
  br label %merge
different:
  %t = add i32 %y, %z
  %b = add i32 %t, 17
  br label %merge
merge:
  %r = phi i32 [%a, %same], [%b, %different]
  ret i32 %r
}
