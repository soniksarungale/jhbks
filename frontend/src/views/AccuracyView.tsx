import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, type Accuracy } from '../api'
import { Chart } from '../components/Chart'
import { Card, Stat, Status } from '../components/ui'
import { dailyEnergyChart, histogramChart, hourOfDayChart, scatterChart } from '../lib/charts'
import { gw, gwh, mw, pct, signedMw } from '../lib/format'
import { formatDay, formatTime } from '../lib/time'

export function AccuracyView({ cutoff, onOpenDay }: { cutoff: string; onOpenDay: (day: string) => void }) {
  const q = useQuery({
    queryKey: ['accuracy', cutoff],
    queryFn: () => api.accuracy(cutoff),
    placeholderData: keepPreviousData,
  })
  const a = q.data
  const charts = useMemo(
    () =>
      a && {
        daily: dailyEnergyChart(a),
        hour: hourOfDayChart(a),
        hist: histogramChart(a),
        scatter: scatterChart(a),
      },
    [a],
  )

  return (
    <div className="stack">
      <Status loading={q.isPending} error={q.error} />
      {a && charts && (
        <>
          <Takeaway a={a} />
          <div className="stats">
            <Stat
              label="Average miss (MAE)"
              value={gw(a.summary.mae)}
              note={`${pct(a.summary.nmae)} of average output`}
            />
            <Stat label="Bias" value={signedMw(a.summary.bias)} note="forecast minus actual" />
            <Stat label="1 hour in 10 misses by more than" value={gw(a.summary.p90_abs)} note={`worst: ${gw(a.summary.max_abs)}`} />
            <Stat
              label="Actual inside P10–P90 range"
              value={pct(a.summary.band_coverage)}
              note="target 80%"
            />
          </div>

          <Card
            title="Daily energy: forecast at decision vs actual"
            subtitle={`GWh per delivery day. Forecast available at ${cutoff} each day, compared with what the wind actually produced the next day.`}
          >
            <Chart option={charts.daily} height={300} label="Daily forecast and actual wind energy" />
          </Card>

          <div className="grid-2">
            <Card title="Error by hour of day" subtitle="Bias and average miss in MW for each delivery hour, UK time.">
              <Chart option={charts.hour} height={280} label="Forecast error by hour of day" />
            </Card>
            <Card title="How big are the misses?" subtitle={`All ${a.summary.n} hourly errors, in 500 MW bins.`}>
              <Chart option={charts.hist} height={280} label="Distribution of forecast errors" />
            </Card>
          </div>

          <Card
            title="Forecast vs actual, every hour"
            subtitle="Points below the line are hours where less wind turned up than forecast."
          >
            <Chart option={charts.scatter} height={380} label="Scatter of forecast against actual generation" />
          </Card>

          <Card
            title="Day by day"
            subtitle="Click a row to open that decision."
            actions={
              <a className="button" href={api.exportUrl(cutoff)} download>
                Download CSV
              </a>
            }
          >
            <DailyTable a={a} onOpenDay={onOpenDay} />
          </Card>
        </>
      )}
    </div>
  )
}

function Takeaway({ a }: { a: Accuracy }) {
  const over = a.daily.filter((d) => d.bias != null && d.bias > 0).length
  const total = a.daily.filter((d) => d.bias != null).length
  const bias = a.summary.bias ?? 0
  return (
    <p className="headline">
      Using the forecast available at <b>{a.cutoff}</b>, wind was{' '}
      <b>{bias >= 0 ? 'over-forecast' : 'under-forecast'}</b> on {bias >= 0 ? over : total - over} of{' '}
      {total} days, by <b>{gw(Math.abs(bias))}</b> on average. Plan for that gap: on a typical
      day it is the extra power that has to be bought elsewhere.
    </p>
  )
}

function DailyTable({ a, onOpenDay }: { a: Accuracy; onOpenDay: (day: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="clickable">
        <thead>
          <tr>
            <th>Decision</th>
            <th>Delivery</th>
            <th>Forecast from</th>
            <th>Forecast</th>
            <th>Actual</th>
            <th>MAE</th>
            <th>Bias</th>
            <th>Worst hour</th>
          </tr>
        </thead>
        <tbody>
          {a.daily.map((r) => (
            <tr
              key={r.decision_day}
              onClick={() => onOpenDay(r.decision_day)}
              onKeyDown={(e) => e.key === 'Enter' && onOpenDay(r.decision_day)}
              tabIndex={0}
            >
              <td>{formatDay(r.decision_day)}</td>
              <td>{formatDay(r.delivery_day)}</td>
              <td>{formatTime(r.publish_time)}</td>
              <td>{gwh(r.forecast_mwh)}</td>
              <td>{gwh(r.actual_mwh)}</td>
              <td>{mw(r.mae)}</td>
              <td>{signedMw(r.bias)}</td>
              <td>{mw(r.max_abs)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
