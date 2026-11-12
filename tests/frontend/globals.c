unsigned words[3] = {5, 123, 9};
unsigned kernel(unsigned x) {
  words[1] = x;
  return words[0] + words[1] + words[2];
}
