import { useMemo, type CSSProperties } from 'react';
import { BotAvatar, type BotAvatarType } from 'bot-avatars';
import './avatars.css';

export type AgentState = 'working' | 'idle' | 'waiting' | 'frozen' | 'killed' | 'mirage';
export type AvatarSize = 20 | 24 | 32 | 48 | 64 | number;

export interface AgentAvatarProps {
  agent: string;
  state?: AgentState;
  size?: AvatarSize;
  className?: string;
  style?: CSSProperties;
}

// Roster: each known agent gets its own shape and characteristic profile.
const AGENT_ROSTER: [RegExp, BotAvatarType][] = [
  [/meeting|assistant|calendar/, 'clover'],
  [/support|ticket|helpdesk/, 'flower'],
  [/invoic|billing/, 'star'],
  [/outreach|sales/, 'drop'],
  [/review|^pr[_-]/, 'cat'],
  [/data|sync/, 'droid'],
  [/schedul|cron/, 'hexagon'],
  [/security|gate|guard/, 'mech'],
  [/monitor|observe|telemetry/, 'cloud'],
];

// Fallback pool of distinct shapes for arbitrary dynamically added agents
const FALLBACK_TYPES: BotAvatarType[] = [
  'triangle',
  'square',
  'blob',
  'ghost',
  'circle',
  'alien',
  'pill',
  'pebble',
  'puddle',
];

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  }
  return h >>> 0;
}

export function agentBotType(agent: string): BotAvatarType {
  const key = agent.toLowerCase();
  const matched = AGENT_ROSTER.find(([re]) => re.test(key));
  if (matched) return matched[1];
  const h = hash(key);
  return FALLBACK_TYPES[h % FALLBACK_TYPES.length];
}

export function AgentAvatar({
  agent,
  state = 'idle',
  size = 20,
  className,
  style,
}: AgentAvatarProps) {
  const type = agentBotType(agent);
  const seed = useMemo(() => (hash(agent) % 1000) / 1000, [agent]);

  // Map agent operational states to bot-avatars states:
  // - working: hopping & spinning with laughs
  // - sleeping (for waiting / paused states)
  // - default: idle looking around with occasional jumps
  // - frozen: held motionless in place, iced over with warning halo
  const isFrozen = state === 'frozen';
  const isKilled = state === 'killed';
  const isMirage = state === 'mirage';

  const botState = state === 'working' ? 'working' : state === 'waiting' ? 'sleeping' : 'default';
  const isPaused = isFrozen || isKilled;

  const numericSize = typeof size === 'number' ? size : 20;

  return (
    <span
      className={`mav-bot-frame ${className ?? ''}`}
      data-state={state}
      data-size={numericSize}
      style={{
        width: numericSize,
        height: numericSize,
        ...style,
      }}
      aria-hidden="true"
    >
      <BotAvatar
        type={type}
        size={numericSize}
        state={botState}
        face="mouth"
        shading="plastic"
        seed={seed}
        paused={isPaused}
        interactive={!isPaused}
        className="mav-bot-canvas"
      />

      {isFrozen && (
        <span className="mav-bot-ice" aria-hidden="true">
          <svg viewBox="0 0 24 24" width={numericSize} height={numericSize}>
            <rect x="1" y="1" width="22" height="22" rx="4.5" />
            <path d="M4.5 9V6.5a2 2 0 0 1 2-2H9" />
          </svg>
        </span>
      )}

      {isMirage && <span className="mav-bot-mirage-ring" aria-hidden="true" />}
    </span>
  );
}

// Re-export type helpers
export { BotAvatar } from 'bot-avatars';
