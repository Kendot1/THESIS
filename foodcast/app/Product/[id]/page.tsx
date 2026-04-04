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
import Header from "../../components/Header";
import Footer from "../../components/Footer";
import ForecastChart from "../../components/ForecastChart";
import ProductCard from "../../components/ProductCard";
import ScrollReveal from "../../components/ScrollReveal";
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
            href="/Search"
            className="px-6 py-3 bg-primary-800 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors"
          >
            Back to Search
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
                href="/Search"
                className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-primary-800 transition-colors"
                aria-label="Back to search"
              >
                <ArrowLeft className="w-4 h-4" />
                Search
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
          <ScrollReveal>
            <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-8">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center text-4xl shadow-sm">
                {product.emoji}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3 flex-wrap">
                  <h1
                    className="text-3xl sm:text-4xl font-bold text-gray-900"
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
                <p className="text-gray-500 mt-1">
                  Price forecast and market analysis
                </p>
              </div>
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
                  label: "Trading Volume",
                  value: product.volume,
                  icon: <Layers className="w-4 h-4" />,
                  sub: "Weekly average",
                  color: "text-gray-900",
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
                  className="text-xl sm:text-2xl font-bold text-gray-900 mb-6"
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
                      category={p.category}
                      currentPrice={p.currentPrice}
                      predictedPrice={p.predictedPrice}
                      sparklineData={p.sparklineData}
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
