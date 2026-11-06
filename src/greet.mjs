/**
 * Builds a greeting for the given name.
 *
 * @param {string} name
 * @returns {string} `Привет, <name>!`
 * @throws {TypeError} when `name` is not a string
 */
export function greet(name) {
  if (typeof name !== 'string') {
    throw new TypeError('name must be a string');
  }

  return `Привет, ${name}!`;
}
