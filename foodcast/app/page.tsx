"use client";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import {
  Search,
  TrendingUp,
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
} from "lucide-react";
import Header from "./components/Header";
import Footer from "./components/Footer";
import WaveDivider from "./components/WaveDivider";
import ProductCard from "./components/ProductCard";
import ScrollReveal from "./components/ScrollReveal";
import ForecastChart from "./components/ForecastChart";
import { products } from "./lib/data";

export default function HomePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const sliderRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const trendingProducts = products.slice(0, 4);
  const allProducts = products;

  const checkScroll = () => {
    const el = sliderRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 10);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  useEffect(() => {
    checkScroll();
    const el = sliderRef.current;
    if (el) el.addEventListener("scroll", checkScroll, { passive: true });
    return () => el?.removeEventListener("scroll", checkScroll);
  }, []);

  const scroll = (dir: "left" | "right") => {
    const el = sliderRef.current;
    if (!el) return;
    el.scrollBy({ left: dir === "left" ? -300 : 300, behavior: "smooth" });
  };

  return (
    <>
      <Header />
      <main id="main-content">
        {/* ─── Hero Section ────────────────────────────── */}
        <section className="relative min-h-[85vh] flex items-center bg-gradient-to-br from-primary-800 via-primary-800 to-primary-900 overflow-hidden">
          {/* Ambient orbs */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
            <div className="absolute top-20 right-[15%] w-[500px] h-[500px] bg-accent/8 rounded-full blur-[120px] animate-float" />
            <div className="absolute bottom-10 left-[10%] w-[400px] h-[400px] bg-orange/6 rounded-full blur-[100px]" />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent/4 rounded-full blur-[150px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10 w-full pt-32 pb-20">
            <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
              {/* Left: Text Content */}
              <div className="max-w-xl">
                {/* Badge */}
                <div className="animate-fade-in-up inline-flex items-center gap-2 px-4 py-1.5 bg-accent/10 border border-accent/20 rounded-full mb-8">
                  <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                  <span className="text-accent text-xs font-medium tracking-wide">
                    AI-Powered Price Forecasting
                  </span>
                </div>

                <h1
                  className="animate-fade-in-up delay-100 text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold text-white leading-[1.1] mb-6"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  Know Tomorrow&apos;s
                  <br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                    Food Prices
                  </span>
                  <br />
                  Today
                </h1>

                <p className="animate-fade-in-up delay-200 text-white/55 text-lg sm:text-xl max-w-xl leading-relaxed mb-10">
                  AI-Based Forecasting and Market Analysis of Agri-Fishery Food
                  Prices in NCR Markets. Make data-driven decisions.
                </p>

                {/* Search Bar */}
                <div className="animate-fade-in-up delay-300">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (searchQuery.trim())
                        window.location.href = `/Search?q=${encodeURIComponent(searchQuery)}`;
                    }}
                    className="relative max-w-lg"
                    role="search"
                    aria-label="Search food products"
                  >
                    <div className="flex items-center bg-white/10 border border-white/15 rounded-2xl overflow-hidden backdrop-blur-sm transition-all duration-300 focus-within:border-accent/50 focus-within:bg-white/15 focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                      <Search
                        className="w-5 h-5 text-white/40 ml-4 shrink-0"
                        aria-hidden="true"
                      />
                      <input
                        type="text"
                        placeholder="Search products, e.g. Rice, Onion..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="flex-1 px-3 py-4 bg-transparent text-white placeholder-white/35 text-sm focus:outline-none"
                        aria-label="Search food products"
                      />
                      <button
                        type="submit"
                        className="mr-2 px-6 py-2.5 bg-orange rounded-xl text-white font-semibold text-sm
                          transition-all duration-300 hover:bg-orange-light hover:shadow-[0_4px_16px_rgba(255,145,77,0.4)]
                          active:scale-95 shrink-0"
                      >
                        Search
                      </button>
                    </div>
                  </form>
                </div>

                {/* Stats row */}
                <div className="animate-fade-in-up delay-500 flex flex-wrap gap-8 mt-12">
                  {[
                    { value: "50+", label: "Products Tracked" },
                    { value: "98.5%", label: "Model Accuracy" },
                    { value: "Real-time", label: "Data Updates" },
                  ].map((stat) => (
                    <div key={stat.label}>
                      <div className="text-2xl font-bold text-accent">{stat.value}</div>
                      <div className="text-white/40 text-xs mt-1">{stat.label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right: Mini Forecast Dashboard */}
              <div className="hidden lg:block relative h-[520px] animate-fade-in-up delay-300">
                {/* Main Dashboard Card */}
                <div
                  className="absolute top-0 right-0 w-[380px] bg-white/8 backdrop-blur-2xl rounded-3xl border border-white/12 shadow-[0_24px_64px_rgba(0,0,0,0.35)] overflow-hidden"
                  style={{ animation: "float 6s ease-in-out 0.5s infinite" }}
                >
                  {/* Dashboard Header */}
                  <div className="px-5 pt-5 pb-3">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                        <span className="text-[11px] font-semibold text-white/70 tracking-wide uppercase">Market Pulse</span>
                      </div>
                      <span className="text-[10px] text-white/30 tabular-nums">NCR Region</span>
                    </div>
                  </div>

                  {/* Mini Sparkline Chart Area */}
                  <div className="px-5 pb-3">
                    <div className="relative h-[100px] w-full rounded-xl bg-white/4 border border-white/6 overflow-hidden">
                      {/* SVG mini chart */}
                      <svg viewBox="0 0 300 80" className="w-full h-full" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="heroChartGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#7ED957" stopOpacity="0.25" />
                            <stop offset="100%" stopColor="#7ED957" stopOpacity="0" />
                          </linearGradient>
                        </defs>
                        {/* Area fill */}
                        <path
                          d="M0,60 Q30,55 60,48 T120,42 T180,35 T240,28 T300,22 L300,80 L0,80 Z"
                          fill="url(#heroChartGrad)"
                        />
                        {/* Actual line */}
                        <path
                          d="M0,60 Q30,55 60,48 T120,42 T180,35"
                          fill="none"
                          stroke="#7ED957"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                        />
                        {/* Predicted dashed line */}
                        <path
                          d="M180,35 T240,28 T300,22"
                          fill="none"
                          stroke="#7ED957"
                          strokeWidth="2"
                          strokeDasharray="6 4"
                          strokeLinecap="round"
                          opacity="0.6"
                        />
                        {/* Forecast divider */}
                        <line x1="180" y1="8" x2="180" y2="75" stroke="white" strokeWidth="0.5" strokeDasharray="3 3" opacity="0.2" />
                        <text x="185" y="14" fill="white" fillOpacity="0.3" fontSize="7" fontFamily="Inter, sans-serif">Forecast →</text>
                        {/* Dot at transition */}
                        <circle cx="180" cy="35" r="3" fill="#7ED957" />
                        <circle cx="180" cy="35" r="6" fill="#7ED957" opacity="0.2">
                          <animate attributeName="r" values="4;8;4" dur="2s" repeatCount="indefinite" />
                          <animate attributeName="opacity" values="0.3;0.05;0.3" dur="2s" repeatCount="indefinite" />
                        </circle>
                      </svg>
                      {/* Y-axis labels */}
                      <div className="absolute top-1 left-1.5 text-[8px] text-white/20 tabular-nums">₱55</div>
                      <div className="absolute bottom-1 left-1.5 text-[8px] text-white/20 tabular-nums">₱48</div>
                    </div>
                    <div className="flex items-center gap-4 mt-2">
                      <div className="flex items-center gap-1.5">
                        <div className="w-3 h-[2px] bg-accent rounded" />
                        <span className="text-[9px] text-white/35">Actual</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-3 h-[2px] bg-accent/50 rounded" style={{ backgroundImage: "repeating-linear-gradient(90deg, #7ED957 0, #7ED957 3px, transparent 3px, transparent 6px)" }} />
                        <span className="text-[9px] text-white/35">Predicted</span>
                      </div>
                    </div>
                  </div>

                  {/* Product Rows */}
                  <div className="px-5 pb-4 space-y-2.5">
                    {products.slice(0, 3).map((p, idx) => {
                      const change = ((p.predictedPrice - p.currentPrice) / p.currentPrice * 100);
                      const isUp = change > 0;
                      return (
                        <div key={p.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/4 border border-white/5 hover:bg-white/8 transition-all duration-300">
                          <div className="w-8 h-8 rounded-lg bg-white/8 flex items-center justify-center text-base shrink-0">
                            {p.emoji}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-semibold text-white truncate">{p.name}</div>
                            <div className="text-[10px] text-white/30">{p.category}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-xs font-bold text-white tabular-nums">₱{p.currentPrice.toFixed(0)}</div>
                            <div className={`text-[10px] font-bold tabular-nums ${isUp ? "text-accent" : "text-red-400"}`}>
                              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Bottom accent bar */}
                  <div className="h-1 bg-gradient-to-r from-accent/60 via-accent to-accent/60" />
                </div>

                {/* Floating stat badge — top-left offset */}
                <div
                  className="absolute top-[10px] right-[400px] bg-white/10 backdrop-blur-xl rounded-2xl border border-white/12 shadow-[0_8px_32px_rgba(0,0,0,0.2)] px-4 py-3"
                  style={{ animation: "float 4s ease-in-out 1s infinite" }}
                >
                  <div className="flex items-center gap-2.5">
                    <Brain className="w-5 h-5 text-accent" />
                    <div>
                      <div className="text-xs font-bold text-white">ML Model</div>
                      <div className="text-[10px] text-white/35">Active & Learning</div>
                    </div>
                  </div>
                </div>

                {/* Floating accuracy badge — bottom-left */}
                <div
                  className="absolute bottom-[20px] right-[390px] bg-white/10 backdrop-blur-xl rounded-2xl border border-white/12 shadow-[0_8px_32px_rgba(0,0,0,0.18)] px-4 py-3"
                  style={{ animation: "float 5s ease-in-out 2s infinite" }}
                >
                  <div className="flex items-center gap-2.5">
                    <BarChart3 className="w-5 h-5 text-orange" />
                    <div>
                      <div className="text-xs font-bold text-white">9 Products</div>
                      <div className="text-[10px] text-white/35">Tracked in NCR</div>
                    </div>
                  </div>
                </div>

                {/* Decorative particles */}
                <div className="absolute top-[150px] right-[395px] w-1.5 h-1.5 rounded-full bg-accent/30 animate-pulse" />
                <div className="absolute top-[350px] right-[405px] w-1 h-1 rounded-full bg-white/15" />
                <div className="absolute top-[250px] right-[385px] w-2 h-2 rounded-full bg-accent/10" />
              </div>
            </div>
          </div>
        </section>

        <WaveDivider from="#0B3D2E" to="#FDFBF7" />

        {/* ─── Daily Market Moves ──────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface" aria-labelledby="market-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-8">
                <div>
                  <h2
                    id="market-heading"
                    className="text-2xl sm:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Daily Market Moves
                  </h2>
                  <p className="text-gray-500 mt-2 text-sm">
                    Track today&apos;s price changes across NCR markets
                  </p>
                </div>
                <div className="hidden sm:flex items-center gap-2">
                  <button
                    onClick={() => scroll("left")}
                    disabled={!canScrollLeft}
                    className="p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      disabled:opacity-30 disabled:cursor-not-allowed
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll left"
                  >
                    <ChevronLeft className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => scroll("right")}
                    disabled={!canScrollRight}
                    className="p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      disabled:opacity-30 disabled:cursor-not-allowed
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll right"
                  >
                    <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </ScrollReveal>

            <div
              ref={sliderRef}
              className="flex gap-5 overflow-x-auto pb-4 snap-x snap-mandatory scrollbar-hide"
              aria-label="Product carousel"
              role="region"
            >
              {allProducts.map((p, i) => (
                <div
                  key={p.id}
                  className="snap-start shrink-0 w-[280px]"
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  <ProductCard
                    id={p.id}
                    name={p.name}
                    emoji={p.emoji}
                    category={p.category}
                    image={p.image}
                    currentPrice={p.currentPrice}
                    predictedPrice={p.predictedPrice}
                    compact
                  />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Trending Products ───────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface" aria-labelledby="trending-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-8">
                <div>
                  <h2
                    id="trending-heading"
                    className="text-2xl sm:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Trending Products
                  </h2>
                  <p className="text-gray-500 mt-2 text-sm">
                    Most searched & volatile commodities this week
                  </p>
                </div>
                <Link
                  href="/Search"
                  className="hidden sm:flex items-center gap-1.5 text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                >
                  View all <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </ScrollReveal>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {trendingProducts.map((p, i) => (
                <ScrollReveal key={p.id} delay={i * 100} animation="scale-in">
                  <ProductCard
                    id={p.id}
                    name={p.name}
                    emoji={p.emoji}
                    category={p.category}
                    image={p.image}
                    currentPrice={p.currentPrice}
                    predictedPrice={p.predictedPrice}
                  />
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Wave + What is FOODCAST ──────────────────── */}
        <div className="bg-surface">
          <WaveDivider from="#FDFBF7" to="#0B3D2E" />
        </div>

        <section
          className="relative py-20 sm:py-28 bg-primary-800 overflow-hidden"
          aria-labelledby="about-heading"
        >
          <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
            <div className="absolute -top-24 -right-24 w-[500px] h-[500px] bg-accent/5 rounded-full blur-[120px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="text-center mb-16">
                <h2
                  id="about-heading"
                  className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  What is{" "}
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                    FOODCAST
                  </span>
                  ?
                </h2>
                <p className="text-white/50 max-w-2xl mx-auto text-base sm:text-lg leading-relaxed">
                  An AI-powered platform that forecasts agri-fishery food prices
                  in National Capital Region (NCR) markets using advanced machine
                  learning algorithms.
                </p>
              </div>
            </ScrollReveal>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[
                {
                  icon: <Brain className="w-7 h-7" />,
                  title: "AI-Driven Analysis",
                  description:
                    "Machine learning models trained on historical data to predict future price trends with high accuracy.",
                },
                {
                  icon: <TrendingUp className="w-7 h-7" />,
                  title: "Real-Time Forecasting",
                  description:
                    "Get up-to-date predictions on agri-fishery product prices across major NCR markets.",
                },
                {
                  icon: <BarChart3 className="w-7 h-7" />,
                  title: "Data Visualization",
                  description:
                    "Interactive charts and graphs that make complex market data easy to understand and act upon.",
                },
              ].map((feature, i) => (
                <ScrollReveal key={feature.title} delay={i * 150} animation="fade-up">
                  <div className="group relative bg-white/5 border border-white/10 rounded-2xl p-7 transition-all duration-400 hover:bg-white/8 hover:border-accent/20 hover:shadow-[0_8px_32px_rgba(126,217,87,0.08)]">
                    <div className="w-14 h-14 rounded-xl bg-accent/10 flex items-center justify-center text-accent mb-5 transition-all duration-300 group-hover:bg-accent/20 group-hover:scale-105">
                      {feature.icon}
                    </div>
                    <h3
                      className="text-lg font-semibold text-white mb-2"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {feature.title}
                    </h3>
                    <p className="text-white/45 text-sm leading-relaxed">
                      {feature.description}
                    </p>
                  </div>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        <WaveDivider from="#0B3D2E" to="#FDFBF7" />

        {/* ─── All Products ────────────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface" aria-labelledby="all-products-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-8">
                <div>
                  <h2
                    id="all-products-heading"
                    className="text-2xl sm:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    All Products
                  </h2>
                  <p className="text-gray-500 mt-2 text-sm">
                    Browse our full catalog of tracked commodities
                  </p>
                </div>
                <Link
                  href="/Table"
                  className="hidden sm:flex items-center gap-1.5 text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                >
                  Table view <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </ScrollReveal>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {allProducts.map((p, i) => (
                <ScrollReveal key={p.id} delay={i * 80} animation="fade-up">
                  <ProductCard
                    id={p.id}
                    name={p.name}
                    emoji={p.emoji}
                    category={p.category}
                    image={p.image}
                    currentPrice={p.currentPrice}
                    predictedPrice={p.predictedPrice}
                  />
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* ─── CTA Banner ──────────────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal animation="scale-in">
              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary-800 via-primary-700 to-primary-800 p-10 sm:p-14 lg:p-20">
                <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                  <div className="absolute -top-20 -right-20 w-80 h-80 bg-accent/10 rounded-full blur-[80px]" />
                  <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-orange/8 rounded-full blur-[60px]" />
                </div>

                <div className="relative text-center">
                  <h2
                    className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Start Forecasting{" "}
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                      Today
                    </span>
                  </h2>
                  <p className="text-white/50 max-w-lg mx-auto mb-10 text-base sm:text-lg">
                    Access AI-driven food price predictions and make smarter
                    decisions for your market strategy.
                  </p>
                  <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                    <Link
                      href="/Search"
                      className="px-8 py-4 bg-accent text-primary-800 font-bold rounded-2xl text-base
                        transition-all duration-300 hover:bg-accent-light hover:shadow-[0_6px_24px_rgba(126,217,87,0.4)] hover:-translate-y-0.5
                        active:translate-y-0 active:scale-[0.98]"
                    >
                      Explore Forecasts
                    </Link>
                    <Link
                      href="/About"
                      className="px-8 py-4 bg-transparent border border-white/20 text-white font-semibold rounded-2xl text-base
                        transition-all duration-300 hover:bg-white/10 hover:border-white/30"
                    >
                      Learn More
                    </Link>
                  </div>
                </div>
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}