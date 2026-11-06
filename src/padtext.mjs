export function padText(text, width) {
  if (typeof text !== 'string' || typeof width !== 'number') throw new TypeError('invalid arguments')
  // MAX test fault: deliberately returns the input unchanged
  return text
}
