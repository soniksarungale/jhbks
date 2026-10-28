import type { EChartsOption, SeriesOption } from 'echarts'
import type { Accuracy, Decision, Horizon, LeadStat } from '../api'
import { compact, gwh, mw, signedMw } from './format'
import { formatDay, ukWallClock } from './time'

export const colors = {
  forecast: '#2a78d6',
  actual: '#eb6834',
  band: 'rgba(42, 120, 214, 0.14)',
  bandKey: 'rgba(42, 120, 214, 0.4)',
  vintage: '#b9b8b0',
  ink: '#0b0b0b',
  ink2: '#52514e',
  muted: '#898781',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  surface: '#fcfcfb',
  highlight: 'rgba(137, 135, 129, 0.08)',
}

const font = 'system-ui, -apple-system, "Segoe UI", sans-serif'

const base: EChartsOption = {
  useUTC: true, // x values are UK wall-clock encoded as UTC, see ukWallClock
  animation: false,
  textStyle: { fontFamily: font, color: colors.ink2 },
  grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
  legend: {
    top: 0,
    left: 0,
    icon: 'roundRect',
    itemWidth: 14,
    itemHeight: 3,
    textStyle: { color: colors.ink2, fontSize: 12 },
  },
  tooltip: {
    backgroundColor: colors.surface,
    borderColor: colors.grid,
    textStyle: { color: colors.ink, fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 6px;',
  },
}

const valueAxis = (name?: string) => ({
  type: 'value' as const,
  name,
  nameTextStyle: { color: colors.muted, align: 'left' as const },
  axisLabel: { color: colors.muted, formatter: (v: number) => compact(v) },
  splitLine: { lineStyle: { color: colors.grid } },
})

const timeAxis = {
  type: 'time' as const,
  axisLine: { lineStyle: { color: colors.axis } },
  axisTick: { show: false },
  axisLabel: { color: colors.muted, hideOverlap: true },
  splitLine: { show: false },
}

type Row = { label: string; value: string; color?: string }

function tooltipHtml(title: string, rows: Row[]): string {
  const body = rows
    .map(
      (r) =>
        `<div style="display:flex;gap:12px;justify-content:space-between;align-items:center">` +
        `<span>${r.color ? `<i style="display:inline-block;width:10px;height:3px;border-radius:2px;background:${r.color};margin-right:6px;vertical-align:middle"></i>` : ''}${r.label}</span>` +
        `<b style="font-variant-numeric:tabular-nums;font-weight:600">${r.value}</b></div>`,
    )
    .join('')
  return `<div style="min-width:180px"><div style="color:${colors.muted};margin-bottom:4px">${title}</div>${body}</div>`
}

const hhmm = (ms: number) => new Date(ms).toISOString().slice(11, 16)

/** Stacked pair of invisible-line series that draws a filled band between lo and hi. */
function band(name: string, points: [number, number | null, number | null][]): SeriesOption[] {
  return [
    {
      name: `${name} (base)`,
      type: 'line',
      stack: name,
      // 'all' so a negative lower bound still offsets the band (errors can be < 0)
      stackStrategy: 'all',
      symbol: 'none',
      lineStyle: { opacity: 0 },
      silent: true,
      tooltip: { show: false },
      data: points.map(([x, lo]) => [x, lo]),
    },
    {
      name,
      type: 'line',
      stack: name,
      stackStrategy: 'all',
      symbol: 'none',
      lineStyle: { opacity: 0 },
      itemStyle: { color: colors.bandKey },
      areaStyle: { color: colors.band },
      silent: true,
      data: points.map(([x, lo, hi]) => [x, lo == null || hi == null ? null : hi - lo]),
    },
  ]
}

export interface DecisionChartOptions {
  showActuals: boolean
  showVintages: boolean
}

export function decisionChart(d: Decision, opts: DecisionChartOptions): EChartsOption {
  const pts = d.points.map((p) => ({ ...p, x: ukWallClock(p.time) }))
  const byX = new Map(pts.map((p) => [p.x, p]))
  const actualByX = new Map(d.actuals.map((a) => [ukWallClock(a.time), a.value]))

  const series: SeriesOption[] = [
    ...band(
      'Likely range (P10–P90)',
      pts.map((p) => [p.x, p.p10, p.p90]),
    ),
  ]
  if (opts.showVintages) {
    d.vintages.forEach((v) =>
      series.push({
        name: 'Earlier forecasts',
        type: 'line',
        symbol: 'none',
        lineStyle: { width: 1, color: colors.vintage },
        itemStyle: { color: colors.vintage },
        emphasis: { disabled: true },
        data: v.points.map((p) => [ukWallClock(p.time), p.value]),
      }),
    )
  }
  series.push({
    name: 'Forecast',
    type: 'line',
    symbol: 'none',
    lineStyle: { width: 2, color: colors.forecast },
    itemStyle: { color: colors.forecast },
    data: pts.map((p) => [p.x, p.forecast]),
    z: 3,
  })
  if (opts.showActuals) {
    series.push({
      name: 'Actual',
      type: 'line',
      symbol: 'none',
      lineStyle: { width: 2, color: colors.actual },
      itemStyle: { color: colors.actual },
      data: d.actuals.map((a) => [ukWallClock(a.time), a.value]),
      z: 4,
    })
  }

  const legend = ['Forecast', 'Likely range (P10–P90)']
  if (opts.showVintages && d.vintages.length) legend.push('Earlier forecasts')
  if (opts.showActuals) legend.push('Actual')

  return {
    ...base,
    legend: { ...base.legend, data: legend },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: colors.axis } },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const x = Number((list[0]?.value as [number, number])?.[0])
        const hour = x - (x % 3_600_000)
        const p = byX.get(hour)
        const rows: Row[] = []
        if (p) {
          const label = hour === x ? 'Forecast' : `Forecast (${hhmm(hour)})`
          rows.push({ label, value: mw(p.forecast), color: colors.forecast })
          if (p.p10 != null && p.p90 != null)
            rows.push({ label: 'Likely range', value: `${compact(p.p10)}–${compact(p.p90)} MW` })
        }
        const a = actualByX.get(x)
        if (opts.showActuals && a != null) {
          rows.push({ label: 'Actual', value: mw(a), color: colors.actual })
          if (p && hour === x)
            rows.push({ label: 'Error (fcst − actual)', value: signedMw(p.forecast - a) })
        }
        if (p) rows.push({ label: 'Lead time', value: `${p.lead_h.toFixed(1)} h` })
        return tooltipHtml(hhmm(x), rows)
      },
    },
    xAxis: {
      ...timeAxis,
      axisLabel: { ...timeAxis.axisLabel, formatter: '{HH}:{mm}' },
    },
    yAxis: { ...valueAxis(), min: 0 },
    series,
  }
}

