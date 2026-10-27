const int = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 })
const oneDp = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

const isNum = (v: number | null | undefined): v is number => v != null && Number.isFinite(v)

export const mw = (v: number | null | undefined) => (isNum(v) ? `${int.format(v)} MW` : '–')

export const gw = (v: number | null | undefined) => (isNum(v) ? `${oneDp.format(v / 1000)} GW` : '–')

export const gwh = (mwh: number | null | undefined) =>
  isNum(mwh) ? `${int.format(mwh / 1000)} GWh` : '–'

export const pct = (v: number | null | undefined) =>
  isNum(v) ? `${int.format(v * 100)}%` : '–'

/** Signed MW, e.g. "+1,250 MW". Positive error means wind under-delivered. */
export const signedMw = (v: number | null | undefined) =>
  isNum(v) ? `${v > 0 ? '+' : v < 0 ? '−' : ''}${int.format(Math.abs(v))} MW` : '–'

/** Compact axis label: 12000 -> "12k". */
export const compact = (v: number) =>
  Math.abs(v) >= 1000 ? `${oneDp.format(v / 1000).replace(/\.0$/, '')}k` : int.format(v)
