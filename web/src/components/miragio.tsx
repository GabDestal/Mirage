import { motion, useAnimationControls, useSpring, useTransform, type MotionStyle, type TargetAndTransition } from 'motion/react'
import { useEffect, useId, useRef, useState, useSyncExternalStore, type RefObject } from 'react'

type Props = { className?: string; animate?: boolean; readingProgress?: number | null }
const spring = { stiffness: 160, damping: 20, mass: 0.55 }
const ENTRY = { x: -100, y: 270, rotate: -10 }
const REST = { x: 0, y: 0, rotate: 0 }
const BLINK: TargetAndTransition = { scaleY: [1, 0.1, 1], transition: { duration: 0.18, times: [0, 0.4, 1], ease: 'easeInOut' } }
const headPath = 'M43 562C53 523 78 489 109 420C178 266 240 90 326 84C423 73 456 224 528 300C593 373 618 317 671 249C711 195 746 170 778 191C834 226 860 337 902 446C932 524 977 587 949 640C923 690 838 700 755 724C620 764 506 748 405 731C291 711 221 683 126 667C57 655 31 623 43 562Z'
const motionPreference = () => window.matchMedia('(prefers-reduced-motion: reduce)')
function subscribeMotionPreference(onChange: () => void) {
  const preference = motionPreference()
  preference.addEventListener('change', onChange)
  return () => preference.removeEventListener('change', onChange)
}
const isReducedMotion = () => motionPreference().matches

// Static reply portraits never mount the animation hooks or global listeners.
export function Miragio({ animate = false, ...props }: Props) {
  return animate ? <AnimatedMiragio {...props} /> : <Portrait className={props.className} />
}

