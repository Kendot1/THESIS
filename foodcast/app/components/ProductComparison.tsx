"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Scale, X } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchLiveProducts, type Product } from "../lib/data";

interface ProductComparisonProps {
  products: Product[];
  open: boolean;
  onClose: () => void;
}

const COLORS = ["#0B3B24", "#F59E0B"] as const;

function productLabel(product: Product) {
  const details = [
    product.variant && product.variant !== "Standard" ? product.variant : null,
    product.origin || null,
    product.unit || null,
  ].filter(Boolean);
  return `${product.name}${details.length ? ` (${details.join(" · ")})` : ""}`;
}

function percentChange(product: Product) {
  if (!product.currentPrice) return 0;
  return ((product.predictedPrice - product.currentPrice) / product.currentPrice) * 100;
}

function formatCurrency(value: number) {
  return `₱${value.toLocaleString("en-PH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function ProductComparison({ products, open, onClose }: ProductComparisonProps) {
  const [firstId, setFirstId] = useState("");
  const [secondId, setSecondId] = useState("");
  const [liveProducts, setLiveProducts] = useState(products);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const usableProducts = useMemo(
    () => liveProducts.filter((product) => product.unit && Number.isFinite(product.currentPrice)),
    [liveProducts],
  );
  const first = usableProducts.find((product) => product.id === firstId);
  const second = usableProducts.find((product) => product.id === secondId);

  useEffect(() => {
    if (!open) return;
    let active = true;

    const refresh = async () => {
      setIsRefreshing(true);
      try {
        const latestProducts = await fetchLiveProducts();
        if (!active) return;
        setLiveProducts(latestProducts);
        setLastUpdated(new Date());
        setRefreshError(false);
      } catch (error) {
        console.error("Could not refresh comparison prices", error);
        if (active) setRefreshError(true);
      } finally {
        if (active) setIsRefreshing(false);
      }
    };

    void refresh();
    const refreshTimer = window.setInterval(refresh, 60_000);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  const chartData = useMemo(() => {
    if (!first || !second) return [];
    const firstHistory = first.sparklineData.map((point) => point.value).filter(Number.isFinite);
    const secondHistory = second.sparklineData.map((point) => point.value).filter(Number.isFinite);
    const historyLength = Math.max(firstHistory.length, secondHistory.length, 1);

    const rows = Array.from({ length: historyLength }, (_, index) => {
      const firstIndex = index - (historyLength - firstHistory.length);
      const secondIndex = index - (historyLength - secondHistory.length);
      return {
        period: index === historyLength - 1 ? "Current" : `${historyLength - index - 1} ago`,
        first: firstIndex >= 0 ? firstHistory[firstIndex] : undefined,
        second: secondIndex >= 0 ? secondHistory[secondIndex] : undefined,
      };
    });

    rows.push({
      period: "Forecast",
      first: first.predictedPrice,
      second: second.predictedPrice,
    });
    return rows;
  }, [first, second]);

  if (!open) return null;

  const sameUnit = first && second ? first.unit === second.unit : true;
  const currentDifference = first && second ? Math.abs(first.currentPrice - second.currentPrice) : 0;
  const forecastDifference = first && second ? Math.abs(first.predictedPrice - second.predictedPrice) : 0;
  const firstChange = first ? percentChange(first) : 0;
  const secondChange = second ? percentChange(second) : 0;

  return (
    <div className="fixed inset-0 z-[200] flex items-end justify-center bg-black/45 p-0 backdrop-blur-sm sm:items-center sm:p-6" role="presentation" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="comparison-title"
        onMouseDown={(event) => event.stopPropagation()}
        className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-t-[2rem] bg-white shadow-2xl sm:rounded-[2rem]"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-100 bg-white/95 px-5 py-4 backdrop-blur sm:px-8 sm:py-5">
          <div>
            <h2 id="comparison-title" className="text-xl font-bold text-gray-900 sm:text-2xl">Compare products</h2>
            <p className="mt-1 text-xs text-gray-500">Compare recent prices and the published forecast.</p>
            <div className="mt-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider">
              <span className={`h-2 w-2 rounded-full ${refreshError ? "bg-amber-500" : "bg-green-500"}`} />
              <span className={refreshError ? "text-amber-700" : "text-gray-400"}>
                {isRefreshing
                  ? "Updating live data…"
                  : refreshError
                    ? "Live refresh failed · showing last available data"
                    : lastUpdated
                      ? `Live · updated ${lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                      : "Connecting to live data…"}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="rounded-xl p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700" aria-label="Close comparison">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-6 p-5 sm:p-8">
          <div className="grid gap-4 md:grid-cols-2">
            {[
              { label: "First product", value: firstId, setValue: setFirstId, disabledId: secondId },
              { label: "Second product", value: secondId, setValue: setSecondId, disabledId: firstId },
            ].map((selector) => (
              <label key={selector.label} className="block">
                <span className="mb-2 block text-[10px] font-black uppercase tracking-widest text-gray-400">{selector.label}</span>
                <select
                  value={selector.value}
                  onChange={(event) => selector.setValue(event.target.value)}
                  className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-800 outline-none transition focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
                >
                  <option value="">Choose a product</option>
                  {usableProducts.map((product) => (
                    <option key={product.id} value={product.id} disabled={product.id === selector.disabledId}>
                      {productLabel(product)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          {!first || !second ? (
            <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-6 text-center">
              <Scale className="mb-3 h-8 w-8 text-primary-600" />
              <p className="font-bold text-gray-800">Select two different products</p>
              <p className="mt-1 max-w-md text-xs leading-5 text-gray-500">The comparison will show their price history, forecast movement, and price difference.</p>
            </div>
          ) : (
            <>
              {!sameUnit && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-medium text-amber-800">
                  These products use different units ({first.unit} and {second.unit}). Their absolute prices are not directly equivalent.
                </div>
              )}

              <div className="grid gap-4 lg:grid-cols-2">
                {[first, second].map((product, index) => {
                  const change = percentChange(product);
                  const rising = change >= 0;
                  return (
                    <article key={product.id} className="rounded-2xl border border-gray-100 bg-gray-50/70 p-5">
                      <div className="mb-4 flex items-start justify-between gap-3">
                        <div>
                          <p className="text-base font-black text-gray-900">{product.name}</p>
                          <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-gray-400">{productLabel(product).replace(`${product.name} (`, "").replace(/\)$/, "")}</p>
                        </div>
                        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: COLORS[index] }} aria-hidden="true" />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Current</p>
                          <p className="mt-1 text-xl font-black text-gray-900">{formatCurrency(product.currentPrice)} <span className="text-xs font-semibold text-gray-400">/ {product.unit}</span></p>
                        </div>
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Predicted</p>
                          <p className="mt-1 text-xl font-black" style={{ color: COLORS[index] }}>{formatCurrency(product.predictedPrice)} <span className="text-xs font-semibold text-gray-400">/ {product.unit}</span></p>
                        </div>
                      </div>
                      <div className={`mt-4 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-black ${rising ? "bg-price-up/10 text-price-up" : "bg-price-down/10 text-price-down"}`}>
                        {rising ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
                        {rising ? "+" : ""}{change.toFixed(1)}% forecast change
                      </div>
                    </article>
                  );
                })}
              </div>

              <div className="rounded-2xl border border-gray-100 p-4 sm:p-6">
                <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <h3 className="font-black text-gray-900">Price comparison</h3>
                    <p className="mt-1 text-xs text-gray-500">Recent seven observations plus the published forecast.</p>
                  </div>
                  {sameUnit && (
                    <p className="text-xs font-bold text-gray-600">Current gap: {formatCurrency(currentDifference)}</p>
                  )}
                </div>
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                      <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="period" tick={{ fontSize: 11, fill: "#6B7280" }} tickLine={false} axisLine={false} />
                      <YAxis tickFormatter={(value) => `₱${Number(value).toFixed(0)}`} tick={{ fontSize: 11, fill: "#6B7280" }} tickLine={false} axisLine={false} width={58} />
                      <Tooltip formatter={(value) => formatCurrency(Number(value))} contentStyle={{ borderRadius: 12, borderColor: "#E5E7EB", fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 11, paddingTop: 12 }} />
                      <Line type="monotone" dataKey="first" name={productLabel(first)} stroke={COLORS[0]} strokeWidth={3} dot={{ r: 3 }} connectNulls />
                      <Line type="monotone" dataKey="second" name={productLabel(second)} stroke={COLORS[1]} strokeWidth={3} dot={{ r: 3 }} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-gray-50 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Lower current price</p>
                  <p className="mt-2 text-sm font-black text-gray-900">{sameUnit ? (first.currentPrice <= second.currentPrice ? first.name : second.name) : "Not comparable"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Projected price gap</p>
                  <p className="mt-2 text-sm font-black text-gray-900">{sameUnit ? formatCurrency(forecastDifference) : "Different units"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Stronger price movement</p>
                  <p className="mt-2 text-sm font-black text-gray-900">{Math.abs(firstChange) >= Math.abs(secondChange) ? first.name : second.name}</p>
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
