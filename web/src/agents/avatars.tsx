import { useId, type CSSProperties, type ReactNode } from 'react';
import './avatars.css';

export type AgentState = 'working' | 'idle' | 'waiting' | 'frozen' | 'killed' | 'mirage';
export type AvatarSize = 20 | 32 | 64;

type Point = [number, number];
type Character = {
  body: string;
  accent: string;
  eyes: [Point, Point];
  eyeR: number;
  draw: (clipId: string) => ReactNode;
};

// Everything is drawn on a 24-unit grid. `.mav-b` = body color, `.mav-a` = accent color,
// `.mav-detail` is dropped at 20 px so the silhouette and eyes carry the read.
const CHARACTERS: Record<string, Character> = {
  owl: {
    body: '#E3B59A',
    accent: '#A8694A',
    eyes: [[8.6, 11.5], [15.4, 11.5]],
    eyeR: 1.5,
    draw: () => (
      <>
        <path className="mav-a" d="M4 9.5 3.5 3l6.5 3z" />
        <path className="mav-a" d="M20 9.5 20.5 3 14 6z" />
        <rect className="mav-b" x="3.5" y="5" width="17" height="17" rx="8" />
        <circle className="mav-stroke" cx="8.6" cy="11.5" r="3.1" />
        <circle className="mav-stroke" cx="15.4" cy="11.5" r="3.1" />
        <path className="mav-a" d="M10.8 14.6h2.4L12 16.6z" />
      </>
    ),
  },
  octopus: {
    body: '#EFB0BC',
    accent: '#C2607A',
    eyes: [[9.5, 10], [14.5, 10]],
    eyeR: 1.6,
    draw: () => (
      <>
        <rect className="mav-b" x="3.5" y="11" width="3" height="10" rx="1.5" transform="rotate(22 5 11)" />
        <rect className="mav-b" x="8" y="12" width="3" height="10" rx="1.5" />
        <rect className="mav-b" x="13" y="12" width="3" height="10" rx="1.5" />
        <rect className="mav-b" x="17.5" y="11" width="3" height="10" rx="1.5" transform="rotate(-22 19 11)" />
        <rect className="mav-b" x="4" y="2.5" width="16" height="14" rx="7" />
        <circle className="mav-a mav-detail" cx="8" cy="6" r="1" />
        <circle className="mav-a mav-detail" cx="16.4" cy="6.8" r="0.75" />
        <circle className="mav-a mav-detail" cx="17.2" cy="4.6" r="0.5" />
      </>
    ),
  },
  bee: {
    body: '#F3D27C',
    accent: '#6E5626',
    eyes: [[9.5, 11.5], [14.5, 11.5]],
    eyeR: 1.6,
    draw: (clipId) => (
      <>
        <path className="mav-detail mav-stroke" d="M10 6.5C9.6 4.6 9 3.6 7.6 3.1M14 6.5c.4-1.9 1-2.9 2.4-3.4" />
        <ellipse className="mav-wing" cx="5.6" cy="8.2" rx="3" ry="2.4" transform="rotate(-30 5.6 8.2)" />
        <ellipse className="mav-wing" cx="18.4" cy="8.2" rx="3" ry="2.4" transform="rotate(30 18.4 8.2)" />
        <clipPath id={clipId}>
          <rect x="5" y="6" width="14" height="15.5" rx="7" />
        </clipPath>
        <rect className="mav-b" x="5" y="6" width="14" height="15.5" rx="7" />
        <g clipPath={`url(#${clipId})`}>
          <rect className="mav-a" x="4" y="15" width="16" height="2.2" />
          <rect className="mav-a" x="4" y="18.8" width="16" height="2" />
        </g>
      </>
    ),
  },
  plane: {
    body: '#A8CBEA',
    accent: '#5A8FBF',
    eyes: [[9.4, 10.6], [13.2, 9.1]],
    eyeR: 1.35,
    draw: () => (
      <>
        <path className="mav-a" d="M11 14 21.5 3 14 21.5z" />
        <path className="mav-a mav-detail" d="m11 14 3 7.5-3.6-3.9z" />
        <path className="mav-b" d="M2.5 11 21.5 3 11 14z" />
      </>
    ),
  },
  fox: {
    body: '#F4B48C',
    accent: '#C8693A',
    eyes: [[9, 11.5], [15, 11.5]],
    eyeR: 1.6,
    draw: () => (
      <>
        <path className="mav-a" d="M4.2 10.5 5 2.5l6 4z" />
        <path className="mav-a" d="M19.8 10.5 19 2.5l-6 4z" />
        <path className="mav-b" d="M4 9.6C4 7.2 5.5 6 8 6h8c2.5 0 4 1.2 4 3.6 0 4-4 8.6-8 11.4-4-2.8-8-7.4-8-11.4Z" />
        <circle className="mav-eye-fill" cx="12" cy="17.2" r="1.1" />
      </>
    ),
  },
};

