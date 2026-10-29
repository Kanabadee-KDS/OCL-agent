// Geometry of the mock's radarSVG (Skill Portfolio, dashboards): axes start at 12 o'clock and go
// clockwise, values 0–5 on a 100-unit radius around (160,150) in a 320×300 view box.

export const RADAR = { cx: 160, cy: 150, r: 100, max: 5, width: 320, height: 300 };

export type Pt = [number, number];

/** Point of axis `i` of `n` at `fraction` of the radius. */
export function radarPoint(i: number, n: number, fraction: number): Pt {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return [RADAR.cx + RADAR.r * fraction * Math.cos(a), RADAR.cy + RADAR.r * fraction * Math.sin(a)];
}

const fmt = (p: Pt) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`;

/** "x,y x,y …" polygon of the values (each clamped to 0–5). */
export function radarPolygon(values: readonly number[]): string {
  return values.map((v, i) => fmt(radarPoint(i, values.length, Math.max(0, Math.min(RADAR.max, v)) / RADAR.max))).join(" ");
}

/** Grid ring at `fraction` of the radius. */
export function radarRing(n: number, fraction: number): string {
  return Array.from({ length: n }, (_, i) => fmt(radarPoint(i, n, fraction))).join(" ");
}

/** Text anchor of a label beside axis point `p`: centred on the vertical axis, else away from the centre. */
export function labelAnchor(p: Pt): "middle" | "start" | "end" {
  return Math.abs(p[0] - RADAR.cx) < 5 ? "middle" : p[0] > RADAR.cx ? "start" : "end";
}
