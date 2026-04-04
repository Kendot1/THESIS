"use client";
import { useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Search, TrendingUp, Filter, X } from "lucide-react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import ForecastChart from "../components/ForecastChart";
import ScrollReveal from "../components/ScrollReveal";
import { products, categories } from "../lib/data";

function SearchPageContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [featuredProduct, setFeaturedProduct] = useState(products[0]);

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
      <main id="main-content" className="pt-20 min-h-screen bg-surface">
        {/* ─── Search Hero ─────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-16 sm:py-20 overflow-hidden">
          <div
            className="absolute inset-0 pointer-events-none"
            aria-hidden="true"
          >
            <div className="absolute top-0 right-1/4 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <h1
              className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-4"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Search{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                Products
              </span>
            </h1>
            <p className="text-white/50 max-w-xl mb-8">
              Explore price forecasts for agri-fishery products across NCR
              markets
            </p>

            {/* Search Input */}
            <form
              role="search"
              aria-label="Search products"
              onSubmit={(e) => e.preventDefault()}
              className="max-w-2xl"
            >
              <div className="flex items-center bg-white/10 border border-white/15 rounded-2xl overflow-hidden backdrop-blur-sm transition-all duration-300 focus-within:border-accent/50 focus-within:shadow-[0_0_30px_rgba(126,217,87,0.1)]">
                <Search className="w-5 h-5 text-white/40 ml-4 shrink-0" />
                <input
                  type="text"
                  placeholder="Search for rice, onion, galunggong..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="flex-1 px-3 py-4 bg-transparent text-white placeholder-white/35 text-sm focus:outline-none"
                  aria-label="Search products"
                  id="search-input"
                />
                {query && (
                  <button
                    onClick={() => setQuery("")}
                    className="mr-2 p-2 rounded-lg hover:bg-white/10 transition-colors"
                    aria-label="Clear search"
                  >
                    <X className="w-4 h-4 text-white/50" />
                  </button>
                )}
                <button
                  type="submit"
                  className="mr-2 px-6 py-2.5 bg-orange rounded-xl text-white font-semibold text-sm
                    transition-all duration-300 hover:bg-orange-light shrink-0"
                >
                  Search
                </button>
              </div>
            </form>
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-10 sm:py-14">
          <div className="grid lg:grid-cols-[1fr_320px] gap-8">
            {/* ─── Main Content ──────────────────────────── */}
            <div>
              {/* Featured Chart */}
              <ScrollReveal>
                <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-8 shadow-sm">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <div className="flex items-center gap-3 mb-1">
                        <span className="text-2xl">{featuredProduct.emoji}</span>
                        <h2
                          className="text-xl font-bold text-gray-900"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          {featuredProduct.name}
                        </h2>
                        <span className="text-xs font-medium text-primary-600 bg-primary-50 px-2 py-0.5 rounded-full">
                          {featuredProduct.category}
                        </span>
                      </div>
                      <p className="text-gray-500 text-sm">Price Market Forecast</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-gray-900">
                        ₱{featuredProduct.currentPrice.toFixed(2)}
                      </div>
                      <div
                        className={`text-sm font-medium ${
                          featuredProduct.predictedPrice >=
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
                  <ForecastChart
                    data={featuredProduct.forecastData}
                    height={280}
                    showGrid
                    showLegend
                  />
                </div>
              </ScrollReveal>

              {/* Category Filters */}
              <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
                <Filter className="w-4 h-4 text-gray-400 shrink-0" />
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all duration-250 ${
                      selectedCategory === cat
                        ? "bg-primary-800 text-white shadow-sm"
                        : "bg-white border border-gray-200 text-gray-600 hover:border-primary-200 hover:text-primary-800"
                    }`}
                    aria-pressed={selectedCategory === cat}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              {/* Product Grid */}
              <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-6">
                {filtered.map((p, i) => (
                  <ScrollReveal key={p.id} delay={i * 60} animation="fade-up">
                    <div onClick={() => setFeaturedProduct(p)} className="cursor-pointer">
                      <ProductCard
                        id={p.id}
                        name={p.name}
                        emoji={p.emoji}
                        image={p.image}
                        category={p.category}
                        currentPrice={p.currentPrice}
                        predictedPrice={p.predictedPrice}
                      />
                    </div>
                  </ScrollReveal>
                ))}
              </div>

              {filtered.length === 0 && (
                <div className="text-center py-20">
                  <div className="text-5xl mb-4">🔍</div>
                  <h3 className="text-lg font-semibold text-gray-700 mb-2">
                    No products found
                  </h3>
                  <p className="text-gray-500 text-sm">
                    Try adjusting your search or category filters
                  </p>
                </div>
              )}
            </div>

            {/* ─── Trending Sidebar ──────────────────────── */}
            <aside className="hidden lg:block" aria-label="Trending products">
              <div className="sticky top-24">
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
                        className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-250 text-left ${
                          featuredProduct.id === p.id
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
                          className={`text-xs font-semibold ${
                            p.predictedPrice >= p.currentPrice
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
