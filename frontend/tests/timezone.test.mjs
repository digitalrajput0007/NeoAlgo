import test from 'node:test';
import assert from 'node:assert/strict';
import { formatLocalDateTime, formatLocalTime, formatLocalDate, parseToDate } from '../src/utils/timezone.ts';

test('UTC 2026-09-16T07:13:24Z renders in IST as 2026-09-16 12:43:24 PM', () => {
  const isoZ = '2026-09-16T07:13:24Z';
  assert.equal(formatLocalDateTime(isoZ), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalTime(isoZ), '12:43:24 PM');
  assert.equal(formatLocalDate(isoZ), '2026-09-16');
});

test('Midnight UTC crossing into IST (+5:30 -> next day)', () => {
  const midnightUtc = '2026-09-16T20:00:00Z';
  assert.equal(formatLocalDateTime(midnightUtc), '2026-09-17 01:30:00 AM');
  assert.equal(formatLocalTime(midnightUtc), '01:30:00 AM');
  assert.equal(formatLocalDate(midnightUtc), '2026-09-17');
});

test('Late night UTC date rollover', () => {
  const lateUtc = '2026-09-16T23:45:00Z';
  assert.equal(formatLocalDateTime(lateUtc), '2026-09-17 05:15:00 AM');
  assert.equal(formatLocalDate(lateUtc), '2026-09-17');
});

test('Timestamps with explicit +00:00 offset', () => {
  const isoPlusZero = '2026-09-16T07:13:24+00:00';
  assert.equal(formatLocalDateTime(isoPlusZero), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalTime(isoPlusZero), '12:43:24 PM');
});

test('Timestamps already containing timezone offsets (+05:30)', () => {
  const isoIst = '2026-09-16T12:43:24+05:30';
  assert.equal(formatLocalDateTime(isoIst), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalTime(isoIst), '12:43:24 PM');
});

test('Naive timestamp handling (canonical UTC storage)', () => {
  const naiveIso = '2026-09-16T07:13:24';
  const naiveSpace = '2026-09-16 07:13:24';
  assert.equal(formatLocalDateTime(naiveIso), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalDateTime(naiveSpace), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalTime(naiveIso), '12:43:24 PM');
});

test('Invalid and empty timestamp handling', () => {
  assert.equal(formatLocalDateTime(null), '—');
  assert.equal(formatLocalDateTime(undefined), '—');
  assert.equal(formatLocalDateTime(''), '—');
  assert.equal(formatLocalDateTime('invalid_date'), '—');
  assert.equal(formatLocalTime(null), '—');
  assert.equal(formatLocalTime('null'), '—');
});

test('SFeed numeric epoch timestamps', () => {
  // 1789542804 is 2026-09-16 07:13:24 UTC
  const epochSec = 1789542804;
  assert.equal(formatLocalDateTime(epochSec), '2026-09-16 12:43:24 PM');
  assert.equal(formatLocalTime(epochSec), '12:43:24 PM');
});