export function dailyEnergyChart(a: Accuracy): EChartsOption {
  const days = a.daily.map((r) => r.delivery_day)
  return {
    ...base,
    legend: { ...base.legend, data: ['Forecast at decision', 'Actual'] },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.highlight } },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const r = a.daily[list[0]?.dataIndex ?? 0]
        const diff = r.actual_mwh == null ? null : r.forecast_mwh - r.actual_mwh
        return tooltipHtml(`Delivery ${formatDay(r.delivery_day)}`, [
          { label: 'Forecast', value: gwh(r.forecast_mwh), color: colors.forecast },
          { label: 'Actual', value: gwh(r.actual_mwh), color: colors.actual },
          { label: 'Difference', value: diff == null ? '–' : `${diff > 0 ? '+' : '−'}${gwh(Math.abs(diff))}` },
          { label: 'Hourly MAE', value: mw(r.mae) },
        ])
      },
    },
    xAxis: {
      type: 'category',
      data: days,
      axisLine: { lineStyle: { color: colors.axis } },
      axisTick: { show: false },
      axisLabel: {
        color: colors.muted,
        formatter: (v: string) => formatDay(v).split(' ').slice(1).join(' '),
      },
    },
    yAxis: { ...valueAxis(), axisLabel: { color: colors.muted, formatter: (v: number) => compact(v / 1000) } },
    series: [
      {
        name: 'Forecast at decision',
        type: 'bar',
        barMaxWidth: 10,
        barGap: '20%',
        itemStyle: { color: colors.forecast, borderRadius: [4, 4, 0, 0] },
        data: a.daily.map((r) => r.forecast_mwh),
      },
      {
        name: 'Actual',
        type: 'bar',
        barMaxWidth: 10,
        itemStyle: { color: colors.actual, borderRadius: [4, 4, 0, 0] },
        data: a.daily.map((r) => r.actual_mwh),
      },
    ],
  }
}

