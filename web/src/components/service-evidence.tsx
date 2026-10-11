import { useServiceView, type ServiceItem, type ServiceView } from '@/api/client'
import { Button } from './ui/button'
import { isDemo } from '@/lib/demo'

const SERVICES = { outbox: 'Outbox', calendar: 'Calendar', crm: 'CRM' } as const

function serviceItemLabel(service: ServiceView['service'], env: ServiceView['env'], flag: ServiceItem['flag']) {
  if (service === 'outbox') {
    if (env === 'mirage') return flag === 'malicious' ? 'Harmful effect · not sent' : 'Captured effect · not sent'
    return flag === 'blocked' ? 'Blocked · never sent' : 'Tool result recorded'
  }
  return flag === 'malicious' ? 'Proven cause' : env === 'mirage' ? 'Snapshot input' : 'Recorded read'
}

export function ServiceEvidence() {
  return <section className="service-evidence" aria-label="Service evidence">
    <div className="fleet-evidence-heading"><h3>Service evidence</h3><span>{isDemo ? 'Recorded synthetic demo' : 'Synthetic / recorded evidence'}</span></div>
    <p className="fleet-evidence-muted">From the engine event log. These panels do not check provider health or confirm delivery.</p>
    <div className="service-evidence-grid">{(['prod', 'mirage'] as const).map((env) => <div className="service-environment" key={env}>
      <h4>{env === 'prod' ? 'Production' : 'Mirage'}</h4><p>{env === 'prod' ? 'Synthetic / recorded tool activity' : 'Simulation inputs and effects · no real writes'}</p>
      {(Object.keys(SERVICES) as ServiceView['service'][]).map((service) => <ServicePanel key={service} service={service} env={env} />)}
    </div>)}</div>
  </section>
}

function ServicePanel({ service, env }: { service: ServiceView['service']; env: ServiceView['env'] }) {
  const view = useServiceView(service, env)
  return <section className="service-panel" aria-label={`${env === 'prod' ? 'Production' : 'Mirage'} ${SERVICES[service]}`}>
    <h5>{SERVICES[service]}{view.data && ` (${view.data.items.length})`}</h5>
    {view.isPending ? <p role="status">Loading evidence…</p>
      : view.isError ? <p role="alert">Could not refresh {SERVICES[service].toLowerCase()}: {view.error.message} <Button onClick={() => void view.refetch()}>Refresh</Button></p>
      : !view.data.items.length ? <p className="fleet-evidence-muted">No {service === 'outbox' ? 'outbound activity' : 'inputs'} recorded.</p>
      : <ul>{view.data.items.slice(-3).map((item) => <li key={item.id} data-flag={item.flag}>
        <strong>{item.title}</strong><span>{item.subtitle}</span><small>{serviceItemLabel(service, env, item.flag)}</small>
      </li>)}</ul>}
    {view.data && view.data.items.length > 3 && <details><summary>All {view.data.items.length} recorded items</summary><ul>{view.data.items.map((item) => <li key={item.id} data-flag={item.flag}>
      <strong>{item.title}</strong><span>{item.subtitle}</span><small>{serviceItemLabel(service, env, item.flag)}</small>
    </li>)}</ul></details>}
  </section>
}
