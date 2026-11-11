'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Target, Activity, ShieldCheck, TrendingUp, BarChart3, HelpCircle } from 'lucide-react';

interface RegressionMetrics {
  rmse_php: number;
  mae_php: number;
  mape_pct: number;
  r_squared: number;
  slope: number;
  intercept: number;
  confidence_level_pct: number;
  empirical_coverage_pct?: number;
  count: number;
}

interface ScatterPoint {
  actual: number;
  predicted: number;
  date?: string;
  category?: string;
}

interface PriceRegressionPlotProps {
  productName?: string;
  categoryName?: string;
  className?: string;
  showSelector?: boolean;
}

export default function PriceRegressionPlot({
  productName,
  categoryName,
  className = '',
  showSelector = false,
}: PriceRegressionPlotProps) {
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<RegressionMetrics | null>(null);
  const [points, setPoints] = useState<ScatterPoint[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>(productName || '');
  const [availableProducts, setAvailableProducts] = useState<{ name: string; variant: string }[]>([]);
  const [viewMode, setViewMode] = useState<'interactive' | 'dashboard' | 'timeseries' | 'residuals' | 'regression'>('interactive');

  useEffect(() => {
    let active = true;
    setLoading(true);

    const query = new URLSearchParams();
    if (selectedProduct) {
      query.set('product', selectedProduct);
    } else if (categoryName) {
      query.set('category', categoryName);
    }

    fetch(`/api/forecast/regression?${query.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        if (!active) return;
        if (data.metrics) {
          setMetrics(data.metrics);
          setPoints(data.points || []);
          if (data.commodities && data.commodities.length > 0) {
            setAvailableProducts(data.commodities);
          }
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load regression metrics:', err);
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedProduct, categoryName]);

  // Compute min and max bounds for plot axes
  const { minVal, maxVal, regressionPoints } = useMemo(() => {
    if (!points || points.length === 0 || !metrics) {
      return { minVal: 0, maxVal: 100, regressionPoints: [] };
    }
    const allVals = points.flatMap((p) => [p.actual, p.predicted]);
    const min = Math.max(0, Math.floor(Math.min(...allVals) * 0.9));
    const max = Math.ceil(Math.max(...allVals) * 1.1);

    // Compute two endpoints for the regression line: y = slope * x + intercept
    const x1 = min;
    const y1 = metrics.slope * x1 + metrics.intercept;
    const x2 = max;
    const y2 = metrics.slope * x2 + metrics.intercept;

    return {
      minVal: min,
      maxVal: max,
      regressionPoints: [
        { actual: x1, predicted: y1 },
        { actual: x2, predicted: y2 },
      ],
    };
  }, [points, metrics]);

  // Determine publication chart image source
  const chartImgSrc = useMemo(() => {
    if (viewMode === 'dashboard') {
      return '/charts/model_evaluation_dashboard.png';
    }
    if (viewMode === 'timeseries') {
      return '/charts/time_series_forecast_tracking.png';
    }
    if (viewMode === 'residuals') {
      return '/charts/residual_error_distribution.png';
    }
    if (selectedProduct?.toLowerCase().includes('rice') || categoryName?.toLowerCase() === 'rice') {
      return '/charts/regression_plot_rice.png';
    }
    if (categoryName?.toLowerCase() === 'vegetables') {
      return '/charts/regression_plot_vegetables.png';
    }
    if (categoryName?.toLowerCase() === 'fish') {
      return '/charts/regression_plot_fish.png';
    }
    return '/charts/regression_plot_overall.png';
  }, [viewMode, selectedProduct, categoryName]);

  return (
    <div
      className={`rounded-2xl border border-emerald-500/20 bg-slate-950/80 backdrop-blur-xl p-5 md:p-6 shadow-2xl space-y-6 ${className}`}
    >
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-emerald-500/10 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[11px] font-mono uppercase tracking-widest text-emerald-400">
              Evaluation & Error Calibration
            </span>
          </div>
          <h3 className="text-lg md:text-xl font-bold text-slate-100 flex items-center gap-2 mt-1">
            <BarChart3 className="w-5 h-5 text-emerald-400" />
            Overall Price Prediction Regression & Accuracy
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Scatter distribution of actual retail prices versus overall model predictions (used to generate weekly and monthly forecasts).
          </p>
        </div>

        {/* View Toggle */}
        <div className="flex flex-wrap items-center gap-1.5 bg-slate-900/90 border border-emerald-500/20 p-1 rounded-xl self-start sm:self-center">
          <button
            type="button"
            onClick={() => setViewMode('interactive')}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'interactive'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Interactive Fit
          </button>
          <button
            type="button"
            onClick={() => setViewMode('dashboard')}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'dashboard'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Master Dashboard
          </button>
          <button
            type="button"
            onClick={() => setViewMode('timeseries')}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'timeseries'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Time-Series Band
          </button>
          <button
            type="button"
            onClick={() => setViewMode('residuals')}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'residuals'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Residual Error
          </button>
          <button
            type="button"
            onClick={() => setViewMode('regression')}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'regression'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Regression Plot
          </button>
        </div>
      </div>

      {/* Commodity Selector (optional) */}
      {showSelector && availableProducts.length > 0 && (
        <div className="flex items-center gap-3">
          <label htmlFor="regression-product-select" className="text-xs font-medium text-slate-400">
            Select Commodity:
          </label>
          <select
            id="regression-product-select"
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
            className="bg-slate-900 border border-emerald-500/20 rounded-xl px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-400"
          >
            <option value="">All Commodities (Pooled Model Evaluation)</option>
            {availableProducts.map((p) => (
              <option key={`${p.name}-${p.variant}`} value={p.name}>
                {p.name} ({p.variant})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Accuracy Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* Confidence Level */}
        <div className="p-3.5 rounded-xl bg-gradient-to-br from-emerald-950/40 to-slate-900/60 border border-emerald-500/30 relative overflow-hidden group">
          <div className="flex items-center justify-between text-xs text-emerald-300 font-medium">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Confidence
            </span>
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">SCORE</span>
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-xl md:text-2xl font-bold font-mono text-emerald-300">
              {metrics ? `${metrics.confidence_level_pct.toFixed(1)}%` : '...'}
            </span>
          </div>
          <p className="text-[10px] text-emerald-400/70 mt-1">
            Calibrated prediction confidence score
          </p>
        </div>

        {/* RMSE */}
        <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span className="flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-cyan-400" />
              RMSE
            </span>
            <span className="text-[10px] text-slate-500 font-mono">Root Mean Sq</span>
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-xl md:text-2xl font-bold font-mono text-cyan-300">
              {metrics ? `₱${metrics.rmse_php.toFixed(2)}` : '...'}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Penalizes large deviations</p>
        </div>

        {/* MAE */}
        <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span className="flex items-center gap-1.5">
              <Target className="w-4 h-4 text-amber-400" />
              MAE
            </span>
            <span className="text-[10px] text-slate-500 font-mono">Mean Absolute</span>
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-xl md:text-2xl font-bold font-mono text-amber-300">
              {metrics ? `₱${metrics.mae_php.toFixed(2)}` : '...'}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Average absolute peso error</p>
        </div>

        {/* MAPE */}
        <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span className="flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-indigo-400" />
              MAPE
            </span>
            <span className="text-[10px] text-slate-500 font-mono">Mean % Error</span>
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-xl md:text-2xl font-bold font-mono text-indigo-300">
              {metrics ? `${metrics.mape_pct.toFixed(2)}%` : '...'}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Relative percentage closeness</p>
        </div>

        {/* R² Regression Fit */}
        <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span className="flex items-center gap-1.5">
              <BarChart3 className="w-4 h-4 text-emerald-400" />
              R² Score
            </span>
            <span className="text-[10px] text-slate-500 font-mono">Goodness of Fit</span>
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-xl md:text-2xl font-bold font-mono text-emerald-400">
              {metrics ? metrics.r_squared.toFixed(4) : '...'}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">
            Fit: y = {metrics?.slope.toFixed(2)}x + {metrics?.intercept.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Main Chart Area */}
      <div className="relative min-h-[360px] w-full rounded-xl bg-slate-900/50 border border-slate-800/80 p-4">
        {loading ? (
          <div className="flex h-80 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
          </div>
        ) : viewMode !== 'interactive' ? (
          <div className="flex flex-col items-center justify-center py-2 space-y-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={chartImgSrc}
              alt="FOODCAST Overall Model Evaluation Plot"
              className="max-h-[500px] w-auto rounded-lg shadow-lg border border-slate-800"
            />
            <p className="text-[11px] text-slate-400 text-center">
              Publication-grade model evaluation chart computed with 95% confidence bands (MAE: ₱4.75, RMSE: ₱11.94, MAPE: 3.14%).
            </p>
          </div>
        ) : (
          <div className="h-[360px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" opacity={0.6} />
                <XAxis
                  type="number"
                  dataKey="actual"
                  name="Actual Price"
                  domain={[minVal, maxVal]}
                  unit="₱"
                  stroke="#64748b"
                  fontSize={11}
                  tickFormatter={(val) => `₱${val}`}
                />
                <YAxis
                  type="number"
                  dataKey="predicted"
                  name="Predicted Price"
                  domain={[minVal, maxVal]}
                  unit="₱"
                  stroke="#64748b"
                  fontSize={11}
                  tickFormatter={(val) => `₱${val}`}
                />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3', stroke: '#059669' }}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as ScatterPoint;
                      const error = (data.predicted - data.actual).toFixed(2);
                      const absErr = Math.abs(Number(error)).toFixed(2);
                      return (
                        <div className="rounded-xl border border-emerald-500/30 bg-slate-950/95 p-3 shadow-2xl backdrop-blur-md text-xs space-y-1">
                          <p className="font-semibold text-slate-200">
                            {data.date ? `Observed: ${data.date}` : 'Forecast Observation'}
                          </p>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400 pt-1">
                            <span>Actual Price:</span>
                            <span className="font-mono font-medium text-emerald-400">₱{data.actual.toFixed(2)}</span>
                            <span>Predicted Price:</span>
                            <span className="font-mono font-medium text-cyan-400">₱{data.predicted.toFixed(2)}</span>
                            <span>Absolute Error:</span>
                            <span className="font-mono font-medium text-amber-300">₱{absErr}</span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />

                {/* Parity Line y = x */}
                <ReferenceLine
                  segment={[
                    { x: minVal, y: minVal },
                    { x: maxVal, y: maxVal },
                  ]}
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{
                    value: 'Ideal Parity (y = x)',
                    position: 'insideBottomRight',
                    fill: '#94a3b8',
                    fontSize: 10,
                  }}
                />

                {/* Fitted Linear Regression Line */}
                {regressionPoints.length === 2 && (
                  <ReferenceLine
                    segment={[
                      { x: regressionPoints[0].actual, y: regressionPoints[0].predicted },
                      { x: regressionPoints[1].actual, y: regressionPoints[1].predicted },
                    ]}
                    stroke="#10b981"
                    strokeWidth={2.5}
                    label={{
                      value: `Fit: y = ${metrics?.slope.toFixed(2)}x + ${metrics?.intercept.toFixed(2)}`,
                      position: 'insideTopLeft',
                      fill: '#10b981',
                      fontSize: 10,
                      fontWeight: 600,
                    }}
                  />
                )}

                {/* Actual vs Predicted Scatter Points */}
                <Scatter
                  name="Observations"
                  data={points}
                  fill="#7ED957"
                  fillOpacity={0.6}
                  line={false}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Footer Notes */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-[11px] text-slate-500 pt-1">
        <span className="flex items-center gap-1">
          <HelpCircle className="w-3.5 h-3.5 text-slate-400" />
          Parity line represents perfect prediction accuracy (error = 0).
        </span>
        <span>
          Sample Population: {metrics?.count.toLocaleString() || 0} observations · Evaluation Protocol
        </span>
      </div>
    </div>
  );
}
