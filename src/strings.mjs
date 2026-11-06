/**
 * Reverses a string by Unicode code points.
 *
 * Code points (rather than UTF-16 code units) are reversed so that surrogate
 * pairs such as emoji stay intact. Combining marks and other multi-code-point
 * grapheme clusters are not reordered as visual units.
 *
 * @param {string} value String to reverse.
 * @returns {string} Reversed string.
 * @throws {TypeError} If `value` is not a string.
 */
export function reverseText(value) {
  if (typeof value !== 'string') {
    throw new TypeError('reverseText expects a string');
  }

  return Array.from(value).reverse().join('');
}
