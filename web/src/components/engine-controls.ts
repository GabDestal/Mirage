import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError, queryClient, type HumanRequest, type Run } from '@/api/client'

export function humanControlError(error: Error) {
  return error instanceof ApiError && error.status === 409 && error.message.includes('owned by another process')
    ? `${error.message}. This engine restored the history, but has no live control of the run. Use the owning agent process to control it.`
    : error.message
}

// Engine medium-risk calls use actor/reason; chat approvals have a different endpoint/body.
export function useEngineApproval() {
  return useMutation({
    retry: false,
    mutationFn: ({ callId, decision, body }: { callId: string; decision: 'approve' | 'reject'; body: HumanRequest }) =>
      api<Run>(`/approvals/${encodeURIComponent(callId)}/${decision}`, body),
    onSuccess: (run, { decision }) => {
      queryClient.setQueryData<Run[]>(['runs'], (old = []) => [...old.filter((r) => r.id !== run.id), run])
      toast(decision === 'approve' ? 'Held call approved.' : 'Held call rejected. The run has ended.')
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['approvals'] })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      void queryClient.invalidateQueries({ queryKey: ['services'] })
    },
  })
}
