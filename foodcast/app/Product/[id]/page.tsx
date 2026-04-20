"use client";
import { use, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Calendar,
  Layers,
} from "lucide-react";
import Header from "../../component/Header";
import Footer from "../../component/Footer";
import ForecastChart from "../../component/ForecastChart";
import ProductCard from "../../component/ProductCard";
import ScrollReveal from "../../component/ScrollReveal";
import { products } from "../../lib/data";

export default function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const product = products.find((p) => p.id === id);

  const suggestedProducts = useMemo(() => {
    if (!product) return [];
    return products
      .filter((p) => p.id !== product.id)
      .filter(
        (p) =>
          p.category === product.category ||
          p.sentiment === product.sentiment
      )
      .slice(0, 4);
  }, [product]);

  if (!product) {
    return (
      <>
        <Header />
        <main className="pt-20 min-h-screen bg-surface flex flex-col items-center justify-center">
          <div className="text-6xl mb-4">🔍</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Product Not Found
          </h1>
          <p className="text-gray-500 mb-6">
            The product you&apos;re looking for doesn&apos;t exist.
          </p>
          <Link
            href="/Predict"
            className="px-6 py-3 bg-primary-800 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors"
          >
            Back to Predict
          </Link>
        </main>
        <Footer />
      </>
    );
  }

  const priceChange = product.predictedPrice - product.currentPrice;
  const priceChangePercent =
    ((priceChange) / product.currentPrice) * 100;
  const isUp = priceChange >= 0;

  const sentimentIcon =
    product.sentiment === "Bullish" ? (
      <TrendingUp className="w-4 h-4" />
    ) : product.sentiment === "Bearish" ? (
      <TrendingDown className="w-4 h-4" />
    ) : (
      <Minus className="w-4 h-4" />
    );

  const sentimentColor =
    product.sentiment === "Bullish"
      ? "text-positive bg-positive/10"
      : product.sentiment === "Bearish"
        ? "text-negative bg-negative/10"
        : "text-gray-600 bg-gray-100";

  return (
    <>
      <Header />
      <main id="main-content" className="pt-20 min-h-screen bg-surface">
        {/* ─── Breadcrumb + Back ──────────────────────── */}
        <div className="bg-surface border-b border-gray-100">
          <div className="max-w-7xl mx-auto px-5 lg:px-10 py-4">
            <div className="flex items-center gap-3">
              <Link
                href="/Predict"
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-primary-800 transition-colors"
                aria-label="Back to Predict"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Predict
              </Link>
              <span className="text-gray-300" aria-hidden="true">/</span>
              <span className="text-sm font-medium text-gray-900">
                {product.name}
              </span>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-8 sm:py-12">
          {/* ─── Product Header ──────────────────────────── */}
          <ScrollReveal delay={200}>
            <div className="relative bg-gradient-to-br from-primary-800 to-primary-900 mb-5 rounded-xl p-5">

              {/* Top section */}
              <div className="flex items-center gap-4 flex-wrap">
                <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center text-4xl shadow-sm">
                  {product.emoji}
                </div>

                <div className="flex flex-col">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h1
                      className="text-3xl sm:text-4xl font-bold text-white"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {product.name}
                    </h1>

                    <span className="text-xs font-medium text-primary-600 bg-primary-50 px-3 py-1 rounded-full">
                      {product.category}
                    </span>

                    <span
                      className={`inline-flex items-center gap-1 text-xs font-semibold px-3 py-1 rounded-full ${sentimentColor}`}
                    >
                      {sentimentIcon}
                      {product.sentiment}
                    </span>
                  </div>
                </div>
              </div>

              {/* Description */}
              <p className="text-gray-400 ml-24 text-sm sm:text-base max-w-2xl">
                {product.description}
              </p>

            </div>
          </ScrollReveal>

          {/* ─── Price Forecast Chart ────────────────────── */}
          <ScrollReveal>
            <div className="bg-white rounded-2xl border border-gray-100 p-6 sm:p-8 mb-8 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-4">
                <div>
                  <h2
                    className="text-xl font-bold text-gray-900 mb-1"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Price Market Forecast
                  </h2>
                  <p className="text-gray-500 text-sm">
                    Historical data with AI-powered predictions
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {["1M", "3M", "6M", "1Y"].map((period) => (
                    <button
                      key={period}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg transition-all hover:bg-primary-50 text-gray-500 hover:text-primary-800"
                    >
                      {period}
                    </button>
                  ))}
                </div>
              </div>
              <ForecastChart
                data={product.forecastData}
                height={350}
                showGrid
                showLegend
              />
            </div>
          </ScrollReveal>

          {/* ─── AI Market Pulse Insight ─────────────────── */}
          <ScrollReveal delay={200}>
            {(() => {
              const isBullish = product.sentiment === "Bullish";
              const isBearish = product.sentiment === "Bearish";
              const insight = isBullish
                ? {
                  title: "Advantageous Procurement Window",
                  message: `Current trends indicate a significant ${priceChangePercent.toFixed(1)}% price increase. Markets show signs of supply constriction.`,
                  action: "Procure Early",
                  recommendation: "Increase stock levels now to mitigate upcoming cost surges in local markets.",
                  status: "Buy Now",
                  statusBg: "bg-positive/10 text-positive",
                  pulseColor: "bg-positive",
                  glowColor: "from-positive/20 to-accent/5",
                }
                : isBearish
                  ? {
                    title: "Market Entry Wait Recommended",
                    message: `Prices are projected to soften by ${Math.abs(priceChangePercent).toFixed(1)}% as supply stabilizes. High-volume availability is expected.`,
                    action: "Defer Purchase",
                    recommendation: "Wait for the projected dip to secure better margins. Avoid large-scale buying today.",
                    status: "Wait",
                    statusBg: "bg-negative/10 text-negative",
                    pulseColor: "bg-negative",
                    glowColor: "from-negative/20 to-accent/5",
                  }
                  : {
                    title: "Stable Market Conditions Observed",
                    message: "Price movements are within standard seasonal ranges with low volatility detected.",
                    action: "Monitor Daily",
                    recommendation: "Maintain standard procurement cycles. No immediate supply shocks are anticipated.",
                    status: "Monitor",
                    statusBg: "bg-gray-100 text-gray-600",
                    pulseColor: "bg-gray-400",
                    glowColor: "from-gray-200 to-transparent",
                  };

              return (
                <div className="relative group mb-8">
                  {/* Creative Background Glow */}
                  <div className={`absolute inset-0 bg-gradient-to-tr ${insight.glowColor} opacity-30 transition-opacity duration-700`} />

                  <div className="relative bg-white/40 backdrop-blur-xl border border-white/60 rounded-[2rem] p-6 sm:p-8 shadow-lg">
                    <div className="flex flex-col lg:flex-row gap-8 items-start lg:items-center">
                      {/* Pulse Indicator */}
                      <div className="relative shrink-0">
                        <div className={`w-16 h-16 rounded-full ${insight.pulseColor}/20 flex items-center justify-center animate-pulse`}>
                          <div className={`w-8 h-8 rounded-full ${insight.pulseColor} shadow-[0_0_20px_rgba(0,0,0,0.1)] flex items-center justify-center`}>
                            <TrendingUp className="w-4 h-4 text-white" />
                          </div>
                        </div>
                        {/* Orbiting Ring */}
                        <div className={`absolute inset-0 rounded-full border-2 border-dashed ${insight.pulseColor}/30 animate-spin-slow`} />
                      </div>

                      <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-3 mb-3">
                          <h3
                            className="text-xl font-bold text-gray-900"
                            style={{ fontFamily: "var(--font-display)" }}
                          >
                            {insight.title}
                          </h3>
                          <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest shadow-sm ${insight.statusBg}`}>
                            {insight.status}
                          </span>
                        </div>
                        <p className="text-gray-600 text-sm sm:text-base leading-relaxed mb-4 max-w-3xl">
                          {insight.message} <span className="font-semibold text-gray-900">{insight.recommendation}</span>
                        </p>

                        <div className="flex items-center gap-6">
                          <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Next Action:</span>
                            <span className="text-[11px] font-black text-primary-800">{insight.action}</span>
                          </div>
                          <div className="h-4 w-px bg-gray-200" />
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Reliability:</span>
                            <div className="flex gap-0.5">
                              {[1, 2, 3, 4, 5].map((s) => (
                                <div key={s} className={`w-1.5 h-1.5 rounded-full ${s <= 4 ? "bg-accent" : "bg-gray-200"}`} />
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
          </ScrollReveal>

          {/* ─── Price Overview Stats ────────────────────── */}
          <ScrollReveal delay={100}>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              {[
                {
                  label: "Current Price",
                  value: `₱${product.currentPrice.toFixed(2)}`,
                  icon: <BarChart3 className="w-4 h-4" />,
                  sub: "Latest recorded price",
                  color: "text-primary-800",
                },
                {
                  label: "Predicted Price",
                  value: `₱${product.predictedPrice.toFixed(2)}`,
                  icon: <TrendingUp className="w-4 h-4" />,
                  sub: "AI forecast estimate",
                  color: isUp ? "text-positive" : "text-negative",
                },
                {
                  label: "Price Change",
                  value: `${isUp ? "+" : ""}${priceChangePercent.toFixed(1)}%`,
                  icon: isUp ? (
                    <TrendingUp className="w-4 h-4" />
                  ) : (
                    <TrendingDown className="w-4 h-4" />
                  ),
                  sub: `${isUp ? "+" : ""}₱${priceChange.toFixed(2)}`,
                  color: isUp ? "text-positive" : "text-negative",
                },
                {
                  label: "Market Volatility",
                  value: isUp ? "Moderate" : "Low",
                  icon: <Layers className="w-4 h-4" />,
                  sub: "Stability Index",
                  color: "text-primary-700",
                },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className="flex items-center gap-2 text-gray-400 mb-3">
                    {stat.icon}
                    <span className="text-xs font-medium uppercase tracking-wider">
                      {stat.label}
                    </span>
                  </div>
                  <div className={`text-2xl font-bold ${stat.color}`}>
                    {stat.value}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">{stat.sub}</div>
                </div>
              ))}
            </div>
          </ScrollReveal>

          {/* ─── Suggested Products ───────────────────────── */}
          {suggestedProducts.length > 0 && (
            <section aria-labelledby="suggested-heading">
              <ScrollReveal>
                <h2
                  id="suggested-heading"
                  className="text-xl sm:text-2xl font-bold text-gray-900 mb-6 mt-20"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  Suggested Products
                </h2>
              </ScrollReveal>

              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
                {suggestedProducts.map((p, i) => (
                  <ScrollReveal key={p.id} delay={i * 80} animation="fade-up">
                    <ProductCard
                      id={p.id}
                      name={p.name}
                      emoji={p.emoji}
                      image={p.image}
                      category={p.category}
                      currentPrice={p.currentPrice}
                      predictedPrice={p.predictedPrice}
                    />
                  </ScrollReveal>
                ))}
              </div>
            </section>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
