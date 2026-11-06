import test from 'node:test';
import assert from 'node:assert/strict';

import { reverseText } from '../src/strings.mjs';

test('reverses an ordinary string', () => {
  assert.equal(reverseText('hello'), 'olleh');
  assert.equal(reverseText('abc def'), 'fed cba');
  assert.equal(reverseText('a'), 'a');
});

test('reverses an empty string', () => {
  assert.equal(reverseText(''), '');
});

test('reverses Unicode text by code points', () => {
  assert.equal(reverseText('привет'), 'тевирп');
  assert.equal(reverseText('日本語'), '語本日');
  // Surrogate pairs are kept intact instead of being split in half.
  assert.equal(reverseText('a😀b'), 'b😀a');
  assert.equal(reverseText('😀😁😂'), '😂😁😀');
});

test('throws TypeError for non-strings', () => {
  for (const value of [undefined, null, 42, true, {}, [], Symbol('s')]) {
    assert.throws(() => reverseText(value), TypeError);
  }
});

test('throws TypeError with a descriptive message', () => {
  assert.throws(() => reverseText(42), {
    name: 'TypeError',
    message: 'reverseText expects a string',
  });
});
