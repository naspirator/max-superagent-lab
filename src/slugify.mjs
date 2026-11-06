/**
 * Convert arbitrary text into a URL-friendly slug.
 *
 * The text is lowercased, diacritics are stripped, runs of characters that
 * are not letters or digits become a single hyphen, and leading/trailing
 * hyphens are removed.
 *
 * @param {string} text
 * @returns {string}
 * @throws {TypeError} when `text` is not a string
 */
export function slugify(text) {
  if (typeof text !== 'string') {
    throw new TypeError('slugify expects a string');
  }

  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
}
