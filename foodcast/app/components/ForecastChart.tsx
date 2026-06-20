"use client";
import { useRef, useEffect, useMemo, useCallback } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  CrosshairMode,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useLanguage } from "../lib/i18n/LanguageContext";

interface DataPoint {
  date: string;
  name: string;
  actual: number | null;
  predicted: number | null;
}

interface ForecastChartProps {
  data: DataPoint[];
  height?: number;
  showGrid?: boolean;
  showLegend?: boolean;
  productName?: string;
  period?: string;
}

const ForecastChart = ({
  data,
  height,
  showGrid = true,
  showLegend = true,
  productName,
  period = "Daily",
}: ForecastChartProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const actualSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const predictedSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const { t } = useLanguage();
  // Keep a ref to t so the chart creation effect doesn't need t as a dependency
  const tRef = useRef(t);
  tRef.current = t;

  // Build series data
  const { actualData, predictedData } = useMemo(() => {
    const groupedActuals = new Map<string, number[]>();
    const groupedPredictions = new Map<string, number[]>();

    const getGroupKey = (dateStr: string) => {
      if (period === "Weekly") {
        const d = new Date(dateStr + "T00:00:00");
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        const weekStart = new Date(d.getFullYear(), d.getMonth(), diff);
        const pad = (n: number) => n.toString().padStart(2, "0");
        return `${weekStart.getFullYear()}-${pad(weekStart.getMonth() + 1)}-${pad(weekStart.getDate())}`;
      }
      if (period === "Monthly") {
        return dateStr.substring(0, 7) + "-01";
      }
      return dateStr;
    };

    for (const point of data) {
      if (!point.date) continue;
      const key = getGroupKey(point.date);

      if (point.actual !== null) {
        if (!groupedActuals.has(key)) groupedActuals.set(key, []);
        groupedActuals.get(key)!.push(point.actual);
      }

      if (point.predicted !== null) {
        if (!groupedPredictions.has(key)) groupedPredictions.set(key, []);
        groupedPredictions.get(key)!.push(point.predicted);
      }
    }

    const actuals = Array.from(groupedActuals.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([time, values]) => ({
        time: time as Time,
        value: values.reduce((a, b) => a + b, 0) / values.length,
      }));

    const predictions = Array.from(groupedPredictions.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([time, values]) => ({
        time: time as Time,
        value: values.reduce((a, b) => a + b, 0) / values.length,
      }));

    return { actualData: actuals, predictedData: predictions };
  }, [data, period]);

  // We just let the chart fit the content to the aggregated data automatically
  const getVisibleRange = useCallback(() => {
    return null;
  }, []);

  // Create chart
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9CA3AF",
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: {
          visible: showGrid,
          color: "rgba(0, 0, 0, 0.04)",
          style: LineStyle.Dotted,
        },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          width: 1,
          color: "rgba(11, 59, 36, 0.3)",
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0B3B24",
        },
        horzLine: {
          width: 1,
          color: "rgba(11, 59, 36, 0.3)",
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0B3B24",
        },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 30,
      },
      handleScroll: { vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true },
      width: container.clientWidth,
      height: height || 380,
    });

    // Actual price series (solid dark green area)
    const actualSeries = chart.addSeries(AreaSeries, {
      lineColor: "#0B3B24",
      topColor: "rgba(11, 59, 36, 0.25)",
      bottomColor: "rgba(11, 59, 36, 0.02)",
      lineWidth: 2,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: "#0B3B24",
      crosshairMarkerBackgroundColor: "#fff",
      crosshairMarkerBorderWidth: 2,
      title: tRef.current("actualPrice"),
    });

    // Predicted price series (dashed green area)
    const predictedSeries = chart.addSeries(AreaSeries, {
      lineColor: "#7ED957",
      topColor: "rgba(126, 217, 87, 0.15)",
      bottomColor: "rgba(126, 217, 87, 0.01)",
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: "#7ED957",
      crosshairMarkerBackgroundColor: "#fff",
      crosshairMarkerBorderWidth: 2,
      title: tRef.current("predictedPrice"),
    });

    chartRef.current = chart;
    actualSeriesRef.current = actualSeries;
    predictedSeriesRef.current = predictedSeries;

    // Tooltip logic
    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip || !containerRef.current) return;

      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > containerRef.current.clientWidth ||
        param.point.y < 0 ||
        param.point.y > containerRef.current.clientHeight
      ) {
        tooltip.style.display = "none";
        return;
      }

      const actualData = param.seriesData.get(actualSeries);
      const predictedData = param.seriesData.get(predictedSeries);

      let priceData: any = null;
      let title = "";
      let color = "";

      if (actualData && (actualData as any).value !== undefined) {
        priceData = actualData;
        title = tRef.current("actualPrice");
        color = "#0B3B24";
      } else if (predictedData && (predictedData as any).value !== undefined) {
        priceData = predictedData;
        title = tRef.current("predictedPrice");
        color = "#7ED957";
      }

      if (priceData) {
        tooltip.style.display = "block";
        const dateStr = param.time as string;
        const formattedDate = new Date(dateStr).toLocaleDateString("en-US", {
          month: "long",
          day: "numeric",
          year: "numeric"
        });

        tooltip.innerHTML = `
          <div style="font-size: 10px; font-weight: 700; color: #9CA3AF; margin-bottom: 4px;">${formattedDate}</div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <div style="width: 8px; height: 8px; border-radius: 50%; background-color: ${color};"></div>
            <span style="font-size: 12px; font-weight: 700; color: #111827;">${title}:</span>
            <span style="font-size: 14px; font-weight: 900; color: #111827;">₱${priceData.value.toFixed(2)}</span>
          </div>
        `;

        // Position tooltip
        let left = param.point.x + 15;
        let top = param.point.y + 15;

        // Prevent tooltip from overflowing the right edge
        if (left > containerRef.current.clientWidth - 150) {
          left = param.point.x - 160;
        }

        tooltip.style.left = left + "px";
        tooltip.style.top = top + "px";
      } else {
        tooltip.style.display = "none";
      }
    });

    // Handle resize
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        chart.applyOptions({ width });
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      actualSeriesRef.current = null;
      predictedSeriesRef.current = null;
    };
  }, [showGrid, height]);

  // Update series titles when language changes (without recreating the chart)
  useEffect(() => {
    if (actualSeriesRef.current) {
      actualSeriesRef.current.applyOptions({ title: t("actualPrice") });
    }
    if (predictedSeriesRef.current) {
      predictedSeriesRef.current.applyOptions({ title: t("predictedPrice") });
    }
  }, [t]);

  // Helper to fit content but preserve right allowance
  const fitContentWithAllowance = useCallback(() => {
    if (!chartRef.current) return;
    chartRef.current.timeScale().fitContent();
    const logicalRange = chartRef.current.timeScale().getVisibleLogicalRange();
    if (logicalRange) {
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: logicalRange.from,
        to: logicalRange.to + 12, // add empty space bars to the right
      });
    }
  }, []);

  // Update data when it changes
  useEffect(() => {
    if (!actualSeriesRef.current || !predictedSeriesRef.current) return;

    actualSeriesRef.current.setData(actualData);
    predictedSeriesRef.current.setData(predictedData);

    // Set visible range or auto-fit
    const range = getVisibleRange();
    if (range && chartRef.current) {
      try {
        chartRef.current.timeScale().setVisibleRange(range);
      } catch {
        fitContentWithAllowance();
      }
    } else if (chartRef.current) {
      fitContentWithAllowance();
    }
  }, [actualData, predictedData, getVisibleRange, fitContentWithAllowance]);

  // Auto-fit when period changes
  useEffect(() => {
    if (!chartRef.current) return;
    const range = getVisibleRange();
    if (range) {
      try {
        chartRef.current.timeScale().setVisibleRange(range);
      } catch {
        fitContentWithAllowance();
      }
    } else {
      fitContentWithAllowance();
    }
  }, [period, getVisibleRange, fitContentWithAllowance]);

  return (
    <div>

      <div className="relative">
        <div
          ref={tooltipRef}
          className="absolute z-50 pointer-events-none bg-white backdrop-blur-sm rounded-xl 
          shadow-[0_8px_30px_rgb(0,0,0,0.12)] border border-gray-100 p-3 transition-all duration-75 ease-out"
          style={{ display: "none" }}
        />
        <div
          ref={containerRef}
          className={!height ? "w-full" : "h-full w-full"}
          style={{ minHeight: height || 380 }}
        />
      </div>
      {showLegend && (
        <div className="flex items-center gap-6 mt-3 -mb-1 ml-2">
          <div className="flex items-center gap-2">
            <div className="forecast-legend-dot" style={{ background: "#0B3B24" }} />
            <span className="text-[10px] font-medium text-gray-900">{t("actualPrice")}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="forecast-legend-dot" style={{ background: "#7ED957" }} />
            <span className="text-[10px] font-medium text-gray-900">{t("predictedPrice")}</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default ForecastChart;
