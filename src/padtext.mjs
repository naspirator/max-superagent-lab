/**
 * Pads a string with spaces on the right up to the requested width.
 *
 * @param {string} text - The string to pad.
 * @param {number} width - The target width in characters. Fractional values are
 *   truncated, matching `String#padEnd`.
 * @returns {string} The padded string, or the original string when it is
 *   already at least `width` characters long.
 * @throws {TypeError} When `text` is not a string or `width` is not a finite number
 *   (including `NaN`, `Infinity` and non-number values).
 */
export function padText(text, width) {
  if (typeof text !== 'string') {
    throw new TypeError('text must be a string');
  }

  if (typeof width !== 'number' || !Number.isFinite(width)) {
    throw new TypeError('width must be a finite number');
  }

  const targetWidth = Math.max(0, Math.trunc(width));
  if (targetWidth <= text.length) {
    return text;
  }

  return text + ' '.repeat(targetWidth - text.length);
}
