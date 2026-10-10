"use client";
import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Search,
  TrendingUp,
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import WaveDivider from "../components/WaveDivider";
import DailyMoverCard from "../components/DailyMoverCard";
import NewsCard from "../components/NewsCard";
import ScrollReveal from "../components/ScrollReveal";
import { DEFAULT_PRODUCT_IMAGE, DashboardProduct, NewsArticle, formatRelativeAge, verifiedWithinTenAccuracy } from "../lib/data";
import { useClock, useDashboardProducts, useForecastStatus, useNews } from "../lib/hooks";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { encryptId } from "../../lib/idCipher";

interface HomeProps {
  initialProducts: DashboardProduct[];
  initialNews: NewsArticle[];
}

export default function Home({ initialProducts, initialNews }: HomeProps) {
  const { data: products = [] } = useDashboardProducts(initialProducts);
  const { data: newsList = [] } = useNews(10, initialNews);
  const { data: forecastStatus } = useForecastStatus();
  const predictionSuccess = verifiedWithinTenAccuracy(forecastStatus?.modelMetrics);
  const now = useClock();
  const router = useRouter();
  const { t, language, isTransitioning } = useLanguage();

  const [searchQuery, setSearchQuery] = useState("");
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  const searchSuggestions = useMemo(() => {
    if (!searchQuery || searchQuery.length < 1) return [];
    return products.filter(
      (p) =>
        p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.variant && p.variant.toLowerCase().includes(searchQuery.toLowerCase()))
    ).slice(0, 5);
  }, [searchQuery, products]);

  /* ─── Daily Movers slider state ─────────────────── */
  const sliderRef = useRef<HTMLDivElement>(null);
  const [isPaused, setIsPaused] = useState(false);
  const autoSlideTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ─── Derived Data (Memoized) ─────────────────────── */
  const dailyMovers = useMemo(() => {
    return [...products]
      .sort((a, b) => {
        const changeA = a.currentPrice === 0 ? 0 : Math.abs((a.predictedPrice - a.currentPrice) / a.currentPrice);
        const changeB = b.currentPrice === 0 ? 0 : Math.abs((b.predictedPrice - b.currentPrice) / b.currentPrice);
        return changeB - changeA;
      })
      .slice(0, 15);
  }, [products]);

  /* ─── News slider state ─────────────────────────── */
  const newsRef = useRef<HTMLDivElement>(null);
  const [isNewsPaused, setIsNewsPaused] = useState(false);
  const newsAutoSlideTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ─── Hero chart state ───────────────────────────── */
  const [hoveredChartPt, setHoveredChartPt] = useState<number | null>(null);
  const [selectedProductIdx, setSelectedProductIdx] = useState(0);

  /* ─── Scroll helpers ────────────────────────────── */
  const scroll = (dir: "left" | "right") => {
    const el = sliderRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 315 : window.innerWidth < 1024 ? 435 : 495;

    if (dir === "left") {
      if (el.scrollLeft <= 10) el.scrollTo({ left: el.scrollWidth, behavior: "smooth" });
      else el.scrollBy({ left: -cardWidth, behavior: "smooth" });
    } else {
      if (el.scrollLeft >= el.scrollWidth - el.clientWidth - 10) el.scrollTo({ left: 0, behavior: "smooth" });
      else el.scrollBy({ left: cardWidth, behavior: "smooth" });
    }
  };

  const scrollNews = (dir: "left" | "right") => {
    const el = newsRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 300 : 380;

    if (dir === "left") {
      if (el.scrollLeft <= 10) el.scrollTo({ left: el.scrollWidth, behavior: "smooth" });
      else el.scrollBy({ left: -cardWidth, behavior: "smooth" });
    } else {
      if (el.scrollLeft >= el.scrollWidth - el.clientWidth - 10) el.scrollTo({ left: 0, behavior: "smooth" });
      else el.scrollBy({ left: cardWidth, behavior: "smooth" });
    }
  };

  /* ─── Auto-slide for Daily Movers ──────────────── */
  const autoSlide = useCallback(() => {
    const el = sliderRef.current;
    if (!el || isPaused) return;

    const atEnd = el.scrollLeft >= el.scrollWidth - el.clientWidth - 10;
    if (atEnd) {
      el.scrollTo({ left: 0, behavior: "smooth" });
    } else {
      const cardWidth = window.innerWidth < 640 ? 315 : window.innerWidth < 1024 ? 435 : 495;
      el.scrollBy({ left: cardWidth, behavior: "smooth" });
    }
  }, [isPaused]);

  /* ─── Auto-slide for News ──────────────────────── */
  const autoSlideNews = useCallback(() => {
    const el = newsRef.current;
    if (!el || isNewsPaused) return;

    const atEnd = el.scrollLeft >= el.scrollWidth - el.clientWidth - 10;
    if (atEnd) {
      el.scrollTo({ left: 0, behavior: "smooth" });
    } else {
      const cardWidth = window.innerWidth < 640 ? 300 : 380;
      el.scrollBy({ left: cardWidth, behavior: "smooth" });
    }
  }, [isNewsPaused]);

  // News auto-slide timer
  useEffect(() => {
    if (isNewsPaused) {
      if (newsAutoSlideTimer.current) clearInterval(newsAutoSlideTimer.current);
      return;
    }
    newsAutoSlideTimer.current = setInterval(autoSlideNews, 5000); // 5s for news
    return () => {
      if (newsAutoSlideTimer.current) clearInterval(newsAutoSlideTimer.current);
    };
  }, [isNewsPaused, autoSlideNews]);

  // Auto-slide timer
  useEffect(() => {
    if (isPaused) {
      if (autoSlideTimer.current) clearInterval(autoSlideTimer.current);
      return;
    }
    autoSlideTimer.current = setInterval(autoSlide, 3500);
    return () => {
      if (autoSlideTimer.current) clearInterval(autoSlideTimer.current);
    };
  }, [isPaused, autoSlide]);

  // When we have initialProducts, we skip the loading skeleton entirely
  // Only show skeleton during language transitions
  if (isTransitioning) {
    return (
      <main className="min-h-screen bg-surface">
        {/* Hero Section Skeleton */}
        <section className="relative min-h-[85vh] flex items-center bg-primary-900 overflow-hidden">
          <div className="relative max-w-7xl mx-auto px-5 lg:px-10 sm:px-5 w-full">
            <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
              <div className="max-w-xl">
                <div className="h-6 w-48 bg-white/10 rounded-full mb-8 animate-pulse" />
                <div className="space-y-4 mb-6">
                  <div className="h-16 w-3/4 bg-white/10 rounded-2xl animate-pulse" />
                  <div className="h-16 w-full bg-white/10 rounded-2xl animate-pulse" />
                  <div className="h-16 w-1/2 bg-white/10 rounded-2xl animate-pulse" />
                </div>
                <div className="h-12 w-full bg-white/5 rounded-xl mb-10 animate-pulse" />
                <div className="h-14 w-full max-w-lg bg-white/20 rounded-2xl animate-pulse" />
              </div>
              <div className="hidden lg:block">
                <div className="w-full h-[500px] bg-white/5 rounded-[3rem] animate-pulse" />
              </div>
            </div>
          </div>
        </section>

        {/* Daily Movers Skeleton */}
        <section className="py-5 sm:py-10 bg-surface -mt-10 relative z-20">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <div className="flex items-end justify-between mb-4 sm:mb-8">
              <div className="space-y-2">
                <div className="h-8 w-64 bg-gray-200 rounded-xl animate-pulse" />
                <div className="h-4 w-48 bg-gray-100 rounded-lg animate-pulse" />
              </div>
              <div className="flex gap-2">
                <div className="h-10 w-10 bg-gray-100 rounded-xl animate-pulse" />
                <div className="h-10 w-10 bg-gray-100 rounded-xl animate-pulse" />
              </div>
            </div>
            <div className="flex gap-4 sm:gap-6 overflow-hidden">
              {[1, 2, 3].map(i => (
                <div key={i} className="shrink-0 w-[300px] sm:w-[420px] lg:w-[480px] bg-white rounded-3xl border border-gray-100 p-6 h-[220px] animate-pulse">
                  <div className="flex items-start gap-4 mb-4">
                    <div className="w-16 h-16 bg-gray-100 rounded-2xl" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-1/3 bg-gray-100 rounded-md" />
                      <div className="h-6 w-3/4 bg-gray-200 rounded-lg" />
                    </div>
                    <div className="h-8 w-20 bg-gray-100 rounded-full" />
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-6">
                    <div className="space-y-2">
                      <div className="h-3 w-16 bg-gray-100 rounded-md" />
                      <div className="h-6 w-24 bg-gray-200 rounded-lg" />
                    </div>
                    <div className="space-y-2">
                      <div className="h-3 w-16 bg-gray-100 rounded-md" />
                      <div className="h-6 w-24 bg-gray-200 rounded-lg" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <>
      <main id="main-content">
        {/* ─── Hero Section ────────────────────────────── */}
        <section className="relative min-h-[55vh] sm:min-h-[85vh] flex items-center shadow-xl/20">          {/* Ambient orbs */}
          {/* Background Image */}
          <div className="absolute inset-0 -z-10 overflow-hidden">
            <Image
              src="/Bg-2.jpg"
              alt="background"
              fill
              priority
              sizes="100vw"
              className="object-cover blur-xs scale-105"
            />
            <div className="absolute inset-0 bg-primary-900/70" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10 sm:px-5 pt-32 pb-20">
            <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
              {/* Left: Text Content */}
              <div className="max-w-xl">
                {/* Badge */}
                <div className="animate-fade-in-up inline-flex items-center gap-1 px-2 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                  <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                  <span className="text-white/80 text-xs tracking-wide">
                    {t("heroBadge")}
                  </span>
                </div>

                <h2
                  className="animate-fade-in-up delay-100 text-4xl sm:text-5xl lg:text-6xl xl:text-7xl font-bold text-surface leading-[1.1] mb-6 "
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {t("heroTitle1")}
                  <br />
                  <span className="bg-gradient-to-r from-[#009966] via-[#BF7B16] to-[#FF984F] bg-clip-text text-transparent">
                    {t("heroTitle2")}
                  </span>
                  <br />
                  {t("heroTitle3")}
                </h2>

                <p className="animate-fade-in-up delay-200 text-white/65 text-xs 
                sm:text-base max-w-xl leading-relaxed mb-10">
                  {t("heroSubtitle")}
                </p>

                {/* Search Bar */}
                <div className="animate-fade-in-up delay-300 min-w-[200px] relative z-20">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (searchQuery.trim())
                        router.push(`/Predict?q=${encodeURIComponent(searchQuery)}`);
                    }}
                    className="relative max-w-lg"
                    role="search"
                    aria-label="Search food products"
                  >
                    <div className="flex items-center bg-white/85 rounded-2xl
                    overflow-hidden backdrop-blur-sm transition-all duration-300 
                    focus-within:border-accent/50 focus-within:bg-white/95 focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                      <Search
                        className="w-5 h-5 text-black/55 ml-4 shrink-0"
                        aria-hidden="true"
                      />
                      <input
                        type="text"
                        placeholder={t("searchPlaceholder")}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onFocus={() => setIsSearchFocused(true)}
                        onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                        className="flex-1 px-3 py-3 bg-transparent text-black placeholder-black/65 text-xs 
                          sm:text-sm focus:outline-none"
                        aria-label="Search food products"
                        autoComplete="off"
                      />
                      <button
                        type="submit"
                        className=" px-6 py-3 bg-orange-dark/90 text-white text-xs sm:text-sm
                          transition-all duration-300 hover:bg-orange hover:shadow-[0_4px_16px_rgba(255,145,77,0.4)]
                          active:scale-95 shrink-0"
                      >
                        {t("searchButton")}
                      </button>
                    </div>

                    {/* Suggestions Dropdown */}
                    {isSearchFocused && searchSuggestions.length > 0 && (
                      <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl border 
                      border-gray-100 shadow-[0_12px_48px_rgba(0,0,0,0.15)] overflow-hidden z-50 animate-fade-in">
                        <div className="px-3 py-2 border-b border-gray-100">
                          <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{t("suggestions")}</span>
                        </div>
                        {searchSuggestions.map((p, i) => {
                          const change = p.currentPrice === 0 ? 0 : ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
                          const isUp = change >= 0;
                          return (
                            <Link
                              prefetch={false}
                              key={`${p.id}-${p.variant || 'std'}-${p.origin || 'loc'}-${i}`}
                              href={`/Product/${encryptId(p.id)}`}
                              className="flex items-center gap-3 px-4 py-3 hover:bg-primary-50/60 transition-colors duration-200 border-b border-gray-50 last:border-0"
                            >
                              <div className="relative w-12 h-12 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center text-xl shrink-0 overflow-hidden">
                                <Image
                                  src={p.image || DEFAULT_PRODUCT_IMAGE}
                                  alt={p.name}
                                  fill
                                  sizes="48px"
                                  className="object-cover"
                                  onError={(e) => {
                                    const target = e.target as HTMLImageElement;
                                    if (target.src !== DEFAULT_PRODUCT_IMAGE && target.srcset) {
                                      target.srcset = "";
                                    }
                                    if (target.src !== DEFAULT_PRODUCT_IMAGE) {
                                      target.src = DEFAULT_PRODUCT_IMAGE;
                                    }
                                  }}
                                />
                              </div>
                              <div className="flex-1 min-w-0 text-left">
                                <div className="text-sm font-semibold text-gray-900 truncate">
                                  {t(p.name)} {p.variant && p.variant !== "Standard" ? `(${p.variant})` : ""}
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] text-gray-400">{p.category}</span>
                                  {p.origin && (
                                    <>
                                      <span className="text-[10px] text-gray-200">•</span>
                                      <span className="text-[9px] font-bold text-primary-500 uppercase tracking-tight">{p.origin}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                              <div className="text-right shrink-0">
                                <div className="text-xs font-bold text-gray-900 tabular-nums">₱{p.currentPrice.toFixed(2)}</div>
                                <div className={`text-[10px] font-bold tabular-nums ${isUp ? "text-price-up" : "text-price-down"}`}>
                                  {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
                                </div>
                              </div>
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </form>
                </div>

                {/* Stats row */}
                <div className="animate-fade-in-up delay-500 grid grid-cols-3 gap-4 sm:gap-8 mt-10 max-w-lg">
                  {[
                    {
                      value: `${products.length}`,
                      label: t("productsTracked"),
                      detail: undefined,
                      period: undefined,
                      title: undefined,
                    },
                    {
                      value: predictionSuccess != null
                        ? `${predictionSuccess.toFixed(1)}%`
                        : "—",
                      label: t("modelAccuracy"),
                      detail: undefined,
                      period: undefined,
                      title: t("predictionSuccessExplanation"),
                    },
                    {
                      value: formatRelativeAge(forecastStatus?.generatedAt, language, now)
                        ?? forecastStatus?.metrics?.processed_through
                        ?? "—",
                      label: t("dataUpdates"),
                      detail: undefined,
                      period: undefined,
                      title: undefined,
                    },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      title={stat.title}
                      className="transition-transform duration-300 transform hover:scale-105"
                    >
                      <div className="text-sm sm:text-xl text-accent-dark">{stat.value}</div>
                      <div className="text-white/40 text-xs sm:text-sm mt-1">{stat.label}</div>
                      {stat.detail && <div className="text-white/35 text-[9px] leading-tight mt-1">{stat.detail}</div>}
                      {stat.period && <div className="text-white/30 text-[8px] leading-tight mt-0.5">{stat.period}</div>}
                    </div>
                  ))}
                </div>
              </div>

              {/* Right: Mini Forecast Dashboard */}
              <div className="hidden lg:block relative h-[520px] animate-fade-in-up delay-300">
                {/* Main Dashboard Card */}
                <div
                  className="absolute top-0 right-0 w-[380px] bg-primary-800/90 backdrop-blur-3xl rounded-3xl border border-white/12 shadow-[0_24px_64px_rgba(0,0,0,0.35)] overflow-hidden"
                  style={{ animation: "float 6s ease-in-out 0.5s infinite" }}
                >
                  {/* Dashboard Header */}
                  <div className="px-5 pt-5 pb-2">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                        <span className="text-[11px] font-semibold text-white/70 tracking-wide uppercase">{t("marketPulse")}</span>
                      </div>
                      <span className="text-[10px] text-white/50 tabular-nums">{t("ncrRegion")}</span>
                    </div>
                    {/* Selected product info */}
                    {dailyMovers[selectedProductIdx] && (() => {
                      const sp = dailyMovers[selectedProductIdx];
                      const change = sp.currentPrice ? ((sp.predictedPrice - sp.currentPrice) / sp.currentPrice * 100) : 0;
                      const isUp = change > 0;
                      return (
                        <div className="flex items-center justify-between">
                          <span className="text-[13px] font-bold text-white truncate max-w-[190px]">
                            {sp.variant && sp.variant !== "Standard" ? `${sp.name} (${sp.variant})` : sp.name}
                          </span>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className="text-[13px] font-bold text-accent tabular-nums">₱{sp.currentPrice.toFixed(0)}</span>
                            <span className={`text-[10px] font-bold tabular-nums ${isUp ? "text-price-up" : "text-price-down"}`}>
                              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Chart for selected product */}
                  {(() => {
                    const sp = dailyMovers[selectedProductIdx];
                    if (!sp) return null;
                    // Build a 7-point sparkline interpolating currentPrice -> predictedPrice
                    const STEPS = 7;
                    const pts7 = Array.from({ length: STEPS }, (_, i) => {
                      const t = i / (STEPS - 1);
                      // Add slight natural noise so the line isn't perfectly straight
                      const noise = i > 0 && i < STEPS - 1 ? (Math.sin(i * 1.9) * 0.012 * sp.currentPrice) : 0;
                      return sp.currentPrice + (sp.predictedPrice - sp.currentPrice) * t + noise;
                    });
                    const splitIdx = 4; // first 5 = actual, last 3 = predicted (overlap at splitIdx)
                    const minP = Math.min(...pts7) * 0.97;
                    const maxP = Math.max(...pts7) * 1.03;
                    const W = 300, H = 72, pad = 10;
                    const toX = (i: number) => pad + (i / (STEPS - 1)) * (W - pad * 2);
                    const toY = (v: number) => H - pad - ((v - minP) / (maxP - minP || 1)) * (H - pad * 2);
                    const coordPts = pts7.map((v, i) => ({ x: toX(i), y: toY(v), v }));
                    const actualPath = coordPts.slice(0, splitIdx + 1).map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
                    const predPath = coordPts.slice(splitIdx).map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
                    const areaPath = `${actualPath} L${coordPts[splitIdx].x},${H} L${coordPts[0].x},${H} Z`;
                    return (
                      <div className="px-5 pb-2">
                        <div
                          className="relative rounded-xl bg-white/5 border border-white/8 overflow-visible"
                          style={{ height: 96 }}
                          onMouseLeave={() => setHoveredChartPt(null)}
                        >
                          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" preserveAspectRatio="none" style={{ cursor: "crosshair" }}>
                            <defs>
                              <linearGradient id="heroChartGradSel" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#7ED957" stopOpacity="0.22" />
                                <stop offset="100%" stopColor="#7ED957" stopOpacity="0" />
                              </linearGradient>
                            </defs>
                            <path d={areaPath} fill="url(#heroChartGradSel)" />
                            <path d={predPath} fill="none" stroke="#FFB74D" strokeWidth="1.8" strokeDasharray="5 3" strokeLinecap="round" opacity="0.7" />
                            <path d={actualPath} fill="none" stroke="#7ED957" strokeWidth="2.2" strokeLinecap="round" />
                            {/* Forecast divider */}
                            <line x1={toX(splitIdx).toFixed(1)} y1="4" x2={toX(splitIdx).toFixed(1)} y2={H - 2} stroke="white" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.2" />
                            <text x={(toX(splitIdx) + 4).toFixed(1)} y="12" fill="white" fillOpacity="0.35" fontSize="6.5" fontFamily="Inter, sans-serif">Forecast →</text>
                            {/* Dots for all 7 points */}
                            {coordPts.map((pt, i) => (
                              <g key={i}>
                                <circle cx={pt.x} cy={pt.y} r={12} fill="transparent" onMouseEnter={() => setHoveredChartPt(i)} />
                                <circle
                                  cx={pt.x} cy={pt.y}
                                  r={hoveredChartPt === i ? 4 : 2.5}
                                  fill={i <= splitIdx ? "#7ED957" : "#FFB74D"}
                                  opacity={hoveredChartPt === i ? 1 : 0.75}
                                  style={{ transition: "r 0.12s ease" }}
                                />
                                {hoveredChartPt === i && <circle cx={pt.x} cy={pt.y} r={8} fill={i <= splitIdx ? "#7ED957" : "#FFB74D"} opacity="0.18" />}
                              </g>
                            ))}
                          </svg>
                          {/* Hover tooltip */}
                          {hoveredChartPt !== null && coordPts[hoveredChartPt] && (() => {
                            const hpt = coordPts[hoveredChartPt];
                            const pctW = (hpt.x / W) * 100;
                            const isActual = hoveredChartPt <= splitIdx;
                            return (
                              <div
                                className="absolute pointer-events-none z-20"
                                style={{ bottom: "calc(100% + 4px)", left: `clamp(4px, ${pctW}%, calc(100% - 115px))`, transform: "translateX(-30%)" }}
                              >
                                <div className="bg-primary-900/95 backdrop-blur-md border border-white/15 rounded-xl px-3 py-2 shadow-lg min-w-[105px]">
                                  <div className="text-[9px] text-white/40 mb-0.5">{isActual ? t("actual") : t("predicted")} · Day {hoveredChartPt + 1}</div>
                                  <div className="text-[12px] font-bold text-accent tabular-nums">₱{hpt.v.toFixed(0)}</div>
                                </div>
                              </div>
                            );
                          })()}
                          {/* Y-axis labels */}
                          <div className="absolute top-1 left-1.5 text-[8px] text-white/30 tabular-nums">₱{Math.round(maxP)}</div>
                          <div className="absolute bottom-1 left-1.5 text-[8px] text-white/30 tabular-nums">₱{Math.round(minP)}</div>
                        </div>
                        <div className="flex items-center gap-4 mt-1.5">
                          <div className="flex items-center gap-1.5">
                            <div className="w-3 h-[2px] bg-accent rounded" />
                            <span className="text-[9px] text-white/35">{t("actual")}</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <div className="w-3 h-[2px] rounded" style={{ backgroundImage: "repeating-linear-gradient(90deg, #FFB74D 0, #FFB74D 3px, transparent 3px, transparent 6px)" }} />
                            <span className="text-[9px] text-white/35">{t("predicted")}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Product Rows — top daily movers, click to select */}
                  <div className="px-5 pb-4 space-y-2">
                    {dailyMovers.slice(0, 3).map((p, idx) => {
                      const change = ((p.predictedPrice - p.currentPrice) / p.currentPrice * 100);
                      const isUp = change > 0;
                      const isSelected = idx === selectedProductIdx;
                      return (
                        <button
                          key={`${p.id}-${p.variant || 'std'}-${idx}`}
                          onClick={() => { setSelectedProductIdx(idx); setHoveredChartPt(null); }}
                          className={`w-full flex items-center gap-3 p-2.5 rounded-xl border transition-all duration-200 text-left cursor-pointer ${isSelected
                            ? "bg-white/10 border-accent/40 shadow-[0_0_0_1px_rgba(126,217,87,0.25)]"
                            : "bg-white/4 border-white/5 hover:bg-white/8 hover:border-white/10"
                            }`}
                        >
                          <div className="relative w-10 h-10 rounded-lg bg-white/10 overflow-hidden flex items-center justify-center shrink-0 border border-white/10">
                            <Image
                              src={p.image || DEFAULT_PRODUCT_IMAGE}
                              alt={p.name}
                              fill
                              className="object-cover"
                              onError={(e) => {
                                const target = e.target as HTMLImageElement;
                                if (target.src !== DEFAULT_PRODUCT_IMAGE && target.srcset) {
                                  target.srcset = "";
                                }
                                if (target.src !== DEFAULT_PRODUCT_IMAGE) {
                                  target.src = DEFAULT_PRODUCT_IMAGE;
                                }
                              }}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={`text-xs font-semibold truncate transition-colors duration-200 ${isSelected ? "text-accent" : "text-white"}`}>
                              {p.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p.name}
                            </div>
                            <div className="text-[10px] text-white/30">{p.category}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-xs font-bold text-white tabular-nums">₱{p.currentPrice.toFixed(0)}</div>
                            <div className={`text-[10px] font-bold tabular-nums ${isUp ? "text-price-up" : "text-price-down"}`}>
                              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
                            </div>
                          </div>
                        </button>
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
                      <div className="text-xs font-bold text-white">{t("aiSmartSystem")}</div>
                      <div className="text-[10px] text-white/35">{t("activeLearning")}</div>
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

        {/* <WaveDivider from="#0B3D2E" to="#FDFBF7" /> */}

        {/* ─── Daily Market Moves + News ───────────────── */}
        <section className="mt-15 py-5 sm:py-10 bg-surface" aria-labelledby="market-heading">
          <div className="max-w-[1440px] mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex gap-5 items-stretch">

                {/* ── LEFT BOX: Daily Market Movers ── */}
                <div className="min-w-0 flex-[3] bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden flex flex-col">

                  {/* Box header with title + arrows */}
                  <div className="flex items-end justify-between px-5 pt-5 pb-0">
                    <div>
                      <h2
                        id="market-heading"
                        className="flex items-center gap-2 text-xl sm:text-2xl font-bold text-gray-900"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        <TrendingUp className="w-5 h-5 text-accent" />
                        {t("dailyMarketMovers")}
                      </h2>
                      <p className="text-gray-400 mt-0.5 text-xs">
                        {t("biggestPriceChanges")}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => scroll("left")}
                        className="p-1.5 rounded-xl bg-gray-50 border border-gray-200 text-gray-500
                          hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                        aria-label="Scroll left"
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => scroll("right")}
                        className="p-1.5 rounded-xl bg-gray-50 border border-gray-200 text-gray-500
                          hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                        aria-label="Scroll right"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Slider */}
                  <div
                    ref={sliderRef}
                    className="daily-movers-slider flex gap-3 sm:gap-4 overflow-x-auto p-5 scroll-pl-4 snap-x snap-mandatory scrollbar-hide flex-1"
                    aria-label="Product carousel"
                    role="region"
                    onMouseEnter={() => setIsPaused(true)}
                    onMouseLeave={() => setIsPaused(false)}
                    onTouchStart={() => setIsPaused(true)}
                    onTouchEnd={() => { setTimeout(() => setIsPaused(false), 5000); }}
                  >
                    {dailyMovers.map((p, i) => (
                      <div
                        key={`${p.id}-${p.variant || 'std'}-${p.origin || 'loc'}-${i}`}
                        className="snap-start shrink-0 w-[270px] sm:w-[310px] lg:w-[280px] xl:w-[310px]"
                        style={{ animationDelay: `${i * 80}ms` }}
                      >
                        <DailyMoverCard
                          id={p.id}
                          name={p.name}
                          category={p.category}
                          image={p.image}
                          currentPrice={p.currentPrice}
                          predictedPrice={p.predictedPrice}
                          forecastDate={p.forecastDate}
                          lastActualDate={p.lastActualDate}
                          forecastSource={p.forecastSource}
                          variant={p.variant}
                          origin={p.origin}
                          unit={p.unit}
                        />
                      </div>
                    ))}
                  </div>
                </div>

                {/* ── RIGHT BOX: Latest News & Updates ── */}
                <div className="hidden lg:flex flex-[1] flex-col">
                  <ScrollReveal delay={150} className="h-full flex flex-col">
                    <div
                      className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden flex flex-col h-full"
                      aria-labelledby="news-panel-heading"
                    >
                      {/* Header */}
                      <div className="px-5 pt-5 pb-4 border-b border-gray-100 shrink-0">
                        <h2
                          id="news-panel-heading"
                          className="text-xl font-bold text-gray-900 leading-tight"
                          style={{ fontFamily: 'var(--font-display)' }}
                        >
                          {t('latestNews') || 'Latest News & Updates'}
                        </h2>
                        <div className="flex items-center gap-2 mt-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                          <Link
                            href="/News"
                            className="text-[10px] font-semibold text-gray-400 hover:text-primary-700 transition-colors flex items-center gap-0.5"
                          >
                            {t('viewAllNews') || 'See more'}
                            <ChevronRight className="w-3 h-3" />
                          </Link>
                        </div>
                      </div>

                      {/* News list */}
                      <div className="divide-y divide-gray-100 overflow-hidden flex-1">
                        {newsList.slice(0, 4).map((item, i) => (
                          <div key={`${item.id}-${i}`} className="group">
                            <NewsCard {...item} _compact />
                          </div>
                        ))}
                      </div>

                      {/* Footer */}
                      <div className="px-5 py-3 border-t border-gray-100 bg-gray-50/60 shrink-0">
                        <Link
                          href="/News"
                          className="text-[10px] font-semibold text-gray-500 hover:text-primary-700 flex items-center gap-1 transition-colors"
                        >
                        {newsList.length > 4
                          ? `+${newsList.length - 4} more articles`
                            : 'View all news'}
                          <ChevronRight className="w-3 h-3" />
                        </Link>
                      </div>
                    </div>
                  </ScrollReveal>
                </div>

              </div>
            </ScrollReveal>
          </div>
        </section>


        {/* ─── Wave + What is FOODCAST ──────────────────── */}
        <div className="bg-surface ">
          <WaveDivider from="#FDFBF7" to="#0B3D2E" />
        </div>

        <section
          className="relative py-15 sm:py-28 bg-primary-800 overflow-hidden shadow-xl/30"
          aria-labelledby="about-heading"
        >
          <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden="true">
            <div className="absolute -top-24 -right-24 w-[500px] h-[500px] bg-accent/5 rounded-full blur-[120px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="text-center mb-10">
                <h2
                  id="about-heading"
                  className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {t("whatIsFoodcast")}{" "}
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                    FOODCAST
                  </span>
                  ?
                </h2>
                <p className="text-white/55 max-w-2xl mx-auto text-xs sm:text-base leading-relaxed">
                  {t("whatIsFoodcastDesc")}
                </p>
              </div>
            </ScrollReveal>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
              {[
                {
                  icon: <Brain className="w-5 h-5 sm:w-7 sm:h-7" />,
                  title: t("aiDrivenAnalysis"),
                  description: t("aiDrivenAnalysisDesc"),
                },
                {
                  icon: <TrendingUp className="w-5 h-5 sm:w-7 sm:h-7" />,
                  title: t("realTimeForecasting"),
                  description: t("realTimeForecastingDesc"),
                },
                {
                  icon: <BarChart3 className="w-5 h-5 sm:w-7 sm:h-7" />,
                  title: t("dataVisualization"),
                  description: t("dataVisualizationDesc"),
                },
              ].map((feature, i) => (
                <ScrollReveal key={feature.title} delay={i * 150} animation="fade-up" className="h-full">
                  <div className="group relative bg-primary-700/70 border border-white/10 rounded-2xl py-4 px-5 sm:p-7 transition-all duration-600 
                    hover:scale-105 flex flex-col h-full">
                    <div className="flex items-center gap-4 mb-4">
                      <div className="w-10 h-10 sm:w-14 sm:h-14 rounded-xl bg-accent/10 flex items-center justify-center text-accent shrink-0">
                        {feature.icon}
                      </div>
                      <h3
                        className="text-base sm:text-lg font-semibold text-white leading-tight"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        {feature.title}
                      </h3>
                    </div>
                    <p className="text-white/45 text-xs sm:text-sm leading-relaxed">
                      {feature.description}
                    </p>
                  </div>
                </ScrollReveal>
              ))}
            </div>
          </div>
        </section>

        {/* <WaveDivider from="#0B3D2E" to="#FDFBF7" /> */}

        {/* ─── CTA Banner ──────────────────────────────── */}
        <section className="mt-5 py-5 sm:py-10 lg:py-15 bg-surface">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal animation="scale-in">
              <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-[#096] via-[#bf7b16] to-[#ff984f] p-8 sm:p-12 lg:p-16">
                <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                  <div className="absolute -top-16 -right-16 w-80 h-80 bg-accent/10 rounded-full blur-[80px]" />
                  <div className="absolute -bottom-16 -left-16 w-60 h-60 bg-orange/8 rounded-full blur-[60px]" />
                </div>

                <div className="relative text-center">
                  <h2
                    className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {t("startForecastingToday")}
                  </h2>
                  <p className="text-white/90 max-w-lg mx-auto mb-10 text-sm sm:text-base">
                    {t("startForecastingDesc")}
                  </p>
                  <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                    <Link
                      href="/Predict"
                      className="px-8 py-3 bg-primary-800 text-white font-bold rounded-2xl text-sm
                        transition-all duration-300 shadow-[0_0_20px_rgba(38,92,15,0.4)]
                        hover:bg-primary-700 hover:shadow-[0_0_30px_rgba(38,92,15,0.6)]"
                    >
                      {t("exploreForecastsBtn")}
                    </Link>
                    <Link
                      href="/About"
                      className="px-8 py-3 bg-transparent border border-white/20 text-white font-semibold rounded-2xl text-sm
                        transition-all duration-300 hover:bg-white/25 hover:border-white/40"
                    >
                      {t("learnMore")}
                    </Link>
                  </div>
                </div>
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>
    </>
  );
}
