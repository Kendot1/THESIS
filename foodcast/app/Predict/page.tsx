"use client";
import { useState, useMemo, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search, TrendingUp, Filter, X, ArrowRight, ChevronLeft, ChevronRight, ArrowRightLeft, Sparkles, AlertCircle, Bookmark, Share2, Grid, List, MoreHorizontal, Flame } from "lucide-react";
import Header from "../component/Header";
import Footer from "../component/Footer";
import ProductCard from "../component/ProductCard";
import ForecastChart from "../component/ForecastChart";
import ScrollReveal from "../component/ScrollReveal";
import { products, categories } from "../lib/data";

function SearchPageContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [showAllRows, setShowAllRows] = useState(false);
  const allMarketsRef = useRef<HTMLElement>(null);
  const [featuredIndex, setFeaturedIndex] = useState(0);
  const [isHoveringFeatured, setIsHoveringFeatured] = useState(false);

  const featuredItems = useMemo(() => {
    return products.filter(p => p.sentiment === "Bullish").slice(0, 6);
  }, []);

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

  /* ─── Market Insights Logic ─────────────────── */
  const filtered = useMemo(() => {
    return products.filter((p) => {
      const matchCategory =
        selectedCategory === "All" || p.category === selectedCategory;
      const matchQuery =
        !query ||
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase());
      return matchCategory && matchQuery;
    });
  }, [query, selectedCategory]);

  /* ─── Layout Data Prep ────────────────────── */
  const featuredProduct = featuredItems[featuredIndex] || products[0];

  const majorChanges = useMemo(() => {
    return products
      .map(p => ({
        ...p,
        change: ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100
      }))
      .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
      .slice(0, 3);
  }, []);

  const trendingProductsSide = useMemo(() => {
    return products
      .filter(p => p.sentiment === "Bullish")
      .slice(0, 5);
  }, []);

  const visibleCount = (showAllRows || query) ? filtered.length : 25; // Show all if searching or expanded

  /* ─── Search Suggestions ────────────────────── */
  const searchSuggestions = useMemo(() => {
    if (!query || query.length < 1) return [];
    return products.filter(
      (p) =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase())
    ).slice(0, 5);
  }, [query]);

  return (
    <>
      <Header />
      <main id="main-content" className="bg-surface min-h-screen">

        {/* ─── Search Hero (Restored) ────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-12 sm:py-15 pt-28 sm:pt-30">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-0 right-1/4 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1 className="text-2xl sm:text-3xl lg:text-5xl font-bold text-white mb-3 sm:mb-4" style={{ fontFamily: "var(--font-display)" }}>
              Search <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">Products</span>
            </h1>
            <p className="text-white/50 max-w-xl mb-8 text-sm sm:text-base">
              Explore price forecasts for agri-fishery products across NCR markets
            </p>

            <div className="relative z-20 max-w-lg">
              <form role="search" aria-label="Search products" onSubmit={(e) => { e.preventDefault(); scrollToAllMarkets(); }}>
                <div className="flex items-center bg-white/60 border border-white/15 rounded-2xl overflow-hidden backdrop-blur-sm transition-all duration-300 focus-within:border-accent/50 focus-within:bg-white/95 focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                  <Search className="w-5 h-5 text-black/55 ml-4 shrink-0" aria-hidden="true" />
                  <input
                    type="text"
                    placeholder="Search for a product"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => setIsSearchFocused(true)}
                    onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                    className="flex-1 px-3 py-3 bg-transparent text-black placeholder-black/65 text-xs sm:text-sm focus:outline-none"
                    autoComplete="off"
                  />
                  <button type="submit" className="mr-2 px-6 py-2 bg-orange rounded-xl text-white text-xs sm:text-sm transition-all duration-300 hover:bg-orange-light hover:shadow-[0_4px_16px_rgba(255,145,77,0.4)] active:scale-95 shrink-0">
                    Search
                  </button>
                </div>
              </form>

              {isSearchFocused && searchSuggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl border border-gray-100 shadow-[0_12px_48px_rgba(0,0,0,0.15)] overflow-hidden z-50 animate-fade-in">
                  <div className="px-3 py-2 border-b border-gray-100">
                    <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Suggestions</span>
                  </div>
                  {searchSuggestions.map((p) => {
                    const change = p.currentPrice === 0 ? 0 : ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
                    const isUp = change >= 0;
                    return (
                      <Link key={p.id} href={`/Product/${p.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-primary-50/60 transition-colors duration-200 border-b border-gray-50 last:border-0">
                        <div className="w-10 h-10 rounded-lg overflow-hidden flex items-center justify-center shrink-0 border border-gray-100">
                          <img src={p.image} alt={p.name} className="w-full h-full object-cover" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-semibold text-gray-900 truncate">{p.name}</div>
                          <div className="text-[10px] text-gray-400">{p.category}</div>
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

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

          {/* ─── Top Section: Featured + Sidebars ─────── */}
          <section className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-10">

            {/* Featured Card (Previous Chart Design: White Background + Grid) */}
            <div
              onMouseEnter={() => setIsHoveringFeatured(true)}
              onMouseLeave={() => setIsHoveringFeatured(false)}
              className="lg:col-span-8 bg-white rounded-3xl overflow-hidden border border-gray-100 shadow-xl 
            flex flex-col group hover:shadow-2xl transition-all duration-500"
            >
              <div className="p-6 sm:p-8 flex-1 flex flex-col">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                  <div className="flex items-center gap-4">
                    <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl overflow-hidden border border-gray-100 shrink-0 bg-gray-50 p-1">
                      <img src={featuredProduct.image} alt={featuredProduct.name} className="w-full h-full object-cover rounded-xl" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 text-primary-600 text-[10px] uppercase font-bold mb-1">
                        <span>Featured Market Pulse</span>
                      </div>
                      <h2 className="text-xl sm:text-3xl font-bold text-gray-900 leading-tight">
                        {featuredProduct.name}
                      </h2>
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
                  <p className="text-gray-500  text-sm max-w-2xl line-clamp-2">
                    {featuredProduct.description}
                  </p>
                </div>

                {/* Retaining Previous Chart Design (with grid and legend) */}
                <div className="mt-2">
                  <ForecastChart data={featuredProduct.forecastData} showGrid={true} showLegend={true} />
                </div>
              </div>

              <div className="px-8 py-4 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400 font-medium ">
                <div className="flex gap-6">
                  <span>Forecast Updated Today</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-positive animate-pulse" />
                  Live Market Data
                </div>
              </div>

              {/* Carousel Pagination & Navigation */}
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
                    {featuredItems[(featuredIndex - 1 + featuredItems.length) % featuredItems.length]?.name}
                  </button>
                  <button
                    onClick={() => setFeaturedIndex((prev) => (prev + 1) % featuredItems.length)}
                    className="flex items-center gap-2 px-4 py-1.5 bg-white border border-gray-200 rounded-full text-xs font-bold text-gray-600 hover:border-primary-200 hover:text-primary-800 transition-all active:scale-95"
                  >
                    {featuredItems[(featuredIndex + 1) % featuredItems.length]?.name}
                    <ChevronRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>

            {/* Sidebars */}
            <div className="lg:col-span-4 flex flex-col gap-6">

              {/* Major Changes in Price */}
              <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    Major changes in price <ArrowRight className="w-3 h-3 text-primary-400" />
                  </h3>
                </div>
                <div className="space-y-6">
                  {majorChanges.map((p, i) => (
                    <Link key={p.id} href={`/Product/${p.id}`} className="flex items-start gap-4 group">
                      <span className="text-lg font-black text-gray-100 group-hover:text-primary-100 transition-colors leading-none">{i + 1}</span>
                      <div className="flex-1">
                        <h4 className="text-sm font-bold text-gray-800 group-hover:text-primary-800 transition-colors leading-tight mb-1 line-clamp-2">
                          {p.name} price swing of {Math.abs(p.change).toFixed(0)}%?
                        </h4>
                        <div className={`text-[10px] font-bold ${p.change >= 0 ? 'text-positive' : 'text-negative'} flex items-center gap-2`}>
                          <span className="px-2 py-0.5 bg-gray-50 rounded-md text-gray-500">Predicted</span>
                          <span className="flex items-center gap-1">
                            {p.change >= 0 ? '▲' : '▼'} {Math.abs(p.change).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>

              {/* Trending Products */}
              <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-shadow flex-1">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    Trending Products <ArrowRight className="w-3 h-3 text-primary-400" />
                  </h3>
                </div>
                <div className="space-y-4">
                  {trendingProductsSide.map((p, i) => (
                    <Link key={p.id} href={`/Product/${p.id}`} className="flex items-center justify-between group p-2 -mx-2 rounded-xl hover:bg-gray-50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg overflow-hidden border border-gray-100 shrink-0">
                          <img src={p.image} alt={p.name} className="w-full h-full object-cover" />
                        </div>
                        <span className="text-sm font-bold text-gray-700 group-hover:text-primary-800 transition-colors">{p.name}</span>
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

              <button
                onClick={scrollToAllMarkets}
                className="w-full py-4 bg-primary-900 hover:bg-primary-800 text-white font-bold rounded-2xl transition-all shadow-lg shadow-primary-900/10 text-sm active:scale-[0.98]"
              >
                Explore all markets
              </button>
            </div>
          </section>

          {/* ─── Bottom Section: All Markets ───────────── */}
          <ScrollReveal>
            <section ref={allMarketsRef} className="mt-12 scroll-mt-32 overflow-hidden">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mb-4">
                <div>
                  <h2 className="text-2xl lg:text-3xl font-black text-gray-900 mb-1">All Markets</h2>
                  <p className="text-sm text-gray-500">Comprehensive price forecasts for all commodities</p>
                </div>
              </div>

              {/* Category Tabs */}
              <div className="flex items-center gap-1 sm:gap-3 scrollbar-hide mb-3 pb-2 px-1 sm:mx-0 sm:px-0">
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-5 py-2 rounded-2xl text-[10px] sm:text-xs font-semibold transition-all whitespace-nowrap ${selectedCategory === cat
                      ? "bg-primary-900 text-white"
                      : "bg-white text-gray-500 border border-gray-100 hover:border-gray-300 hover:text-gray-700 shadow-sm"
                      }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                {filtered.slice(0, visibleCount).map((p) => (
                  <ProductCard
                    key={p.id}
                    id={p.id}
                    name={p.name}
                    emoji={p.emoji}
                    image={p.image}
                    category={p.category}
                    currentPrice={p.currentPrice}
                    predictedPrice={p.predictedPrice}
                    compact
                  />
                ))}
              </div>

              {!showAllRows && !query && filtered.length > 25 && (
                <div className="mt-16 text-center">
                  <button
                    onClick={() => setShowAllRows(true)}
                    className="group relative px-12 py-4 bg-white border border-gray-200 rounded-2xl font-black text-gray-900 hover:border-accent hover:text-accent transition-all duration-300 shadow-sm hover:shadow-xl overflow-hidden"
                  >
                    <span className="relative z-10 flex items-center gap-2">
                      Load More Markets <MoreHorizontal className="w-5 h-5" />
                    </span>
                    <div className="absolute inset-0 bg-accent/5 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
                  </button>
                </div>
              )}
            </section>
          </ScrollReveal>

        </div>
      </main>
      <Footer />
    </>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface flex items-center justify-center"><div className="w-8 h-8 border-3 border-accent border-t-transparent rounded-full animate-spin" /></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
