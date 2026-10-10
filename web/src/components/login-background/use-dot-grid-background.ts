import { type RefObject, useEffect } from "react";
import { createDotGridMotion, stepDotGridMotion } from "./dot-grid-motion";
import { createDotGridRenderer } from "./dot-grid-renderer";

const BRUSH_MIN_SPEED = 20;

const readDpr = () => Math.min(window.devicePixelRatio || 1, 2);

export const useDotGridBackground = (canvasRef: RefObject<HTMLCanvasElement | null>) => {
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const renderer = createDotGridRenderer(canvas);
        if (!renderer) {
            canvas.style.visibility = "hidden";
            return;
        }

        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const motion = createDotGridMotion();
        const target = { x: 0, y: 0, strength: 0 };
        let dpr = readDpr();
        let frame = 0;
        let previous = 0;
        let lost = false;

        const loop = (now: number) => {
            const delta = Math.min((now - previous) / 1000, 1 / 30);
            const from = { x: motion.x, y: motion.y };
            const animating = stepDotGridMotion(motion, target, delta);
            previous = now;
            let wet = renderer.dry(delta);
            if (motion.strength > 0.05 && Math.hypot(motion.vx, motion.vy) > BRUSH_MIN_SPEED * dpr) {
                renderer.paint(from.x, from.y, motion.x, motion.y, motion.strength);
                wet = true;
            }
            renderer.draw();
            frame = animating || wet ? requestAnimationFrame(loop) : 0;
        };

        const start = () => {
            if (frame || lost) return;
            previous = performance.now();
            frame = requestAnimationFrame(loop);
        };

        const resize = () => {
            if (lost) return;
            if (renderer.resize(dpr)) renderer.draw();
        };

        const handlePointerMove = (event: PointerEvent) => {
            const rect = canvas.getBoundingClientRect();
            const x = (event.clientX - rect.left) * dpr;
            const y = (rect.bottom - event.clientY) * dpr;
            if (motion.strength < 0.01) Object.assign(motion, { x, y, vx: 0, vy: 0 });
            Object.assign(target, { x, y, strength: 1 });
            start();
        };

        const handlePointerEnd = (event: PointerEvent) => {
            if (event.type === "pointerleave" || event.pointerType !== "mouse") {
                target.strength = 0;
                start();
            }
        };

        const handleContextLost = () => {
            lost = true;
            cancelAnimationFrame(frame);
            frame = 0;
            canvas.style.visibility = "hidden";
        };

        let resolutionQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
        const handleResolutionChange = () => {
            const next = readDpr();
            const scale = next / dpr;
            for (const point of [motion, target]) {
                point.x *= scale;
                point.y *= scale;
            }
            dpr = next;
            resize();
            resolutionQuery.removeEventListener("change", handleResolutionChange);
            resolutionQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
            resolutionQuery.addEventListener("change", handleResolutionChange);
        };

        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(canvas);
        resolutionQuery.addEventListener("change", handleResolutionChange);
        canvas.addEventListener("webglcontextlost", handleContextLost);

        if (!reducedMotion) {
            window.addEventListener("pointermove", handlePointerMove);
            window.addEventListener("pointerup", handlePointerEnd);
            window.addEventListener("pointercancel", handlePointerEnd);
            document.documentElement.addEventListener("pointerleave", handlePointerEnd);
        }

        return () => {
            cancelAnimationFrame(frame);
            resizeObserver.disconnect();
            resolutionQuery.removeEventListener("change", handleResolutionChange);
            canvas.removeEventListener("webglcontextlost", handleContextLost);
            window.removeEventListener("pointermove", handlePointerMove);
            window.removeEventListener("pointerup", handlePointerEnd);
            window.removeEventListener("pointercancel", handlePointerEnd);
            document.documentElement.removeEventListener("pointerleave", handlePointerEnd);
            renderer.dispose();
        };
    }, [canvasRef]);
};
