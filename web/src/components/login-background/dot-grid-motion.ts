const SPRING_STIFFNESS = 26;
const SPRING_DAMPING_RATIO = 0.8;
const SPRING_DAMPING = 2 * SPRING_DAMPING_RATIO * Math.sqrt(SPRING_STIFFNESS);
const FADE_RATE = 2;
const MAX_DELTA = 1 / 30;
const EPSILON = 0.002;

export type DotGridMotion = {
    x: number;
    y: number;
    vx: number;
    vy: number;
    strength: number;
};

export type DotGridTarget = {
    x: number;
    y: number;
    strength: number;
};

export const createDotGridMotion = (): DotGridMotion => ({ x: 0, y: 0, vx: 0, vy: 0, strength: 0 });

export const stepDotGridMotion = (motion: DotGridMotion, target: DotGridTarget, elapsed: number): boolean => {
    const delta = Math.min(elapsed, MAX_DELTA);

    motion.vx += ((target.x - motion.x) * SPRING_STIFFNESS - motion.vx * SPRING_DAMPING) * delta;
    motion.vy += ((target.y - motion.y) * SPRING_STIFFNESS - motion.vy * SPRING_DAMPING) * delta;
    motion.x += motion.vx * delta;
    motion.y += motion.vy * delta;
    motion.strength += (target.strength - motion.strength) * (1 - Math.exp(-delta * FADE_RATE));

    const stopped = Math.hypot(motion.vx, motion.vy) < 1 && Math.hypot(target.x - motion.x, target.y - motion.y) < 0.5;
    const faded = Math.abs(target.strength - motion.strength) < EPSILON;
    const finished = faded && (stopped || target.strength === 0);

    if (finished) {
        motion.strength = target.strength;
        motion.vx = 0;
        motion.vy = 0;
    }

    return !finished;
};
