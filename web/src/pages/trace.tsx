import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, Clock, ShieldAlert, Wrench } from 'lucide-react'
import { useEvents, useRuns, type GateDecision, type MirageEvent } from '@/api/client'
import { useNow } from '@/api/stream'
import { AgentAvatar } from '@/components/avatar'
import { Button } from '@/components/ui/button'
import { avatarState, relTime, runLabel } from '@/lib/runs'
import './trace.css'

export type TraceCallDetail = {
  callId: string
  tool: string
  args: Record<string, unknown>
  result: unknown
  error: string | null
  decision?: GateDecision
  blocked: boolean
  ts: string
}

export function RunPage() {
  const { id } = useParams<{ id: string }>()
  const { data: runs = [] } = useRuns()
  const { data: events = [] } = useEvents()
  const now = useNow()

  const run = runs.find((r) => r.id === id)
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null)

  if (!run) {
    return (
      <div className="trace-page">
        <div className="trace-container">
          <Link to="/fleet" className="trace-nav-back">
            <ArrowLeft size={16} /> Back to Fleet
          </Link>
          <div className="trace-timeline-card" style={{ textAlign: 'center', padding: '60px 24px' }}>
            <h3>Agent run not found</h3>
            <p style={{ color: 'var(--trace-muted)', marginTop: '8px' }}>
              Run <code style={{ fontFamily: 'monospace' }}>{id}</code> could not be found in active state.
            </p>
            <div style={{ marginTop: '20px' }}>
              <Button asChild variant="secondary">
                <Link to="/fleet">Return to Fleet</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Extract all tool calls and enrich them with gate decisions & results
  const traceCalls = buildTraceCalls(events, run.id)
  const activeCall = traceCalls.find((c) => c.callId === selectedCallId) || traceCalls.at(-1) || null

  return (
    <div className="trace-page" aria-label={`Trace for ${runLabel(run, runs)}`}>
      <div className="trace-container">
        {/* Navigation Breadcrumb */}
        <Link to="/fleet" className="trace-nav-back">
          <ArrowLeft size={16} /> Back to Fleet overview
        </Link>

        {/* Header Summary */}
        <header className="trace-header">
          <div className="trace-header-left">
            <AgentAvatar agent={run.agent} state={avatarState(run)} size={32} />
            <div className="trace-header-title">
              <h2>
                {runLabel(run, runs)}
                <span
                  className={`fleet-status-pill ${
                    run.status === 'frozen'
                      ? 'pill-frozen'
                      : run.status === 'running'
                      ? 'pill-running'
                      : run.status === 'completed'
                      ? 'pill-completed'
                      : 'pill-killed'
                  }`}
                >
                  {run.status.toUpperCase()}
                </span>
              </h2>
              <p title={run.task}>{run.task}</p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {run.status === 'frozen' && run.incident_id && (
              <Button asChild variant="primary">
                <Link to={`/incidents/${run.incident_id}`}>Open incident story</Link>
              </Button>
            )}
            <span style={{ fontSize: '12px', color: 'var(--trace-ink-3)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={13} /> {relTime(run.ended_at ?? run.started_at, now)}
            </span>
          </div>
        </header>

        {/* Trace Visual Layout */}
        <div className="trace-layout-grid">
          {/* Left Column: Chronological Node Steps */}
          <div className="trace-timeline-card">
            <h3>
              <span>Execution Timeline</span>
              <span style={{ fontSize: '12px', fontWeight: 400, color: 'var(--trace-muted)' }}>
                {traceCalls.length} tool {traceCalls.length === 1 ? 'call' : 'calls'}
              </span>
            </h3>

            {traceCalls.length === 0 ? (
              <p style={{ color: 'var(--trace-muted)', fontSize: '13px' }}>
                No tool calls recorded yet. The agent is initializing.
              </p>
            ) : (
              <div className="trace-node-list">
                {traceCalls.map((step) => {
                  const isSelected = activeCall?.callId === step.callId
                  return (
                    <div
                      key={step.callId}
                      className={`trace-node-item ${step.blocked ? 'node-blocked' : ''} ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedCallId(step.callId)}
                    >
                      <span
                        className={`trace-dot ${step.blocked ? 'dot-blocked' : isSelected ? 'dot-active' : ''}`}
                      />
                      <div className="trace-node-header">
                        <span className="trace-node-name">
                          {step.blocked ? (
                            <ShieldAlert size={14} color="var(--trace-alarm)" />
                          ) : (
                            <Wrench size={14} color="var(--trace-muted)" />
                          )}
                          {step.tool}
                          {step.blocked && (
                            <span style={{ color: 'var(--trace-alarm)', fontSize: '11px', fontWeight: 600 }}>
                              [BLOCKED]
                            </span>
                          )}
                        </span>
                        <span className="trace-node-time">{relTime(step.ts, now)}</span>
                      </div>

                      <div className="trace-node-summary">
                        {summarizeStep(step)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Right Column: Step Inspection Sheet */}
          <div className="trace-detail-card">
            <h3>
              <span>Step Inspection</span>
              {activeCall && (
                <span
                  className="trace-detail-badge"
                  style={{
                    background: activeCall.blocked ? 'var(--trace-alarm-wash)' : 'var(--trace-wash)',
                    color: activeCall.blocked ? 'var(--trace-alarm)' : 'var(--trace-ink-2)',
                    border: `1px solid ${activeCall.blocked ? 'var(--trace-alarm-border)' : 'var(--trace-line)'}`,
                  }}
                >
                  {activeCall.blocked ? 'Gate Blocked' : 'Allowed'}
                </span>
              )}
            </h3>

            {activeCall ? (
              <>
                {activeCall.blocked && activeCall.decision && (
                  <div className="trace-blocked-banner">
                    <strong>Gateway blocked this action</strong>
                    <span>{activeCall.decision.explanation || 'Matched protective security boundary rule.'}</span>
                  </div>
                )}

                <div className="trace-meta-list">
                  <div className="trace-meta-row">
                    <span className="trace-meta-label">Tool:</span>
                    <span className="trace-meta-value" style={{ fontFamily: 'monospace' }}>
                      {activeCall.tool}
                    </span>
                  </div>
                  <div className="trace-meta-row">
                    <span className="trace-meta-label">Call ID:</span>
                    <span className="trace-meta-value" style={{ fontFamily: 'monospace', fontSize: '11.5px' }}>
                      {activeCall.callId}
                    </span>
                  </div>
                  <div className="trace-meta-row">
                    <span className="trace-meta-label">Decision Layer:</span>
                    <span className="trace-meta-value">
                      {activeCall.decision?.layer === 'hard_rule' ? 'Deterministic Hard Rule' : 'Policy Engine'}
                    </span>
                  </div>
                  {activeCall.decision?.rule_id && (
                    <div className="trace-meta-row">
                      <span className="trace-meta-label">Rule ID:</span>
                      <span className="trace-meta-value" style={{ fontFamily: 'monospace', color: 'var(--trace-alarm)' }}>
                        {activeCall.decision.rule_id}
                      </span>
                    </div>
                  )}
                </div>

                <div className="trace-code-section">
                  <h4>Arguments</h4>
                  <pre className="trace-code-block">
                    {JSON.stringify(activeCall.args, null, 2)}
                  </pre>
                </div>

                <div className="trace-code-section">
                  <h4>Result</h4>
                  {activeCall.blocked ? (
                    <div
                      style={{
                        padding: '10px 12px',
                        background: 'var(--trace-wash)',
                        border: '1px solid var(--trace-line)',
                        borderRadius: '8px',
                        fontSize: '12px',
                        color: 'var(--trace-muted)',
                      }}
                    >
                      Call held before execution. No data reached external systems.
                    </div>
                  ) : activeCall.result !== undefined ? (
                    <pre className="trace-code-block">
                      {typeof activeCall.result === 'string'
                        ? activeCall.result
                        : JSON.stringify(activeCall.result, null, 2)}
                    </pre>
                  ) : (
                    <div style={{ color: 'var(--trace-muted)', fontSize: '12px' }}>Executing or pending...</div>
                  )}
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--trace-muted)', fontSize: '13px' }}>
                Select a tool call from the timeline to inspect its parameters and outcome.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function summarizeStep(step: TraceCallDetail): string {
  if (step.tool === 'send_email') {
    const to = step.args?.to as string | undefined
    return to ? `Email to ${to}` : 'Sending email message'
  }
  if (step.tool === 'read_calendar') {
    return 'Inspecting calendar appointments'
  }
  if (step.tool === 'search_contacts') {
    const q = step.args?.query as string | undefined
    return q ? `CRM query: "${q}"` : 'Listing customer contacts'
  }
  if (step.tool === 'list_invoices' || step.tool === 'get_invoice') {
    return 'Retrieving invoice ledger status'
  }
  if (step.tool === 'list_pull_requests' || step.tool === 'read_pull_request') {
    return 'Reviewing pull request diff and comments'
  }
  return `Arguments: ${JSON.stringify(step.args).slice(0, 45)}...`
}

function buildTraceCalls(events: MirageEvent[], runId: string): TraceCallDetail[] {
  const map = new Map<string, TraceCallDetail>()

  for (const e of events) {
    if (e.run_id !== runId) continue
    const p = e.payload as Record<string, any>

    if (e.type === 'tool.requested') {
      const callId = String(p.call_id)
      map.set(callId, {
        callId,
        tool: String(p.tool),
        args: (p.args as Record<string, unknown>) || {},
        result: undefined,
        error: null,
        blocked: false,
        ts: e.ts,
      })
    } else if (e.type === 'gate.decision') {
      const callId = String(p.call_id)
      const existing = map.get(callId)
      if (existing) {
        existing.decision = p as GateDecision
        if (p.decision !== 'allow') {
          existing.blocked = true
        }
      }
    } else if (e.type === 'tool.result') {
      const callId = String(p.call_id)
      const existing = map.get(callId)
      if (existing) {
        existing.result = p.result
        existing.error = p.error || null
      }
    }
  }

  return Array.from(map.values())
}
