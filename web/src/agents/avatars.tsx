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

  const isFrozen = state === 'frozen';
  const isMirage = state === 'mirage';

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
        state={state === 'waiting' ? 'sleeping' : 'default'}
        face="mouth"
        shading="plastic"
        seed={seed}
        color={isFrozen ? '#78c9ea' : undefined}
        saturation={isFrozen ? 1 : undefined}
        // Hold the renderer still; CSS adds only a tiny working-state drift.
        paused
        interactive={false}
        className="mav-bot-canvas"
      />

      {isFrozen && (
        <span className="mav-bot-ice" aria-hidden="true">
          <svg viewBox="0 0 24 24" width={numericSize} height={numericSize}>
            <path className="mav-ice-top" d="M2 5 6 1H23L19 5Z" />
            <path className="mav-ice-side" d="m19 5 4-4v17l-4 4Z" />
            <rect x="2" y="5" width="17" height="17" rx="2" />
            <path className="mav-ice-highlight" d="M4 12V8a1 1 0 0 1 1-1h5M5 19h5M21 5v9" />
          </svg>
        </span>
      )}

      {isMirage && <span className="mav-bot-mirage-ring" aria-hidden="true" />}
    </span>
  );
}

// Re-export type helpers
export { BotAvatar } from 'bot-avatars';
