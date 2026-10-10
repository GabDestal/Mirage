const BRUSH_RADIUS = 198;
const BRUSH_LOAD = 0.14;
const BRUSH_DRY_RATE = 0.3;
const BRUSH_EDGE = [0.36, 0.46];
const BRUSH_FRINGE = [0.14, 0.36];
const BRUSH_FRINGE_STRENGTH = 0.35;
const BRUSH_RAGGEDNESS = 0.34;
const BRUSH_LOBES = [
    { lobes: 2, amount: 0.22 },
    { lobes: 3, amount: 0.16 },
    { lobes: 5, amount: 0.1 },
];
const INK_FLOOR = 0.004;
const REST_DOT_RADIUS = 0.8;
const ACTIVE_DOT_RADIUS = 1.05;

type Palette = {
    background: [number, number, number];
    dot: [number, number, number];
    active: [number, number, number];
    glow: [number, number, number];
    spacing: number;
};

const glsl = (value: number) => value.toFixed(4);

const smoothstep = (from: number, to: number, value: number) => {
    const t = Math.min(Math.max((value - from) / (to - from), 0), 1);
    return t * t * (3 - 2 * t);
};

const brushProfile = (scaled: number) => 1 - smoothstep(0.2, 1, scaled);

const seeded = (x: number, y: number, salt: number) => {
    const value = Math.sin(x * 12.9898 + y * 78.233 + salt * 37.719) * 43758.5453;
    return value - Math.floor(value);
};

const brushShape = (x: number, y: number) => {
    const phases = BRUSH_LOBES.map((_, index) => seeded(Math.round(x / 40), Math.round(y / 40), index) * Math.PI * 2);
    return (angle: number) =>
        1 + BRUSH_LOBES.reduce((sum, { lobes, amount }, index) => sum + amount * Math.sin(lobes * angle + phases[index]), 0);
};

const VERTEX_SHADER = `
attribute vec2 aPosition;
void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform float uDpr;
uniform float uSpacing;
uniform vec3 uBackground;
uniform vec3 uDot;
uniform vec3 uActive;
uniform vec3 uGlow;
uniform sampler2D uInk;
uniform vec2 uInkSize;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y) * 2.0 - 1.0;
}

float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float dotCoverage(vec2 px, vec2 center, float dotRadius) {
    return 1.0 - smoothstep(dotRadius * uDpr - 0.5, dotRadius * uDpr + 0.5, length(px - center));
}

void main() {
    vec2 px = gl_FragCoord.xy;
    float cell = uSpacing * uDpr;
    vec2 index = floor(px / cell);
    vec2 center = (index + 0.5) * cell;

    float ink = texture2D(uInk, (index + 0.5) / uInkSize).r;
    float intensity = 0.0;
    if (ink > 0.0) {
        vec2 paper = center / (${glsl(BRUSH_RADIUS)} * uDpr);
        float bristles = 0.5 * valueNoise(paper * 2.5 + 4.7) + 0.3 * valueNoise(paper * 6.0 + 1.9) + 0.2 * valueNoise(paper * 15.0 + 8.3);
        float wet = ink + bristles * ${glsl(BRUSH_RAGGEDNESS)};
        float body = smoothstep(${glsl(BRUSH_EDGE[0])}, ${glsl(BRUSH_EDGE[1])}, wet);
        float fringe = smoothstep(${glsl(BRUSH_FRINGE[0])}, ${glsl(BRUSH_FRINGE[1])}, wet) * ${glsl(BRUSH_FRINGE_STRENGTH)};
        intensity = max(body, fringe);
    }

    float coverage = dotCoverage(px, center, mix(${glsl(REST_DOT_RADIUS)}, ${glsl(ACTIVE_DOT_RADIUS)}, intensity));
    vec3 color = mix(uDot, uActive, smoothstep(0.02, 0.6, intensity));
    vec3 glow = mix(uBackground, uGlow, intensity * 0.5);

    gl_FragColor = vec4(mix(glow, color, coverage), 1.0);
}
`;

const toRgb = (color: string): [number, number, number] => {
    const context = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
    if (!context) return [0, 0, 0];
    context.fillStyle = color;
    context.fillRect(0, 0, 1, 1);
    const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
    return [r / 255, g / 255, b / 255];
};

const readPalette = (element: HTMLElement): Palette => {
    const styles = getComputedStyle(element);
    const read = (name: string) => styles.getPropertyValue(name).trim();
    return {
        background: toRgb(read("--auth-background")),
        dot: toRgb(read("--auth-dot")),
        active: toRgb(read("--auth-dot-active")),
        glow: toRgb(read("--auth-glow")),
        spacing: Number.parseFloat(read("--auth-dot-spacing")) || 5,
    };
};

const compile = (gl: WebGLRenderingContext, type: number, source: string) => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        gl.deleteShader(shader);
        return null;
    }
    return shader;
};

