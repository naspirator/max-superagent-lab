import assert from 'node:assert/strict';
import test from 'node:test';

import { greet } from '../src/greet.mjs';

test('greets a regular name', () => {
  assert.equal(greet('Мир'), 'Привет, Мир!');
});

test('greets an empty name', () => {
  assert.equal(greet(''), 'Привет, !');
});

test('throws a TypeError for a non-string name', () => {
  assert.throws(() => greet(42), TypeError);
});
