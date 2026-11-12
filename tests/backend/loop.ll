target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
define i32 @kernel(i32 %n, i32 %x) {
entry:
  br label %loop
loop:
  %i = phi i32 [0, %entry], [%next, %body]
  %s = phi i32 [0, %entry], [%sum, %body]
  %done = icmp eq i32 %i, %n
  br i1 %done, label %exit, label %body
body:
  %sum = add i32 %s, %x
  %next = add i32 %i, 1
  br label %loop
exit:
  ret i32 %s
}