export type DotGridRenderer = {
    resize: (dpr: number) => boolean;
    draw: () => void;
    paint: (fromX: number, fromY: number, toX: number, toY: number, strength: number) => void;
    dry: (delta: number) => boolean;
    dispose: () => void;
};

export const createDotGridRenderer = (canvas: HTMLCanvasElement): DotGridRenderer | null => {
    const gl = canvas.getContext("webgl", { antialias: false });
    if (!gl) return null;

    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    const program = gl.createProgram();
    const buffer = gl.createBuffer();

    const traceTexture = gl.createTexture();

    const dispose = () => {
        gl.deleteProgram(program);
        gl.deleteShader(vertex);
        gl.deleteShader(fragment);
        gl.deleteBuffer(buffer);
        gl.deleteTexture(traceTexture);
    };

    if (!vertex || !fragment || !program || !buffer || !traceTexture) {
        dispose();
        return null;
    }

    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        dispose();
        return null;
    }
    gl.useProgram(program);

    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const uniform = (name: string) => gl.getUniformLocation(program, name);
    const uniforms = {
        dpr: uniform("uDpr"),
        inkSize: uniform("uInkSize"),
    };

    let dpr = 1;
    let columns = 1;
    let rows = 1;
    let trace = new Float32Array(1);
    let traceBytes = new Uint8Array(1);
    let traceDirty = true;

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, traceTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.uniform1i(uniform("uInk"), 0);

    const stamp = (x: number, y: number, strength: number) => {
        const cell = palette.spacing * dpr;
        const radius = (BRUSH_RADIUS * dpr) / cell;
        const reach = radius * (1 + BRUSH_LOBES.reduce((sum, { amount }) => sum + amount, 0));
        const shape = brushShape(x / dpr, y / dpr);
        const load = BRUSH_LOAD * (0.6 + 0.8 * seeded(Math.round(x / dpr / 25), Math.round(y / dpr / 25), 7));
        const column = x / cell;
        const row = y / cell;
        for (let r = Math.max(0, Math.floor(row - reach)); r <= Math.min(rows - 1, Math.ceil(row + reach)); r++) {
            for (let c = Math.max(0, Math.floor(column - reach)); c <= Math.min(columns - 1, Math.ceil(column + reach)); c++) {
                const dx = c + 0.5 - column;
                const dy = r + 0.5 - row;
                const scaled = Math.hypot(dx, dy) / (radius * shape(Math.atan2(dy, dx)));
                if (scaled >= 1) continue;
                const index = r * columns + c;
                trace[index] = 1 - (1 - trace[index]) * (1 - brushProfile(scaled) * strength * load);
            }
        }
        traceDirty = true;
    };

    const palette = readPalette(canvas);
    gl.uniform1f(uniform("uSpacing"), palette.spacing);
    gl.uniform3fv(uniform("uBackground"), palette.background);
    gl.uniform3fv(uniform("uDot"), palette.dot);
    gl.uniform3fv(uniform("uActive"), palette.active);
    gl.uniform3fv(uniform("uGlow"), palette.glow);

    return {
        resize: (nextDpr) => {
            const width = Math.round(canvas.clientWidth * nextDpr);
            const height = Math.round(canvas.clientHeight * nextDpr);
            if (width === canvas.width && height === canvas.height && nextDpr === dpr) return false;
            dpr = nextDpr;
            canvas.width = width;
            canvas.height = height;
            gl.viewport(0, 0, width, height);
            gl.uniform1f(uniforms.dpr, dpr);
            columns = Math.ceil(width / (palette.spacing * dpr));
            rows = Math.ceil(height / (palette.spacing * dpr));
            trace = new Float32Array(columns * rows);
            traceBytes = new Uint8Array(columns * rows);
            traceDirty = true;
            gl.uniform2f(uniforms.inkSize, columns, rows);
            return true;
        },
        paint: (fromX, fromY, toX, toY, strength) => {
            const steps = Math.min(Math.ceil(Math.hypot(toX - fromX, toY - fromY) / ((BRUSH_RADIUS * dpr) / 4)), 24);
            for (let step = 1; step <= Math.max(steps, 1); step++) {
                const t = step / Math.max(steps, 1);
                stamp(fromX + (toX - fromX) * t, fromY + (toY - fromY) * t, strength);
            }
        },
        dry: (delta) => {
            const dry = delta * BRUSH_DRY_RATE;
            let active = false;
            for (let i = 0; i < trace.length; i++) {
                if (trace[i] === 0) continue;
                trace[i] = trace[i] - dry < INK_FLOOR ? 0 : trace[i] - dry;
                active ||= trace[i] > 0;
                traceDirty = true;
            }
            return active;
        },
        draw: () => {
            if (traceDirty) {
                for (let i = 0; i < trace.length; i++) traceBytes[i] = trace[i] * 255;
                gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, columns, rows, 0, gl.LUMINANCE, gl.UNSIGNED_BYTE, traceBytes);
                traceDirty = false;
            }
            gl.drawArrays(gl.TRIANGLES, 0, 3);
        },
        dispose,
    };
};
