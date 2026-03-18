"use client";
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

const ForecastChart = ({ data, height = 200, showGrid = true, showLegend = true }: ForecastChartProps) => {
  // Find transition point
  const transitionIndex = data.findIndex(d => d.predicted !== null && d.actual === null);

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
          {showGrid && (
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
          )}
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={{ stroke: "#E5E7EB" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `₱${v}`}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 12,
              border: "none",
              boxShadow: "0 4px 14px rgba(0,0,0,0.1)",
              fontSize: 12,
              fontFamily: "'Inter', sans-serif",
            }}
            formatter={(value: number, name: string) => [
              `₱${value.toFixed(2)}`,
              name === "actual" ? "Actual Price" : "Predicted Price",
            ]}
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
                fontSize: 10,
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
            strokeWidth={2.5}
            fill="url(#actualGradient)"
            dot={false}
            connectNulls={false}
          />
          <Area
            type="monotone"
            dataKey="predicted"
            stroke="#7ED957"
            strokeWidth={2.5}
            strokeDasharray="6 4"
            fill="url(#predictedGradient)"
            dot={false}
            connectNulls={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      {showLegend && (
        <div className="forecast-legend">
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