export function hourOfDayChart(a: Accuracy): EChartsOption {
  const hours = a.by_hour.map((h) => `${String(h.hour).padStart(2, '0')}:00`)
  return {
    ...base,
    legend: { ...base.legend, data: ['Bias (mean error)', 'MAE'] },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: colors.highlight } },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const h = a.by_hour[list[0]?.dataIndex ?? 0]
        return tooltipHtml(`${hours[list[0]?.dataIndex ?? 0]} UK`, [
          { label: 'Bias', value: signedMw(h.bias), color: colors.forecast },
          { label: 'MAE', value: mw(h.mae), color: colors.ink2 },
          { label: '80% of errors within', value: `${signedMw(h.p10)} … ${signedMw(h.p90)}` },
          { label: 'Days', value: String(h.n) },
        ])
      },
    },
    xAxis: {
      type: 'category',
      data: hours,
      axisLine: { lineStyle: { color: colors.axis } },
      axisTick: { show: false },
      axisLabel: { color: colors.muted, interval: 2 },
    },
    yAxis: valueAxis(),
    series: [
      {
        name: 'Bias (mean error)',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: { color: colors.forecast, borderRadius: 4 },
        data: a.by_hour.map((h) => h.bias),
      },
      {
        name: 'MAE',
        type: 'line',
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: colors.ink2 },
        itemStyle: { color: colors.ink2, borderColor: colors.surface, borderWidth: 2 },
        data: a.by_hour.map((h) => h.mae),
      },
    ],
  }
}

export function histogramChart(a: Accuracy): EChartsOption {
  return {
    ...base,
    grid: { ...base.grid, top: 24, bottom: 28 },
    tooltip: {
      ...base.tooltip,
      trigger: 'item',
      formatter: (p) => {
        const b = a.histogram[(p as { dataIndex: number }).dataIndex]
        return tooltipHtml(`${signedMw(b.lo)} to ${signedMw(b.hi)}`, [
          { label: 'Hours', value: String(b.count) },
        ])
      },
    },
    xAxis: {
      type: 'category',
      data: a.histogram.map((b) => compact(b.lo)),
      name: 'Error (forecast − actual), MW',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { color: colors.muted },
      axisLine: { lineStyle: { color: colors.axis } },
      axisTick: { show: false },
      axisLabel: { color: colors.muted },
    },
    yAxis: valueAxis('Hours'),
    series: [
      {
        type: 'bar',
        barCategoryGap: 2,
        itemStyle: { color: colors.forecast, borderRadius: [4, 4, 0, 0] },
        data: a.histogram.map((b) => b.count),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.ink2, type: 'solid', width: 1 },
          label: { formatter: 'no error', color: colors.ink2 },
          data: [{ xAxis: a.histogram.findIndex((b) => b.lo === 0) }],
        },
      },
    ],
  }
}

export function scatterChart(a: Accuracy): EChartsOption {
  const max = Math.max(1000, ...a.scatter.flatMap((p) => [p.forecast, p.actual]))
  const top = Math.ceil(max / 2000) * 2000
  return {
    ...base,
    grid: { ...base.grid, top: 24, bottom: 24 },
    tooltip: {
      ...base.tooltip,
      trigger: 'item',
      formatter: (p) => {
        const s = a.scatter[(p as { dataIndex: number }).dataIndex]
        const x = ukWallClock(s.time)
        return tooltipHtml(`${formatDay(new Date(x).toISOString().slice(0, 10))} ${hhmm(x)}`, [
          { label: 'Forecast', value: mw(s.forecast), color: colors.forecast },
          { label: 'Actual', value: mw(s.actual) },
          { label: 'Error', value: signedMw(s.forecast - s.actual) },
        ])
      },
    },
    xAxis: {
      ...valueAxis(),
      name: 'Forecast MW',
      nameLocation: 'middle',
      nameGap: 28,
      min: 0,
      max: top,
    },
    yAxis: { ...valueAxis('Actual MW'), min: 0, max: top },
    series: [
      {
        type: 'scatter',
        symbolSize: 7,
        itemStyle: { color: colors.forecast, opacity: 0.45 },
        data: a.scatter.map((p) => [p.forecast, p.actual]),
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: colors.ink2, type: 'solid', width: 1 },
          label: { formatter: 'perfect forecast', position: 'insideEndTop', color: colors.ink2 },
          data: [[{ coord: [0, 0] }, { coord: [top, top] }]],
        },
      },
    ],
  }
}

