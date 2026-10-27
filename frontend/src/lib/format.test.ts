import { describe, expect, it } from 'vitest'
import { compact, gw, gwh, mw, pct, signedMw } from './format'

describe('number formatting', () => {
  it('formats power and energy', () => {
    expect(mw(12345.6)).toBe('12,346 MW')
    expect(gw(12345)).toBe('12.3 GW')
    expect(gwh(190330)).toBe('190 GWh')
    expect(pct(0.8615)).toBe('86%')
  })

  it('shows a dash for missing values', () => {
    expect(mw(null)).toBe('–')
    expect(gw(undefined)).toBe('–')
    expect(signedMw(Number.NaN)).toBe('–')
  })

  it('signs errors explicitly', () => {
    expect(signedMw(1250)).toBe('+1,250 MW')
    expect(signedMw(-80)).toBe('−80 MW')
    expect(signedMw(0)).toBe('0 MW')
  })

  it('compacts axis labels', () => {
    expect(compact(12000)).toBe('12k')
    expect(compact(2500)).toBe('2.5k')
    expect(compact(-1500)).toBe('-1.5k')
    expect(compact(800)).toBe('800')
  })
})
