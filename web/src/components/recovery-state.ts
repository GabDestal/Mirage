// Recovery completion is engine-ledger proof, never the queued approval or SDK return alone.
export type RecoverySummary = {
  status: 'prepared' | 'queued' | 'running' | 'completed' | 'failed'
  new_run_id?: string | null
  useful_task_completed: boolean
  error?: string | null
  report: { merged_sha: string; verified_sha: string; candidate_tree: string; merged_tree: string;
    snapshot_digest: string; policy_digest: string; config_digest: string; checkpoint_digest: string;
    pull_request: { url: string; number: number }; agent: string; task: string }
}

export function recoveryMessage(state: Pick<RecoverySummary, 'status' | 'useful_task_completed'>) {
  switch (state.status) {
    case 'prepared': return 'Merged repair prepared. The repaired factory is registered; the task has not restarted.'
    case 'queued': return 'Clean restart approved and queued. Waiting for the launcher to claim the task.'
    case 'running': return 'The repaired agent is running the original task with fresh context.'
    case 'completed': return state.useful_task_completed
      ? 'Original task completed. Mirage confirmed exactly one expected prep brief.'
      : 'Invocation returned; useful task completion has not been established.'
    case 'failed': return 'Recovery failed or was contained. Review the new task trace before deciding what to do next.'
  }
}
