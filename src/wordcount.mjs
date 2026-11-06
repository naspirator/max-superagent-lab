/**
 * Counts the words in a string. Words are separated by whitespace;
 * leading, trailing and repeated whitespace does not produce empty words.
 *
 * @param {string} text
 * @returns {number}
 * @throws {TypeError} when text is not a string
 */
export function countWords(text) {
  if (typeof text !== 'string') {
    throw new TypeError('countWords expects a string');
  }

  const trimmed = text.trim();
  if (trimmed === '') {
    return 0;
  }

  return trimmed.split(/\s+/).length;
}
