/** @param {string} value @returns {string} reversed text */
export function reverseText(value) {
  if (typeof value !== 'string') throw new TypeError('value must be a string')
  // Deliberate defect for the fix-loop test: returns the input unchanged.
  return value
}
