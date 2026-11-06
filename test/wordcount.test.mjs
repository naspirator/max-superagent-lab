import test from 'node:test';
import assert from 'node:assert/strict';

import { countWords } from '../src/wordcount.mjs';

test('counts words in ordinary text', () => {
  assert.equal(countWords('Hello world'), 2);
  assert.equal(countWords('one two three'), 3);
});

test('returns 0 for an empty string', () => {
  assert.equal(countWords(''), 0);
});

test('handles multiple and surrounding spaces', () => {
  assert.equal(countWords('  hello   world  '), 2);
  assert.equal(countWords('   '), 0);
});

test('throws TypeError for non-string input', () => {
  assert.throws(() => countWords(42), TypeError);
  assert.throws(() => countWords(null), TypeError);
  assert.throws(() => countWords(undefined), TypeError);
  assert.throws(() => countWords(['one', 'two']), TypeError);
});