export function leadTimeChart(curve: LeadStat[], decisionLeads?: [number, number]): EChartsOption {
  const series: SeriesOption[] = [
    ...band(
      'Middle 80% of errors',
      curve.map((c) => [c.lead_h, c.p10, c.p90]),
    ),
    {
      name: 'MAE',
      type: 'line',
      symbol: 'none',
      lineStyle: { width: 2, color: colors.ink2 },
      itemStyle: { color: colors.ink2 },
      data: curve.map((c) => [c.lead_h, c.mae]),
      markArea: decisionLeads
        ? {
            silent: true,
            itemStyle: { color: colors.highlight },
            label: { color: colors.muted, position: 'insideTop' },
            data: [[{ name: 'Your day-ahead decision', xAxis: decisionLeads[0] }, { xAxis: decisionLeads[1] }]],
          }
        : undefined,
    },
    {
      name: 'Bias',
      type: 'line',
      symbol: 'none',
      lineStyle: { width: 2, color: colors.forecast },
      itemStyle: { color: colors.forecast },
      data: curve.map((c) => [c.lead_h, c.bias]),
    },
  ]
  const byLead = new Map(curve.map((c) => [c.lead_h, c]))
  return {
    ...base,
    useUTC: false,
    legend: { ...base.legend, data: ['MAE', 'Bias', 'Middle 80% of errors'] },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: colors.axis } },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const lead = Number((list[0]?.value as [number, number])?.[0])
        const c = byLead.get(lead)
        if (!c) return ''
        return tooltipHtml(`${lead}–${lead + 1} h ahead`, [
          { label: 'MAE', value: mw(c.mae), color: colors.ink2 },
          { label: 'Bias', value: signedMw(c.bias), color: colors.forecast },
          { label: 'RMSE', value: mw(c.rmse) },
          { label: 'Middle 80%', value: `${signedMw(c.p10)} … ${signedMw(c.p90)}` },
          { label: 'Samples', value: String(c.n) },
        ])
      },
    },
    xAxis: {
      type: 'value',
      name: 'Hours ahead',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { color: colors.muted },
      min: 0,
      max: Math.max(...curve.map((c) => c.lead_h), 1),
      interval: 6,
      axisLine: { lineStyle: { color: colors.axis } },
      axisLabel: { color: colors.muted },
      splitLine: { show: false },
    },
    yAxis: valueAxis(),
    grid: { ...base.grid, bottom: 24 },
    series,
  }
}

export function horizonChart(h: Horizon): EChartsOption {
  const byX = new Map(h.points.map((p) => [ukWallClock(p.time), p]))
  return {
    ...base,
    legend: { ...base.legend, data: ['Forecast', 'Actual'] },
    tooltip: {
      ...base.tooltip,
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: colors.axis } },
      formatter: (params) => {
        const list = Array.isArray(params) ? params : [params]
        const x = Number((list[0]?.value as [number, number])?.[0])
        const p = byX.get(x)
        if (!p) return ''
        const title = `${formatDay(new Date(x).toISOString().slice(0, 10))} ${hhmm(x)}`
        return tooltipHtml(title, [
          { label: 'Forecast', value: mw(p.forecast), color: colors.forecast },
          { label: 'Actual', value: mw(p.actual), color: colors.actual },
          { label: 'Published', value: hhmm(ukWallClock(p.publish_time)) + ' ' + formatDay(new Date(ukWallClock(p.publish_time)).toISOString().slice(0, 10)) },
        ])
      },
    },
    xAxis: {
      ...timeAxis,
      axisLabel: { ...timeAxis.axisLabel, formatter: '{d} {MMM}' },
    },
    yAxis: { ...valueAxis(), min: 0 },
    dataZoom: [{ type: 'inside', filterMode: 'none' }],
    series: [
      {
        name: 'Forecast',
        type: 'line',
        symbol: 'none',
        lineStyle: { width: 1.5, color: colors.forecast },
        itemStyle: { color: colors.forecast },
        data: h.points.map((p) => [ukWallClock(p.time), p.forecast]),
      },
      {
        name: 'Actual',
        type: 'line',
        symbol: 'none',
        lineStyle: { width: 1.5, color: colors.actual },
        itemStyle: { color: colors.actual },
        data: h.points.map((p) => [ukWallClock(p.time), p.actual]),
      },
    ],
  }
}