// Unknown agents: a hashed color + shape, same face, so a new agent still feels part of the set.
const BLOB_COLORS: [string, string][] = [
  ['#A9DCC4', '#4E9C79'],
  ['#C9B8E8', '#8169B5'],
  ['#E2D3B5', '#9C8457'],
  ['#BCC6D0', '#66768A'],
];
const BLOB_SHAPES: ReactNode[] = [
  <circle className="mav-b" cx="12" cy="13" r="9" />,
  <rect className="mav-b" x="3.5" y="4.5" width="17" height="17" rx="5" />,
  <path className="mav-b" d="M12 3.5 20.2 8.5v9L12 22.5 3.8 17.5v-9z" strokeLinejoin="round" />,
];

const ALIASES: [RegExp, string][] = [
  [/support|ticket|helpdesk/, 'octopus'],
  [/meeting|assistant|calendar/, 'owl'],
  [/invoic|billing/, 'bee'],
  [/outreach|sales/, 'plane'],
  [/review|^pr[_-]/, 'fox'],
];

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

function characterFor(agent: string): Character {
  const key = agent.toLowerCase();
  const match = ALIASES.find(([re]) => re.test(key));
  if (match) return CHARACTERS[match[1]];
  const h = hash(key);
  const [body, accent] = BLOB_COLORS[h % BLOB_COLORS.length];
  const shape = BLOB_SHAPES[(h >>> 4) % BLOB_SHAPES.length];
  return { body, accent, eyes: [[9.5, 12.5], [14.5, 12.5]], eyeR: 1.6, draw: () => shape };
}

function Eyes({ eyes, r, state }: { eyes: [Point, Point]; r: number; state: AgentState }) {
  return (
    <g className="mav-eyes">
      {eyes.map(([x, y], i) => {
        if (state === 'killed') return <path key={i} className="mav-eye-line" d={`M${x - r} ${y}h${2 * r}`} />;
        if (state === 'frozen')
          return <path key={i} className="mav-eye-line" d={`M${x - r} ${y - 0.4}a${r} ${r * 0.6} 0 0 0 ${2 * r} 0`} />;
        if (state === 'idle')
          return <path key={i} className="mav-eye-fill" d={`M${x - r} ${y}a${r} ${r} 0 0 0 ${2 * r} 0z`} />;
        return <circle key={i} className="mav-eye-fill mav-pupil" cx={x} cy={y} r={r} />;
      })}
    </g>
  );
}

export function AgentAvatar({ agent, state, size = 20 }: { agent: string; state: AgentState; size?: AvatarSize }) {
  const clipId = useId();
  const c = characterFor(agent);
  const style = {
    width: size,
    height: size,
    '--av-body': c.body,
    '--av-accent': c.accent,
    // Desync blinks so a fleet of avatars never blinks in unison.
    '--av-blink-delay': `-${hash(agent) % 6000}ms`,
  } as CSSProperties;

  return (
    <span className="mav" data-state={state} data-size={size} style={style} aria-hidden="true">
      <svg viewBox="0 0 24 24" width={size} height={size}>
        {c.draw(clipId)}
        <Eyes eyes={c.eyes} r={c.eyeR} state={state} />
        <rect className="mav-hand" x="18.8" y="2.2" width="3.8" height="5.2" rx="1.9" />
        <g className="mav-ice">
          <rect x="1" y="1" width="22" height="22" rx="4.5" />
          <path d="M4.5 9V6.5a2 2 0 0 1 2-2H9" />
        </g>
      </svg>
    </span>
  );
}
