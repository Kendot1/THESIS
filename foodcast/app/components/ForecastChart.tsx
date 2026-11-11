"use client";
import { useRef, useEffect, useMemo, useCallback, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineStyle,
  CrosshairMode,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesPrimitive,
  type ISeriesMarkersPluginApi,
  type IPrimitivePaneRenderer,
  type IPrimitivePaneView,
  type SeriesAttachedParameter,
  type Time,
} from "lightweight-charts";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { type ForecastDataPoint, type ForecastHorizon } from "../lib/data";
import { marketAnalysisForecasts } from "../lib/market-analysis";

type DataPoint = ForecastDataPoint;

interface ForecastChartProps {
  data: DataPoint[];
  height?: number;
  showGrid?: boolean;
  showLegend?: boolean;
  productName?: string;
  period?: string;
  forecastOriginDate: string | undefined;
  forecastContract?: "rolling" | "calendar_research";
}

function getSeriesValue(value: unknown): number | undefined {
  if (!value || typeof value !== "object" || !("value" in value)) return undefined;
  const candidate = (value as { value?: unknown }).value;
  return typeof candidate === "number" ? candidate : undefined;
}

interface PriceLabelData {
  actualPrice: number | null;
  predictedPrice: number | null;
  actualLabel: string;
  predictedLabel: string;
  predictedColor: string;
}

class ForecastPriceLabelsPrimitive implements ISeriesPrimitive<Time> {
  private labels: PriceLabelData = {
    actualPrice: null,
    predictedPrice: null,
    actualLabel: "Actual Price",
    predictedLabel: "Predicted Price",
    predictedColor: "#2E7D32",
  };
  private requestUpdate: () => void = () => {};
  private readonly view: IPrimitivePaneView;
  private readonly views: readonly IPrimitivePaneView[];

