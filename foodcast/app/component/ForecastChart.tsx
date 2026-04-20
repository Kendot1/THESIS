"use client";
import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface DataPoint {
  name: string;
  actual: number | null;
  predicted: number | null;
}

interface ForecastChartProps {
  data: DataPoint[];
  height?: number;
  showGrid?: boolean;
  showLegend?: boolean;
}

const ForecastChart = ({ data, showGrid = true, showLegend = true }: ForecastChartProps) => {
  // Find transition point
  const transitionIndex = data.findIndex(d => d.predicted !== null && d.actual === null);

  // Compute Y-axis domain so the chart zooms to the data range instead of starting at 0
  const [yMin, yMax] = useMemo(() => {
    const allValues = data.flatMap(d => [d.actual, d.predicted]).filter((v): v is number => v !== null);
    if (allValues.length === 0) return [0, 100];
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    const padding = (max - min) * 0.15 || 5; // 15% padding, minimum 5
    return [Math.floor(min - padding), Math.ceil(max + padding)];
  }, [data]);

  return (
    <div className="w-full min-w-0 overflow-hidden h-[160px] sm:h-[200px] lg:h-[280px]" style={{ maxWidth: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          {showGrid && (
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
          )}
          <XAxis
            dataKey="name"
            tick={{ fontSize: 9, fill: "#9CA3AF" }}
            axisLine={{ stroke: "#E5E7EB" }}
            tickLine={false}
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fontSize: 9, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `₱${v}`}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 12,
              border: "none",
              boxShadow: "0 4px 14px rgba(0,0,0,0.1)",
              fontSize: 10,
              fontFamily: "'Inter', sans-serif",
            }}
            formatter={(value, name) => {
              const numValue = typeof value === "number" ? value : 0;
              return [
                `₱${numValue.toFixed(2)}`,
                name === "actual" ? "Actual Price" : "Predicted Price",
              ];
            }}
          />
          {transitionIndex > 0 && (
            <ReferenceLine
              x={data[transitionIndex - 1]?.name}
              stroke="#9CA3AF"
              strokeDasharray="5 5"
              label={{
                value: "Forecast",
                position: "top",
                fill: "#9CA3AF",
                fontSize: 9,
              }}
            />
          )}
          <defs>
            <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7ED957" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#7ED957" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="predictedGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7ED957" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#7ED957" stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="actual"
            stroke="#0B3B24"
            strokeWidth={2}
            fill="url(#actualGradient)"
            dot={false}
            connectNulls={false}
          />
          <Area
            type="monotone"
            dataKey="predicted"
            stroke="#7ED957"
            strokeWidth={2}
            strokeDasharray="6 4"
            fill="url(#predictedGradient)"
            dot={false}
            connectNulls={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      {showLegend && (
        <div className="forecast-legend pt-2 sm:pt-0">
          <div className="forecast-legend-item">
            <div className="forecast-legend-dot" style={{ background: "#0B3B24" }} />
            Actual Price
          </div>
          <div className="forecast-legend-item">
            <div className="forecast-legend-dot" style={{ background: "#7ED957" }} />
            Predicted Price
          </div>
        </div>
      )}
    </div>
  );
};

export default ForecastChart;
