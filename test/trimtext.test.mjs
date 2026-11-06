import test from 'node:test';
import assert from 'node:assert/strict';

import { trimSpaces } from '../src/trimtext.mjs';

test('removes spaces at the start and end of a string', () => {
  assert.equal(trimSpaces('  hello world  '), 'hello world');
  assert.equal(trimSpaces('   leading'), 'leading');
  assert.equal(trimSpaces('trailing   '), 'trailing');
});

test('returns a string without surrounding spaces unchanged', () => {
  assert.equal(trimSpaces('hello'), 'hello');
  assert.equal(trimSpaces('hello world'), 'hello world');
});

test('returns an empty string for an empty string', () => {
  assert.equal(trimSpaces(''), '');
});

test('throws TypeError for non-string input', () => {
  assert.throws(() => trimSpaces(42), TypeError);
  assert.throws(() => trimSpaces(null), TypeError);
  assert.throws(() => trimSpaces(undefined), TypeError);
  assert.throws(() => trimSpaces(['hello']), TypeError);
});
