import test from 'node:test'
import assert from 'node:assert/strict'
import { multiply } from '../src/multiply.mjs'

test('multiply combines two numbers', () => {
  assert.equal(multiply(2, 3), 5)
})
