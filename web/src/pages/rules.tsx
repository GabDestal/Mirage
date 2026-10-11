import { useState, useMemo, type FormEvent } from 'react'
import {
  Plus,
  Pencil,
  Trash2,
  CheckCircle2,
  ShieldCheck,
  Search,
  Check,
  AlertCircle,
  RefreshCw,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { queryClient } from '@/api/client'
import {
  activateRule,
  createRule,
  draftFromFields,
  previewRule,
  ruleSentence,
  useRuleAgents,
  useRules,
  type RulePreview,
  type RuleRevision,
} from '@/api/rules'
import { Button } from '@/components/ui/button'
import { agentName } from '@/lib/runs'
import './rules.css'

/**
 * Built-in local policies and baseline guardrails enforced across all runs.
 * Source of truth: engine/detection/decision_model.py (P1–P6) & policies.yaml
 */
export const LOCAL_POLICIES = [
  {
    id: 'P1',
    code: 'P1',
    name: 'Data Confinement',
    scope: 'All Agents',
    type: 'System Guardrail',
    description: 'Data must only go where the task needs it. Prohibits cross-customer data leakage and external exfiltration of internal notes or pricing.',
    restrictions: 'Task-approved destinations only',
    status: 'enforced' as const,
  },
  {
    id: 'P2',
    code: 'P2',
    name: 'Secret & Canary Shield',
    scope: 'All Agents',
    type: 'Hard Rule',
    description: 'Tool arguments must never carry credentials, API keys, tokens, passwords, or canary secrets.',
    restrictions: 'Monitors FLAG{team26-canary} and credentials',
    status: 'enforced' as const,
  },
  {
    id: 'P3',
    code: 'P3',
    name: 'Task Alignment',
    scope: 'All Agents',
    type: 'System Guardrail',
    description: 'Every tool invocation must strictly fit the user-assigned task and legitimate operational scope.',
    restrictions: 'Tool operations strictly fit user prompt',
    status: 'enforced' as const,
  },
  {
    id: 'P4',
    code: 'P4',
    name: 'Bulk Export Blocker',
    scope: 'All Agents',
    type: 'Hard Rule',
    description: 'Blocks unauthorized bulk exfiltration of customer records (five or more customer names or emails in a single tool call).',
    restrictions: 'Max 4 records per single outbound call',
    status: 'enforced' as const,
  },
  {
    id: 'P5',
    code: 'P5',
    name: 'Unnamed Recipient Gate',
    scope: 'All Agents',
    type: 'System Guardrail',
    description: 'Blocks sending communications to recipients that the user did not explicitly name and the task does not require.',
    restrictions: 'Unprompted external recipients blocked',
    status: 'enforced' as const,
  },
  {
    id: 'P6',
    code: 'P6',
    name: 'Prompt Injection Defense',
    scope: 'All Agents',
    type: 'System Guardrail',
    description: 'Agents must never execute instructions embedded inside untrusted content (emails, calendar invites, web pages, or attachments).',
    restrictions: 'Untrusted content treated strictly as data',
    status: 'enforced' as const,
  },
] as const

export type UnifiedRule = {
  id: string
  code: string
  name: string
  agentKey?: string
  scope: string
  type: 'System Guardrail' | 'Hard Rule' | 'Role Baseline' | 'Custom Rule'
  description: string
  restrictions: string
  status: 'enforced' | 'active' | 'draft' | 'superseded'
  isSystem: boolean
  isBaseline: boolean
  revision?: RuleRevision
}

export function Rules() {
  const agents = useRuleAgents()
  const rules = useRules()

  // Filter & Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [scopeFilter, setScopeFilter] = useState<'all' | 'system' | 'custom'>('all')

  // Add / Edit Modal state
  const [isEditorOpen, setIsEditorOpen] = useState(false)
  const [editAgent, setEditAgent] = useState('')
  const [editTools, setEditTools] = useState<string[]>([])
  const [editRecipients, setEditRecipients] = useState('')
  const [editingVersion, setEditingVersion] = useState<string | null>(null)

  // Activation & Review Modal state
  const [activeReviewRevision, setActiveReviewRevision] = useState<RuleRevision | null>(null)
  const [previewData, setPreviewData] = useState<RulePreview | null>(null)
  const [operatorName, setOperatorName] = useState('Operator')
  const [operatorReason, setOperatorReason] = useState('Verified restrictive policy for upcoming runs')

  // UI state
  const [busyAction, setBusyAction] = useState('')
  const [deletedVersions, setDeletedVersions] = useState<Set<string>>(new Set())

  // Current editing agent definition
  const selectedAgentSpec = agents.data?.find((a) => a.name === editAgent)

  // Synthesize unified list of all rules
  const unifiedRules = useMemo<UnifiedRule[]>(() => {
    const list: UnifiedRule[] = []

    // 1. Local Policies (P1 - P6)
    LOCAL_POLICIES.forEach((p) => {
      list.push({
        id: p.id,
        code: p.code,
        name: p.name,
        scope: p.scope,
        type: p.type,
        description: p.description,
        restrictions: p.restrictions,
        status: p.status,
        isSystem: true,
        isBaseline: false,
      })
    })

    // 2. Registered Agent Role Baselines
    if (agents.data) {
      agents.data.forEach((agent) => {
        list.push({
          id: `BASE-${agent.name}`,
          code: 'BASE',
          name: `${agentName(agent.name)} Baseline`,
          agentKey: agent.name,
          scope: agentName(agent.name),
          type: 'Role Baseline',
          description: `Registered capabilities for ${agentName(agent.name)}. Establishes maximum allowable tool authority.`,
          restrictions: `Tools: ${agent.tools.join(', ') || 'None'}`,
          status: 'active',
          isSystem: false,
          isBaseline: true,
        })
      })
    }

    // 3. Dynamic / Custom Revisions from Engine
    if (rules.data) {
      rules.data
        .filter((r) => !deletedVersions.has(r.version))
        .forEach((revision) => {
          const toolsStr = revision.allow.tools.join(', ') || 'No tools'
          const emailsStr = revision.allow.email_to.join(', ') || 'No external recipients'
          list.push({
            id: revision.version,
            code: `REV-${revision.version.slice(0, 6)}`,
            name: `${agentName(revision.agent)} Custom Policy`,
            agentKey: revision.agent,
            scope: agentName(revision.agent),
            type: 'Custom Rule',
            description: ruleSentence(agentName(revision.agent), revision.allow),
            restrictions: `Tools: ${toolsStr} · Recipients: ${emailsStr}`,
            status: revision.status,
            isSystem: false,
            isBaseline: false,
            revision,
          })
        })
    }

    return list
  }, [agents.data, rules.data, deletedVersions])

  // Filtered rules
  const displayedRules = useMemo(() => {
    return unifiedRules.filter((r) => {
      if (scopeFilter === 'system' && !r.isSystem && !r.isBaseline) return false
      if (scopeFilter === 'custom' && (r.isSystem || r.isBaseline)) return false

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase()
        const match =
          r.code.toLowerCase().includes(query) ||
          r.name.toLowerCase().includes(query) ||
          r.scope.toLowerCase().includes(query) ||
          r.description.toLowerCase().includes(query) ||
          r.restrictions.toLowerCase().includes(query) ||
          r.status.toLowerCase().includes(query)
        if (!match) return false
      }
      return true
    })
  }, [unifiedRules, scopeFilter, searchQuery])

  // Open Add Rule Modal
  function handleOpenAdd() {
    const defaultAgent = agents.data?.[0]?.name ?? ''
    const initialTools = agents.data?.[0]?.tools ?? []
    setEditingVersion(null)
    setEditAgent(defaultAgent)
    setEditTools(initialTools)
    setEditRecipients('')
    setIsEditorOpen(true)
  }

  // Open Edit Rule Modal
  function handleOpenEdit(rule: UnifiedRule) {
    if (!rule.revision) return
    setEditingVersion(rule.revision.version)
    setEditAgent(rule.revision.agent)
    setEditTools(rule.revision.allow.tools)
    setEditRecipients(rule.revision.allow.email_to.join(', '))
    setIsEditorOpen(true)
  }

  // Toggle tool in editor
  function handleToggleTool(tool: string) {
    setEditTools((prev) => (prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]))
  }

  // Save Rule from Modal Form
  async function handleSaveRule(e: FormEvent) {
    e.preventDefault()
    if (!editAgent) {
      toast.error('Please select an agent.')
      return
    }

    setBusyAction('save')
    try {
      const draft = draftFromFields(editAgent, editTools.join(', '), editRecipients)
      const revision = await createRule(draft)
      await queryClient.invalidateQueries({ queryKey: ['rules'] })
      setIsEditorOpen(false)
      toast.success(`Draft saved for ${agentName(revision.agent)}. Preview and activate it in the table.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save rule draft.')
    } finally {
      setBusyAction('')
    }
  }

  // Delete a custom rule / draft
  function handleDeleteRule(rule: UnifiedRule) {
    if (rule.isSystem || rule.isBaseline || !rule.revision) return
    setDeletedVersions((prev) => new Set([...prev, rule.revision!.version]))
    toast.success(`Rule ${rule.code} removed from active view.`)
  }

  // Open Review / Activate modal
  async function openReviewModal(revision: RuleRevision) {
    setActiveReviewRevision(revision)
    setPreviewData(null)
    setBusyAction('preview')
    try {
      const result = await previewRule(revision.version)
      setPreviewData(result)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to generate engine preview.')
    } finally {
      setBusyAction('')
    }
  }

  // Activate rule in engine
  async function handleActivateRule(e: FormEvent) {
    e.preventDefault()
    if (!activeReviewRevision || !previewData) return

    setBusyAction('activate')
    try {
      const version = activeReviewRevision.version
      const result = await activateRule(version, `${operatorName.trim()} via Rules UI`, operatorReason.trim())
      if (result.status !== 'active') throw new Error('Engine did not confirm activation.')
      await queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success(`Rule activated for ${agentName(result.agent)}! Future runs will enforce this policy.`)
      setActiveReviewRevision(null)
      setPreviewData(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Activation failed.')
    } finally {
      setBusyAction('')
    }
  }

  return (
    <div className="rules-page">
      {/* Page Header */}
      <header className="rules-header">
        <div>
          <h1 className="rules-title">Rules & Policies</h1>
          <p className="rules-subtitle">
            Safety boundaries, P1–P6 guardrails, and restrictive agent policies.
          </p>
        </div>
        <div className="rules-header-stats">
          <div className="stat-pill">
            <ShieldCheck className="size-4 text-mirage" />
            <span>{unifiedRules.filter((r) => r.status === 'enforced' || r.status === 'active').length} Active Rules</span>
          </div>
        </div>
      </header>

      {/* Table Toolbar: Filter, Search, and Manual Add */}
      <div className="rules-toolbar">
        <div className="rules-toolbar-left">
          <div className="rules-search-box">
            <Search className="size-4 text-ink-3" />
            <input
              type="text"
              placeholder="Filter rules by name, scope, or text…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="rules-search-clear" onClick={() => setSearchQuery('')} aria-label="Clear search">
                <X className="size-3.5" />
              </button>
            )}
          </div>

          <div className="rules-filter-pills" role="radiogroup" aria-label="Scope filter">
            <button
              className={`filter-pill ${scopeFilter === 'all' ? 'active' : ''}`}
              onClick={() => setScopeFilter('all')}
            >
              All Rules ({unifiedRules.length})
            </button>
            <button
              className={`filter-pill ${scopeFilter === 'system' ? 'active' : ''}`}
              onClick={() => setScopeFilter('system')}
            >
              System & Baselines ({unifiedRules.filter((r) => r.isSystem || r.isBaseline).length})
            </button>
            <button
              className={`filter-pill ${scopeFilter === 'custom' ? 'active' : ''}`}
              onClick={() => setScopeFilter('custom')}
            >
              Custom Policies ({unifiedRules.filter((r) => !r.isSystem && !r.isBaseline).length})
            </button>
          </div>
        </div>

        <div className="rules-toolbar-right">
          <Button variant="secondary" onClick={() => rules.refetch()} title="Refresh rules list">
            <RefreshCw className="size-3.5" /> Refresh
          </Button>
          <Button variant="primary" onClick={handleOpenAdd}>
            <Plus className="size-4" /> Add Rule
          </Button>
        </div>
      </div>

      {/* Main Rules Table */}
      <div className="rules-table-container">
        <table className="rules-table">
          <thead>
            <tr>
              <th scope="col" style={{ width: '90px' }}>ID</th>
              <th scope="col" style={{ width: '180px' }}>Rule Name</th>
              <th scope="col" style={{ width: '160px' }}>Applies To</th>
              <th scope="col" style={{ width: '140px' }}>Type</th>
              <th scope="col">Restrictions & Purpose</th>
              <th scope="col" style={{ width: '110px' }}>Status</th>
              <th scope="col" style={{ width: '130px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayedRules.length === 0 ? (
              <tr>
                <td colSpan={7} className="rules-empty-state">
                  <AlertCircle className="size-6 text-ink-3" />
                  <p>No matching rules found. Try clearing filters or add a new rule above.</p>
                </td>
              </tr>
            ) : (
              displayedRules.map((rule) => {
                const isDraft = rule.status === 'draft'

                return (
                  <tr key={rule.id} className={`rules-row-item ${isDraft ? 'row-draft' : ''}`}>
                    {/* ID */}
                    <td className="rules-cell-id">
                      <span className="rule-code-badge">{rule.code}</span>
                    </td>

                    {/* Rule Name */}
                    <td className="rules-cell-name">
                      <span className="rule-name-text">{rule.name}</span>
                    </td>

                    {/* Applies To */}
                    <td className="rules-cell-scope">
                      <span className={`scope-badge ${rule.isSystem ? 'scope-global' : 'scope-agent'}`}>
                        {rule.scope}
                      </span>
                    </td>

                    {/* Type */}
                    <td className="rules-cell-type">
                      <span className={`type-tag type-${rule.type.toLowerCase().replace(/\s+/g, '-')}`}>
                        {rule.type}
                      </span>
                    </td>

                    {/* Restrictions / Description */}
                    <td className="rules-cell-desc">
                      <p className="rule-description-text">{rule.description}</p>
                      <span className="rule-bounds-snippet">{rule.restrictions}</span>
                    </td>

                    {/* Status */}
                    <td className="rules-cell-status">
                      <span className={`status-pill status-${rule.status}`}>
                        {rule.status === 'enforced' ? (
                          <>
                            <ShieldCheck className="size-3" /> Enforced
                          </>
                        ) : rule.status === 'active' ? (
                          <>
                            <CheckCircle2 className="size-3" /> Active
                          </>
                        ) : rule.status === 'draft' ? (
                          'Draft'
                        ) : (
                          'Superseded'
                        )}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="rules-cell-actions">
                      {rule.isSystem || rule.isBaseline ? (
                        <span className="locked-label" title="Core engine boundary">Permanent</span>
                      ) : (
                        <div className="action-buttons-group">
                          {isDraft && (
                            <button
                              className="action-btn-primary"
                              onClick={() => rule.revision && openReviewModal(rule.revision)}
                              title="Preview & Activate draft"
                            >
                              Activate
                            </button>
                          )}
                          <button
                            className="action-btn-icon"
                            onClick={() => handleOpenEdit(rule)}
                            title="Edit policy"
                            aria-label={`Edit ${rule.name}`}
                          >
                            <Pencil className="size-3.5" />
                          </button>
                          <button
                            className="action-btn-icon text-alarm"
                            onClick={() => handleDeleteRule(rule)}
                            title="Delete policy"
                            aria-label={`Delete ${rule.name}`}
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Add / Edit Rule Modal */}
      {isEditorOpen && (
        <div className="rules-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="editor-title">
          <div className="rules-modal-card">
            <div className="rules-modal-header">
              <h3 id="editor-title">{editingVersion ? 'Edit Custom Rule' : 'Create New Restrictive Rule'}</h3>
              <button className="modal-close-btn" onClick={() => setIsEditorOpen(false)} aria-label="Close">
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleSaveRule} className="rules-modal-form">
              <div className="form-group">
                <label htmlFor="agent-select">Target Agent</label>
                <select
                  id="agent-select"
                  value={editAgent}
                  disabled={!!editingVersion}
                  onChange={(e) => {
                    const next = e.target.value
                    setEditAgent(next)
                    const spec = agents.data?.find((a) => a.name === next)
                    if (spec) setEditTools(spec.tools)
                  }}
                  required
                >
                  <option value="">Select registered agent</option>
                  {agents.data?.map((a) => (
                    <option key={a.name} value={a.name}>
                      {agentName(a.name)} ({a.name})
                    </option>
                  ))}
                </select>
                <span className="form-help">Rules only narrow the registered capabilities of the selected agent.</span>
              </div>

              {selectedAgentSpec && (
                <div className="form-group">
                  <label>Allowed Tools (Click to toggle)</label>
                  <div className="tool-selector-pills">
                    {selectedAgentSpec.tools.map((tool) => {
                      const selected = editTools.includes(tool)
                      return (
                        <button
                          key={tool}
                          type="button"
                          className={`tool-pill ${selected ? 'selected' : ''}`}
                          onClick={() => handleToggleTool(tool)}
                        >
                          {selected ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}
                          <code>{tool}</code>
                        </button>
                      )
                    })}
                  </div>
                  <span className="form-help">
                    Selected: {editTools.length ? editTools.join(', ') : 'None (agent cannot invoke tools)'}
                  </span>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="recipients-input">Exact Allowed Email Recipients</label>
                <textarea
                  id="recipients-input"
                  rows={2}
                  value={editRecipients}
                  onChange={(e) => setEditRecipients(e.target.value)}
                  placeholder="demo-user@mirage-demo.com, user@synthetic.example"
                />
                <span className="form-help">Comma-separated full email addresses. Empty allows no outbound emails.</span>
              </div>

              {editAgent && (
                <div className="preview-summary-box">
                  <p className="summary-title">Summary:</p>
                  <p className="summary-text">
                    {ruleSentence(agentName(editAgent), {
                      tools: editTools,
                      email_to: editRecipients
                        .split(/[\n,]/)
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })}
                  </p>
                </div>
              )}

              <div className="rules-modal-actions">
                <Button type="button" variant="secondary" onClick={() => setIsEditorOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" disabled={busyAction === 'save'}>
                  {busyAction === 'save' ? 'Saving Draft…' : 'Save as Draft'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Review & Activate Modal */}
      {activeReviewRevision && (
        <div className="rules-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="review-title">
          <div className="rules-modal-card">
            <div className="rules-modal-header">
              <h3 id="review-title">Activate Rule for {agentName(activeReviewRevision.agent)}</h3>
              <button
                className="modal-close-btn"
                onClick={() => setActiveReviewRevision(null)}
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="rules-review-body">
              <div className="review-revision-meta">
                <span>Revision Hash:</span>
                <code>{activeReviewRevision.version}</code>
              </div>

              {previewData ? (
                <div className="preview-details-card">
                  <p className="preview-summary">{previewData.summary}</p>
                  <div className="preview-grid">
                    <div>
                      <strong>Effective Tools:</strong>
                      <p>{previewData.effective_allow.tools.join(', ') || 'None'}</p>
                    </div>
                    <div>
                      <strong>Effective Recipients:</strong>
                      <p>{previewData.effective_allow.email_to.join(', ') || 'None'}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="preview-loading">
                  <RefreshCw className="size-4 animate-spin text-mirage" />
                  <span>Loading authoritative engine preview…</span>
                </div>
              )}

              <form onSubmit={handleActivateRule} className="rules-modal-form">
                <div className="form-group">
                  <label htmlFor="actor-input">Operator Name</label>
                  <input
                    id="actor-input"
                    type="text"
                    required
                    value={operatorName}
                    onChange={(e) => setOperatorName(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="reason-input">Reason for Activation</label>
                  <input
                    id="reason-input"
                    type="text"
                    required
                    value={operatorReason}
                    onChange={(e) => setOperatorReason(e.target.value)}
                  />
                </div>

                <p className="activation-disclaimer">
                  Activation takes effect for all future runs. Existing frozen and in-flight runs retain their pinned policies.
                </p>

                <div className="rules-modal-actions">
                  <Button type="button" variant="secondary" onClick={() => setActiveReviewRevision(null)}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!previewData || busyAction === 'activate' || !operatorName.trim() || !operatorReason.trim()}
                  >
                    {busyAction === 'activate' ? 'Activating…' : 'Activate for New Runs'}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
