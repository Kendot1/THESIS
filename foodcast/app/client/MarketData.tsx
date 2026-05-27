"use client";
import { useState, useMemo, useEffect, useRef, useDeferredValue } from "react";
import Link from "next/link";
import { Search, ArrowUpDown, Filter, Eye, ArrowLeft, ChevronLeft, ChevronRight, X, SlidersHorizontal, ChevronDown } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import SparklineChart from "../components/SparklineChart";
import ScrollReveal from "../components/ScrollReveal";
import { Product, fetchCategories } from "../lib/data";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { useProducts } from "../lib/hooks";

type SortKey = "name" | "category" | "origin" | "currentPrice" | "predictedPrice" | "change" | "volume";
type SortDir = "asc" | "desc";

export default function MarketData({ initialProducts }: { initialProducts: Product[] }) {
  const { t, isTransitioning } = useLanguage();
  const { data: products = [], isLoading } = useProducts(initialProducts);

  const [query, setQuery] = useState("");
  const [categories, setCategories] = useState<string[]>(["All"]);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [currentPage, setCurrentPage] = useState(1);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [priceRange, setPriceRange] = useState("All Prices");
  const [selectedOrigin, setSelectedOrigin] = useState("All");
  const [showMoreCategories, setShowMoreCategories] = useState(false);
  const [visibleCount, setVisibleCount] = useState(6);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const itemsPerPage = 12;
  const router = useRouter();

  useEffect(() => {
    fetchCategories().then((cats) => {
      setCategories(cats);
    });
  }, []);

  // Responsive visible categories
  useEffect(() => {
    const updateCount = () => {
      if (window.innerWidth < 640) setVisibleCount(2);
      else if (window.innerWidth < 1024) setVisibleCount(4);
      else setVisibleCount(6);
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

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const deferredQuery = useDeferredValue(query);
  const deferredCategory = useDeferredValue(selectedCategory);

  useEffect(() => {
    setCurrentPage(1);
  }, [deferredQuery, deferredCategory, priceRange, selectedOrigin]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { All: products.length };
    products.forEach(p => {
      counts[p.category] = (counts[p.category] || 0) + 1;
    });
    return counts;
  }, [products]);

  const originCounts = useMemo(() => {
    const counts: Record<string, number> = { All: products.length };
    products.forEach(p => {
      if (p.origin) {
        counts[p.origin] = (counts[p.origin] || 0) + 1;
      }
    });
    return counts;
  }, [products]);

  const uniqueOrigins = useMemo(() => {
    const origins = new Set<string>();
    products.forEach(p => {
      if (p.origin) origins.add(p.origin);
    });
    return Array.from(origins).sort();
  }, [products]);

  const sortedProducts = useMemo(() => {
    let results = products.filter((p) => {
      const matchCategory =
        deferredCategory === "All" || p.category === deferredCategory;
      const matchQuery =
        !deferredQuery ||
        p.name.toLowerCase().includes(deferredQuery.toLowerCase()) ||
        p.category.toLowerCase().includes(deferredQuery.toLowerCase()) ||
        (p.variant && p.variant.toLowerCase().includes(deferredQuery.toLowerCase())) ||
        (p.origin && p.origin.toLowerCase().includes(deferredQuery.toLowerCase()));

      const matchPrice = (() => {
        if (priceRange === "All Prices") return true;
        if (priceRange === "Below ₱50") return p.currentPrice < 50;
        if (priceRange === "₱50 - ₱100") return p.currentPrice >= 50 && p.currentPrice <= 100;
        if (priceRange === "Above ₱100") return p.currentPrice > 100;
        return true;
      })();

      const matchOrigin = selectedOrigin === "All" || p.origin === selectedOrigin;

      return matchCategory && matchQuery && matchPrice && matchOrigin;
    });

    results.sort((a, b) => {
      let comp = 0;
      switch (sortKey) {
        case "name":
          comp = a.name.localeCompare(b.name);
          break;
        case "category":
          comp = a.category.localeCompare(b.category);
          break;
        case "origin":
          comp = (a.origin || "").localeCompare(b.origin || "");
          break;
        case "currentPrice":
          comp = a.currentPrice - b.currentPrice;
          break;
        case "predictedPrice":
          comp = a.predictedPrice - b.predictedPrice;
          break;
        case "change":
          comp =
            (a.predictedPrice - a.currentPrice) / a.currentPrice -
            (b.predictedPrice - b.currentPrice) / b.currentPrice;
          break;
        case "volume":
          comp =
            parseInt(a.volume.replace(/,/g, "")) -
            parseInt(b.volume.replace(/,/g, ""));
          break;
      }
      return sortDir === "asc" ? comp : -comp;
    });

    return results;
  }, [deferredQuery, deferredCategory, sortKey, sortDir, products, priceRange, selectedOrigin]);

  const paginatedProducts = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return sortedProducts.slice(start, start + itemsPerPage);
  }, [sortedProducts, currentPage]);

  const totalPages = Math.ceil(sortedProducts.length / itemsPerPage);

  const SortHeader = ({
    label,
    sortKeyName,
    center = false,
  }: {
    label: string;
    sortKeyName: SortKey;
    center?: boolean;
  }) => (
    <button
      onClick={() => toggleSort(sortKeyName)}
      className={`flex items-center gap-1 text-[10px] sm:text-xs font-semibold text-white uppercase tracking-wider 
      hover:text-primary-400 transition-colors group ${center ? "mx-auto" : ""}`}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <ArrowUpDown
        className={`w-3 h-3 transition-colors ${sortKey === sortKeyName ? "text-primary-400" : "text-white"}`}
      />
    </button>
  );

  if (isLoading || isTransitioning) {
    return (
      <main className="min-h-screen bg-surface">
          {/* Header Skeleton */}
          <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-7 sm:py-10 pt-22 sm:pt-25 overflow-hidden">
            <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
              <div className="h-4 w-32 bg-white/10 rounded-md mb-6 animate-pulse" />
              <div className="h-10 sm:h-12 w-48 sm:w-64 bg-white/10 rounded-xl mb-4 animate-pulse" />
              <div className="h-4 w-64 sm:w-96 bg-white/5 rounded-lg animate-pulse" />
            </div>
          </section>

          <div className="max-w-7xl mx-auto px-5 lg:px-10 py-6 sm:py-8 lg:py-10">
            {/* Filter Skeleton */}
            <div className="mb-5 flex flex-col lg:flex-row gap-4">
              <div className="flex gap-2 flex-1">
                <div className="h-12 flex-1 bg-white border border-gray-100 rounded-2xl animate-pulse" />
                <div className="h-12 w-12 bg-white border border-gray-100 rounded-2xl animate-pulse" />
              </div>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map(i => (
                  <div key={i} className="h-12 w-24 bg-white border border-gray-100 rounded-2xl animate-pulse hidden sm:block" />
                ))}
              </div>
            </div>

            {/* Table Skeleton */}
            <div className="bg-white rounded-[1.5rem] border border-gray-100 shadow-xl overflow-hidden">
              <div className="h-14 bg-primary-700 animate-pulse border-b border-black/5" />
              <div className="divide-y divide-gray-50">
                {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                  <div key={i} className="flex items-center justify-between p-4 sm:px-8 py-5">
                    <div className="flex items-center gap-1.5 sm:gap-2">
                        <div className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-positive animate-pulse" />
                        <span className="text-gray-400 font-medium">{t("dataRefreshed")}</span>
                    </div>
                    <div className="h-6 w-20 bg-primary-100 rounded-lg animate-pulse hidden sm:block" />
                    <div className="h-5 w-16 bg-gray-200 rounded-md animate-pulse" />
                    <div className="h-5 w-16 bg-gray-200 rounded-md animate-pulse" />
                    <div className="h-6 w-16 bg-gray-100 rounded-full animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
          </div>
      </main>
    );
  }

  return (
    <>
      <main id="main-content">
        {/* ─── Header ──────────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-7 sm:py-10 pt-22 sm:pt-25 overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-0 left-1/3 w-[400px] h-[400px] bg-accent/6 rounded-full blur-[100px]" />
          </div>
          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            {/* Back to search link */}
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-white/50 hover:text-white/80 transition-colors mb-4 sm:mb-5"
            >
              <ArrowLeft className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              {t("backToHome")}
            </Link>
            <h1
              className="text-[2rem] sm:text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-white mb-4 sm:mb-6 animate-fade-in-up"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {t("market")}{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light relative inline-block">
                {t("data")}
              </span>
            </h1>
            <p className="text-sm sm:text-base md:text-lg lg:text-xl text-white/70 max-w-2xl font-light animate-fade-in-up" style={{ animationDelay: "100ms" }}>
              {t("marketDataSubtitle")}
            </p>
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-6 sm:py-8 lg:py-10">
          {/* ─── Filters ─────────────────────────────────── */}
          <ScrollReveal className="relative z-30">
            <div className="mb-5 space-y-4">
              <div className="flex flex-col lg:flex-row items-stretch lg:items-center gap-4">
                {/* Search & Filter Trigger */}
                <div className="flex items-center gap-2 flex-1">
                  <div className="relative flex-1 group">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-primary-600 transition-colors" />
                    <input
                      type="text"
                      placeholder={t("searchMarketsPlaceholder")}
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      className="w-full pl-11 pr-4 py-3 bg-white border border-gray-200 rounded-2xl text-sm text-gray-800 placeholder-gray-400
                        focus:outline-none focus:border-primary-500 focus:shadow-[0_0_0_4px_rgba(46,125,50,0.1)] transition-all shadow-sm"
                      id="table-search"
                      aria-label="Search markets or products"
                    />
                  </div>
                  <button
                    onClick={() => setIsFilterOpen(!isFilterOpen)}
                    className={`p-3 rounded-2xl border transition-all flex items-center justify-center ${isFilterOpen
                      ? "bg-primary-800 border-primary-800 text-white shadow-lg"
                      : "bg-white border-gray-200 text-gray-500 hover:border-primary-300 hover:text-primary-800"
                      }`}
                    aria-label="Advanced filters"
                    aria-expanded={isFilterOpen}
                  >
                    <SlidersHorizontal className="w-5 h-5" />
                  </button>
                </div>

                {/* Category pills with More button */}
                <div className="relative flex items-center gap-2" ref={dropdownRef}>
                  <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-hide">
                    {categories.slice(0, visibleCount).map((cat) => {
                      const isActive = selectedCategory === cat;
                      const count = categoryCounts[cat] || 0;

                      return (
                        <button
                          key={cat}
                          onClick={() => setSelectedCategory(cat)}
                          className={`flex items-center gap-1.5 px-4 py-2.5 rounded-2xl text-xs font-bold whitespace-nowrap transition-all duration-300 border ${isActive
                            ? "bg-primary-900 border-primary-900 text-white shadow-md scale-105"
                            : "bg-white border-gray-100 text-gray-500 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-800"
                            }`}
                          aria-pressed={isActive}
                        >
                          {t(cat)}
                          <span className={`text-[10px] font-medium opacity-60 ${isActive ? "text-white" : "text-gray-400"}`}>
                            ({count})
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {/* More Button */}
                  {categories.length > visibleCount && (
                    <div className="relative">
                      <button
                        onClick={() => setShowMoreCategories(!showMoreCategories)}
                        className={`flex items-center gap-1.5 px-4 py-2.5 rounded-2xl text-xs font-bold whitespace-nowrap transition-all duration-300 border ${categories.slice(visibleCount).includes(selectedCategory)
                          ? "bg-primary-900 border-primary-900 text-white shadow-md scale-105"
                          : "bg-white border-gray-100 text-gray-500 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-800"
                          }`}
                        aria-expanded={showMoreCategories}
                      >
                        {categories.slice(visibleCount).includes(selectedCategory) ? t(selectedCategory) : t("more")}
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-300 ${showMoreCategories ? "rotate-180" : ""}`} />
                      </button>

                      {/* Dropdown */}
                      {showMoreCategories && (
                        <div className="absolute top-full right-0 mt-2 w-56 bg-white rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.15)] border border-gray-100 py-2 z-[100] animate-fade-in origin-top-right">
                          {categories.slice(visibleCount).map((cat) => {
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
              </div>

              {/* Advanced Filter Panel */}
              {isFilterOpen && (
                <div className="mt-4 p-6 bg-white rounded-[2rem] border border-gray-100 shadow-xl animate-in fade-in slide-in-from-top-4 duration-300">
                  <div className="flex items-center justify-between mb-6">
                    <span className="text-[10px] font-bold uppercase tracking-wider">{t("advancedFilters")}</span>
                    <button onClick={() => setIsFilterOpen(false)} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
                      <X className="w-4 h-4 text-gray-400" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t("priceRange")}</label>
                      <select
                        value={priceRange}
                        onChange={(e) => setPriceRange(e.target.value)}
                        className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-xl text-xs font-bold text-gray-700 outline-none focus:border-primary-500"
                      >
                        <option value="All">{t("allPrices")}</option>
                        <option value="Below ₱50">{t("below50")}</option>
                        <option value="₱50 - ₱100">₱50 - ₱100</option>
                        <option value="Above ₱100">{t("above100")}</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t("marketOrigin")}</label>
                      <select
                        value={selectedOrigin}
                        onChange={(e) => setSelectedOrigin(e.target.value)}
                        className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-xl text-xs font-bold text-gray-700 outline-none focus:border-primary-500"
                      >
                        <option value="All">{t("allLocations")}</option>
                        {uniqueOrigins.map(origin => (
                          <option key={origin} value={origin}>{t(origin)}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollReveal>

          {/* ─── Data Table ───────────────────────────────── */}
          <div className="bg-white rounded-[1.5rem] border border-gray-100 shadow-xl overflow-hidden relative z-10">
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full" role="grid" aria-label="Product prices table">
                <thead>
                  <tr className="border-b border-black/5 text-white bg-primary-700">
                    <th className="text-left px-6 lg:px-8 py-4">
                      <SortHeader label={t("product")} sortKeyName="name" />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4 ">
                      <SortHeader label={t("category")} sortKeyName="category" center />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4">
                      <SortHeader label={t("origin")} sortKeyName="origin" center />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4">
                      <SortHeader label={t("unit")} sortKeyName="volume" center />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4">
                      <SortHeader label={t("currentPrice")} sortKeyName="currentPrice" center />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4">
                      <SortHeader label={t("predictedPrice")} sortKeyName="predictedPrice" center />
                    </th>
                    <th className="text-center px-6 lg:px-8 py-4">
                      <SortHeader label={t("change")} sortKeyName="change" center />
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5">
                  {paginatedProducts.map((p) => {
                    const change =
                      ((p.predictedPrice - p.currentPrice) /
                        p.currentPrice) *
                      100;
                    const isUp = change >= 0;

                    return (
                      <tr
                        key={p.id}
                        onClick={() => router.push(`/Product/${p.id}`)}
                        onMouseEnter={() => router.prefetch(`/Product/${p.id}`)}
                        className="group transition-all duration-300 hover:bg-primary-50/40 cursor-pointer"
                      >
                        <td className="px-6 lg:px-8 py-3">
                          <div className="flex items-center gap-4">
                            <div className="flex flex-col">
                              <span className="font-bold text-sm text-gray-900 group-hover:text-primary-800 transition-colors">
                                {t(p.name)} {p.variant && p.variant !== "Standard" ? `(${p.variant})` : ""}
                              </span>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          <span className="inline-block text-[10px] font-bold text-primary-700 bg-primary-50 px-2.5 py-1 rounded-lg">
                            {t(p.category)}
                          </span>
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          {p.origin ? (
                            <span className="inline-block text-[10px] font-bold text-orange-dark bg-orange-light/10 px-2.5 py-1 rounded-lg uppercase tracking-wider">
                              {t(p.origin)}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400 font-bold">-</span>
                          )}
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          <span className="text-sm font-bold text-gray-900 tabular-nums">
                            {p.unit ? p.unit : "-"}
                          </span>
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          <span className="text-sm font-bold text-gray-900 tabular-nums">
                            ₱{p.currentPrice.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          <span
                            className={`text-sm font-black tabular-nums transition-all ${isUp ? "text-positive group-hover:drop-shadow-[0_0_8px_rgba(46,125,50,0.3)]" : "text-negative group-hover:drop-shadow-[0_0_8px_rgba(198,40,40,0.3)]"
                              }`}
                          >
                            ₱{p.predictedPrice.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-6 lg:px-8 py-3 text-center">
                          <div
                            className={`inline-flex items-center gap-1 text-[11px] font-black px-3 py-1 rounded-full transition-all duration-300 ${isUp
                              ? "text-positive bg-positive/10 group-hover:bg-positive/20"
                              : "text-negative bg-negative/10 group-hover:bg-negative/20"
                              }`}
                          >
                            {isUp ? "▲" : "▼"}{" "}
                            {Math.abs(change).toFixed(1)}%
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Card Layout */}
            <div className="md:hidden divide-y divide-black/5 bg-white/20">
              {paginatedProducts.map((p) => {
                const change =
                  ((p.predictedPrice - p.currentPrice) / p.currentPrice) *
                  100;
                const isUp = change >= 0;

                return (
                  <div
                    key={p.id}
                    onClick={() => router.push(`/Product/${p.id}`)}
                    onMouseEnter={() => router.prefetch(`/Product/${p.id}`)}
                    className="p-5 active:bg-white/60 transition-colors cursor-pointer"
                  >
                    <div className="flex items-start justify-between gap-3 mb-4">
                      <div className="flex items-center gap-3">
                        <div>
                          <div className="text-base font-bold text-gray-900">
                            {t(p.name)} {p.variant && p.variant !== "Standard" ? `(${p.variant})` : ""}
                          </div>
                          <span className="text-[10px] font-bold text-primary-700 bg-primary-100/60 px-2 py-0.5 rounded-lg mr-1.5 uppercase">
                            {t(p.category)}
                          </span>
                          {p.origin && (
                            <span className="text-[10px] font-bold text-orange-dark bg-orange-light/10 px-2 py-0.5 rounded-lg uppercase tracking-wide">
                              {t(p.origin)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div
                        className={`inline-flex items-center gap-1 text-[11px] font-black px-3 py-1 rounded-full ${isUp
                          ? "text-positive bg-positive/10"
                          : "text-negative bg-negative/10"
                          }`}
                      >
                        {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-[9px] text-gray-400 uppercase tracking-widest font-black mb-1">
                          {t("current")}
                        </div>
                        <div className="text-sm font-bold text-gray-900 tabular-nums">
                          ₱{p.currentPrice.toFixed(2)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[9px] text-gray-400 uppercase tracking-widest font-black mb-1">
                          {t("predicted")}
                        </div>
                        <div className={`text-sm font-black tabular-nums ${isUp ? "text-positive" : "text-negative"}`}>
                          ₱{p.predictedPrice.toFixed(2)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {sortedProducts.length === 0 && (
              <div className="text-center py-12 sm:py-16">
                <h3 className="text-sm sm:text-base font-semibold text-gray-700 mb-1">
                  {t("noResults")}
                </h3>
                <p className="text-gray-500 text-xs sm:text-sm">
                  {t("tryDifferentFilters")}
                </p>
              </div>
            )}

            {/* Pagination + Summary row */}
            <div className="px-4 sm:px-6 py-4 bg-surface-warm/50 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] sm:text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  {t("showing")} <span className="text-gray-900">{(currentPage - 1) * itemsPerPage + 1}</span> {t("to")} <span className="text-gray-900">{Math.min(currentPage * itemsPerPage, sortedProducts.length)}</span> {t("of")} <span className="text-gray-900">{sortedProducts.length}</span> {t("products")}
                </span>
              </div>

              {totalPages > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    className="p-2 rounded-lg bg-white border border-gray-200 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:border-primary-300 hover:text-primary-800 transition-all"
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>

                  <div className="flex items-center gap-1 px-2">
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => {
                      // Only show a few page numbers around the current page
                      if (
                        page === 1 ||
                        page === totalPages ||
                        (page >= currentPage - 1 && page <= currentPage + 1)
                      ) {
                        return (
                          <button
                            key={page}
                            onClick={() => setCurrentPage(page)}
                            className={`w-8 h-8 rounded-lg text-xs font-bold transition-all ${currentPage === page
                              ? "bg-primary-800 text-white shadow-md scale-110"
                              : "bg-white border border-gray-100 text-gray-500 hover:border-primary-200"
                              }`}
                          >
                            {page}
                          </button>
                        );
                      } else if (
                        (page === 2 && currentPage > 3) ||
                        (page === totalPages - 1 && currentPage < totalPages - 2)
                      ) {
                        return <span key={page} className="text-gray-300 text-[10px]">...</span>;
                      }
                      return null;
                    })}
                  </div>

                  <button
                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                    className="p-2 rounded-lg bg-white border border-gray-200 text-gray-600 disabled:opacity-40 disabled:cursor-not-allowed hover:border-primary-300 hover:text-primary-800 transition-all"
                    aria-label="Next page"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}

              <span className="text-[11px] sm:text-xs text-gray-400 font-medium">
                {t("dataRefreshedHourly")}
              </span>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
