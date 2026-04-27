"use client";
import { useState, useMemo, useRef, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search, TrendingUp, Filter, X, ArrowRight, ChevronLeft, ChevronRight, ArrowRightLeft, Sparkles, AlertCircle } from "lucide-react";
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

  const marketInsights = useMemo(() => {
    if (!query || filtered.length === 0) return null;

    const bestMatch = filtered[0];
    const commonKeywords = ["Onion", "Garlic", "Rice", "Fish", "Tomato", "Cabbage"];
    const keyword = commonKeywords.find(k => bestMatch.name.includes(k));
    const variants = keyword
      ? products.filter(p => p.id !== bestMatch.id && p.name.includes(keyword))
      : [];

    const alternatives = bestMatch.sentiment === "Bullish"
      ? products.filter(p =>
        p.id !== bestMatch.id &&
        p.category === bestMatch.category &&
        p.sentiment !== "Bullish" &&
        !variants.some(v => v.id === p.id)
      )
        .sort((a, b) => a.currentPrice - b.currentPrice)
        .slice(0, 3)
      : [];

    if (variants.length === 0 && alternatives.length === 0) return null;

    return { bestMatch, variants, alternatives };
  }, [query, filtered]);

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

  const trendingProducts = useMemo(() => {
    return products
      .filter((p) => {
        const matchCategory = selectedCategory === "All" || p.category === selectedCategory;
        return matchCategory && p.sentiment === "Bullish";
      })
      .slice(0, 6);
  }, [selectedCategory]);

  const discoveryItems = useMemo(() => {
    return [
      products.find(p => p.id === 'premium-rice'),
      products.find(p => p.id === 'tomato'),
      products.find(p => p.id === 'garlic')
    ].filter((p): p is (typeof products)[0] => !!p);
  }, []);

  return (
    <>
      <Header />
      <main id="main-content" className="transition-all duration-300">
        {/* ─── Search Hero ─────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-12 sm:py-15 pt-28 sm:pt-30">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-0 right-1/4 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1 className="text-2xl sm:text-3xl lg:text-5xl font-bold text-white mb-3 sm:mb-4" style={{ fontFamily: "var(--font-display)" }}>
              Search <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">Products</span>
            </h1>
            <p className="text-white/50 max-w-xl mb-6 sm:mb-8 text-sm sm:text-base">
              Explore price forecasts for agri-fishery products across NCR markets
            </p>

            <div className="animate-fade-in-up delay-300 min-w-[200px] relative z-20">
              <div className="relative max-w-lg">
                <form role="search" aria-label="Search products" onSubmit={(e) => e.preventDefault()}>
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
                      aria-label="Search products"
                      id="search-input"
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
          </div>
        </section>

        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 py-10 lg:py-16">
          {/* ─── Discovery Section ──────────────────────── */}
          <ScrollReveal>
            {!query && selectedCategory === "All" && (
              <section className="mb-16">
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h2 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-2">Market Discovery</h2>
                    <p className="text-gray-500">Key commodities to watch today</p>
                  </div>
                </div>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                  {discoveryItems.map((p) => (
                    <ProductCard
                      key={p.id}
                      id={p.id}
                      name={p.name}
                      emoji={p.emoji}
                      image={p.image}
                      category={p.category}
                      currentPrice={p.currentPrice}
                      predictedPrice={p.predictedPrice}
                    />
                  ))}
                </div>
              </section>
            )}
          </ScrollReveal>



          {/* ─── Trending Now Section ───────────────────── */}
          <section className="mb-16">
            <ScrollReveal>
              <div className="flex items-center gap-3 mb-4">
                <div>
                  <h2 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-1">Trending Now</h2>
                  <p className="text-gray-500">Rising prices and market momentum</p>
                </div>
              </div>

              {/* ─── Category Navigation ────────────────────── */}
              <div className="border-b border-gray-100">
                <div className="max-w-7xl mx-auto px-2">
                  <div className="flex items-center gap-8 overflow-x-auto scrollbar-hide py-4 transition-all duration-300">
                    {["All", "Grains", "Vegetables", "Fishery", "Spices"].map((cat) => (
                      <button
                        key={cat}
                        onClick={() => setSelectedCategory(cat)}
                        className={`relative pb-4 text-sm font-semibold whitespace-nowrap transition-all duration-300 ${selectedCategory === cat ? "text-primary-800" : "text-gray-400 hover:text-gray-600"
                          }`}
                      >
                        {cat === "Fishery" ? "Seafood" : cat}
                        {selectedCategory === cat && (
                          <div className="absolute bottom-0 left-0 right-0 h-1 bg-accent rounded-full animate-scale-in" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid lg:grid-cols-2 gap-6">
                {trendingProducts.map((p) => {
                  const change = ((p.predictedPrice - p.currentPrice) / p.currentPrice) * 100;
                  return (
                    <Link key={p.id} href={`/Product/${p.id}`} className="group bg-white rounded-2xl border border-gray-100 p-6 flex flex-col sm:flex-row gap-6 hover:shadow-xl hover:border-accent/20 transition-all duration-300">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-4 mb-4">
                          <div className="w-12 h-12 rounded-xl overflow-hidden border border-gray-100 bg-gray-50 shrink-0">
                            <img src={p.image} alt={p.name} className="w-full h-full object-cover" />
                          </div>
                          <div>
                            <h3 className="font-bold text-gray-900 truncate">{p.name}</h3>
                            <p className="text-xs text-gray-400 uppercase tracking-widest">{p.category}</p>
                          </div>
                        </div>
                        <div className="flex items-start gap-5 mb-2">
                          <div>
                            <p className="text-[10px] text-gray-400 uppercase font-bold mb-1">Current</p>
                            <p className="text-lg font-bold text-gray-900">₱{p.currentPrice.toFixed(2)}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-gray-400 uppercase font-bold mb-1">Predicted</p>
                            <p className="text-lg font-bold text-positive">₱{p.predictedPrice.toFixed(2)}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-positive/8 rounded-lg w-fit">
                          <TrendingUp className="w-3 h-3 text-positive" />
                          <span className="text-xs font-bold text-positive">+{change.toFixed(1)}% Expected</span>
                        </div>
                      </div>

                      <div className="w-full sm:w-[350px] h-[135px] bg-gray-50 rounded-xl overflow-hidden border border-gray-100 group-hover:border-accent/10 transition-colors">
                        <ForecastChart data={p.forecastData} height={100} showGrid={false} showLegend={false} />
                      </div>
                    </Link>
                  );
                })}
              </div>
            </ScrollReveal>
          </section>

          {/* ─── Search Results / Insights ──────────────── */}
          <ScrollReveal>
            {(query || selectedCategory !== "All") && (
              <section className="mb-16">
                <div className="flex items-center justify-between mb-8">
                  <h2 className="text-xl lg:text-2xl font-bold text-gray-900">
                    {query ? `Results for "${query}"` : `${selectedCategory === "Fishery" ? "Seafood" : selectedCategory}`}
                  </h2>
                  <span className="text-sm text-gray-500">{filtered.length} items found</span>
                </div>

                {marketInsights && (
                  <div className="grid md:grid-cols-2 gap-6 mb-10">
                    {marketInsights.variants.length > 0 && (
                      <div className="bg-white rounded-3xl border border-gray-100 p-6 shadow-sm">
                        <div className="flex items-center gap-3 mb-4">
                          <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center text-primary-800">
                            <ArrowRightLeft className="w-4 h-4" />
                          </div>
                          <h3 className="text-sm font-bold text-gray-900" style={{ fontFamily: "var(--font-display)" }}>
                            Similar Types of {marketInsights.bestMatch.name}
                          </h3>
                        </div>
                        <div className="space-y-3">
                          {marketInsights.variants.map(v => (
                            <Link key={v.id} href={`/Product/${v.id}`} className="flex items-center justify-between p-3 rounded-xl border border-gray-50 hover:bg-gray-50 transition-colors">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg overflow-hidden border border-gray-100 shrink-0">
                                  <img src={v.image} alt={v.name} className="w-full h-full object-cover" />
                                </div>
                                <span className="text-xs font-medium text-gray-700">{v.name}</span>
                              </div>
                              <span className="text-xs font-bold text-gray-900">₱{v.currentPrice.toFixed(2)}</span>
                            </Link>
                          ))}
                        </div>
                      </div>
                    )}

                    {marketInsights.alternatives.length > 0 && (
                      <div className="bg-primary-900 rounded-3xl p-6 shadow-lg relative overflow-hidden">
                        <div className="absolute -top-6 -right-6 w-24 h-24 bg-accent/10 rounded-full blur-2xl" />
                        <div className="relative flex items-center gap-3 mb-4">
                          <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center text-accent">
                            <Sparkles className="w-4 h-4" />
                          </div>
                          <h3 className="text-sm font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
                            Recommended Alternatives
                          </h3>
                        </div>
                        <p className="relative text-[10px] text-white/60 mb-3">
                          Save costs by considering these options instead of <span className="text-accent">{marketInsights.bestMatch.name}</span>.
                        </p>
                        <div className="relative space-y-2">
                          {marketInsights.alternatives.map(a => (
                            <Link key={a.id} href={`/Product/${a.id}`} className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg overflow-hidden border border-white/10 shrink-0 bg-white/5">
                                  <img src={a.image} alt={a.name} className="w-full h-full object-cover" />
                                </div>
                                <span className="text-xs font-medium text-white">{a.name}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] font-bold text-accent">Best Value</span>
                                <ArrowRight className="w-3 h-3 text-white/40" />
                              </div>
                            </Link>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {filtered.length > 0 ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                    {filtered.map((p, i) => (
                      <ScrollReveal key={p.id} delay={i * 60} animation="fade-up">
                        <ProductCard id={p.id} name={p.name} emoji={p.emoji} image={p.image} category={p.category} currentPrice={p.currentPrice} predictedPrice={p.predictedPrice} compact />
                      </ScrollReveal>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-20 bg-gray-50 rounded-3xl border border-dashed border-gray-200">
                    <div className="text-4xl mb-4">🔍</div>
                    <h3 className="text-lg font-bold text-gray-900">No products found</h3>
                    <p className="text-gray-500">Try adjusting your search or filters</p>
                  </div>
                )}
              </section>
            )}
          </ScrollReveal>

          {/* ─── Market Overview Slider ────────────────── */}
          <ScrollReveal>
            {!query && selectedCategory === "All" && (
              <section>
                <div className="flex items-end justify-between mb-8">
                  <div>
                    <h3 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-2">Market Overview</h3>
                    <p className="text-gray-500">Real-time price tracking across all commodities</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <button onClick={() => scrollAll("left")} disabled={!allCanLeft} className="p-2 rounded-xl bg-white border border-gray-200 disabled:opacity-30 hover:bg-gray-50 transition-all"><ChevronLeft className="w-5 h-5" /></button>
                      <button onClick={() => scrollAll("right")} disabled={!allCanRight} className="p-2 rounded-xl bg-white border border-gray-200 disabled:opacity-30 hover:bg-gray-50 transition-all"><ChevronRight className="w-5 h-5" /></button>
                    </div>
                    <Link href="/Table" className="flex items-center gap-1.5 text-sm font-bold text-primary-800 hover:text-accent transition-colors">
                      View All <ArrowRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>

                <div ref={allProductsRef} className="flex gap-4 overflow-x-auto pt-4 pb-12 px-10 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide">
                  {products.slice(0, 10).map((p) => (
                    <div key={p.id} className="snap-start shrink-0 w-[180px] sm:w-[220px] lg:w-[240px]">
                      <ProductCard id={p.id} name={p.name} emoji={p.emoji} category={p.category} image={p.image} currentPrice={p.currentPrice} predictedPrice={p.predictedPrice} compact />
                    </div>
                  ))}
                </div>
              </section>
            )}
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
