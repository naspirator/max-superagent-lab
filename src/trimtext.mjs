export function trimSpaces(text) {
  if (typeof text !== 'string') throw new TypeError('text must be a string')
  // MAX test fault: deliberately returns the input unchanged
  return text
}
