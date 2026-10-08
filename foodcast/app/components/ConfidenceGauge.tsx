"use client";

/**
 * ConfidenceGauge – a circular/radial SVG progress gauge that
 * displays a backend reliability percentage visually.
 *
 * Props:
 *  - percentage: backend score from 0–100, or null when unavailable
 *  - size: pixel diameter (default 64)
 *  - strokeWidth: thickness of the arc (default 5)
 *  - label: backend confidence level
 *  - sublabel: optional secondary line (e.g. "n=25889")
 *  - variant: "badge" (compact, top bar) | "card" (larger, insight card)
 */
interface ConfidenceGaugeProps {
  percentage: number | null;
  size?: number;
  strokeWidth?: number;
  label?: string;
  sublabel?: string;
  variant?: "badge" | "card";
  title?: string;
}

function getGaugeColor(pct: number): { stroke: string; text: string; bg: string; glow: string } {
  if (pct >= 90) return { stroke: "#2E7D32", text: "text-positive", bg: "bg-positive/10", glow: "shadow-[0_0_12px_rgba(46,125,50,0.25)]" };
  if (pct >= 80) return { stroke: "#7ED957", text: "text-accent-dark", bg: "bg-accent/10", glow: "shadow-[0_0_12px_rgba(126,217,87,0.25)]" };
  if (pct >= 70) return { stroke: "#FFB300", text: "text-yellow-600", bg: "bg-yellow/10", glow: "shadow-[0_0_12px_rgba(255,179,0,0.2)]" };
  return { stroke: "#C62828", text: "text-negative", bg: "bg-negative/10", glow: "shadow-[0_0_12px_rgba(198,40,40,0.2)]" };
}

export default function ConfidenceGauge({
  percentage,
  size = 64,
  strokeWidth = 5,
  label,
  sublabel,
  variant = "badge",
  title,
}: ConfidenceGaugeProps) {
  const pct = percentage ?? 0;
  const hasData = percentage != null;

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = hasData ? Math.min(Math.max(pct / 100, 0), 1) : 0;
  const dashOffset = circumference * (1 - progress);

  const { stroke, text, glow } = hasData
    ? getGaugeColor(pct)
    : { stroke: "#d1d5db", text: "text-gray-400", glow: "" };

  const isBadge = variant === "badge";

  return (
    <div
      className={`flex items-center gap-3 ${isBadge ? "" : "gap-4"}`}
      title={title}
    >
      {/* SVG radial gauge */}
      <div className={`relative shrink-0 rounded-full ${glow}`} style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-90"
        >
          {/* Background track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            className="text-gray-200"
            strokeWidth={strokeWidth}
          />
          {/* Progress arc */}
          {hasData && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={stroke}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              className="transition-all duration-1000 ease-out"
            />
          )}
        </svg>
        {/* Center percentage */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className={`font-black ${text} leading-none`}
            style={{ fontSize: isBadge ? size * 0.22 : size * 0.24 }}
          >
            {hasData ? `${pct.toFixed(0)}%` : "—"}
          </span>
        </div>
      </div>

      {/* Text info beside the gauge */}
      <div className={`flex flex-col min-w-0 ${isBadge ? "items-end text-right" : ""}`}>
        {label && (
          <span
            className={`font-bold uppercase tracking-wider leading-tight ${
              isBadge ? "text-[10px] text-accent" : "text-[11px] text-gray-700"
            }`}
          >
            {label}
          </span>
        )}

        {sublabel && (
          <span className="text-[8px] text-gray-400 font-bold mt-0.5 uppercase">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  );
}
