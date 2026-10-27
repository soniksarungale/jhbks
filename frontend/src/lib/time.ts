// Everything on screen is UK local time, whatever the viewer's own timezone is.
export const UK_TZ = 'Europe/London'

const wallClockParts = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/**
 * UK wall-clock time of an instant, encoded as if it were UTC.
 *
 * Charts run with useUTC so their ticks and labels land on UK hours and
 * midnights instead of the browser's local ones.
 */
export function ukWallClock(iso: string): number {
  const p: Record<string, string> = {}
  for (const part of wallClockParts.formatToParts(new Date(iso))) p[part.type] = part.value
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute)
}

const timeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})
const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK_TZ,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})
// Calendar dates carry no timezone; format them as UTC so they never shift.
const dayFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})

export const formatTime = (iso: string) => timeFmt.format(new Date(iso))
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso)).replace(',', '')
export const formatDay = (isoDate: string) => dayFmt.format(new Date(`${isoDate}T00:00:00Z`))

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export const isValidCutoff = (value: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
