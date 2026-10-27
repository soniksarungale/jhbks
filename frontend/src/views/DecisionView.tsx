import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, type Decision, type Meta } from '../api'
import { Chart } from '../components/Chart'
import { Card, Stat, Status, Toggle } from '../components/ui'
import { decisionChart } from '../lib/charts'
import { gw, gwh, mw, pct, signedMw } from '../lib/format'
import { addDays, formatDateTime, formatDay, formatTime } from '../lib/time'

interface Props {
  meta: Meta
  day: string
  cutoff: string
  onDayChange: (day: string) => void
}

const decisionQuery = (day: string, cutoff: string) => ({
  queryKey: ['decision', day, cutoff],
  queryFn: () => api.decision(day, cutoff),
})

export function DecisionView({ meta, day, cutoff, onDayChange }: Props) {
  const [showActuals, setShowActuals] = useState(true)
  const [showVintages, setShowVintages] = useState(true)
  const [showTable, setShowTable] = useState(false)

  const q = useQuery({ ...decisionQuery(day, cutoff), placeholderData: keepPreviousData })
  const qc = useQueryClient()

  const prev = day > meta.decision_start ? addDays(day, -1) : null
  const next = day < meta.decision_end ? addDays(day, 1) : null

  // Warm the neighbouring days so stepping through the month feels instant.
  useEffect(() => {
    for (const d of [prev, next]) if (d) void qc.prefetchQuery(decisionQuery(d, cutoff))
  }, [qc, prev, next, cutoff])

  const d = q.data
  const option = useMemo(
    () => (d ? decisionChart(d, { showActuals, showVintages }) : null),
    [d, showActuals, showVintages],
  )

  return (
    <div className="stack">
      <div className="toolbar">
        <div className="day-nav">
          <button type="button" onClick={() => prev && onDayChange(prev)} disabled={!prev} aria-label="Previous day">
            ‹
          </button>
          <label>
            <span className="muted">Decision day</span>
            <input
              type="date"
              value={day}
              min={meta.decision_start}
              max={meta.decision_end}
              onChange={(e) => e.target.value && onDayChange(e.target.value)}
            />
          </label>
          <button type="button" onClick={() => next && onDayChange(next)} disabled={!next} aria-label="Next day">
            ›
          </button>
        </div>
        <Status loading={q.isPending} error={q.error} />
      </div>

      {d && <Headline d={d} cutoff={cutoff} />}

      {d?.kpis && (
        <div className="stats">
          <Stat label="Forecast wind energy" value={gwh(d.kpis.forecast_mwh)} note={`for ${formatDay(d.delivery_day)}`} />
          <Stat label="Peak" value={gw(d.kpis.peak_mw)} note={`at ${formatTime(d.kpis.peak_time)}`} />
          <Stat label="Lowest" value={gw(d.kpis.min_mw)} note={`at ${formatTime(d.kpis.min_time)}`} />
          <Stat
            label="Largest hourly ramp"
            value={mw(d.kpis.max_ramp_mw)}
            note={d.kpis.max_ramp_time ? `into ${formatTime(d.kpis.max_ramp_time)}` : undefined}
          />
        </div>
      )}

      {d && option && (
        <Card
          title={`Wind forecast for ${formatDay(d.delivery_day)}`}
          subtitle="Hourly national wind generation, UK time. The shaded range is where 8 in 10 outcomes landed for forecasts made this far ahead, using only errors already known at the decision time."
          actions={
            <>
              <Toggle checked={showVintages} onChange={setShowVintages}>
                Earlier forecasts
              </Toggle>
              <Toggle checked={showActuals} onChange={setShowActuals}>
                Actual (hindsight)
              </Toggle>
            </>
          }
        >
          <Chart option={option} height={360} label={`Wind forecast and actual generation for ${d.delivery_day}`} />
          {showActuals && d.hindsight.n > 0 && (
            <div className="hindsight">
              <span className="muted">In hindsight:</span>
              <span>
                average miss <b>{mw(d.hindsight.mae)}</b>
              </span>
              <span>
                bias <b>{signedMw(d.hindsight.bias)}</b>
              </span>
              <span>
                actual inside range <b>{pct(d.hindsight.band_coverage)}</b> of hours
              </span>
            </div>
          )}
          <button type="button" className="link" onClick={() => setShowTable((v) => !v)}>
            {showTable ? 'Hide' : 'Show'} hourly table
          </button>
          {showTable && <HourlyTable d={d} showActuals={showActuals} />}
        </Card>
      )}
    </div>
  )
}

function Headline({ d, cutoff }: { d: Decision; cutoff: string }) {
  if (!d.publish_time) {
    return (
      <p className="headline">
        No forecast had been published by {cutoff} on {formatDay(d.decision_day)}.
      </p>
    )
  }
  const ageMin = Math.round((Date.parse(d.cutoff) - Date.parse(d.publish_time)) / 60000)
  const age = ageMin >= 60 ? `${Math.floor(ageMin / 60)} h ${ageMin % 60} min` : `${ageMin} min`
  return (
    <p className="headline">
      At <b>{cutoff}</b> on {formatDay(d.decision_day)}, the latest wind forecast was published at{' '}
      <b>{formatDateTime(d.publish_time)}</b> ({age} earlier). It covers delivery on{' '}
      <b>{formatDay(d.delivery_day)}</b>, {d.points[0]?.lead_h.toFixed(1)}–
      {d.points.at(-1)?.lead_h.toFixed(1)} h ahead.
    </p>
  )
}

function HourlyTable({ d, showActuals }: { d: Decision; showActuals: boolean }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Hour (UK)</th>
            <th>Forecast</th>
            <th>P10</th>
            <th>P90</th>
            {showActuals && <th>Actual</th>}
            {showActuals && <th>Error</th>}
          </tr>
        </thead>
        <tbody>
          {d.points.map((p) => (
            <tr key={p.time}>
              <td>{formatTime(p.time)}</td>
              <td>{mw(p.forecast)}</td>
              <td>{mw(p.p10)}</td>
              <td>{mw(p.p90)}</td>
              {showActuals && <td>{mw(p.actual)}</td>}
              {showActuals && <td>{signedMw(p.error)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
