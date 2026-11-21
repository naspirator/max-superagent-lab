export function hello(name) {
  if (typeof name !== "string") {
    throw new TypeError("name must be a string");
  }

  return `Привет, ${name}!`;
}
