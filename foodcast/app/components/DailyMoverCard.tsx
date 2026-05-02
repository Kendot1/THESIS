"use client";
import { useMemo, useId } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, TrendingUp } from "lucide-react";
import { DEFAULT_PRODUCT_IMAGE } from "../lib/data";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface DailyMoverCardProps {
  id: string;
  name: string;
  emoji: string;
  image: string;
  category: string;
  currentPrice: number;
  predictedPrice: number;
  forecastData: {
    name: string;
    actual: number | null;
    predicted: number | null;
  }[];
  variant?: string;
  origin?: string;
}


const DailyMoverCard = ({
  id,
  name,
  emoji,
  image,
  category,
  currentPrice,
  predictedPrice,
  forecastData,
  variant,
  origin,
}: DailyMoverCardProps) => {
  const change = ((predictedPrice - currentPrice) / currentPrice) * 100;
  const priceChange = predictedPrice - currentPrice;
  const isUp = change >= 0;
  const baseId = useId();
  const gradientId = `mover-grad-${baseId.replace(/:/g, "")}`;

  // Merge actual + predicted into a single continuous line for the chart
  const chartData = useMemo(() => {
    return forecastData.map((d) => ({
      name: d.name,
      price: d.actual ?? d.predicted ?? 0,
      isForecasted: d.actual === null,
    }));
  }, [forecastData]);

  return (
    <Link
      href={`/Product/${id}`}
      className="daily-mover-card group relative block bg-white/90 rounded-2xl sm:rounded-3xl border border-gray-100/80
        transition-all duration-500 ease-out
        hover:shadow-[0_12px_48px_rgba(11,61,46,0.12)] hover:-translate-y-1
        focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
    >
      {/* Top gradient wave decoration */}
      <div className="absolute top-0 left-0 right-0 h-16 sm:h-20">
        <svg
          viewBox="0 0 500 80"
          className="w-full h-full rounded-2xl sm:rounded-3xl"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id={`${gradientId}-wave`} x1="0" y1="0" x2="1" y2="0.5">
              <stop offset="30%" stopColor="#1ec492ff" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#7ED957" stopOpacity="0.1" />
            </linearGradient>
          </defs>
          <path
            d="M0,0 L500,0 L500,35 Q400,55 300,40 Q200,25 100,45 Q50,55 0,40 Z"
            fill={`url(#${gradientId}-wave)`}
          />
        </svg>
      </div>

      <div className="relative p-3 sm:p-5">
        {/* Row 1: Header — icon, name, category, change badge */}
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl overflow-hidden border border-gray-100 bg-gray-50 shrink-0 shadow-sm">
              <img
                src={image || DEFAULT_PRODUCT_IMAGE}
                alt={name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  if (target.src !== DEFAULT_PRODUCT_IMAGE) {
                    target.src = DEFAULT_PRODUCT_IMAGE;
                  }
                }}
              />
            </div>
            <div className="min-w-0">
              <h3
                className="font-bold text-gray-900 text-[13px] sm:text-[15px] leading-tight truncate group-hover:text-primary-800 transition-colors"
                style={{ fontFamily: "var(--font-display)" }}
              >
                {variant ? `${variant} ${name}` : name}
              </h3>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] sm:text-xs text-gray-400">{category}</span>
                {origin && (
                  <>
                    <span className="text-[10px] text-gray-300">•</span>
                    <span className="text-[10px] sm:text-xs text-primary-600/60 font-medium truncate max-w-[80px]">
                      {origin}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <span
            className={`inline-flex items-center gap-0.5 text-[10px] sm:text-xs font-bold px-2 sm:px-2.5 py-1 sm:py-1.5 rounded-lg sm:rounded-xl transition-all duration-300 shrink-0 ${isUp
              ? "text-positive bg-positive/10 group-hover:bg-positive/15"
              : "text-negative bg-negative/10 group-hover:bg-negative/15"
              }`}
          >
            {isUp ? "Increase" : "Decrease"}{" "}
            {isUp ? (
              <ArrowUpRight className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
            ) : (
              <ArrowDownRight className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
            )}
            {Math.abs(change).toFixed(2)}%
          </span>
        </div>

        {/* Row 2: Price stat boxes */}
        <div className="grid grid-cols-3 gap-1.5 sm:gap-3 mb-3 sm:mb-5">
          {/* Current Price */}
          <div className="bg-gray-50/80 rounded-lg sm:rounded-xl p-2 sm:p-3 border border-gray-100/60">
            <div className="text-[8px] sm:text-[10px] text-gray-400 uppercase tracking-wider font-semibold mb-0.5">
              Current Price
            </div>
            <div className="text-[12px] sm:text-base font-bold text-gray-900 tabular-nums">
              ₱{currentPrice.toFixed(2)}
            </div>
            <div className="text-[8px] sm:text-[10px] text-gray-400">per kg</div>
          </div>

          {/* Predicted Price */}
          <div className="bg-gray-50/80 rounded-lg sm:rounded-xl p-2 sm:p-3 border border-gray-100/60">
            <div className="text-[8px] sm:text-[10px] text-gray-400 uppercase tracking-wider font-semibold mb-0.5">
              Predicted Price
            </div>
            <div className={`text-[12px] sm:text-base font-bold tabular-nums ${isUp ? "text-positive" : "text-negative"}`}>
              ₱{predictedPrice.toFixed(2)}
            </div>
            <div className="text-[8px] sm:text-[10px] text-gray-400">per kg</div>
          </div>

          {/* Price Change */}
          <div className={`rounded-lg sm:rounded-xl p-2 sm:p-3 border ${isUp
            ? "bg-positive/5 border-positive/10"
            : "bg-negative/5 border-negative/10"
            }`}>
            <div className="text-[8px] sm:text-[10px] text-gray-400 uppercase tracking-wider font-semibold mb-0.5">
              Price Change
            </div>
            <div className={`text-[12px] sm:text-base font-bold tabular-nums ${isUp ? "text-positive" : "text-negative"}`}>
              {isUp ? "+" : ""}₱{priceChange.toFixed(2)}
            </div>
            <div className={`text-[8px] sm:text-[10px] ${isUp ? "text-positive/60" : "text-negative/60"}`}>
              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Row 3: Line Chart */}
        <div className="bg-gray-50/50 rounded-lg sm:rounded-xl border border-gray-100/60 p-2 sm:p-3">
          <div className="h-[120px] sm:h-[160px]">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4A90D9" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#4A90D9" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 9, fill: "#9CA3AF" }}
                  axisLine={{ stroke: "#E5E7EB" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: "#9CA3AF" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `₱${v}`}
                  width={40}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 10,
                    border: "none",
                    boxShadow: "0 4px 14px rgba(0,0,0,0.1)",
                    fontSize: 11,
                    fontFamily: "'Inter', sans-serif",
                    padding: "6px 10px",
                  }}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any) => [
                    `₱${Number(value).toFixed(2)}`,
                    variant ? `${variant} ${name}` : name
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke="#4A90D9"
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  dot={{ r: 3, fill: "#4A90D9", stroke: "#fff", strokeWidth: 1.5 }}
                  activeDot={{ r: 4, fill: "#4A90D9", stroke: "#fff", strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </Link>
  );
};

export default DailyMoverCard;
