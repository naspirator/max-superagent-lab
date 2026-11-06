import test from 'node:test';
import assert from 'node:assert/strict';

import { add, multiply } from '../src/math.mjs';

test('add handles positive numbers', () => {
  assert.equal(add(2, 3), 5);
});

test('add handles zero', () => {
  assert.equal(add(0, 0), 0);
  assert.equal(add(7, 0), 7);
});

test('add handles negative numbers', () => {
  assert.equal(add(-2, -3), -5);
  assert.equal(add(-2, 3), 1);
});

test('multiply handles positive numbers', () => {
  assert.equal(multiply(2, 3), 6);
});

test('multiply handles zero', () => {
  assert.equal(multiply(0, 5), 0);
  assert.equal(multiply(5, 0), 0);
});

test('multiply handles negative numbers', () => {
  assert.equal(multiply(-2, 3), -6);
  assert.equal(multiply(-2, -3), 6);
});
