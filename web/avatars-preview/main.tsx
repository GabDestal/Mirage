// Throwaway preview: every agent x state x size, light and dark. Not part of the app.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AgentAvatar, type AgentState } from '../src/agents/avatars';

const AGENTS = ['meeting_assistant', 'support', 'invoicing', 'outreach', 'pr_reviewer', 'data_sync', 'scheduler'];
const STATES: AgentState[] = ['working', 'idle', 'waiting', 'frozen', 'killed', 'mirage'];
const SIZES = [20, 32, 64] as const;

const css = `
  body { margin: 0; font: 13px/20px system-ui, sans-serif; }
  .theme { padding: 24px; background: var(--paper); color: var(--ink); }
  .theme[data-theme=light] { --paper:#FCFCFA; --paper-3:#EAEAE6; --ink:#151716; --ink-2:#5C605E; --ink-3:#8C908E; --mirage:#0E8C86; --alarm:#D93A2B; }
  .theme[data-theme=dark] { --paper:#0C0D0D; --paper-3:#1D1E1E; --ink:#ECEDEA; --ink-2:#9DA19F; --ink-3:#6E7270; --mirage:#3CC7BE; --alarm:#FF6A5C; }
  table { border-collapse: collapse; }
  td, th { padding: 6px 10px; text-align: center; font-weight: 500; color: var(--ink-2); }
  th:first-child { text-align: left; }
  .cell { display: flex; gap: 10px; align-items: center; justify-content: center; }
  .row { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
`;

function Grid({ theme }: { theme: string }) {
  return (
    <div className="theme" data-theme={theme}>
      <table>
        <thead><tr><th />{STATES.map((s) => <th key={s}>{s}</th>)}</tr></thead>
        <tbody>
          {AGENTS.map((a) => (
            <tr key={a}>
              <th>{a}</th>
              {STATES.map((s) => (
                <td key={s}><div className="cell">{SIZES.map((z) => <AgentAvatar key={z} agent={a} state={s} size={z} />)}</div></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Toggle() {
  const [i, setI] = useState(0);
  return (
    <div className="theme" data-theme="light">
      <div className="row">
        <button onClick={() => setI((i + 1) % STATES.length)}>Next state: {STATES[(i + 1) % STATES.length]}</button>
        {AGENTS.map((a) => <AgentAvatar key={a} agent={a} state={STATES[i]} size={32} />)}
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <>
    <style>{css}</style>
    <Toggle />
    <Grid theme="light" />
    <Grid theme="dark" />
  </>,
);
