import assert from 'node:assert/strict';
import test from 'node:test';

import { padText } from '../src/padtext.mjs';

test('pads a string with spaces on the right to the requested width', () => {
  assert.equal(padText('abc', 6), 'abc   ');
  assert.equal(padText('', 3), '   ');
  assert.equal(padText('hello', 5), 'hello');
});

test('returns the original string when width is not greater than its length', () => {
  assert.equal(padText('abcdef', 3), 'abcdef');
  assert.equal(padText('abcdef', 6), 'abcdef');
  assert.equal(padText('abcdef', 0), 'abcdef');
  assert.equal(padText('abcdef', -2), 'abcdef');
});

test('throws TypeError for a non-string text', () => {
  assert.throws(() => padText(42, 5), TypeError);
  assert.throws(() => padText(null, 5), TypeError);
  assert.throws(() => padText(undefined, 5), TypeError);
});

test('throws TypeError for a non-numeric width', () => {
  assert.throws(() => padText('abc', '5'), TypeError);
  assert.throws(() => padText('abc', null), TypeError);
  assert.throws(() => padText('abc'), TypeError);
});

test('throws TypeError for NaN and Infinity widths', () => {
  assert.throws(() => padText('abc', NaN), TypeError);
  assert.throws(() => padText('abc', Infinity), TypeError);
  assert.throws(() => padText('abc', -Infinity), TypeError);
});

test('truncates a fractional width like String#padEnd', () => {
  assert.equal(padText('abc', 5.9), 'abc  ');
  assert.equal(padText('abc', 4.1), 'abc ');
  assert.equal(padText('abc', 3.9), 'abc');
});
