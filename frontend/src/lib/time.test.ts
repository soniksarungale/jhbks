import { describe, expect, it } from 'vitest'
import { addDays, formatDay, formatTime, isValidCutoff, ukWallClock } from './time'

describe('ukWallClock', () => {
  it('is unchanged in winter (GMT)', () => {
    expect(ukWallClock('2026-01-15T07:30:00Z')).toBe(Date.UTC(2026, 0, 15, 7, 30))
  })

  it('shifts by an hour in summer (BST)', () => {
    expect(ukWallClock('2026-07-15T07:30:00Z')).toBe(Date.UTC(2026, 6, 15, 8, 30))
  })
})

describe('formatting', () => {
  it('formats times in UK time', () => {
    expect(formatTime('2026-07-15T23:30:00Z')).toBe('00:30')
  })

  it('formats calendar days without shifting them', () => {
    expect(formatDay('2026-01-15')).toBe('Thu 15 Jan')
  })
})

describe('addDays', () => {
  it('crosses month boundaries', () => {
    expect(addDays('2026-01-31', 1)).toBe('2026-02-01')
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31')
  })
})

describe('isValidCutoff', () => {
  it.each(['09:20', '00:00', '23:59'])('accepts %s', (v) => expect(isValidCutoff(v)).toBe(true))
  it.each(['9:20', '24:00', '09:60', '', 'noon'])('rejects %s', (v) =>
    expect(isValidCutoff(v)).toBe(false),
  )
})
