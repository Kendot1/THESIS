"use client";
import { use, useMemo, useState, useRef, useEffect } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Calendar,
  Layers,
  CheckCircle2,
  AlertCircle,
  ArrowRightLeft,
  Sparkles,
  ChevronLeft,
  ChevronRight,
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

  const variants = useMemo(() => {
    if (!product) return [];
    // Simple variant detection: shared keyword in name (e.g. "Onion", "Garlic", "Rice")
    const commonKeywords = ["Onion", "Garlic", "Rice", "Fish", "Tomato", "Cabbage"];
    const keyword = commonKeywords.find(k => product.name.includes(k));
    if (!keyword) return [];

    return products.filter(
      (p) => p.id !== product.id && p.name.includes(keyword)
    );
  }, [product]);

  const smartAlternatives = useMemo(() => {
    if (!product) return [];
    // Suggest alternatives if current product is Bullish
    if (product.sentiment !== "Bullish") return [];

    const variantIds = variants.map(v => v.id);

    return products
      .filter((p) => p.id !== product.id && p.category === product.category)
      .filter((p) => p.sentiment !== "Bullish")
      .filter((p) => !variantIds.includes(p.id))
      .sort((a, b) => a.currentPrice - b.currentPrice)
      .slice(0, 3);
  }, [product, variants]);

  const suggestedProducts = useMemo(() => {
    if (!product) return [];
    const excludeIds = [product.id, ...variants.map(v => v.id), ...smartAlternatives.map(a => a.id)];
    return products
      .filter((p) => !excludeIds.includes(p.id))
      .filter(
        (p) =>
          p.category === product.category ||
          p.sentiment === product.sentiment
      )
      .slice(0, 4);
  }, [product, variants, smartAlternatives]);

  /* ─── Slider Logic (Predict style) ──────────── */
  const sliderRef = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(true);

  const checkScroll = () => {
    const el = sliderRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 10);
    setCanRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  const scrollSlider = (dir: "left" | "right") => {
    const el = sliderRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 200 : 260;
    el.scrollBy({ left: dir === "left" ? -cardWidth : cardWidth, behavior: "smooth" });
  };

  useEffect(() => {
    checkScroll();
    const el = sliderRef.current;
    if (el) {
      el.addEventListener("scroll", checkScroll, { passive: true });
      window.addEventListener("resize", checkScroll);
    }
    return () => {
      el?.removeEventListener("scroll", checkScroll);
      window.removeEventListener("resize", checkScroll);
    };
  }, [suggestedProducts]);

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

  const trendLabel = product.sentiment === "Bullish" ? "Price Rising" : product.sentiment === "Bearish" ? "Price Dropping" : "Stable";

  return (
    <>
      <Header />
      <main id="main-content" className="relative pt-20 min-h-screen bg-surface overflow-hidden">
        {/* ─── Page Top Design ────────────────────────── */}
        <div className="absolute top-0 left-0 right-0 h-[500px] pointer-events-none overflow-hidden" aria-hidden="true">
          {/* Subtle Color Wash */}
          <div className="absolute inset-0 bg-gradient-to-b from-primary-50/30 via-surface/80 to-surface" />

          {/* Animated Atmospheric Orbs */}
          <div className="absolute top-[-10%] left-[15%] w-[45%] h-[60%] bg-accent/8 rounded-full blur-[120px] animate-pulse opacity-60" />
          <div className="absolute top-[5%] right-[10%] w-[35%] h-[50%] bg-orange/5 rounded-full blur-[100px] animate-float opacity-50" style={{ animationDelay: '-3s' }} />
        </div>

        <div className="relative z-10">
          {/* ─── Breadcrumb + Back ──────────────────────── */}
          <div className="border-b border-gray-100/50 backdrop-blur-sm bg-white/5">
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

          <div className="max-w-7xl mx-auto px-5 lg:px-10 py-6 sm:py-10">
            {/* ─── Product Header ──────────────────────────── */}
            <ScrollReveal delay={200}>
              <div className="relative bg-gradient-to-br from-primary-800 to-primary-900 mb-6 sm:mb-8 rounded-2xl p-5 sm:p-8 overflow-hidden shadow-2xl">
                <div className="absolute top-0 right-0 w-48 sm:w-64 h-48 sm:h-64 bg-accent/10 rounded-full blur-3xl -mr-16 -mt-16 sm:-mr-20 sm:-mt-20" />
                <div className="absolute bottom-0 left-0 w-24 sm:w-32 h-24 sm:h-32 bg-white/5 rounded-full blur-2xl -ml-8 -mb-8 sm:-ml-10 sm:-mb-10" />

                <div className="relative space-y-8">
                  {/* Top Row: Image + Identity */}
                  <div className="flex flex-col sm:flex-row items-center sm:items-end gap-6 sm:gap-10">
                    <div className="shrink-0 w-25 h-25 sm:w-35 sm:h-35 rounded-xl bg-white overflow-hidden shadow-2xl border-4 border-white/20 transform hover:scale-105 transition-transform duration-500">
                      <img src={product.image} alt={product.name} className="w-full h-full object-cover rounded-xl" />
                    </div>

                    <div className="flex-1 flex flex-col items-center sm:items-start">
                      <div className="flex flex-col gap-3 mb-2 ">
                        <div className="flex flex-wrap items-center justify-center sm:justify-start gap-3">
                          <span
                            className={`inline-flex items-center gap-1 text-[10px] sm:text-xs font-bold px-4 py-1.5 rounded-full shadow-lg ${sentimentColor} backdrop-blur-md`}
                          >
                            {sentimentIcon}
                            {trendLabel}
                          </span>
                          <span className="text-[10px] sm:text-xs font-bold text-accent bg-accent/10 px-4 py-1.5 rounded-full border border-accent/20">
                            {product.category}
                          </span>
                        </div>
                        <h1
                          className="text-2xl sm:text-4xl font-bold text-white leading-tight"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          {product.name}
                        </h1>
                      </div>
                      <span className="text-white/40 text-[10px] sm:text-xs font-medium tracking-wider">NCR-AGRI-{product.id.toUpperCase()}</span>
                    </div>
                  </div>

                  {/* Bottom Row: Description */}
                  <div className="pt-8 border-t border-white/10">
                    <p className="text-white/70 text-xs sm:text-base leading-relaxed text-justify max-w-4xl">
                      {product.description}
                    </p>
                  </div>
                </div>
              </div>
            </ScrollReveal>

            {/* ─── Main Content Layout (Dashboard Style) ──────── */}
            <div className="grid lg:grid-cols-12 gap-8 items-start">
              {/* Left Column: Forecast & Core Stats */}
              <div className="lg:col-span-8 space-y-8">
                {/* Price Forecast Chart */}
                <ScrollReveal>
                  <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
                      <div>
                        <h2
                          className="text-2xl sm:text-2xl font-bold text-gray-900 mb-1"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          Market Price Forecast
                        </h2>
                        <p className="text-gray-500 text-sm">
                          Real-time price insights with AI forecasting
                        </p>
                      </div>
                      <div className="flex items-center p-1 bg-gray-50 rounded-xl border border-gray-100 w-fit">
                        {["1M", "3M", "6M", "1Y"].map((period) => (
                          <button
                            key={period}
                            className={`px-3 sm:px-4 py-1.5 sm:py-2 text-[10px] sm:text-xs font-bold rounded-lg transition-all ${period === "6M" ? "bg-white text-primary-800 shadow-sm" : "text-gray-400 hover:text-gray-600"}`}
                          >
                            {period}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="relative">
                      <ForecastChart
                        data={product.forecastData}
                        showGrid
                        showLegend
                      />
                    </div>
                  </div>
                </ScrollReveal>

                {/* Price Overview Stats */}
                <ScrollReveal delay={100}>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {[
                      {
                        label: "Current Price",
                        value: `₱${product.currentPrice.toFixed(2)}`,
                        icon: <BarChart3 className="w-4 h-4" />,
                        sub: "Live Market",
                        color: "text-primary-800",
                        bg: "bg-primary-50/30",
                      },
                      {
                        label: "Predicted",
                        value: `₱${product.predictedPrice.toFixed(2)}`,
                        icon: <TrendingUp className="w-4 h-4" />,
                        sub: "AI Target",
                        color: isUp ? "text-positive" : "text-negative",
                        bg: isUp ? "bg-positive/5" : "bg-negative/5",
                      },
                      {
                        label: "Price Change",
                        value: `${isUp ? "+" : ""}${priceChangePercent.toFixed(1)}%`,
                        icon: isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />,
                        sub: `${isUp ? "+" : ""}₱${Math.abs(priceChange).toFixed(2)}`,
                        color: isUp ? "text-positive" : "text-negative",
                        bg: isUp ? "bg-positive/5" : "bg-negative/5",
                      },
                      {
                        label: "Price Stability",
                        value: isUp ? "Moderate" : "High",
                        icon: <Layers className="w-4 h-4" />,
                        sub: "Stability Index",
                        color: "text-primary-700",
                        bg: "bg-gray-50",
                      },
                    ].map((stat) => (
                      <div
                        key={stat.label}
                        className={`rounded-2xl border border-gray-100 p-5 shadow-sm transition-all hover:border-accent/20 ${stat.bg}`}
                      >
                        <div className="flex items-center gap-2 text-gray-400 mb-3">
                          {stat.icon}
                          <span className="text-[10px] font-black uppercase tracking-widest">
                            {stat.label}
                          </span>
                        </div>
                        <div className={`text-xl sm:text-2xl font-black ${stat.color}`}>
                          {stat.value}
                        </div>
                        <div className="text-[10px] font-bold text-gray-400 mt-1 uppercase tracking-tighter">{stat.sub}</div>
                      </div>
                    ))}
                  </div>
                </ScrollReveal>
              </div>

              {/* Side Column (Market Pulse) */}
              <div className="lg:col-span-4 space-y-5">
                <ScrollReveal delay={200}>
                  {(() => {
                    const isBullish = product.sentiment === "Bullish";
                    const isBearish = product.sentiment === "Bearish";
                    const insight = isBullish
                      ? {
                        title: "Buying Opportunity",
                        message: `Prices rising by ${priceChangePercent.toFixed(1)}%. Markets are getting tighter.`,
                        action: "Buy Now",
                        recommendation: "Increase stock levels now to avoid higher costs later.",
                        status: "Suggested Buy",
                        statusBg: "bg-positive/10 text-positive",
                        pulseColor: "bg-positive",
                        glowColor: "from-positive/10 to-accent/5",
                      }
                      : isBearish
                        ? {
                          title: "Wait to Purchase",
                          message: `Prices dropping by ${Math.abs(priceChangePercent).toFixed(1)}%.`,
                          action: "Wait",
                          recommendation: "Wait for the price to drop further to save money.",
                          status: "Hold Off",
                          statusBg: "bg-negative/10 text-negative",
                          pulseColor: "bg-negative",
                          glowColor: "from-negative/10 to-accent/5",
                        }
                        : {
                          title: "Stable Market",
                          message: "Prices are following normal seasonal patterns.",
                          action: "No Action",
                          recommendation: "Continue your normal buying schedule.",
                          status: "Monitor",
                          statusBg: "bg-gray-100 text-gray-600",
                          pulseColor: "bg-gray-400",
                          glowColor: "from-gray-100 to-transparent",
                        };

                    return (
                      <div className="relative group">
                        <div className={`absolute inset-0 bg-gradient-to-br ${insight.glowColor} opacity-50 rounded-[2rem] blur-xl transition-opacity duration-700`} />
                        <div className="relative bg-white/70 backdrop-blur-xl border border-white/80 rounded-[2rem] p-6 sm:p-8 shadow-xl flex flex-col items-center text-center overflow-hidden">
                          <div className="relative mb-6">
                            <div className={`w-20 h-20 rounded-full ${insight.pulseColor}/20 flex items-center justify-center animate-pulse`}>
                              <div className={`w-10 h-10 rounded-full ${insight.pulseColor} shadow-lg flex items-center justify-center`}>
                                {isBullish ? <TrendingUp className="w-5 h-5 text-white" /> : isBearish ? <TrendingDown className="w-5 h-5 text-white" /> : <Minus className="w-5 h-5 text-white" />}
                              </div>
                            </div>
                            <div className={`absolute inset-0 rounded-full border-2 border-dashed ${insight.pulseColor}/30 animate-spin-slow`} />
                          </div>

                          <span className={`px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-widest shadow-sm mb-3 ${insight.statusBg}`}>
                            {insight.status}
                          </span>

                          <h3 className="text-xl font-bold text-gray-900 mb-3" style={{ fontFamily: "var(--font-display)" }}>
                            {insight.title}
                          </h3>

                          <p className="text-gray-600 text-sm leading-relaxed mb-6">
                            {insight.message} <span className="font-bold text-gray-900">{insight.recommendation}</span>
                          </p>

                          <div className="w-full pt-6 border-t border-gray-100 flex flex-col gap-4">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Next Action</span>
                              <span className="text-xs font-black text-primary-800 uppercase tracking-tight">{insight.action}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Confidence Level</span>
                              <div className="flex gap-1">
                                {[1, 2, 3, 4, 5].map((s) => (
                                  <div key={s} className={`w-2 h-2 rounded-full ${s <= 4 ? "bg-accent" : "bg-gray-200"}`} />
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </ScrollReveal>

                {/* Smart Comparison & Alternatives (Stacked Sidebar Layout) */}
                {(variants.length > 0 || smartAlternatives.length > 0) && (
                  <div className="space-y-6">
                    {/* Variants */}
                    {variants.length > 0 && (
                      <ScrollReveal delay={300}>
                        <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm overflow-hidden relative">
                          <div className="flex items-center gap-3 mb-5">
                            <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center text-primary-800">
                              <ArrowRightLeft className="w-5 h-5" />
                            </div>
                            <div>
                              <h3 className="text-sm font-bold text-gray-900" style={{ fontFamily: "var(--font-display)" }}>
                                Market Variants
                              </h3>
                              <p className="text-[10px] text-gray-500 font-bold uppercase tracking-tighter">Compare types</p>
                            </div>
                          </div>

                          <div className="space-y-3">
                            {variants.map(v => (
                              <Link
                                key={v.id}
                                href={`/Product/${v.id}`}
                                className="group flex items-center justify-between p-3.5 rounded-2xl border border-gray-50 hover:border-accent/40 hover:bg-accent/5 transition-all duration-300"
                              >
                                <div className="flex items-center gap-3">
                                  <div className="w-9 h-9 rounded-xl overflow-hidden border border-gray-100 shrink-0 bg-gray-50">
                                    <img src={v.image} alt={v.name} className="w-full h-full object-cover" />
                                  </div>
                                  <div>
                                    <div className="text-xs font-bold text-gray-900 group-hover:text-primary-800 transition-colors">{v.name}</div>
                                    <div className="text-[9px] text-gray-400 font-black uppercase tracking-widest">₱{v.currentPrice.toFixed(2)}</div>
                                  </div>
                                </div>
                                <ArrowRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-accent group-hover:translate-x-1 transition-all" />
                              </Link>
                            ))}
                          </div>
                        </div>
                      </ScrollReveal>
                    )}

                    {/* Alternatives */}
                    {smartAlternatives.length > 0 && (
                      <ScrollReveal delay={400}>
                        <div className="bg-primary-900 rounded-3xl p-6 shadow-xl relative overflow-hidden">
                          <div className="absolute top-0 right-0 w-24 h-24 bg-accent/20 rounded-full blur-2xl -mr-12 -mt-12" />

                          <div className="relative flex items-center gap-3 mb-5">
                            <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center text-accent">
                              <Sparkles className="w-5 h-5" />
                            </div>
                            <div>
                              <h3 className="text-sm font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
                                Smart Alternatives
                              </h3>
                              <p className="text-[10px] text-white/50 font-bold uppercase tracking-tighter">Better Value</p>
                            </div>
                          </div>

                          <div className="relative space-y-2">
                            {smartAlternatives.map(a => (
                              <Link
                                key={a.id}
                                href={`/Product/${a.id}`}
                                className="group flex items-center justify-between p-3.5 rounded-2xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-accent/40 transition-all duration-300"
                              >
                                <div className="flex items-center gap-3">
                                  <div className="w-9 h-9 rounded-xl overflow-hidden border border-white/10 shrink-0 bg-white/5">
                                    <img src={a.image} alt={a.name} className="w-full h-full object-cover" />
                                  </div>
                                  <div>
                                    <div className="text-xs font-bold text-white group-hover:text-accent transition-colors">{a.name}</div>
                                    <div className="text-[9px] text-white/40 font-black uppercase tracking-widest">₱{a.currentPrice.toFixed(2)}</div>
                                  </div>
                                </div>
                                <ArrowRight className="w-3.5 h-3.5 text-white/30 group-hover:text-accent group-hover:translate-x-1 transition-all" />
                              </Link>
                            ))}
                          </div>
                        </div>
                      </ScrollReveal>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* ─── Suggested Products ───────────────────────── */}
            {suggestedProducts.length > 0 && (
              <section aria-labelledby="suggested-heading" className="mt-16 sm:mt-24">
                <ScrollReveal className="flex items-end justify-between mb-6">
                  <div>
                    <h2
                      id="suggested-heading"
                      className="text-xl sm:text-2xl font-bold text-gray-900"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      Suggested Products
                    </h2>
                    <p className="text-gray-500 text-xs mt-1">Based on category and trends</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Link
                      href="/Table"
                      className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                    >
                      View all <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                    </Link>
                  </div>
                </ScrollReveal>

                {/* Slider Container */}
                <div
                  ref={sliderRef}
                  className="flex gap-4 sm:gap-6 overflow-x-auto pt-4 pb-12 px-10 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
                  aria-label="Suggested products slider"
                  role="region"
                >
                  {suggestedProducts.map((p, i) => (
                    <div
                      key={p.id}
                      className="snap-start shrink-0 w-[180px] sm:w-[240px] lg:w-[280px]"
                    >
                      <ScrollReveal delay={i * 80} animation="fade-up">
                        <ProductCard
                          id={p.id}
                          name={p.name}
                          emoji={p.emoji}
                          image={p.image}
                          category={p.category}
                          currentPrice={p.currentPrice}
                          predictedPrice={p.predictedPrice}
                          compact
                        />
                      </ScrollReveal>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
