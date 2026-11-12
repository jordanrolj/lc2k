target triple = "lc2k-unknown-none"
target datalayout = "e-p:32:32-i32:32-n32-S32"
@a = global [4 x i32] [i32 11, i32 22, i32 33, i32 44], align 4
@other = global i32 91, align 4
define i32 @kernel(i32 %x) {
  %first = load i32, ptr @a, align 4
  %middle = load i32, ptr getelementptr ([4 x i32], ptr @a, i32 0, i32 2), align 4
  %last = load i32, ptr getelementptr ([4 x i32], ptr @a, i32 0, i32 3), align 4
  store i32 %x, ptr getelementptr ([4 x i32], ptr @a, i32 0, i32 1), align 4
  %neighbor = load i32, ptr getelementptr ([4 x i32], ptr @a, i32 0, i32 2), align 4
  %separate = load i32, ptr @other, align 4
  %s0 = add i32 %first, %middle
  %s1 = add i32 %last, %neighbor
  %s2 = add i32 %s0, %s1
  %s3 = add i32 %s2, %separate
  %r = add i32 %s3, %x
  ret i32 %r
}