  constructor(private readonly series: ISeriesApi<"Area">) {
    const renderer: IPrimitivePaneRenderer = {
      draw: target => target.useMediaCoordinateSpace(({ context, mediaSize }) => {
        const actualY = this.labels.actualPrice == null
          ? null
          : this.series.priceToCoordinate(this.labels.actualPrice);
        const predictedY = this.labels.predictedPrice == null
          ? null
          : this.series.priceToCoordinate(this.labels.predictedPrice);
        const separateHorizontally = actualY != null && predictedY != null
          && Math.abs(actualY - predictedY) < 18;

        context.save();
        context.font = "700 9px Inter, sans-serif";
        context.textAlign = "left";
        context.textBaseline = "middle";
        if (actualY != null && actualY >= 0 && actualY <= mediaSize.height) {
          this.drawLabel(context, mediaSize.width, this.labels.actualLabel, "#111827", actualY, 4);
        }
        if (predictedY != null && predictedY >= 0 && predictedY <= mediaSize.height) {
          this.drawLabel(
            context,
            mediaSize.width,
            this.labels.predictedLabel,
            this.labels.predictedColor,
            predictedY,
            separateHorizontally ? 82 : 4,
          );
        }
        context.restore();
      }),
    };
    this.view = { zOrder: () => "top", renderer: () => renderer };
    this.views = [this.view];
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.requestUpdate = () => {};
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  setLabels(labels: PriceLabelData): void {
    this.labels = labels;
    this.requestUpdate();
  }

  private drawLabel(
    context: CanvasRenderingContext2D,
    paneWidth: number,
    text: string,
    color: string,
    centerY: number,
    preferredX: number,
  ): void {
    const paddingX = 6;
    const height = 16;
    const width = context.measureText(text).width + paddingX * 2;
    const x = Math.max(2, Math.min(preferredX, paneWidth - width - 2));
    const y = centerY - height / 2;
    const radius = 3;

    context.beginPath();
    context.moveTo(x + radius, y);
    context.lineTo(x + width - radius, y);
    context.arcTo(x + width, y, x + width, y + radius, radius);
    context.lineTo(x + width, y + height - radius);
    context.arcTo(x + width, y + height, x + width - radius, y + height, radius);
    context.lineTo(x + radius, y + height);
    context.arcTo(x, y + height, x, y + height - radius, radius);
    context.lineTo(x, y + radius);
    context.arcTo(x, y, x + radius, y, radius);
    context.closePath();
    context.fillStyle = color;
    context.fill();
    context.fillStyle = "#fff";
    context.fillText(text, x + paddingX, centerY);
  }
}

const ForecastChart = ({
  data,
  height,
  showGrid = true,
  showLegend = true,
  period = "Daily",
  forecastOriginDate,
  forecastContract = "rolling",
}: ForecastChartProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const tooltipConfidenceRef = useRef<Record<string, { score: number | null; level: string }>>({});
  const historicalRangesRef = useRef<Record<string, string>>({});
  const forecastRangesRef = useRef<Record<string, string>>({});
  const chartRef = useRef<IChartApi | null>(null);
  const actualSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const predictedSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const predictedPriceLineRef = useRef<ReturnType<ISeriesApi<"Area">["createPriceLine"]> | null>(null);
  const priceLabelsPrimitiveRef = useRef<ForecastPriceLabelsPrimitive | null>(null);
  const predictedMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const { t } = useLanguage();
  const [zoomRange, setZoomRange] = useState<"30d" | "60d" | "all">("60d");
  // Keep a ref to t so the chart creation effect doesn't need t as a dependency
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    const selected = period.toLowerCase() as ForecastHorizon;
    forecastRangesRef.current = selected === "daily"
      ? {}
      : Object.fromEntries(
          data
            .filter(point => point.horizon === selected && point.predicted != null && point.target_period_start && point.target_period_start !== point.date)
            .map(point => [point.date, point.target_period_start!])
        );
    tooltipConfidenceRef.current = Object.fromEntries(data
      .filter(point => (point.horizon === selected || (!point.horizon && selected === "daily"))
        && point.predicted != null)
      .map(point => [point.date, {
        score: point.confidence_score != null && Number.isFinite(point.confidence_score)
          && point.confidence_score >= 0 && point.confidence_score <= 100
          ? point.confidence_score : null,
        level: point.confidence_level ?? "Insufficient data",
      }]));
  }, [data, period]);

  // Build series data
  const { actualData, predictedData, forecastPoints } = useMemo(() => {
    const selected = period.toLowerCase() as ForecastHorizon;
    const selectedForecasts = marketAnalysisForecasts(
      { forecastData: data, forecastOriginDate, forecastSource: "model" },
      selected,
      forecastContract,
    );

    // 1. The actual price on chart should only show the price for the actual day, week, or month (the present anchor)
    const dailyActuals = data.filter(point => (point.horizon ?? "daily") === "daily"
      && point.actual != null && Number.isFinite(point.actual));
    const observations = [...new Map(dailyActuals
      .map(point => [point.date, point])).values()]
      .sort((left, right) => left.date.localeCompare(right.date));
    const latest = observations[observations.length - 1];
    
    // Only show the price for the actual day, month, or week
    let actuals: { time: Time; value: number; periodStart?: string }[] = [];
    if (latest) {
      actuals = [{ time: latest.date as Time, value: latest.actual! }];
    }

    // 2. Next predicted prices connect from the present actual price
    const forecastPoints = selectedForecasts.filter(p => p.predicted != null && Number.isFinite(p.predicted) && p.predicted > 0);
    const rawPredictions = forecastPoints.map(point => ({ time: point.date as Time, value: point.predicted! }));

    const latestActual = actuals[actuals.length - 1];
    const firstPrediction = rawPredictions[0];
    const connectedPredictions = latestActual && firstPrediction
      && String(latestActual.time) < String(firstPrediction.time)
      ? [{ time: latestActual.time, value: latestActual.value }, ...rawPredictions]
      : rawPredictions;

    return { actualData: actuals, predictedData: connectedPredictions, forecastPoints: selectedForecasts };
  }, [data, period, forecastOriginDate, forecastContract]);

  const forecastColor = "#10B981"; // Emerald green line for predicted price
  const forecastFill = "rgba(16, 185, 129, 0.10)";

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
        fixLeftEdge: false,
        fixRightEdge: true,
        rightOffset: 15,
        barSpacing: 14,
        minBarSpacing: 3,
      },
      handleScroll: { vertTouchDrag: false, horzTouchDrag: true, mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      width: container.clientWidth,
      height: height || 380,
    });

    // Actual prices use a solid black line (the price that really exists)
    const actualSeries = chart.addSeries(AreaSeries, {
      lineColor: "#000000",
      topColor: "rgba(0, 0, 0, 0.08)",
      bottomColor: "rgba(0, 0, 0, 0.00)",
      lineWidth: 2,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: "#000000",
      crosshairMarkerBackgroundColor: "#fff",
      crosshairMarkerBorderWidth: 2,
      lastValueVisible: false,
    });

    // Predicted prices use an emerald green line to compare
    const predictedSeries = chart.addSeries(AreaSeries, {
      lineColor: forecastColor,
      topColor: forecastFill,
      bottomColor: "rgba(16, 185, 129, 0.00)",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      priceFormat: { type: "custom", formatter: (p: number) => `₱${p.toFixed(2)}` },
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: forecastColor,
      crosshairMarkerBackgroundColor: "#fff",
      crosshairMarkerBorderWidth: 2,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    actualSeriesRef.current = actualSeries;
    predictedSeriesRef.current = predictedSeries;
    const priceLabelsPrimitive = new ForecastPriceLabelsPrimitive(actualSeries);
    actualSeries.attachPrimitive(priceLabelsPrimitive);
    priceLabelsPrimitiveRef.current = priceLabelsPrimitive;
    predictedMarkersRef.current = createSeriesMarkers(predictedSeries, []);

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
        const formatDate = (date: string) => new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
          month: "long", day: "numeric", year: "numeric", timeZone: "UTC",
        });
        const isDaily = period.toLowerCase() === "daily";
        const periodStart = !isDaily
          ? (predictedValue !== undefined ? forecastRangesRef.current[dateStr] : historicalRangesRef.current[dateStr])
          : undefined;
        const formattedDate = (periodStart && periodStart !== dateStr)
          ? `${formatDate(periodStart)} – ${formatDate(dateStr)}`
          : formatDate(dateStr);

        const hasActual = actualValue !== undefined && Number.isFinite(actualValue);
        const hasPredicted = predictedValue !== undefined && Number.isFinite(predictedValue);
        let rowsHtml = "";
        if (hasActual) {
          rowsHtml += `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:3px">
            <span style="display:flex;align-items:center;gap:6px">
              <span style="width:8px;height:8px;border-radius:50%;background:#000000;display:inline-block"></span>
              <b>${tRef.current("actualPrice")}:</b>
            </span>
            <strong style="color:#000000;font-family:monospace">₱${actualValue.toFixed(2)}</strong>
          </div>`;
        }
        if (hasPredicted) {
          rowsHtml += `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:3px">
            <span style="display:flex;align-items:center;gap:6px">
              <span style="width:8px;height:8px;border-radius:50%;background:${forecastColor};display:inline-block"></span>
              <b>${tRef.current("predictedPrice")}:</b>
            </span>
            <strong style="color:${forecastColor};font-family:monospace">₱${predictedValue!.toFixed(2)}</strong>
          </div>`;
        }
        if (hasActual && hasPredicted) {
          const delta = predictedValue! - actualValue;
          const deltaPct = actualValue > 0 ? ((delta / actualValue) * 100).toFixed(1) : "0.0";
          const sign = delta >= 0 ? "+" : "";
          rowsHtml += `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:4px;margin-top:2px;border-top:1px dashed #e2e8f0;font-size:10px;color:#64748b">
            <span>Variance:</span>
            <strong style="color:${Math.abs(delta) <= 5 ? '#10B981' : '#f59e0b'};font-family:monospace">
              ${sign}₱${delta.toFixed(2)} (${sign}${deltaPct}%)
            </strong>
          </div>`;
        }

        const confidence = tooltipConfidenceRef.current[dateStr];
        const confidenceLabels: Record<string, string> = {
          "Very High": "confidenceVeryHigh", High: "confidenceHigh", Moderate: "confidenceModerate",
          Low: "confidenceLow", "Very Low": "confidenceVeryLow",
        };
        const confidenceText = confidence?.score != null
          ? `${confidence.score.toFixed(1)}% · ${tRef.current(confidenceLabels[confidence.level] ?? "confidenceUnavailable")}`
          : "";
        const confidenceRow = confidence?.score != null && predictedValue !== undefined
          ? `<div style="margin-top:4px"><b>${tRef.current("confidence")}:</b> ${confidenceText}</div>`
          : "";
        tooltip.innerHTML = `<div style="font-size:10px;font-weight:700;color:#9CA3AF;margin-bottom:4px">${formattedDate}</div>${rowsHtml}${confidenceRow}`;

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
      if (predictedPriceLineRef.current) {
        predictedSeriesRef.current?.removePriceLine(predictedPriceLineRef.current);
        predictedPriceLineRef.current = null;
      }
      if (priceLabelsPrimitiveRef.current) {
        actualSeriesRef.current?.detachPrimitive(priceLabelsPrimitiveRef.current);
        priceLabelsPrimitiveRef.current = null;
      }
      predictedMarkersRef.current?.detach();
      chart.remove();
      chartRef.current = null;
      actualSeriesRef.current = null;
      predictedSeriesRef.current = null;
      predictedMarkersRef.current = null;
    };
  }, [showGrid, height, forecastColor, forecastFill]);

  // Each view fits its own observed cadence plus the unchanged forecast targets.
  const applyRelevantRange = useCallback((rangeOverride?: "30d" | "60d" | "all") => {
    if (!chartRef.current) return;
    const selected = period.toLowerCase();
    chartRef.current.applyOptions({ timeScale: {
      tickMarkFormatter: (time: Time) => {
        const date = typeof time === "string" ? new Date(`${time}T00:00:00Z`)
          : typeof time === "number" ? new Date(time * 1000)
          : new Date(Date.UTC(time.year, time.month - 1, time.day));
        return date.toLocaleDateString("en-US", selected === "monthly"
          ? { month: "short", timeZone: "UTC" }
          : selected === "weekly" ? { month: "short", day: "numeric", timeZone: "UTC" }
          : { month: "short", day: "numeric", timeZone: "UTC" });
      },
    } });

    const allTimes = [
      ...actualData.map(p => String(p.time)),
      ...predictedData.map(p => String(p.time))
    ].filter(Boolean).sort();

    if (allTimes.length === 0) return;

    const last = allTimes[allTimes.length - 1] as Time;
    const activeRange = rangeOverride ?? zoomRange;

    if (activeRange === "all") {
      const first = allTimes[0] as Time;
      try {
        chartRef.current.timeScale().setVisibleRange({ from: first, to: last });
      } catch {
        chartRef.current.timeScale().fitContent();
      }
      return;
    }

    // Default zoom window: 60 days (or 30 days) to make the comparison clear and readable
    const windowDays = activeRange === "30d" ? 30 : 60;
    const lastDate = new Date(`${String(last)}T00:00:00Z`);
    const fromDate = new Date(lastDate);
    fromDate.setUTCDate(fromDate.getUTCDate() - windowDays);
    const fromStr = fromDate.toISOString().slice(0, 10);

    const fromCandidate = allTimes.find(t => t >= fromStr) ?? allTimes[Math.max(0, allTimes.length - windowDays)];
    const from = (fromCandidate || allTimes[0]) as Time;

    try {
      chartRef.current.timeScale().setVisibleRange({ from, to: last });
    } catch {
      chartRef.current.timeScale().fitContent();
    }
  }, [actualData, predictedData, period, zoomRange]);

  const handleRangeChange = (range: "30d" | "60d" | "all") => {
    setZoomRange(range);
    applyRelevantRange(range);
  };

  // Update data when it changes
  useEffect(() => {
    if (!actualSeriesRef.current || !predictedSeriesRef.current) return;

    historicalRangesRef.current = Object.fromEntries(actualData
      .filter(point => point.periodStart)
      .map(point => [String(point.time), point.periodStart!]));
    actualSeriesRef.current.setData(actualData);
    predictedSeriesRef.current.setData(predictedData);
    if (predictedPriceLineRef.current) {
      predictedSeriesRef.current.removePriceLine(predictedPriceLineRef.current);
      predictedPriceLineRef.current = null;
    }
    const latestActualTime = actualData[actualData.length - 1]?.time;
    predictedMarkersRef.current?.setMarkers(predictedData
      .map(point => ({
        time: point.time,
        position: "atPriceMiddle" as const,
        price: point.value,
        color: String(point.time) === String(latestActualTime) ? "#111827" : forecastColor,
        shape: "circle" as const,
        size: 0.4,
      })));
    const latestActual = actualData[actualData.length - 1];
    const nextPrediction = predictedData.find(point => !latestActual
      || String(point.time) > String(latestActual.time));
    // The right price-axis label badge from Image 2 is removed per user instruction.
    priceLabelsPrimitiveRef.current?.setLabels({
      actualPrice: latestActual?.value ?? null,
      predictedPrice: nextPrediction?.value ?? null,
      actualLabel: t("actualPrice"),
      predictedLabel: t("predictedPrice"),
      predictedColor: forecastColor,
    });
    applyRelevantRange();
  }, [actualData, predictedData, forecastColor, period, applyRelevantRange, t]);

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
          data-testid="rendered-chart-series"
          data-predicted-values={JSON.stringify(predictedData)}
          data-actual-count={actualData.length}
          data-actual-values={JSON.stringify(actualData)}
          data-forecast-count={forecastPoints.length}
          className={!height ? "w-full" : "h-full w-full"}
          style={{ minHeight: height || 380 }}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 mt-3 -mb-1 ml-2">
        {showLegend && (
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="h-0 w-4 border-t-[3px] border-black" />
              <span className="text-xs font-semibold text-gray-900">{t("actualPrice")}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-0 w-4 border-t-[3px] border-[#10B981]" />
              <span className="text-xs font-semibold text-emerald-700">{t("predictedPrice")}</span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-1.5 bg-gray-100/80 p-1 rounded-xl border border-gray-200/60 ml-auto">
          <button
            type="button"
            onClick={() => handleRangeChange("30d")}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-all ${
              zoomRange === "30d"
                ? "bg-white text-gray-900 shadow-xs border border-gray-200"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            30 Days
          </button>
          <button
            type="button"
            onClick={() => handleRangeChange("60d")}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-all ${
              zoomRange === "60d"
                ? "bg-white text-emerald-700 shadow-xs border border-emerald-200"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            60 Days (Default)
          </button>
          <button
            type="button"
            onClick={() => handleRangeChange("all")}
            className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-all ${
              zoomRange === "all"
                ? "bg-white text-gray-900 shadow-xs border border-gray-200"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            All History
          </button>
        </div>
      </div>
      {predictedData.length === 0 && <p className="mt-1 ml-2 text-xs text-gray-500">{t("forecastPeriodUnavailable")}</p>}
    </div>
  );
};

export default ForecastChart;
