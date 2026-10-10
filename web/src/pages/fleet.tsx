// Fleet UI (DESIGN.md §1, §2, §6, §11). Opereit-style simplicity and warmth.
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ArrowRight, Bot, CheckCircle2, Play, Search, ShieldAlert, ShieldCheck } from 'lucide-react'
import { api, useEvents, useRuns, type MirageEvent, type Run } from '@/api/client'
import { resetStream, useNow } from '@/api/stream'
import { useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { Button } from '@/components/ui/button'
import { avatarState, relTime, rowSentence, runLabel, steps } from '@/lib/runs'
import './fleet.css'

export function Fleet() {
  const { data: runs = [], isPending, isError, error } = useRuns()
  const { data: events = [] } = useEvents()
  const now = useNow()
  const navigate = useNavigate()
  const ask = useAsk()

  const [filterTab, setFilterTab] = useState<'all' | 'running' | 'frozen'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selected, setSelected] = useState(-1)
  const [startingDemo, setStartingDemo] = useState(false)

  // Keyboard navigation: J/K move, Enter opens, U unfreezes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!runs.length || e.metaKey || e.ctrlKey || e.altKey || document.querySelector('[role=dialog]')) return
      if (e.target instanceof HTMLElement && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return
      const run = runs[selected]
      if (e.key === 'j') setSelected((i) => Math.min(i + 1, runs.length - 1))
      else if (e.key === 'k') setSelected((i) => Math.max(i - 1, 0))
      else if (e.key === 'Enter' && run) navigate(`/runs/${run.id}`)
      else if (e.key === 'u' && run?.status === 'frozen') ask('unfreeze', run)
      else if (e.key === 'Escape') setSelected(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [runs, selected, navigate, ask])

  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (filterTab === 'running' && r.status !== 'running') return false
      if (filterTab === 'frozen' && r.status !== 'frozen') return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const nameMatch = r.agent.toLowerCase().includes(q) || r.id.toLowerCase().includes(q)
        const taskMatch = r.task.toLowerCase().includes(q)
        if (!nameMatch && !taskMatch) return false
      }
      return true
    })
  }, [runs, filterTab, searchQuery])

  const stats = useMemo(() => {
    const active = runs.filter((r) => r.status === 'running').length
    const frozen = runs.filter((r) => r.status === 'frozen').length
    const completed = runs.filter((r) => r.status === 'completed').length
    const toolCalls = runs.reduce((acc, r) => acc + (r.tool_calls || 0), 0)
    return { active, frozen, completed, toolCalls, total: runs.length }
  }, [runs])

  const handleStartDemo = async () => {
    setStartingDemo(true)
    try {
      await api('/demo/start', {})
      resetStream()
      toast.success('Started 4-agent demo fleet')
    } catch (e: any) {
      toast.error(e?.message || 'Could not start demo')
    } finally {
      setStartingDemo(false)
    }
  }

  if (isPending) return <Skeleton />
  if (isError) {
    return (
      <div className="fleet-page">
        <div className="fleet-container">
          <div className="fleet-empty">
            <h3>Can't reach the Mirage engine</h3>
            <p>{error.message}</p>
            <Button variant="secondary" onClick={() => location.reload()}>
              Try again
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <section className="fleet-page" aria-label="Agent Fleet">
      <div className="fleet-container">
        {/* Header summary & action */}
        <div className="fleet-header">
          <div className="fleet-title-group">
            <h2>Agent Fleet</h2>
            <p>Real-time protection and transparent observability for autonomous agents.</p>
          </div>
          <div className="fleet-actions">
            <button
              type="button"
              className="fleet-btn fleet-btn-secondary"
              onClick={handleStartDemo}
              disabled={startingDemo}
            >
              <Play size={13} fill="currentColor" />
              {startingDemo ? 'Starting…' : 'Run 4-agent demo'}
            </button>
            <Button asChild variant="primary">
              <Link to="/">Ask Miragio</Link>
            </Button>
          </div>
        </div>

        {/* Fleet KPI cards */}
        <div className="fleet-stats-grid">
          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Active Agents</span>
              <Bot size={15} color="var(--fleet-muted)" />
            </div>
            <div className="fleet-stat-value">{stats.active}</div>
            <div className="fleet-stat-sub">Parallel background workers</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Safeguard Freezes</span>
              <ShieldAlert size={15} color={stats.frozen > 0 ? 'var(--fleet-alarm)' : 'var(--fleet-muted)'} />
            </div>
            <div className="fleet-stat-value" style={{ color: stats.frozen > 0 ? 'var(--fleet-alarm)' : 'inherit' }}>
              {stats.frozen}
            </div>
            <div className="fleet-stat-sub">Held safely for human verification</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Completed Tasks</span>
              <CheckCircle2 size={15} color="var(--fleet-emerald)" />
            </div>
            <div className="fleet-stat-value">{stats.completed}</div>
            <div className="fleet-stat-sub">Cleanly finished workflows</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Tool Calls Gated</span>
              <ShieldCheck size={15} color="var(--fleet-mirage)" />
            </div>
            <div className="fleet-stat-value" style={{ color: 'var(--fleet-mirage)' }}>
              {stats.toolCalls}
            </div>
            <div className="fleet-stat-sub">Pre-execution policy checks</div>
          </div>
        </div>

        {/* Toolbar & Filter Tabs */}
        <div className="fleet-toolbar">
          <div className="fleet-tabs">
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'all' ? 'active' : ''}`}
              onClick={() => setFilterTab('all')}
            >
              All Runs ({runs.length})
            </button>
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'running' ? 'active' : ''}`}
              onClick={() => setFilterTab('running')}
            >
              Working ({stats.active})
            </button>
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'frozen' ? 'active' : ''}`}
              onClick={() => setFilterTab('frozen')}
            >
              Frozen ({stats.frozen})
            </button>
          </div>

          <div className="fleet-search-wrap">
            <Search size={14} className="fleet-search-icon" />
            <input
              type="search"
              className="fleet-search-input"
              placeholder="Filter by agent or task…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Fleet Table Card */}
        <div className="fleet-card">
          {filteredRuns.length === 0 ? (
            <div className="fleet-empty">
              <h3>No agents matching current filter</h3>
              <p>Your fleet will show up in this view as soon as actions begin executing.</p>
              <button type="button" className="fleet-btn fleet-btn-primary" onClick={handleStartDemo}>
                Launch demo fleet
              </button>
            </div>
          ) : (
            <div className="fleet-table-region" role="region" aria-label="Fleet runs" tabIndex={0}>
              <table className="fleet-table">
                <colgroup>
                  <col className="fleet-col-agent" />
                  <col className="fleet-col-status" />
                  <col />
                  <col className="fleet-col-action" />
                  <col className="fleet-col-time" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Agent & Task</th>
                    <th>Status</th>
                    <th>Recent Tool Activity</th>
                    <th className="fleet-action-cell">Action</th>
                    <th className="fleet-time-cell">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run, i) => (
                    <AgentTableRow
                      key={run.id}
                      run={run}
                      runs={runs}
                      events={events}
                      now={now}
                      selected={i === selected}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function AgentTableRow({
  run,
  runs,
  events,
  now,
  selected,
}: {
  run: Run
  runs: Run[]
  events: MirageEvent[]
  now: number
  selected: boolean
}) {
  const navigate = useNavigate()
  const label = runLabel(run, runs)
  const sentence = rowSentence(run, events)
  const when = run.ended_at ?? run.started_at
  const isFrozen = run.status === 'frozen'

  return (
    <tr
      className={`fleet-row ${selected ? 'selected' : ''} ${isFrozen ? 'row-frozen' : ''}`}
      onClick={() => navigate(`/runs/${run.id}`)}
    >
      {/* Agent Avatar & Task */}
      <td>
        <div className="fleet-agent-cell">
          <AgentAvatar agent={run.agent} state={avatarState(run)} size={32} />
          <div className="fleet-agent-info">
            <Link
              to={`/runs/${run.id}`}
              className="fleet-agent-name"
              onClick={(e) => e.stopPropagation()}
            >
              {label}
            </Link>
            <span className="fleet-agent-task" title={sentence.text || run.task}>
              {sentence.text || run.task}
            </span>
          </div>
        </div>
      </td>

      {/* Status Pill */}
      <td>
        <span
          className={`fleet-status-pill ${
            isFrozen
              ? 'pill-frozen'
              : run.status === 'running'
              ? 'pill-running'
              : run.status === 'completed'
              ? 'pill-completed'
              : run.status === 'queued'
              ? 'pill-queued'
              : 'pill-killed'
          }`}
        >
          {isFrozen ? '• FROZEN' : run.status === 'running' ? '• Working' : run.status}
        </span>
      </td>

      {/* Tool Call Activity Strip */}
      <td>
        <InlineTraceStrip run={run} events={events} />
      </td>

      {/* Quick Action Button */}
      <td className="fleet-action-cell">
        {isFrozen && run.incident_id ? (
          <Button asChild variant="secondary" onClick={(e) => e.stopPropagation()}>
            <Link to={`/incidents/${run.incident_id}`}>Review Incident</Link>
          </Button>
        ) : (
          <Link
            to={`/runs/${run.id}`}
            className="fleet-action-link"
            onClick={(e) => e.stopPropagation()}
          >
            Trace <ArrowRight size={13} />
          </Link>
        )}
      </td>

      {/* Relative Time */}
      <td className="fleet-time-cell">
        {relTime(when, now)}
      </td>
    </tr>
  )
}

const MAX_STEPS = 4

function InlineTraceStrip({ run, events }: { run: Run; events: MirageEvent[] }) {
  const all = steps(events, run.id)
  const recent = all.slice(-MAX_STEPS)
  const lastBlocked = all.findLast((step) => step.blocked)
  // Keep the last denied call visible even after subsequent tool activity.
  const shown = lastBlocked && !recent.includes(lastBlocked)
    ? [lastBlocked, ...all.slice(-(MAX_STEPS - 1))]
    : recent
  const hidden = all.length - shown.length

  if (all.length === 0) {
    return <span style={{ color: 'var(--fleet-muted)', fontSize: '12px' }}>Initializing run…</span>
  }

  return (
    <div className="fleet-trace-strip" aria-label="Tool call sequence">
      {hidden > 0 && (
        <Link
          className="fleet-trace-more"
          to={`/runs/${run.id}`}
          onClick={(e) => e.stopPropagation()}
          aria-label={`View full trace, ${hidden} more tool calls`}
        >+{hidden}</Link>
      )}
      {shown.map((step, idx) => (
        <span key={step.callId} className="trace-step">
          {idx > 0 && <span className="trace-arrow">→</span>}
          <span
            className={`trace-step-tag ${step.blocked ? 'blocked' : idx === shown.length - 1 && run.status === 'running' ? 'active' : ''}`}
            title={`${step.tool}${step.blocked ? ' — blocked' : ''}`}
          >
            <span className="trace-tool-name">{step.tool}</span>
            {step.blocked && ' ✕'}
          </span>
        </span>
      ))}
    </div>
  )
}

function Skeleton() {
  return (
    <div className="fleet-page">
      <div className="fleet-container">
        <div style={{ height: '32px', width: '200px', background: '#f4f4f5', borderRadius: '8px' }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} style={{ height: '80px', background: '#f4f4f5', borderRadius: '12px' }} />
          ))}
        </div>
        <div style={{ height: '240px', background: '#f4f4f5', borderRadius: '14px' }} />
      </div>
    </div>
  )
}
