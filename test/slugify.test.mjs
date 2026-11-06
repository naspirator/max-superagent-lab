import assert from 'node:assert/strict';
import test from 'node:test';

import { slugify } from '../src/slugify.mjs';

test('converts a regular string to a slug', () => {
  assert.equal(slugify('hello world'), 'hello-world');
});

test('lowercases uppercase input', () => {
  assert.equal(slugify('Hello WORLD'), 'hello-world');
});

test('collapses extra whitespace into single hyphens', () => {
  assert.equal(slugify('  Hello   World  '), 'hello-world');
});

test('removes punctuation and other extra characters', () => {
  assert.equal(slugify('Hello, World! (2026)'), 'hello-world-2026');
});

test('throws a TypeError for non-string input', () => {
  assert.throws(() => slugify(42), TypeError);
  assert.throws(() => slugify(null), TypeError);
  assert.throws(() => slugify(undefined), TypeError);
  assert.throws(() => slugify({}), TypeError);
});
