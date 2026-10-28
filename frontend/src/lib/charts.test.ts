import { describe, expect, it } from 'vitest'
import type { SeriesOption } from 'echarts'
import type { Decision } from '../api'
import { decisionChart, leadTimeChart } from './charts'

const decision: Decision = {
  decision_day: '2026-01-15',
  delivery_day: '2026-01-16',
  cutoff: '2026-01-15T09:20:00Z',
  publish_time: '2026-01-15T07:30:00Z',
  points: [
    { time: '2026-01-16T00:00:00Z', forecast: 7000, lead_h: 16.5, p10: 5000, p90: 8000, band_n: 100, actual: 7200, error: -200 },
    { time: '2026-01-16T01:00:00Z', forecast: 7100, lead_h: 17.5, p10: null, p90: null, band_n: 0, actual: null, error: null },
  ],
  vintages: [
    { publish_time: '2026-01-15T04:30:00Z', points: [{ time: '2026-01-16T00:00:00Z', value: 6800 }] },
  ],
  actuals: [{ time: '2026-01-16T00:00:00Z', value: 7200 }],
  kpis: null,
  hindsight: { n: 1 },
}

const names = (series: SeriesOption[]) => series.map((s) => s.name)

describe('decisionChart', () => {
  it('stacks the band as P10 plus the P10–P90 width', () => {
    const series = decisionChart(decision, { showActuals: true, showVintages: true })
      .series as SeriesOption[]
    const [lower, width] = series
    expect(lower.data).toEqual([
      [Date.UTC(2026, 0, 16, 0), 5000],
      [Date.UTC(2026, 0, 16, 1), null],
    ])
    expect(width.data).toEqual([
      [Date.UTC(2026, 0, 16, 0), 3000],
      [Date.UTC(2026, 0, 16, 1), null],
    ])
  })

  it('drops toggled-off layers', () => {
    const all = decisionChart(decision, { showActuals: true, showVintages: true }).series as SeriesOption[]
    const bare = decisionChart(decision, { showActuals: false, showVintages: false }).series as SeriesOption[]
    expect(names(all)).toContain('Actual')
    expect(names(all)).toContain('Earlier forecasts')
    expect(names(bare)).not.toContain('Actual')
    expect(names(bare)).not.toContain('Earlier forecasts')
  })
})

describe('leadTimeChart', () => {
  it('stacks the error band across zero', () => {
    const curve = [{ lead_h: 0, mae: 500, rmse: 600, bias: 100, p10: -300, p90: 900, n: 10 }]
    const [lower, width] = leadTimeChart(curve).series as SeriesOption[]
    // With the default 'samesign' stacking a negative base would not offset the band.
    expect(lower).toMatchObject({ stackStrategy: 'all', data: [[0, -300]] })
    expect(width).toMatchObject({ stackStrategy: 'all', data: [[0, 1200]] })
  })
})
