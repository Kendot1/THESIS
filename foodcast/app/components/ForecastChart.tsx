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
import { forecastHorizonPoints, type ForecastHorizon } from "../lib/data";

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
  forecastOriginDate: string | undefined;
}

function getSeriesValue(value: unknown): number | undefined {
  if (!value || typeof value !== "object" || !("value" in value)) return undefined;
  const candidate = (value as { value?: unknown }).value;
  return typeof candidate === "number" ? candidate : undefined;
}

const ForecastChart = ({
  data,
  height,
  showGrid = true,
  showLegend = true,
  period = "Daily",
  forecastOriginDate,
}: ForecastChartProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const actualSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const predictedSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const { t } = useLanguage();
  // Keep a ref to t so the chart creation effect doesn't need t as a dependency
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);

  // Build series data
  const { actualData, predictedData } = useMemo(() => {
    const actuals = data.filter(point => point.actual != null && Number.isFinite(point.actual))
      .sort((left, right) => left.date.localeCompare(right.date))
      .map(point => ({ time: point.date as Time, value: point.actual! }));
    const predictions = forecastHorizonPoints(data, forecastOriginDate,
      period.toLowerCase() as ForecastHorizon)
      .map(point => ({ time: point.date as Time, value: point.predicted! }));

    return { actualData: actuals, predictedData: predictions };
  }, [data, period, forecastOriginDate]);

  const forecastRising = useMemo(() => {
    const latestActual = actualData[actualData.length - 1]?.value;
    const finalForecast = predictedData[predictedData.length - 1]?.value;
    return latestActual !== undefined && finalForecast !== undefined
      ? finalForecast >= latestActual
      : true;
  }, [actualData, predictedData]);
  const forecastColor = forecastRising ? "#C62828" : "#2E7D32";
  const forecastFill = forecastRising
    ? "rgba(198, 40, 40, 0.12)"
    : "rgba(46, 125, 50, 0.12)";

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

    // Actual prices use a neutral near-black line so they cannot be confused
    // with the green forecast.
    const actualSeries = chart.addSeries(AreaSeries, {
      lineColor: "#111827",
      topColor: "rgba(17, 24, 39, 0.18)",
      bottomColor: "rgba(17, 24, 39, 0.02)",
      lineWidth: 2,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: "#111827",
      crosshairMarkerBackgroundColor: "#fff",
      crosshairMarkerBorderWidth: 2,
      title: tRef.current("actualPrice"),
    });

    // Keep actuals neutral; forecast color communicates direction.
    const predictedSeries = chart.addSeries(AreaSeries, {
      lineColor: forecastColor,
      topColor: forecastFill,
      bottomColor: forecastRising
        ? "rgba(198, 40, 40, 0.01)"
        : "rgba(46, 125, 50, 0.01)",
      lineWidth: 3,
      lineStyle: LineStyle.Dashed,
      pointMarkersVisible: true,
      pointMarkersRadius: 3,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: forecastColor,
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
      const actualValue = getSeriesValue(actualData);
      const predictedValue = getSeriesValue(predictedData);

      if (actualValue !== undefined || predictedValue !== undefined) {
        tooltip.style.display = "block";
        const dateStr = param.time as string;
        const formattedDate = new Date(dateStr).toLocaleDateString("en-US", {
          month: "long",
          day: "numeric",
          year: "numeric"
        });

        const priceRow = actualValue !== undefined
          ? `<div style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:#111827"></span><b>${tRef.current("actualPrice")}:</b><strong>₱${actualValue.toFixed(2)}</strong></div>`
          : `<div style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:${forecastColor}"></span><b>${tRef.current("predictedPrice")}:</b><strong>₱${predictedValue!.toFixed(2)}</strong></div>`;
        tooltip.innerHTML = `<div style="font-size:10px;font-weight:700;color:#9CA3AF;margin-bottom:4px">${formattedDate}</div>${priceRow}`;

        // Position tooltip
        let left = param.point.x + 15;
        const top = param.point.y + 15;

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
  }, [showGrid, height, forecastColor, forecastFill, forecastRising]);

  // Update series titles when language changes (without recreating the chart)
  useEffect(() => {
    if (actualSeriesRef.current) {
      actualSeriesRef.current.applyOptions({ title: t("actualPrice") });
    }
    if (predictedSeriesRef.current) {
      predictedSeriesRef.current.applyOptions({ title: t("predictedPrice") });
    }
  }, [t]);

  // All tabs keep actual daily dates; predictions follow the selected cadence.
  const applyRelevantRange = useCallback(() => {
    if (!chartRef.current) return;
    const historyBars = period.toLowerCase() === "daily" ? 14 : period.toLowerCase() === "weekly" ? 28 : 90;
    const first = actualData[Math.max(0, actualData.length - historyBars)]?.time
      ?? predictedData[0]?.time;
    const last = predictedData[predictedData.length - 1]?.time
      ?? actualData[actualData.length - 1]?.time;
    if (!first || !last) return;
    try {
      chartRef.current.timeScale().setVisibleRange({ from: first, to: last });
    } catch {
      chartRef.current.timeScale().fitContent();
    }
  }, [actualData, predictedData, period]);

  // Update data when it changes
  useEffect(() => {
    if (!actualSeriesRef.current || !predictedSeriesRef.current) return;

    actualSeriesRef.current.setData(actualData);
    predictedSeriesRef.current.setData(predictedData);
    applyRelevantRange();
  }, [actualData, predictedData, applyRelevantRange]);

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
            <div className="h-0 w-4 border-t-2 border-[#111827]" />
            <span className="text-[10px] font-medium text-gray-900">{t("actualPrice")}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-0 w-4 border-t-[3px] border-dashed" style={{ borderColor: forecastColor }} />
            <span className="text-[10px] font-medium text-gray-900">{t("predictedPrice")}</span>
          </div>
        </div>
      )}
      {predictedData.length === 0 && <p className="mt-1 ml-2 text-xs text-gray-500">{t("forecastPeriodUnavailable")}</p>}
    </div>
  );
};

export default ForecastChart;
