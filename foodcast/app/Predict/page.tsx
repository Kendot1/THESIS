"use client";
import { useState, useMemo, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search, TrendingUp, Filter, X, ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
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
  const [featuredProduct, setFeaturedProduct] = useState(products[0]);
  const [isSearchFocused, setIsSearchFocused] = useState(false);

  /* ─── Predictive search suggestions ─────────── */
  const searchSuggestions = useMemo(() => {
    if (!query || query.length < 1) return [];
    return products.filter(
      (p) =>
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase())
    ).slice(0, 5);
  }, [query]);

  /* ─── All Products slider state ──────────────── */
  const allProductsRef = useRef<HTMLDivElement>(null);
  const [allCanLeft, setAllCanLeft] = useState(false);
  const [allCanRight, setAllCanRight] = useState(true);

  const checkAllScroll = () => {
    const el = allProductsRef.current;
    if (!el) return;
    setAllCanLeft(el.scrollLeft > 10);
    setAllCanRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  const scrollAll = (dir: "left" | "right") => {
    const el = allProductsRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 200 : 260;
    el.scrollBy({ left: dir === "left" ? -cardWidth : cardWidth, behavior: "smooth" });
  };

  useEffect(() => {
    checkAllScroll();
    const el = allProductsRef.current;
    if (el) el.addEventListener("scroll", checkAllScroll, { passive: true });
    return () => el?.removeEventListener("scroll", checkAllScroll);
  }, []);

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

  const trendingProducts = products
    .filter((p) => p.sentiment === "Bullish")
    .slice(0, 4);

  return (
    <>
      <Header />
      <main id="main-content">
        {/* ─── Search Hero ─────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-12 sm:py-15 pt-28 sm:pt-30">
          <div
            className="absolute inset-0 pointer-events-none"
            aria-hidden="true"
          >
            <div className="absolute top-0 right-1/4 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1
              className="text-2xl sm:text-3xl lg:text-5xl font-bold text-white mb-3 sm:mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Search{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                Products
              </span>
            </h1>
            <p className="text-white/50 max-w-xl mb-6 sm:mb-8 text-sm sm:text-base">
              Explore price forecasts for agri-fishery products across NCR
              markets
            </p>

            {/* Search Input */}
            <div className="animate-fade-in-up delay-300 min-w-[200px]">
              <div className="relative max-w-lg">
                <form
                  role="search"
                  aria-label="Search products"
                  onSubmit={(e) => e.preventDefault()}
                >
                  <div className="flex items-center bg-white/60 border border-white/15 rounded-2xl 
                      overflow-hidden backdrop-blur-sm transition-all duration-300 
                      focus-within:border-accent/50 focus-within:bg-white/95 
                      focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                    <Search
                      className="w-5 h-5 text-black/55 ml-4 shrink-0"
                      aria-hidden="true"
                    />
                    <input
                      type="text"
                      placeholder="Search for a product"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onFocus={() => setIsSearchFocused(true)}
                      onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}
                      className="flex-1 px-3 py-3 bg-transparent text-black 
                      placeholder-black/65 text-xs sm:text-sm focus:outline-none"
                      aria-label="Search products"
                      id="search-input"
                      autoComplete="off"
                    />
                    <button
                      type="submit"
                      className="mr-2 px-6 py-2 bg-orange rounded-xl text-white text-xs sm:text-sm
                            transition-all duration-300 hover:bg-orange-light hover:shadow-[0_4px_16px_rgba(255,145,77,0.4)]
                            active:scale-95 shrink-0"
                    >
                      Search
                    </button>
                  </div>
                </form>

                {/* Predictive search backdrop + dropdown */}
                {isSearchFocused && searchSuggestions.length > 0 && (
                  <>
                    {/* Dropdown */}
                    <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-2xl border 
                    border-gray-100 shadow-[0_12px_48px_rgba(0,0,0,0.15)] overflow-hidden z-50 animate-fade-in">
                      <div className="px-3 py-2 border-b border-gray-100">
                        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Suggestions</span>
                      </div>
                      {searchSuggestions.map((p) => {
                        const change = p.currentPrice === 0 ? 0 : ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
                        const isUp = change >= 0;
                        return (
                          <Link
                            key={p.id}
                            href={`/Product/${p.id}`}
                            className="flex items-center gap-3 px-4 py-3 hover:bg-primary-50/60 transition-colors duration-200 border-b border-gray-50 last:border-0"
                          >
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center text-lg shrink-0">
                              {p.emoji}
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
                  </>
                )}
              </div>
            </div>
          </div>
        </section>

        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 py-8 sm:py-10 lg:py-14 overflow-hidden">
          <div className="grid lg:grid-cols-[1fr_320px] gap-6 lg:gap-8 min-w-0">
            {/* ─── Main Content ──────────────────────────── */}
            <div className="min-w-0 overflow-hidden -z-10">
              {/* Featured Chart — responsive height */}
              <ScrollReveal>
                <div className="bg-white overflow-hidden rounded-2xl border border-gray-100 py-4 pb-10 sm:py-10 px-4 sm:px-7 mb-6 sm:mb-8 shadow-sm">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-1 mb-4 sm:mb-6">
                    <div>
                      <div className="flex items-center gap-2 sm:gap-3 mb-1">
                        <span className="text-xl sm:text-2xl">{featuredProduct.emoji}</span>
                        <h2
                          className="text-sm sm:text-base font-bold text-gray-900"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          {featuredProduct.name}
                        </h2>
                        <span className="text-[10px] sm:text-xs font-medium text-primary-600 bg-primary-50 px-2 sm:px-2 py-0.5 rounded-full">
                          {featuredProduct.category}
                        </span>
                      </div>
                      <p className="text-gray-500 text-xs">Price Market Forecast</p>
                    </div>
                    <div className="text-left sm:text-right">
                      <div className="text-lg sm:text-xl font-bold text-gray-900">
                        ₱{featuredProduct.currentPrice.toFixed(2)}
                      </div>
                      <div
                        className={`text-xs sm:text-sm font-medium ${featuredProduct.predictedPrice >=
                          featuredProduct.currentPrice
                          ? "text-positive"
                          : "text-negative"
                          }`}
                      >
                        {featuredProduct.predictedPrice >=
                          featuredProduct.currentPrice
                          ? "▲"
                          : "▼"}{" "}
                        ₱{featuredProduct.predictedPrice.toFixed(2)} predicted
                      </div>
                    </div>
                  </div>

                  {/* Responsive chart: smaller on mobile/tablet, larger on desktop */}
                  {/* Mobile */}
                  <div className="block sm:hidden ">
                    <ForecastChart
                      data={featuredProduct.forecastData}

                      showGrid
                      showLegend
                    />
                  </div>
                  {/* Tablet */}
                  <div className="hidden sm:block lg:hidden">
                    <ForecastChart
                      data={featuredProduct.forecastData}
                      height={200}
                      showGrid
                      showLegend
                    />
                  </div>
                  {/* Desktop */}
                  <div className="hidden lg:block">
                    <ForecastChart
                      data={featuredProduct.forecastData}
                      height={280}
                      showGrid
                      showLegend
                    />
                  </div>
                </div>
              </ScrollReveal>
            </div>

            {/* ─── Trending Sidebar ──────────────────────── */}
            <aside className="hidden lg:block" aria-label="Trending products">
              <div className="sticky top-0">
                <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                  <div className="flex items-center gap-2 mb-5">
                    <TrendingUp className="w-4 h-4 text-accent" />
                    <h3
                      className="text-sm font-bold text-gray-900"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      Trending Now
                    </h3>
                  </div>
                  <div className="space-y-3">
                    {trendingProducts.map((p, i) => (
                      <button
                        key={p.id}
                        onClick={() => setFeaturedProduct(p)}
                        className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-250 text-left ${featuredProduct.id === p.id
                          ? "bg-primary-50 border border-primary-100"
                          : "hover:bg-gray-50"
                          }`}
                      >
                        <span className="text-xl">{p.emoji}</span>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {p.name}
                          </div>
                          <div className="text-xs text-gray-500">
                            ₱{p.currentPrice.toFixed(2)}
                          </div>
                        </div>
                        <span
                          className={`text-xs font-semibold ${p.predictedPrice >= p.currentPrice
                            ? "text-positive"
                            : "text-negative"
                            }`}
                        >
                          {p.predictedPrice >= p.currentPrice ? "▲" : "▼"}
                          {Math.abs(
                            ((p.predictedPrice - p.currentPrice) /
                              p.currentPrice) *
                            100
                          ).toFixed(1)}
                          %
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </aside>
          </div>

          {/* ─── All Products (Trending-style layout) ── */}
          {selectedCategory === "All" && !query && (
            <>
              <ScrollReveal>
                <div className="flex items-end justify-between mt-10 sm:mt-15 mb-5 sm:mb-6">
                      <h3
                        className="text-lg sm:text-xl lg:text-2xl font-bold text-gray-900"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        Suggested Products
                      </h3>
                      <div className="flex items-center gap-2">
                        {/* Arrow buttons */}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => scrollAll("left")}
                            disabled={!allCanLeft}
                            className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                              disabled:opacity-30 disabled:cursor-not-allowed
                              hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                            aria-label="Scroll left"
                          >
                            <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                          </button>
                          <button
                            onClick={() => scrollAll("right")}
                            disabled={!allCanRight}
                            className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                              disabled:opacity-30 disabled:cursor-not-allowed
                              hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                            aria-label="Scroll right"
                          >
                            <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                          </button>
                        </div>
                        <Link
                          href="/Table"
                          className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                        >
                          View All <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                        </Link>
                      </div>
                    </div>
                  </ScrollReveal>

                  {/* Single-row horizontal slider (all breakpoints) */}
                  <div
                    ref={allProductsRef}
                    className="flex gap-3 sm:gap-4 overflow-x-auto pb-4 snap-x snap-mandatory scrollbar-hide"
                    aria-label="Suggested products slider"
                    role="region"
                  >
                    {products.slice(0, 10).map((p) => (
                      <div
                        key={p.id}
                        className="snap-start shrink-0 w-[180px] sm:w-[220px] lg:w-[240px]"
                        onClick={() => setFeaturedProduct(p)}
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
                </>
              )}

              {/* ─── Filtered Product Grid ─────────────────── */}
              {(selectedCategory !== "All" || query) && (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-4 lg:gap-5 w-full">
                    {filtered.map((p, i) => (
                      <ScrollReveal key={p.id} delay={i * 60} animation="fade-up">
                        <div onClick={() => setFeaturedProduct(p)} className="cursor-pointer min-w-0 overflow-hidden">
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
                        </div>
                      </ScrollReveal>
                    ))}
                  </div>

                  {filtered.length === 0 && (
                    <div className="text-center py-16 sm:py-20">
                      <div className="text-4xl sm:text-5xl mb-4">🔍</div>
                      <h3 className="text-base sm:text-lg font-semibold text-gray-700 mb-2">
                        No products found
                      </h3>
                      <p className="text-gray-500 text-xs sm:text-sm">
                        Try adjusting your search or category filters
                      </p>
                    </div>
                  )}
                </>
              )}
        </div>
      </main>

      <Footer />
    </>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface flex items-center justify-center">
          <div className="w-8 h-8 border-3 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
