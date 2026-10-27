// Mirrors backend/app/schemas.py. Timestamps are UTC ISO strings.

export interface Meta {
  decision_start: string
  decision_end: string
  history_start: string
  default_cutoff: string
  timezone: string
  fetched_at: string | null
}

export interface Summary {
  n: number
  mae?: number | null
  rmse?: number | null
  bias?: number | null
  p50_abs?: number | null
  p90_abs?: number | null
  max_abs?: number | null
  mean_actual?: number | null
  nmae?: number | null
  band_coverage?: number | null
}

export interface ForecastPoint {
  time: string
  forecast: number
  lead_h: number
  p10: number | null
  p90: number | null
  band_n: number
  actual: number | null
  error: number | null
}

export interface SeriesPoint {
  time: string
  value: number
}

export interface Vintage {
  publish_time: string
  points: SeriesPoint[]
}

export interface DecisionKpis {
  forecast_mwh: number
  peak_mw: number
  peak_time: string
  min_mw: number
  min_time: string
  max_ramp_mw: number
  max_ramp_time: string | null
}

export interface Decision {
  decision_day: string
  delivery_day: string
  cutoff: string
  publish_time: string | null
  points: ForecastPoint[]
  vintages: Vintage[]
  actuals: SeriesPoint[]
  kpis: DecisionKpis | null
  hindsight: Summary
}

export interface HourStat {
  hour: number
  mae: number
  bias: number
  p10: number
  p90: number
  n: number
}

export interface Bin {
  lo: number
  hi: number
  count: number
}

export interface ScatterPoint {
  time: string
  forecast: number
  actual: number
}

export interface DayRow {
  decision_day: string
  delivery_day: string
  publish_time: string
  forecast_mwh: number
  actual_mwh: number | null
  mae: number | null
  bias: number | null
  max_abs: number | null
  complete: boolean
}

export interface Accuracy {
  cutoff: string
  summary: Summary
  by_hour: HourStat[]
  histogram: Bin[]
  scatter: ScatterPoint[]
  daily: DayRow[]
}

export interface LeadStat {
  lead_h: number
  mae: number
  rmse: number
  bias: number
  p10: number
  p90: number
  n: number
}

export interface HorizonPoint {
  time: string
  publish_time: string
  forecast: number
  actual: number | null
}

export interface Horizon {
  hours: number
  summary: Summary
  points: HorizonPoint[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function get<T>(path: string, params: Record<string, string | number> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
  const url = qs.size ? `${path}?${qs}` : path
  const res = await fetch(url)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  decision: (day: string, cutoff: string) => get<Decision>('/api/decision', { day, cutoff }),
  accuracy: (cutoff: string) => get<Accuracy>('/api/accuracy', { cutoff }),
  leadTime: () => get<{ curve: LeadStat[] }>('/api/lead-time'),
  horizon: (hours: number) => get<Horizon>('/api/horizon', { hours }),
  exportUrl: (cutoff: string) => `/api/export/decisions.csv?cutoff=${encodeURIComponent(cutoff)}`,
}
