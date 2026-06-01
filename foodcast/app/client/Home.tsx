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
  ArrowRight,
} from "lucide-react";
import WaveDivider from "../components/WaveDivider";
import ProductCard from "../components/ProductCard";
import DailyMoverCard from "../components/DailyMoverCard";
import NewsCard from "../components/NewsCard";
import ScrollReveal from "../components/ScrollReveal";
import { DEFAULT_PRODUCT_IMAGE, Product, NewsArticle } from "../lib/data";
import { useProducts, useNews, useTrendingInteractions } from "../lib/hooks";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { encryptId } from "../../lib/idCipher";

interface HomeProps {
  initialProducts: Product[];
  initialNews: NewsArticle[];
}

export default function Home({ initialProducts, initialNews }: HomeProps) {
  const { data: products = [], isLoading } = useProducts(initialProducts);
  const { data: newsList = [] } = useNews(10, initialNews);
  const { data: trendingInteractions } = useTrendingInteractions();
  const router = useRouter();
  const { t, isTransitioning } = useLanguage();

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

  /* ─── Trending slider state ─────────────────────── */
  const trendingRef = useRef<HTMLDivElement>(null);

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

  const trendingGrouped = useMemo(() => {
    const groupedMap = new Map<string, any>();
    
    // Sort products by user interactions
    const sortedProducts = [...products].sort((a, b) => {
        const viewsA = trendingInteractions?.[a.id] || 0;
        const viewsB = trendingInteractions?.[b.id] || 0;
        return viewsB - viewsA;
    });

    // Take top interacted products
    const trending = sortedProducts.slice(0, 4);
    
    trending.forEach(p => {
      if (!groupedMap.has(p.name)) {
        groupedMap.set(p.name, {
          name: p.name,
          category: p.category,
          image: p.image,
          unit: p.unit,
          variants: []
        });
      }
      groupedMap.get(p.name).variants.push({
        id: p.id,
        variant: p.variant,
        origin: p.origin,
        currentPrice: p.currentPrice,
        predictedPrice: p.predictedPrice
      });
    });
    return Array.from(groupedMap.values());
  }, [products, trendingInteractions]);

  /* ─── News slider state ─────────────────────────── */
  const newsRef = useRef<HTMLDivElement>(null);
  const [isNewsPaused, setIsNewsPaused] = useState(false);
  const newsAutoSlideTimer = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const scrollTrending = (dir: "left" | "right") => {
    const el = trendingRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 200 : 260;

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
        <section className="relative min-h-[85vh] flex items-center shadow-xl/20">          {/* Ambient orbs */}
          {/* Background Image */}
          <div className="absolute inset-0 -z-10 overflow-hidden">
            <Image
              src="/Bg-2.jpg"
              alt="background"
              fill
              priority
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
                    <div className="flex items-center bg-white/85 border border-white/15 rounded-2xl 
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
                                <div className={`text-[10px] font-bold tabular-nums ${isUp ? "text-positive" : "text-negative"}`}>
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
                <div className="animate-fade-in-up delay-500 flex flex-wrap gap-8 mt-10">
                  {[
                    { value: `${products.length}`, label: t("productsTracked") },
                    { value: "98.5%", label: t("predictionSuccess") },
                    { value: "Real-time", label: t("dataUpdates") },
                  ].map((stat) => (
                    <div
                      key={stat.label}
                      className="transition-transform duration-300 transform hover:scale-105"
                    >
                      <div className="text-sm sm:text-xl text-accent-dark">{stat.value}</div>
                      <div className="text-white/40 text-xs sm:text-sm mt-1">{stat.label}</div>
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
                  <div className="px-5 pt-5 pb-3">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                        <span className="text-[11px] font-semibold text-white/70 tracking-wide uppercase">{t("marketPulse")}</span>
                      </div>
                      <span className="text-[10px] text-white/50 tabular-nums">{t("ncrRegion")}</span>
                    </div>
                  </div>

                  {/* Mini Sparkline Chart Area */}
                  <div className="px-5 pb-3">
                    <div className="relative h-[100px] w-full rounded-xl bg-white/8 border border-white/6 overflow-hidden">
                      {/* SVG mini chart */}
                      <svg viewBox="0 0 300 80" className="w-full h-full" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="heroChartGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#265c0fff" stopOpacity="0.25" />
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
                          stroke="orange"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                        />
                        {/* Predicted dashed line */}
                        <path
                          d="M180,35 T240,28 T300,22"
                          fill="none"
                          stroke="#FFB74D"
                          strokeWidth="2"
                          strokeDasharray="6 4"
                          strokeLinecap="round"
                          opacity="0.6"
                        />
                        {/* Forecast divider */}
                        <line x1="180" y1="8" x2="180" y2="75" stroke="white" strokeWidth="0.5" strokeDasharray="3 3" opacity="0.2" />
                        <text x="185" y="14" fill="white" fillOpacity="0.4" fontSize="7" fontFamily="Inter, sans-serif">Forecast →</text>
                        {/* Dot at transition */}
                        <circle cx="180" cy="35" r="3" fill="#FF6900" />
                        <circle cx="180" cy="35" r="6" fill="#FF6900" opacity="0.2">
                          <animate attributeName="r" values="4;8;4" dur="2s" repeatCount="indefinite" />
                          <animate attributeName="opacity" values="0.3;0.05;0.3" dur="2s" repeatCount="indefinite" />
                        </circle>
                      </svg>
                      {/* Y-axis labels */}
                      <div className="absolute top-1 left-1.5 text-[8px] text-white/40 tabular-nums">₱55</div>
                      <div className="absolute bottom-1 left-1.5 text-[8px] text-white/40 tabular-nums">₱48</div>
                    </div>
                    <div className="flex items-center gap-4 mt-2">
                      <div className="flex items-center gap-1.5">
                        <div className="w-3 h-[2px] bg-accent rounded" />
                        <span className="text-[9px] text-white/35">{t("actual")}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-3 h-[2px] bg-accent/50 rounded" style={{ backgroundImage: "repeating-linear-gradient(90deg, #7ED957 0, #7ED957 3px, transparent 3px, transparent 6px)" }} />
                        <span className="text-[9px] text-white/35">{t("predicted")}</span>
                      </div>
                    </div>
                  </div>

                  {/* Product Rows */}
                  <div className="px-5 pb-4 space-y-2.5">
                    {products.slice(0, 3).map((p, idx) => {
                      const change = ((p.predictedPrice - p.currentPrice) / p.currentPrice * 100);
                      const isUp = change > 0;
                      return (
                        <div key={`${p.id}-${p.variant || 'std'}-${idx}`} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/4 border border-white/5 hover:bg-white/8 transition-all duration-300">
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
                            <div className="text-xs font-semibold text-white truncate">
                              {p.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p.name}
                            </div>
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
                      <div className="text-xs font-bold text-white">{t("aiSmartSystem")}</div>
                      <div className="text-[10px] text-white/35">{t("activeLearning")}</div>
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
                      <div className="text-xs font-bold text-white">{products.length} {t("products")}</div>
                      <div className="text-[10px] text-white/35">{t("trackedInNcr")}</div>
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

        {/* ─── Daily Market Moves ──────────────────────── */}
        <section className="mt-15 py-5 sm:py-10 bg-surface" aria-labelledby="market-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-2 sm:mb-4">
                <div>
                  <h2
                    id="market-heading"
                    className="flex items-center gap-2 text-xl sm:text-2xl lg:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    <TrendingUp className="w-5 h-5 sm:w-6 sm:h-6 text-accent" />
                    {t("dailyMarketMovers")}
                  </h2>
                  <p className="text-gray-500 mt-1 sm:mt-2 text-xs sm:text-sm">
                    {t("biggestPriceChanges")}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => scroll("left")}
                    className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll left"
                  >
                    <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                  </button>
                  <button
                    onClick={() => scroll("right")}
                    className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll right"
                  >
                    <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                  </button>
                </div>
              </div>
            </ScrollReveal>

            <div
              ref={sliderRef}
              className="daily-movers-slider flex gap-3 sm:gap-5 overflow-x-auto py-6 px-10 -mt-6 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
              aria-label="Product carousel"
              role="region"
              onMouseEnter={() => setIsPaused(true)}
              onMouseLeave={() => setIsPaused(false)}
              onTouchStart={() => setIsPaused(true)}
              onTouchEnd={() => {
                setTimeout(() => setIsPaused(false), 5000);
              }}
            >
              {dailyMovers.map((p, i) => (
                <div
                  key={`${p.id}-${p.variant || 'std'}-${p.origin || 'loc'}-${i}`}
                  className="snap-start shrink-0 w-[280px] sm:w-[calc(50%-10px)] lg:w-[calc(33.333%-14px)]"
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  <DailyMoverCard
                    id={p.id}
                    name={p.name}
                    category={p.category}
                    image={p.image}
                    currentPrice={p.currentPrice}
                    predictedPrice={p.predictedPrice}
                    forecastData={p.forecastData}
                    variant={p.variant}
                    origin={p.origin}
                    unit={p.unit}
                  />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Latest News Section ────────────────────── */}
        <section className="py-5 sm:py-10 bg-surface" aria-labelledby="news-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-4 sm:mb-8">
                <div>
                  <h2
                    id="news-heading"
                    className="text-xl sm:text-2xl lg:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    {t("latestNews")}
                  </h2>
                  <p className="text-gray-500 mt-1 sm:mt-2 text-xs sm:text-sm">
                    {t("newsSubtitle")}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => scrollNews("left")}
                    className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll news left"
                  >
                    <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                  </button>
                  <button
                    onClick={() => scrollNews("right")}
                    className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                      hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                    aria-label="Scroll news right"
                  >
                    <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                  </button>
                </div>
              </div>
            </ScrollReveal>

            <div
              ref={newsRef}
              className="news-slider flex gap-4 sm:gap-6 overflow-x-auto pt-6 pb-12 px-10 -mt-6 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
              onMouseEnter={() => setIsNewsPaused(true)}
              onMouseLeave={() => setIsNewsPaused(false)}
            >
              {newsList.map((item, i) => (
                <div
                  key={`${item.id}-${i}`}
                  className="snap-start shrink-0 w-[280px] sm:w-[350px]"
                  style={{ animationDelay: `${i * 100}ms` }}
                >
                  <NewsCard {...item} />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Trending Products ───────────────────────── */}
        {/* <section className="py-5 sm:py-10 bg-surface " aria-labelledby="trending-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-7">
            <ScrollReveal>
              <div className="flex items-end justify-between mb-5 sm:mb-8">
                <div>
                  <h2
                    id="trending-heading"
                    className="text-xl sm:text-2xl lg:text-3xl font-bold text-gray-900"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Trending Products
                  </h2>
                  <p className="text-gray-500 mt-1 sm:mt-2 text-xs sm:text-sm">
                    Most searched & active items this week
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex lg:hidden items-center gap-2">
                    <button
                      onClick={() => scrollTrending("left")}
                      className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                        hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                      aria-label="Scroll trending left"
                    >
                      <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                    <button
                      onClick={() => scrollTrending("right")}
                      className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                        hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                      aria-label="Scroll trending right"
                    >
                      <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                    </button>
                  </div>
                  <Link
                    href="/MarketData"
                    className="hidden sm:flex items-center gap-1.5 text-xs sm:text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                  >
                    View all <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  </Link>
                </div>
              </div>
            </ScrollReveal>

            <div
              ref={trendingRef}
              className="flex lg:hidden gap-3 sm:gap-4 overflow-x-auto pt-6 pb-12 px-10 -mt-6 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
              aria-label="Trending products slider"
              role="region"
            >
              {trendingGrouped.map((product, i) => (
                  <div
                    key={product.name}
                    className="snap-start shrink-0 w-[180px] sm:w-[240px]"
                  >
                    <ProductCard
                      name={product.name}
                      category={product.category}
                      image={product.image}
                      variants={product.variants}
                      unit={product.unit}
                      compact
                    />
                  </div>
                ))}
            </div>

            <div className="hidden lg:grid grid-cols-4 gap-6">
              {trendingGrouped.map((product, i) => (
                  <ScrollReveal key={product.name} delay={i * 100} animation="scale-in" className="h-full">
                    <ProductCard
                      name={product.name}
                      image={product.image}
                      category={product.category}
                      variants={product.variants}
                      unit={product.unit}
                    />
                  </ScrollReveal>
                ))}
            </div>

            <div className="flex sm:hidden justify-center mt-4">
              <Link
                href="/MarketData"
                className="flex items-center gap-1.5 text-xs font-medium text-primary-800 hover:text-accent transition-colors"
              >
                View all products <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </section> */}

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
        <section className="mt-20 py-5 sm:py-10 lg:py-15 bg-surface">
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
