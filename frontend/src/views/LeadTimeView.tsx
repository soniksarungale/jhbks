import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useDeferredValue, useMemo } from 'react'
import { api } from '../api'
import { Chart } from '../components/Chart'
import { Card, Stat, Status } from '../components/ui'
import { horizonChart, leadTimeChart } from '../lib/charts'
import { gw, pct, signedMw } from '../lib/format'

interface Props {
  cutoff: string
  hours: number
  onHoursChange: (h: number) => void
}

export function LeadTimeView({ cutoff, hours, onHoursChange }: Props) {
  const curve = useQuery({ queryKey: ['lead-time'], queryFn: api.leadTime })
  // Keeps the slider responsive while the next horizon loads; each is cached.
  const deferredHours = useDeferredValue(hours)
  const horizon = useQuery({
    queryKey: ['horizon', deferredHours],
    queryFn: () => api.horizon(deferredHours),
    placeholderData: keepPreviousData,
  })

  // A forecast used at the cutoff is at least this far ahead of next-day 00:00 and 23:00.
  const curveOption = useMemo(() => {
    if (!curve.data) return undefined
    const [h, m] = cutoff.split(':').map(Number)
    const cutoffH = h + m / 60
    return leadTimeChart(curve.data.curve, [24 - cutoffH, 47 - cutoffH])
  }, [curve.data, cutoff])
  const horizonOption = useMemo(() => horizon.data && horizonChart(horizon.data), [horizon.data])
  const s = horizon.data?.summary

  return (
    <div className="stack">
      <Status loading={curve.isPending} error={curve.error ?? horizon.error} />
      {curveOption && (
        <Card
          title="How accuracy changes with lead time"
          subtitle="Error in MW of every forecast published for January delivery, grouped by how far ahead it was made. The shaded zone is the earliest lead time of a forecast used at your cutoff (later hours of the delivery day sit further right)."
        >
          <Chart option={curveOption} height={320} label="Forecast error against lead time" />
        </Card>
      )}

      <Card
        title="Forecast at a fixed horizon"
        subtitle="Hourly MW. For each hour, the latest forecast published at least this long before it."
        actions={
          <label className="slider">
            <span className="muted">Horizon</span>
            <input
              type="range"
              min={0}
              max={48}
              step={1}
              value={hours}
              onChange={(e) => onHoursChange(Number(e.target.value))}
            />
            <b>{hours} h</b>
          </label>
        }
      >
        {s && (
          <div className="stats compact">
            <Stat label="Average miss (MAE)" value={gw(s.mae)} note={`${pct(s.nmae)} of average output`} />
            <Stat label="Bias" value={signedMw(s.bias)} />
            <Stat label="RMSE" value={gw(s.rmse)} />
            <Stat label="1 hour in 10 misses by more than" value={gw(s.p90_abs)} />
          </div>
        )}
        {horizonOption && (
          <Chart option={horizonOption} height={340} label={`Forecast ${hours} hours ahead against actual`} />
        )}
        <p className="muted small">Scroll or pinch on the chart to zoom into a few days.</p>
      </Card>
    </div>
  )
}