function AnimatedMiragio({ className, readingProgress = null }: Omit<Props, 'animate'>) {
  // Motion's hook snapshots the preference; subscribe so a live OS change also stops everything.
  const reduce = useSyncExternalStore(subscribeMotionPreference, isReducedMotion, () => true)
  const [visible, setVisible] = useState(() => !document.hidden)
  const ref = useRef<SVGSVGElement>(null)
  const reading = useRef(readingProgress !== null)
  const lastPointer = useRef(0)
  const entered = useRef(false)
  const entry = useAnimationControls()
  const eyes = useAnimationControls()
  const lookX = useSpring(0, spring)
  const lookY = useSpring(0, spring)
  const headX = useTransform(lookX, (x) => x * 8.75)
  const headY = useTransform(lookY, (y) => y * 5)
  const headRotate = useTransform(lookX, (x) => x * 1.5)
  const eyeX = useTransform(lookX, (x) => x * 16.25)
  const eyeY = useTransform(lookY, (y) => y * 12.5)
  const active = !reduce && visible

  useEffect(() => {
    const sync = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [])

  useEffect(() => {
    reading.current = readingProgress !== null
    if (!active) { lookX.jump(0); lookY.jump(0); return }
    lookX.set(readingProgress === null ? 0 : 0.1 + readingProgress * 0.5)
    lookY.set(readingProgress === null ? 0 : 0.9)
  }, [readingProgress, active, lookX, lookY])

  useEffect(() => {
    if (!active) {
      entered.current = true
      entry.stop(); entry.set(REST)
      eyes.stop(); eyes.set({ scaleY: 1 })
      return
    }
    let cancelled = false
    let blinkTimer: ReturnType<typeof setTimeout>
    let glanceTimer: ReturnType<typeof setTimeout>
    const blink = async () => {
      if (cancelled) return
      await eyes.start(BLINK)
      if (cancelled) return
      if (Math.random() < 0.2) await eyes.start(BLINK)
      if (!cancelled) blinkTimer = setTimeout(blink, 2000 + Math.random() * 2500)
    }
    const enter = async () => {
      await entry.start({ ...REST, transition: { type: 'spring', duration: 0.9, bounce: 0.15, delay: 0.25 } })
      if (cancelled) return
      entered.current = true
      void blink()
    }
    const glance = () => {
      if (!reading.current && Date.now() - lastPointer.current > 2500) {
        lookX.set((Math.random() - 0.5) * 1.1)
        lookY.set((Math.random() - 0.5) * 0.5)
      }
      glanceTimer = setTimeout(glance, 2500 + Math.random() * 2000)
    }
    const clamp = (v: number) => Math.max(-1, Math.min(1, v))
    const pointer = (event: PointerEvent) => {
      const rect = ref.current?.getBoundingClientRect()
      if (!rect || reading.current || event.pointerType === 'touch') return
      lastPointer.current = Date.now()
      lookX.set(clamp((event.clientX - rect.left - rect.width / 2) / (innerWidth / 2.5)))
      lookY.set(clamp((event.clientY - rect.top - rect.height / 2) / (innerHeight / 2.5)))
    }
    const centre = () => { if (!reading.current) { lookX.set(0); lookY.set(0) } }
    if (entered.current) blinkTimer = setTimeout(blink, 2000 + Math.random() * 2500)
    else void enter()
    glanceTimer = setTimeout(glance, 2500)
    window.addEventListener('pointermove', pointer, { passive: true })
    document.documentElement.addEventListener('pointerleave', centre)
    return () => {
      cancelled = true
      clearTimeout(blinkTimer)
      clearTimeout(glanceTimer)
      entry.stop()
      eyes.stop()
      window.removeEventListener('pointermove', pointer)
      document.documentElement.removeEventListener('pointerleave', centre)
    }
  }, [active, entry, eyes, lookX, lookY])

  return <Portrait className={className} svgRef={ref} active={active} eyes={active ? eyes : undefined} entry={entry}
    headStyle={active ? { x: headX, y: headY, rotate: headRotate, originX: 0.5, originY: 0.75 } : { x: 0, y: 0, rotate: 0 }}
    eyeStyle={active ? { x: eyeX, y: eyeY } : { x: 0, y: 0 }} />
}

function Portrait({ className, svgRef, active = false, eyes, entry, headStyle, eyeStyle }: {
  className?: string; svgRef?: RefObject<SVGSVGElement | null>; active?: boolean
  eyes?: ReturnType<typeof useAnimationControls>; entry?: ReturnType<typeof useAnimationControls>; headStyle?: MotionStyle; eyeStyle?: MotionStyle
}) {
  const id = useId()
  const url = (name: string) => `url(#${id}-${name})`
  return <svg ref={svgRef} className={className} viewBox="0 0 1000 1000" width="80" height="80" role="img" aria-label="Miragio, Mirage assistant" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <clipPath id={`${id}-tile`}><path d="M250 0H750Q1000 0 1000 250V750Q1000 1000 750 1000H250Q0 1000 0 750V250Q0 0 250 0Z" /></clipPath>
      <radialGradient id={`${id}-paper`} cx="50%" cy="42%" r="75%"><stop stopColor="#fffdf8" /><stop offset="0.65" stopColor="#faf1e4" /><stop offset="1" stopColor="#e9d8c1" /></radialGradient>
      <radialGradient id={`${id}-chest`} cx="54%" cy="15%" r="90%"><stop stopColor="#fffaf1" /><stop offset="0.65" stopColor="#eee2d1" /><stop offset="1" stopColor="#d2c7b9" /></radialGradient>
      <linearGradient id={`${id}-sun`} x1="20%" y1="100%" x2="90%" y2="0%"><stop stopColor="#bd4828" /><stop offset="0.5" stopColor="#ed7e50" /><stop offset="1" stopColor="#ffb581" /></linearGradient>
      <linearGradient id={`${id}-head`} x1="0%" y1="55%" x2="100%" y2="25%"><stop stopColor="#182f55" /><stop offset="0.3" stopColor="#0d213e" /><stop offset="0.68" stopColor="#15335e" /><stop offset="1" stopColor="#365487" /></linearGradient>
      <radialGradient id={`${id}-crest`} cx="36%" cy="0%" r="80%"><stop stopColor="#92b7ff" stopOpacity="0.45" /><stop offset="0.3" stopColor="#779dde" stopOpacity="0.08" /><stop offset="0.65" stopColor="#0b1c35" stopOpacity="0" /><stop offset="1" stopColor="#05152e" stopOpacity="0.45" /></radialGradient>
      <radialGradient id={`${id}-edge`} cx="58%" cy="100%" r="58%"><stop stopColor="#1377ff" /><stop offset="0.42" stopColor="#005bea" stopOpacity="0.65" /><stop offset="0.85" stopColor="#005bea" stopOpacity="0" /></radialGradient>
      <radialGradient id={`${id}-face`} cx="51%" cy="32%" r="74%"><stop stopColor="#fffefa" /><stop offset="0.55" stopColor="#fbf3e6" /><stop offset="0.82" stopColor="#e5d4bb" /><stop offset="1" stopColor="#c3c5ce" /></radialGradient>
      <linearGradient id={`${id}-eye`} x1="20%" y1="0%" x2="80%" y2="100%"><stop stopColor="#060b14" /><stop offset="0.5" stopColor="#111825" /><stop offset="1" stopColor="#303846" /></linearGradient>
      <linearGradient id={`${id}-ribbon`} x1="15%" y1="100%" x2="85%" y2="0%"><stop stopColor="#0043b8" /><stop offset="0.5" stopColor="#0068fa" /><stop offset="0.8" stopColor="#137eff" /><stop offset="1" stopColor="#46b7ff" /></linearGradient>
    </defs>
    <g clipPath={url('tile')}>
      <rect width="1000" height="1000" fill={url('paper')} />
      <path d="M78 1000C110 878 166 821 256 789C451 718 827 720 902 846Q932 897 940 1000Z" fill={url('chest')} />
      <motion.g data-miragio="entry" initial={active ? ENTRY : false} animate={active ? entry : REST}>
        <motion.g data-miragio="head" style={headStyle}>
          <path d="M452 188C480 143 525 124 572 124C632 124 673 161 694 213C664 251 613 306 573 307C524 309 489 248 452 188Z" fill={url('sun')} />
          <path d={headPath} fill={url('head')} />
          <path d={headPath} fill={url('crest')} />
          <path d={headPath} fill={url('edge')} />
          <path d="M188 521C198 440 299 331 397 326C487 319 514 383 586 397C637 408 690 382 744 404C806 424 827 484 821 573C816 660 778 697 699 720C605 748 513 743 432 723C323 697 177 650 188 521Z" fill={url('face')} />
          <motion.g data-miragio="gaze" style={eyeStyle}>
            <motion.g data-miragio="blink" animate={eyes} style={{ transformBox: 'fill-box', originY: 0.5, ...(!active ? { scaleY: 1 } : {}) }}>
              <path d="M345 552C349 488 367 422 405 422C451 420 450 470 441 540C435 586 426 615 392 615C353 615 341 593 345 552Z" fill={url('eye')} />
              <path d="M607 578C611 518 622 458 657 457C700 454 701 500 691 566C685 612 675 640 646 640C612 640 603 617 607 578Z" fill={url('eye')} />
              <ellipse cx="417" cy="457" rx="13" ry="19" transform="rotate(-12 417 457)" fill="#fff" />
              <ellipse cx="668" cy="489" rx="12" ry="17" transform="rotate(-14 668 489)" fill="#fff" />
            </motion.g>
          </motion.g>
        </motion.g>
      </motion.g>
      <motion.path data-miragio="ribbon" d="M97 774C132 708 209 692 282 716C391 749 484 797 592 796C683 796 737 750 790 743C847 733 888 774 904 812C913 837 869 861 829 872C718 906 615 871 508 849C384 824 271 794 179 835C153 846 139 866 115 856C86 846 87 800 97 774Z" fill={url('ribbon')} animate={{ x: active ? [0, 6.25, 0, -6.25, 0] : 0 }} transition={{ duration: active ? 9 : 0, repeat: active ? Infinity : 0, ease: 'easeInOut' }} />
      <motion.path data-miragio="ribbon" d="M258 901C277 857 345 847 402 853C498 860 539 911 641 925C671 930 697 928 701 938C710 957 666 980 623 980C572 980 549 959 495 958C416 958 322 971 280 947C263 938 252 921 258 901Z" fill={url('ribbon')} animate={{ x: active ? [0, -5, 0, 5, 0] : 0 }} transition={{ duration: active ? 11 : 0, repeat: active ? Infinity : 0, ease: 'easeInOut' }} />
    </g>
  </svg>
}
