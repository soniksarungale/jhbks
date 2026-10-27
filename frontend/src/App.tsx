import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Meta } from './api'
import { Status } from './components/ui'
import { isValidCutoff } from './lib/time'
import { useUrlParams } from './lib/urlState'
import { AccuracyView } from './views/AccuracyView'
import { DecisionView } from './views/DecisionView'
import { LeadTimeView } from './views/LeadTimeView'

const views = [
  { id: 'decision', label: 'Day-ahead decision' },
  { id: 'accuracy', label: 'Forecast accuracy' },
  { id: 'lead-time', label: 'Lead time' },
] as const
type ViewId = (typeof views)[number]['id']

export default function App() {
  const meta = useQuery({ queryKey: ['meta'], queryFn: api.meta, staleTime: Infinity })

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden />
          <div>
            <h1>WindSight</h1>
            <p className="muted">GB wind forecasts for day-ahead purchasing</p>
          </div>
        </div>
      </header>
      {meta.data ? <Main meta={meta.data} /> : <Status loading={meta.isPending} error={meta.error} />}
      <footer className="foot muted small">
        Data: Elexon BMRS — wind outturn (FUELHH) and national wind forecast (WINDFOR). All times UK.
        {meta.data?.fetched_at && <> Data fetched {meta.data.fetched_at.slice(0, 10)}.</>}
      </footer>
    </div>
  )
}

function Main({ meta }: { meta: Meta }) {
  const [params, setParams] = useUrlParams()

  const view = (views.find((v) => v.id === params.get('view'))?.id ?? 'decision') as ViewId
  const cutoffParam = params.get('cutoff')
  const cutoff = cutoffParam && isValidCutoff(cutoffParam) ? cutoffParam : meta.default_cutoff
  const dayParam = params.get('day')
  const day =
    dayParam && dayParam >= meta.decision_start && dayParam <= meta.decision_end
      ? dayParam
      : meta.decision_start
  const hours = Math.min(48, Math.max(0, Number(params.get('h') ?? 24) || 0))

  return (
    <>
      <nav className="tabs-row">
        <div className="tabs" role="tablist">
          {views.map((v) => (
            <button
              key={v.id}
              role="tab"
              aria-selected={v.id === view}
              className={v.id === view ? 'tab active' : 'tab'}
              onClick={() => setParams({ view: v.id })}
            >
              {v.label}
            </button>
          ))}
        </div>
        <CutoffInput
          key={cutoff}
          value={cutoff}
          isDefault={cutoff === meta.default_cutoff}
          onChange={(c) => setParams({ cutoff: c === meta.default_cutoff ? null : c })}
        />
      </nav>
      <main>
        {view === 'decision' && (
          <DecisionView meta={meta} day={day} cutoff={cutoff} onDayChange={(d) => setParams({ day: d })} />
        )}
        {view === 'accuracy' && (
          <AccuracyView cutoff={cutoff} onOpenDay={(d) => setParams({ view: 'decision', day: d })} />
        )}
        {view === 'lead-time' && (
          <LeadTimeView cutoff={cutoff} hours={hours} onHoursChange={(h) => setParams({ h: String(h) })} />
        )}
      </main>
    </>
  )
}

function CutoffInput({
  value,
  isDefault,
  onChange,
}: {
  value: string
  isDefault: boolean
  onChange: (v: string) => void
}) {
  // Local draft so typing "0" then "9" doesn't refetch on every keystroke.
  // The parent keys this component on the committed value to reset it.
  const [draft, setDraft] = useState(value)

  const commit = () => (isValidCutoff(draft) ? onChange(draft) : setDraft(value))

  return (
    <label className="cutoff" title="When the desk commits its day-ahead purchase. Default is the EPEX GB day-ahead auction gate closure.">
      <span className="muted">Decision cutoff</span>
      <input
        type="time"
        step={300}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
      />
      <span className="muted small">{isDefault ? 'gate closure' : 'custom'}</span>
    </label>
  )
}
