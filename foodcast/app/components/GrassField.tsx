"use client";
import { useMemo } from "react";

/* ──────────────────────────────────────────────────────
   GrassField – Farm-style animated grass for the footer
   ─────────────────────────────────────────────────────
   Optimisations vs the old 800-blade / 7-layer version:
   • 3 SVG layers with ~180 total blades (not 800×7)
   • One shared <defs> block
   • CSS class animation (GPU-composited rotate)
   • Seeded PRNG → deterministic, SSR-safe
   ────────────────────────────────────────────────────── */

// Seeded PRNG — identical output server & client
const rand = (seed: number) => {
  const x = Math.sin(seed * 9301 + 49297) * 49297;
  return x - Math.floor(x);
};

// Rich farm greens — darker → lighter
const PALETTE = [
  "#1B5E20", "#2E7D32", "#388E3C", "#43A047",
  "#4CAF50", "#66BB6A", "#7CB342", "#8BC34A",
  "#9CCC65", "#AED581",
];

interface Blade {
  x: number;       // base x in viewBox units
  height: number;  // blade height
  curve: number;   // horizontal tip offset
  width: number;   // stroke width
  color: string;
  delay: number;   // animation delay (s)
  dur: number;     // animation duration (s)
}

const VIEW_W = 1440;
const VIEW_H = 300;
const BASE_Y = VIEW_H; // blades grow upward from bottom

function generateBlade(i: number, seedOffset: number, total: number): Blade {
  const r0 = rand(i + seedOffset);
  const r1 = rand(i + seedOffset + 1111);
  const r2 = rand(i + seedOffset + 2222);
  const r3 = rand(i + seedOffset + 3333);
  const r4 = rand(i + seedOffset + 4444);

  return {
    x: (i / total) * VIEW_W + (r0 - 0.5) * 18,
    height: 35 + r1 * 120,
    curve: (r2 - 0.5) * 40,
    width: 1 + r3 * 3,
    color: PALETTE[Math.floor(r4 * PALETTE.length)],
    delay: r0 * 8,
    dur: 4 + r1 * 8,
  };
}

/** Cubic bezier path from (x, baseY) curving up to the tip */
function bladePath(b: Blade): string {
  const tipX = b.x + b.curve;
  const tipY = BASE_Y - b.height;
  const cp1X = b.x + b.curve * 0.3;
  const cp1Y = BASE_Y - b.height * 0.4;
  const cp2X = b.x + b.curve * 0.7;
  const cp2Y = BASE_Y - b.height * 0.8;
  return `M${b.x},${BASE_Y} C${cp1X},${cp1Y} ${cp2X},${cp2Y} ${tipX},${tipY}`;
}

/* ── Layer configs ────────────────────────────────
   [count, heightScale, opacityBase, strokeScale, tintColor?]
   Back → front so painters algorithm works.              */
type LayerCfg = [number, number, number, number, string | null];
const LAYERS: LayerCfg[] = [
  [40, 0.35, 0.22, 0.6, "#4a7a46"],  // far — small, muted
  [55, 0.60, 0.45, 0.8, null],       // mid
  [70, 1.00, 0.80, 1.0, null],       // close — full size, vivid
];

const GrassField = () => {
  const layers = useMemo(() =>
    LAYERS.map(([count, hScale, opacity, wScale, tint], li) => {
      const blades: Blade[] = [];
      for (let i = 0; i < count; i++) {
        const b = generateBlade(i, li * 7000, count);
        blades.push({
          ...b,
          height: b.height * hScale,
          width: b.width * wScale,
          color: tint ?? b.color,
        });
      }
      return { blades, opacity };
    }),
    []);

  // Small wildflower dots nestled in the grass
  const flowers = useMemo(() =>
    Array.from({ length: 12 }, (_, i) => {
      const r = rand(i + 9000);
      const r2 = rand(i + 9200);
      const r3 = rand(i + 9400);
      const colors = ["#FFF9C4", "#FFFFFF", "#F8BBD0", "#CE93D8", "#FFD54F"];
      return {
        cx: 40 + r * (VIEW_W - 80),
        cy: VIEW_H - 30 - r2 * 60,
        r: 2.5 + r * 3,
        fill: colors[Math.floor(r3 * colors.length)],
        delay: r2 * 6,
        dur: 5 + r * 5,
      };
    }),
    []);

  return (
    <div className="grass-field" aria-hidden="true">
      {/* Sky-to-ground gradient background */}
      <div className="grass-sky" />

      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
        className="grass-svg"
      >
        {/* Shared gradient defs */}
        <defs>
          <linearGradient id="grass-soil" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2E7D32" stopOpacity="0" />
            <stop offset="50%" stopColor="#1B5E20" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#0B3D2E" stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* Ground soil band */}
        <rect x="0" y={VIEW_H - 50} width={VIEW_W} height="50" fill="url(#grass-soil)" />

        {/* Grass blade layers */}
        {layers.map((layer, li) =>
          layer.blades.map((b, bi) => (
            <path
              key={`g${li}-${bi}`}
              d={bladePath(b)}
              stroke={b.color}
              strokeWidth={b.width}
              fill="none"
              strokeLinecap="round"
              opacity={layer.opacity}
              className="grass-blade"
              style={{
                transformOrigin: `${b.x}px ${BASE_Y}px`,
                animationDelay: `${b.delay}s`,
                animationDuration: `${b.dur}s`,
              }}
            />
          ))
        )}

        {/* Wildflowers */}
        {flowers.map((f, i) => (
          <g key={`fl-${i}`}>
            <circle
              cx={f.cx} cy={f.cy} r={f.r}
              fill={f.fill} opacity={0.55}
              className="grass-blade"
              style={{
                transformOrigin: `${f.cx}px ${f.cy}px`,
                animationDelay: `${f.delay}s`,
                animationDuration: `${f.dur}s`,
              }}
            />
            {/* tiny glow dot in center */}
            <circle
              cx={f.cx} cy={f.cy} r={f.r * 0.3}
              fill="#FFD54F" opacity={0.4}
            />
          </g>
        ))}
      </svg>

      {/* Darkening gradient that blends into the footer body color */}
      <div className="grass-fade" />
    </div>
  );
};

export default GrassField;
