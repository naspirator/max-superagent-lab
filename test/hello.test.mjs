import test from "node:test";
import assert from "node:assert/strict";

import { hello } from "../src/hello.mjs";

test("hello returns a greeting for a regular name", () => {
  assert.equal(hello("Мир"), "Привет, Мир!");
});

test("hello handles an empty string", () => {
  assert.equal(hello(""), "Привет, !");
});

test("hello throws TypeError for non-string input", () => {
  for (const value of [42, null, undefined, {}, []]) {
    assert.throws(() => hello(value), TypeError);
  }
});
