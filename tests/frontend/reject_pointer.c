/* Must be rejected: arbitrary pointer arguments are outside the small ABI. */
unsigned kernel(unsigned *p) { return *p; }
