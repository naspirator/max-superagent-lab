/**
 * Removes leading and trailing whitespace from a string. Whitespace inside
 * the string is left untouched.
 *
 * @param {string} text
 * @returns {string} the string without leading and trailing spaces
 * @throws {TypeError} when text is not a string
 */
export function trimSpaces(text) {
  if (typeof text !== 'string') {
    throw new TypeError('trimSpaces expects a string');
  }

  return text.trim();
}
