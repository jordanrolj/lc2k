/* Must be rejected: byte objects/loads do not satisfy the word-memory contract. */
unsigned char bytes[4] = {1, 2, 3, 4};
unsigned kernel(unsigned a) { return bytes[0] + a; }
