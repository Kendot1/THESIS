"use client";
import { useState, useMemo, useRef, useEffect, Suspense, useDeferredValue } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { Search, TrendingUp, Filter, X, ArrowRight, ChevronLeft, ChevronRight, ArrowRightLeft, Sparkles, AlertCircle, Bookmark, Share2, Grid, List, MoreHorizontal, Flame, ChevronDown } from "lucide-react";
import ProductCard from "../components/ProductCard";
import dynamic from "next/dynamic";
const ForecastChart = dynamic(() => import("../components/ForecastChart"), {
  ssr: false,
});
import ScrollReveal from "../components/ScrollReveal";
import { Product, fetchCategories, DEFAULT_PRODUCT_IMAGE } from "../lib/data";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { encryptId } from "../../lib/idCipher";
import { useProducts } from "../lib/hooks";

interface PredictProps {
  initialProducts: Product[];
}

export default function Predict({ initialProducts }: PredictProps) {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface flex items-center justify-center"><div className="w-8 h-8 border-3 border-accent border-t-transparent rounded-full animate-spin" /></div>}>
      <PredictContent initialProducts={initialProducts} />
    </Suspense>
  );
}

function PredictContent({ initialProducts }: PredictProps) {
  const { t, isTransitioning } = useLanguage();
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const { data: products = [], isLoading } = useProducts(initialProducts);
  const [categories, setCategories] = useState<string[]>(["All"]);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [showAllRows, setShowAllRows] = useState(false);
  const [showMoreCategories, setShowMoreCategories] = useState(false);
  const [visibleCategoryCount, setVisibleCategoryCount] = useState(6);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const allMarketsRef = useRef<HTMLElement>(null);
  const [featuredIndex, setFeaturedIndex] = useState(0);
  const [isHoveringFeatured, setIsHoveringFeatured] = useState(false);

  // Swipe gesture support for mobile/touch screens
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.targetTouches[0].clientX;
    touchEndX.current = null;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    touchEndX.current = e.targetTouches[0].clientX;
  };

  const handleTouchEnd = () => {
    if (!touchStartX.current || !touchEndX.current || featuredItems.length <= 1) return;
    const diffX = touchStartX.current - touchEndX.current;
    const threshold = 50;

    if (diffX > threshold) {
      setFeaturedIndex((prev) => (prev + 1) % featuredItems.length);
    } else if (diffX < -threshold) {
      setFeaturedIndex((prev) => (prev - 1 + featuredItems.length) % featuredItems.length);
    }

    touchStartX.current = null;
    touchEndX.current = null;
  };

  useEffect(() => {
    fetchCategories().then((cats) => {
      setCategories(cats);
    });
  }, []);

  // Responsive visible categories
  useEffect(() => {
    const updateCount = () => {
      // Container width is window width minus the page padding (px-5 on mobile, px-10 on desktop)
      const padding = window.innerWidth >= 1024 ? 80 : 40;
      const containerWidth = Math.min(window.innerWidth, 1280) - padding;

      const moreButtonWidth = 100;
      const gapWidth = 8; // gap-2 = 8px
      const availableWidthForCats = containerWidth - moreButtonWidth;

      // The average category button width is smaller than 120px, closer to 90-100px including gaps.
      // So we divide by 95px to pack more buttons before breaking into "More"
      const estimatedCount = Math.floor(availableWidthForCats / 95);

      setVisibleCategoryCount(Math.max(2, estimatedCount));
    };

    updateCount();
    window.addEventListener('resize', updateCount);
    return () => window.removeEventListener('resize', updateCount);
  }, []);

  // Close category dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowMoreCategories(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const featuredItems = useMemo(() => {
    const uniqueMap = new Map();
    for (const p of products) {
      if (!uniqueMap.has(p.name)) {
        uniqueMap.set(p.name, p);
      } else if (p.sentiment === "Bullish" && uniqueMap.get(p.name).sentiment !== "Bullish") {
        uniqueMap.set(p.name, p);
      }
    }
    const uniqueProducts = Array.from(uniqueMap.values());

    return uniqueProducts
      .sort((a, b) => {
        const isBullishA = a.sentiment === "Bullish" ? 1 : 0;
        const isBullishB = b.sentiment === "Bullish" ? 1 : 0;
        if (isBullishA !== isBullishB) return isBullishB - isBullishA;

        const changeA = a.currentPrice ? ((a.predictedPrice - a.currentPrice) / a.currentPrice) * 100 : 0;
        const changeB = b.currentPrice ? ((b.currentPrice === 0 ? 0 : (b.predictedPrice - b.currentPrice) / b.currentPrice)) * 100 : 0;
        return changeB - changeA;
      })
      .slice(0, 6);
  }, [products]);

  useEffect(() => {
    if (isHoveringFeatured || featuredItems.length <= 1) return;

    const timer = setInterval(() => {
      setFeaturedIndex((prev) => (prev + 1) % featuredItems.length);
    }, 5000);

    return () => clearInterval(timer);
  }, [isHoveringFeatured, featuredItems.length]);

  const scrollToAllMarkets = () => {
    allMarketsRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const deferredQuery = useDeferredValue(query);
  const deferredCategory = useDeferredValue(selectedCategory);

  /* ─── Market Insights Logic ─────────────────── */
  const filtered = useMemo(() => {
    return products.filter((p) => {
      const matchCategory =
        deferredCategory === "All" || p.category === deferredCategory;
      const matchQuery =
        !deferredQuery ||
        p.name.toLowerCase().includes(deferredQuery.toLowerCase()) ||
        p.category.toLowerCase().includes(deferredQuery.toLowerCase()) ||
        (p.variant && p.variant.toLowerCase().includes(deferredQuery.toLowerCase())) ||
        (p.origin && p.origin.toLowerCase().includes(deferredQuery.toLowerCase()));
      return matchCategory && matchQuery;
    });
  }, [deferredQuery, deferredCategory, products]);

  /* ─── Layout Data Prep ────────────────────── */
  const featuredProduct = featuredItems[featuredIndex] || products[0] || null;



  const majorChanges = useMemo(() => {
    return products
      .map(p => ({
        ...p,
        change: ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100
      }))
      .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
      .slice(0, 3);
  }, [products]);

  const trendingProductsSide = useMemo(() => {
    const uniqueMap = new Map();
    for (const p of products) {
      if (!uniqueMap.has(p.name)) {
        uniqueMap.set(p.name, p);
      } else if (p.sentiment === "Bullish" && uniqueMap.get(p.name).sentiment !== "Bullish") {
        uniqueMap.set(p.name, p);
      }
    }
    const uniqueProducts = Array.from(uniqueMap.values());

    return uniqueProducts
      .sort((a, b) => {
        const isBullishA = a.sentiment === "Bullish" ? 1 : 0;
        const isBullishB = b.sentiment === "Bullish" ? 1 : 0;
        if (isBullishA !== isBullishB) return isBullishB - isBullishA;

        const changeA = a.currentPrice ? ((a.predictedPrice - a.currentPrice) / a.currentPrice) * 100 : 0;
        const changeB = b.currentPrice ? ((b.currentPrice === 0 ? 0 : (b.predictedPrice - b.currentPrice) / b.currentPrice)) * 100 : 0;
        return changeB - changeA;
      })
      .slice(0, 5);
  }, [products]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { All: products.length };
    products.forEach(p => {
      counts[p.category] = (counts[p.category] || 0) + 1;
    });
    return counts;
  }, [products]);

  const groupedProducts = useMemo(() => {
    const groupedMap = new Map<string, {
      name: string;
      category: string;
      image: string;
      unit: string;
      variants: {
        id: string;
        variant: string;
        origin: string;
        image: string;
        currentPrice: number;
        predictedPrice: number;
      }[];
    }>();

    filtered.forEach(p => {
      if (!groupedMap.has(p.name)) {
        groupedMap.set(p.name, {
          name: p.name,
          category: p.category,
          image: p.image,
          unit: p.unit,
          variants: []
        });
      }
      groupedMap.get(p.name)!.variants.push({
        id: p.id,
        variant: p.variant,
        origin: p.origin,
        image: p.image,
        currentPrice: p.currentPrice,
        predictedPrice: p.predictedPrice
      });
    });
    return Array.from(groupedMap.values());
  }, [filtered]);

  const visibleCount = (showAllRows || query) ? groupedProducts.length : 4;

  /* ─── Search Suggestions ────────────────────── */
  const searchSuggestions = useMemo(() => {
    if (!query || query.length < 1) return [];
    return products.filter(
      (p) =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase()) ||
        (p.variant && p.variant.toLowerCase().includes(query.toLowerCase()))
    ).slice(0, 5);
  }, [query, products]);

  if (products.length === 0 || isTransitioning) {
    return (
      <main className="min-h-screen bg-surface">
          <section className="relative py-12 sm:py-15 pt-28 sm:pt-30 bg-primary-900 overflow-hidden">
            <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
              <div className="h-10 sm:h-12 w-48 sm:w-64 bg-white/10 rounded-xl mb-4 animate-pulse" />
              <div className="h-4 w-64 sm:w-96 bg-white/5 rounded-lg mb-8 animate-pulse" />
              <div className="h-12 sm:h-14 max-w-lg bg-white/10 rounded-2xl animate-pulse" />
            </div>
          </section>

          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-10">
              <div className="lg:col-span-8 bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 flex flex-col min-h-[400px]">
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-16 h-16 sm:w-20 sm:h-20 bg-gray-100 rounded-2xl animate-pulse shrink-0" />
                  <div className="flex-1 space-y-3">
                    <div className="h-3 w-24 bg-gray-100 rounded-md animate-pulse" />
                    <div className="h-6 sm:h-8 w-32 sm:w-48 bg-gray-200 rounded-lg animate-pulse" />
                  </div>
                  <div className="w-20 sm:w-24 h-8 sm:h-10 bg-gray-100 rounded-xl animate-pulse hidden sm:block" />
                </div>
                <div className="space-y-2 mb-8">
                  <div className="h-3 w-full bg-gray-100 rounded-md animate-pulse" />
                  <div className="h-3 w-3/4 bg-gray-100 rounded-md animate-pulse" />
                </div>
                <div className="flex-1 bg-gray-50 rounded-2xl animate-pulse min-h-[200px]" />
              </div>

              <div className="lg:col-span-4 flex flex-col gap-6">
                <div className="bg-white rounded-3xl border border-gray-100 p-6 h-fit">
                  <div className="h-4 w-32 bg-gray-200 rounded-lg mb-6 animate-pulse" />
                  <div className="space-y-4">
                    {[1, 2, 3, 4, 5].map(i => (
                      <div key={i} className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-gray-100 animate-pulse shrink-0" />
                        <div className="flex-1 space-y-2">
                          <div className="h-3 w-24 bg-gray-200 rounded-md animate-pulse" />
                          <div className="h-2 w-16 bg-gray-100 rounded-md animate-pulse" />
                        </div>
                        <div className="h-3 w-10 bg-gray-100 rounded-md animate-pulse" />
                      </div>
                    ))}
                  </div>
                </div>
                <div className="h-12 w-full bg-gray-100 rounded-2xl animate-pulse" />
              </div>
            </section>

            <section className="mt-12">
              <div className="h-6 w-32 sm:w-48 bg-gray-200 rounded-xl mb-2 animate-pulse" />
              <div className="h-3 w-40 sm:w-64 bg-gray-100 rounded-lg mb-6 animate-pulse" />
              <div className="flex gap-2 mb-8 overflow-hidden">
                {[1, 2, 3, 4, 5, 6].map(i => (
                  <div key={i} className="h-10 w-20 sm:w-24 bg-gray-100 rounded-2xl animate-pulse shrink-0" />
                ))}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
                {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                  <div key={i} className="bg-white rounded-[1.5rem] sm:rounded-[2rem] border border-gray-100 p-3 sm:p-4 h-[220px] sm:h-[260px] flex flex-col">
                    <div className="h-24 sm:h-32 w-full bg-gray-100 rounded-xl sm:rounded-2xl mb-4 animate-pulse" />
                    <div className="h-4 sm:h-5 w-3/4 bg-gray-200 rounded-lg mb-2 animate-pulse" />
                    <div className="h-3 w-1/2 bg-gray-100 rounded-md mb-auto animate-pulse" />
                    <div className="flex justify-between items-end mt-4">
                      <div className="h-4 sm:h-5 w-12 sm:w-16 bg-gray-100 rounded-lg animate-pulse" />
                      <div className="h-6 sm:h-8 w-16 sm:w-20 bg-gray-100 rounded-xl animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
      </main>
    );
  }

  return (
    <>
      <main id="main-content" className="min-h-screen relative z-20">

        <section className="relative py-12 sm:py-15 pt-28 sm:pt-30">
          {/* Background Image */}
          <div className="absolute inset-0 -z-10">
            <Image
              src="/Bg-5.jpg"
              alt="background"
              fill
              priority
              className="object-cover blur-[1px]"
            />
            <div className="absolute inset-0 bg-primary-900/80" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1 className="text-2xl sm:text-3xl lg:text-5xl font-bold text-white mb-3 sm:mb-4" style={{ fontFamily: "var(--font-display)" }}>
              {t("searchProducts")}
            </h1>
            <p className="text-white/50 max-w-xl mb-8 text-sm sm:text-base">
              {t("exploreForecasts")}
            </p>

            <div className="relative z-20 max-w-lg">
              <form role="search" aria-label="Search products" onSubmit={(e) => { e.preventDefault(); scrollToAllMarkets(); }}>
                <div className="flex items-center bg-white/85 border border-white/15 rounded-2xl overflow-hidden backdrop-blur-sm transition-all duration-300 focus-within:border-accent/50 focus-within:bg-white/95 focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                  <Search className="w-5 h-5 text-black/55 ml-4 shrink-0" aria-hidden="true" />
                  <input
                    type="text"
                    placeholder={t("searchPlaceholder")}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => setIsSearchFocused(true)}
                    onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                    className="flex-1 px-3 py-3 bg-transparent text-black placeholder-black/65 text-xs sm:text-sm focus:outline-none"
                    autoComplete="off"
                  />
                  <button type="submit" className="mr-2 px-6 py-2 bg-orange rounded-xl text-white text-xs sm:text-sm transition-all duration-300 hover:bg-orange-light hover:shadow-[0_4px_16px_rgba(255,145,77,0.4)] active:scale-95 shrink-0">
                    {t("searchButton")}
                  </button>
                </div>
              </form>

              {isSearchFocused && searchSuggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl border border-gray-100 shadow-[0_12px_48px_rgba(0,0,0,0.15)] overflow-hidden z-50 animate-fade-in">
                  <div className="px-3 py-2 border-b border-gray-100">
                    <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{t("suggestions")}</span>
                  </div>
                  {searchSuggestions.map((p) => {
                    const change = p.currentPrice === 0 ? 0 : ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
                    const isUp = change >= 0;
                    return (
                      <Link prefetch={false} key={p.id} href={`/Product/${encryptId(p.id)}`} className="flex items-center gap-3 px-4 py-3 hover:bg-primary-50/60 transition-colors duration-200 border-b border-gray-50 last:border-0">
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
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-gray-900 truncate">
                            {p.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p.name}
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
            </div>
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-12">

          {/* ─── Top Section: Featured + Sidebars ─────── */}
          <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-10">

            {/* Featured Card (Previous Chart Design: White Background + Grid) */}
            <div
              onMouseEnter={() => setIsHoveringFeatured(true)}
              onMouseLeave={() => setIsHoveringFeatured(false)}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
              className="lg:col-span-8 bg-white rounded-3xl overflow-hidden border border-gray-100 shadow-xl 
                        flex flex-col group hover:shadow-2xl transition-all duration-500 md:cursor-grab md:active:cursor-grabbing select-none"
            >
              <div className="p-6 sm:p-8 flex-1 flex flex-col">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                  <div className="flex items-center gap-4">
                    <div className="relative w-16 h-16 sm:w-20 sm:h-20 bg-gray-50 rounded-2xl border border-gray-100 shadow-inner flex items-center justify-center text-3xl overflow-hidden">
                      <Image
                        src={featuredProduct.image || DEFAULT_PRODUCT_IMAGE}
                        alt={featuredProduct.name}
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
                    <div>
                      <div className="flex items-center gap-2 text-primary-600 text-[10px] uppercase font-bold mb-1">
                        <span>{t("featuredMarketPulse")}</span>
                      </div>
                      <h2 className="text-xl sm:text-3xl font-bold text-gray-900 leading-tight">
                        {featuredProduct.variant && featuredProduct.variant !== "Standard" ? `${featuredProduct.name} (${featuredProduct.variant})` : featuredProduct.name}
                      </h2>
                      {featuredProduct.origin && (
                        <div className="mt-1">
                          <span className="text-[10px] font-bold text-primary-400 uppercase tracking-widest bg-primary-50 px-2 py-0.5 rounded-md">
                            {featuredProduct.origin}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-row sm:flex-col items-center sm:items-end justify-between sm:justify-start gap-2 sm:gap-2">
                    <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] sm:text-xs font-bold ${featuredProduct.sentiment === 'Bullish' ? 'text-positive bg-positive/8' : 'text-negative bg-negative/8'}`}>
                      {featuredProduct.sentiment === 'Bullish' ? '▲' : '▼'} {Math.abs(((featuredProduct.predictedPrice - featuredProduct.currentPrice) / featuredProduct.currentPrice) * 100).toFixed(1)}% {featuredProduct.sentiment}
                    </div>
                    <span className="text-3xl sm:text-4xl font-black text-primary-900 leading-none">
                      ₱{featuredProduct.predictedPrice.toFixed(1)}
                    </span>
                  </div>
                </div>

                <div className="mb-4 text-wrap">
                  <p className="text-gray-500 text-sm max-w-2xl line-clamp-2">
                    {featuredProduct.description}
                  </p>
                </div>

                {/* Retaining Previous Chart Design (with grid and legend) */}
                <div className="mt-2">
                  <ForecastChart
                    data={featuredProduct.forecastData}
                    showGrid={true}
                    showLegend={true}
                    productName={featuredProduct.variant && featuredProduct.variant !== "Standard" ? `${featuredProduct.name} (${featuredProduct.variant})` : featuredProduct.name}
                  />
                </div>
              </div>

              <div className="px-8 py-4 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400 font-medium ">
                <div className="flex gap-6">
                  <span>{t("forecastUpdatedToday")}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-positive animate-pulse" />
                  {t("liveMarketData")}
                </div>
              </div>

              {/* Carousel Pagination & Navigation */}
              {featuredItems.length > 1 && (
                <div className="px-8 py-4 bg-gray-50/30 border-t border-gray-100 flex items-center justify-between">
                  <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide py-1 px-1 -mx-1">
                    {featuredItems.map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setFeaturedIndex(i)}
                        className={`h-1.5 rounded-full transition-all duration-500 shrink-0 ${featuredIndex === i ? "w-8 bg-primary-800" : "w-1.5 bg-gray-300"
                          }`}
                        aria-label={`Go to featured item ${i + 1}`}
                      />
                    ))}
                  </div>
                  <div className="flex items-center gap-3 hidden md:flex">
                    <button
                      onClick={() => setFeaturedIndex((prev) => (prev - 1 + featuredItems.length) % featuredItems.length)}
                      className="flex items-center gap-2 px-4 py-1.5 bg-white border border-gray-200 rounded-full 
                    text-xs font-bold text-gray-600 hover:border-primary-200 
                    hover:text-primary-800 transition-all active:scale-95"
                    >
                      <ChevronLeft className="w-3 h-3" />
                      {(() => {
                        const p = featuredItems[(featuredIndex - 1 + featuredItems.length) % featuredItems.length];
                        return p?.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p?.name;
                      })()}
                    </button>
                    <button
                      onClick={() => setFeaturedIndex((prev) => (prev + 1) % featuredItems.length)}
                      className="flex items-center gap-2 px-4 py-1.5 bg-white border border-gray-200 rounded-full text-xs font-bold text-gray-600 hover:border-primary-200 hover:text-primary-800 transition-all active:scale-95"
                    >
                      {(() => {
                        const p = featuredItems[(featuredIndex + 1) % featuredItems.length];
                        return p?.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p?.name;
                      })()}
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Sidebars */}
            <div className="lg:col-span-4 flex flex-col gap-6 self-start">

              {/* Major Changes in Price
              <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    Major changes in price
                  </h3>
                </div>
                <div className="space-y-6">
                  {majorChanges.map((p, i) => (
                    <Link prefetch={false} key={p.id} href={`/Product/${encryptId(p.id)}`} className="flex items-start gap-4 group">
                      <span className="text-lg font-black text-gray-100 group-hover:text-primary-100 transition-colors leading-none">{i + 1}</span>
                      <div className="flex-1">
                        <h4 className="text-sm font-bold text-gray-800 group-hover:text-primary-800 transition-colors leading-tight mb-1 line-clamp-2">
                          {p.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p.name} price swing of {Math.abs(p.change).toFixed(0)}%?
                        </h4>
                        <div className={`text-[10px] font-bold ${p.change >= 0 ? 'text-positive' : 'text-negative'} flex items-center gap-2`}>
                          <span className="px-2 py-0.5 bg-gray-50 rounded-md text-gray-500">Predicted</span>
                          <span className="flex items-center gap-1">
                            {p.change >= 0 ? '▲' : '▼'} {Math.abs(p.change).toFixed(1)}%
                          </span>
                        </div>
                        {p.origin && (
                          <div className="mt-1 text-[9px] font-bold text-primary-400/60 uppercase tracking-widest">
                            {p.origin}
                          </div>
                        )}
                      </div>
                    </Link>
                  ))}
                </div>
              </div> */}

              {/* Trending Products */}
              <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-shadow h-fit">
                <div className="mb-6">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    {t("trendingProducts")}
                  </h3>
                </div>
                <div className="space-y-4">
                  {trendingProductsSide.map((p, i) => (
                    <Link prefetch={false} key={p.id} href={`/Product/${encryptId(p.id)}`} className="flex items-center justify-between group p-2 -mx-2 rounded-xl hover:bg-gray-50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="relative w-8 h-8 rounded-lg overflow-hidden border border-gray-100 shrink-0">
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
                        <div className="flex flex-col">
                          <span className="text-sm font-bold text-gray-700 group-hover:text-primary-800 transition-colors line-clamp-1">
                            {p.variant && p.variant !== "Standard" ? `${p.name} (${p.variant})` : p.name}
                          </span>
                          {p.origin && (
                            <span className="text-[9px] font-medium text-gray-400 uppercase tracking-tight">{p.origin}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="text-[10px] font-bold text-gray-900">₱{p.currentPrice.toFixed(1)}</div>
                        </div>
                        <Flame className="w-3 h-3 text-orange fill-orange animate-bounce-subtle" />
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
              <Link href="/MarketData"
                className="block w-full max-h-13 py-4 bg-primary-900 hover:bg-primary-800 text-white text-center font-bold rounded-2xl transition-all shadow-lg shadow-primary-900/10 text-sm active:scale-[0.98]">
                {t("viewFullTable")}
              </Link>
            </div>
          </section>

          {/* ─── Bottom Section: All Markets ───────────── */}
          <ScrollReveal>
            <section ref={allMarketsRef} className="mt-12 scroll-mt-32 overflow-visible relative z-30">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mb-4">
                <div>
                  <h2 className="text-2xl lg:text-3xl font-black text-gray-900 mb-1">{t("allMarkets")}</h2>
                  <p className="text-sm text-gray-500">{t("comprehensivePriceForecasts")}</p>
                </div>
              </div>

              {/* Category Tabs with More Button */}
              <div className="relative mb-8 flex flex-nowrap items-center gap-2 w-full" ref={dropdownRef}>
                <div className="flex items-center gap-2 flex-nowrap shrink-0">
                  {categories.slice(0, visibleCategoryCount).map((cat) => {
                    const isActive = selectedCategory === cat;
                    const count = categoryCounts[cat] || 0;

                    return (
                      <button
                        key={cat}
                        onClick={() => setSelectedCategory(cat)}
                        className={`group flex items-center gap-1.5 px-5 py-3 rounded-2xl transition-all duration-300 whitespace-nowrap border ${isActive
                          ? "bg-primary-900 border-primary-900 text-white shadow-md shadow-primary-900/20 scale-105"
                          : "bg-white border-gray-100 text-gray-700 hover:border-primary-200 hover:bg-primary-50/30 hover:text-primary-800"
                          }`}
                      >
                        <span className="text-xs font-bold">{t(cat)}</span>
                        <span className={`text-[10px] font-medium opacity-60 ${isActive ? "text-white" : "text-gray-400"}`}>
                          ({count})
                        </span>
                      </button>
                    );
                  })}
                </div>

                {/* More Button */}
                {categories.length > visibleCategoryCount && (
                  <div className="relative shrink-0">
                    <button
                      onClick={() => setShowMoreCategories(!showMoreCategories)}
                      className={`flex items-center gap-1.5 px-5 py-3 rounded-2xl text-xs font-bold whitespace-nowrap transition-all duration-300 border ${categories.slice(visibleCategoryCount).includes(selectedCategory)
                        ? "bg-primary-900 border-primary-900 text-white shadow-md scale-105"
                        : "bg-white border-gray-100 text-gray-700 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-800"
                        }`}
                      aria-expanded={showMoreCategories}
                    >
                      {categories.slice(visibleCategoryCount).includes(selectedCategory) ? selectedCategory : "More"}
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-300 ${showMoreCategories ? "rotate-180" : ""}`} />
                    </button>

                    {/* Dropdown */}
                    {showMoreCategories && (
                      <div className="absolute top-full right-0 mt-2 w-56 bg-white rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.15)] border border-gray-100 py-2 z-[100] animate-fade-in origin-top-right">
                        {categories.slice(visibleCategoryCount).map((cat) => {
                          const isActive = selectedCategory === cat;
                          const count = categoryCounts[cat] || 0;
                          return (
                            <button
                              key={cat}
                              onClick={() => {
                                setSelectedCategory(cat);
                                setShowMoreCategories(false);
                              }}
                              className={`w-full flex items-center justify-between px-5 py-2.5 text-xs font-bold transition-colors hover:bg-gray-50
                                 ${isActive ? "text-primary-800 bg-primary-50/50" : "text-gray-600 hover:text-primary-800"}`}
                            >
                              <span>{t(cat)}</span>
                              <span className="text-[10px] opacity-60">({count})</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-6">
                {groupedProducts.slice(0, visibleCount).map((product, idx) => {
                  const bestVariant = product.variants.find((v: any) =>
                    deferredQuery && (
                      v.variant?.toLowerCase().includes(deferredQuery.toLowerCase()) ||
                      v.origin?.toLowerCase().includes(deferredQuery.toLowerCase())
                    )
                  ) || product.variants[0];

                  return (
                    <ProductCard
                      key={idx}
                      name={product.name}
                      image={product.image}
                      category={product.category}
                      variants={product.variants}
                      unit={product.unit}
                      initialVariantId={bestVariant.id}
                      compact
                    />
                  );
                })}
              </div>

              {!showAllRows && !query && groupedProducts.length > 4 && (
                <div className="mt-10 text-center">
                  <button
                    onClick={() => setShowAllRows(true)}
                    className="group relative px-10 py-4 bg-white border border-gray-200 rounded-[2rem] text-primary-900 font-black uppercase tracking-[0.2em] text-[10px] hover:text-white transition-all duration-500 overflow-hidden shadow-lg hover:shadow-primary-900/20 active:scale-95"
                  >
                    <span className="relative z-10 flex items-center gap-2">
                      {t("loadMore")} <MoreHorizontal className="w-5 h-5" />
                    </span>
                    <div className="absolute inset-0 bg-primary-900 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
                  </button>
                </div>
              )}
            </section>
          </ScrollReveal>

        </div>
      </main>
    </>
  );
}
