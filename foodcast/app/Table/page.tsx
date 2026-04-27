"use client";
import { useState, useMemo } from "react";
import Link from "next/link";
import { Search, ArrowUpDown, Filter, Eye, ArrowLeft } from "lucide-react";
import Header from "../component/Header";
import Footer from "../component/Footer";
import SparklineChart from "../component/SparklineChart";
import ScrollReveal from "../component/ScrollReveal";
import { products, categories } from "../lib/data";

type SortKey = "name" | "currentPrice" | "predictedPrice" | "change" | "volume";
type SortDir = "asc" | "desc";

export default function TablePage() {
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedProducts = useMemo(() => {
    let results = products.filter((p) => {
      const matchCategory =
        selectedCategory === "All" || p.category === selectedCategory;
      const matchQuery =
        !query ||
        p.name.toLowerCase().includes(query.toLowerCase()) ||
        p.category.toLowerCase().includes(query.toLowerCase());
      return matchCategory && matchQuery;
    });

    results.sort((a, b) => {
      let comp = 0;
      switch (sortKey) {
        case "name":
          comp = a.name.localeCompare(b.name);
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
  }, [query, selectedCategory, sortKey, sortDir]);

  const SortHeader = ({
    label,
    sortKeyName,
  }: {
    label: string;
    sortKeyName: SortKey;
  }) => (
    <button
      onClick={() => toggleSort(sortKeyName)}
      className="flex items-center gap-1 text-[10px] sm:text-xs font-semibold text-white uppercase tracking-wider 
      hover:text-primary-400 transition-colors group"
      aria-label={`Sort by ${label}`}
    >
      {label}
      <ArrowUpDown
        className={`w-3 h-3 transition-colors ${sortKey === sortKeyName ? "text-primary-400" : "text-white"}`}
      />
    </button>
  );

  return (
    <>
      <Header />
      <main id="main-content">
        {/* ─── Header ──────────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-12 sm:py-14 pt-28 sm:pt-30 overflow-hidden">
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
              Back to Home
            </Link>
            <h1
              className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white mb-2"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Market{" "}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                Table View
              </span>
            </h1>
            <p className="text-white/50 max-w-xl text-sm sm:text-base">
              Comprehensive data view of all tracked agri-fishery products
            </p>
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-6 sm:py-8 lg:py-10">
          {/* ─── Filters ─────────────────────────────────── */}
          <ScrollReveal>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 mb-5 sm:mb-6">
              {/* Search */}
              <div className="relative flex-1 w-full sm:max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Filter products..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-800 placeholder-gray-400
                    focus:outline-none focus:border-accent/50 focus:shadow-[0_0_0_3px_rgba(126,217,87,0.1)] transition-all"
                  id="table-search"
                  aria-label="Filter products"
                />
              </div>

              {/* Category pills */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1 w-full sm:w-auto">
                <Filter className="w-4 h-4 text-gray-400 shrink-0" />
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200 ${selectedCategory === cat
                      ? "bg-primary-800 text-white"
                      : "bg-white border border-gray-200 text-gray-600 hover:border-primary-200 hover:text-primary-800"
                      }`}
                    aria-pressed={selectedCategory === cat}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>
          </ScrollReveal>

          {/* ─── Data Table ───────────────────────────────── */}
          <ScrollReveal>
            <div className="bg-white/40 backdrop-blur-md rounded-[2.5rem] border border-white/50 shadow-xl overflow-hidden">
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full" role="grid" aria-label="Product prices table">
                  <thead>
                    <tr className="border-b border-black/5 text-white bg-primary-700 ">
                      <th className="text-left px-6 lg:px-8 py-5">
                        <SortHeader label="Product" sortKeyName="name" />
                      </th>
                      <th className="text-left px-6 lg:px-8 py-5 ">
                        <span className="text-[10px] font-bold uppercase tracking-widest">
                          Category
                        </span>
                      </th>
                      <th className="text-center px-6 py-5">
                        <SortHeader label="Current Price" sortKeyName="currentPrice" />
                      </th>
                      <th className=" text-center px-6 py-5">
                        <SortHeader label="Predicted" sortKeyName="predictedPrice" />
                      </th>
                      <th className="text-center px-6 py-5">
                        <SortHeader label="Change" sortKeyName="change" />
                      </th>
                      <th className="text-center px-6 py-5">
                        <span className="text-[10px] font-bold uppercase tracking-widest">
                          Action
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/5">
                    {sortedProducts.map((p) => {
                      const change =
                        ((p.predictedPrice - p.currentPrice) /
                          p.currentPrice) *
                        100;
                      const isUp = change >= 0;

                      return (
                        <tr
                          key={p.id}
                          className="group transition-all duration-300 hover:bg-white/60"
                        >
                          <td className="px-6 lg:px-8 py-5">
                            <div className="flex items-center gap-4">
                              <div className="w-10 h-10 rounded-xl bg-white/80 shadow-sm flex items-center justify-center text-2xl transition-transform duration-300 group-hover:scale-110">
                                {p.emoji}
                              </div>
                              <span className="font-bold text-base text-gray-900 group-hover:text-primary-800 transition-colors">
                                {p.name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 lg:px-8 py-5 text-left">
                            <span className="inline-block text-[10px] font-bold text-primary-700 bg-primary-100/50 backdrop-blur-sm px-2.5 py-1 rounded-lg">
                              {p.category}
                            </span>
                          </td>
                          <td className="px-6 lg:px-8 py-5 text-left">
                            <span className="text-sm font-bold text-gray-900 tabular-nums">
                              ₱{p.currentPrice.toFixed(2)}
                            </span>
                          </td>
                          <td className="px-6 lg:px-8 py-5 text-left">
                            <span
                              className={`text-sm font-black tabular-nums transition-all ${isUp ? "text-positive group-hover:drop-shadow-[0_0_8px_rgba(46,125,50,0.3)]" : "text-negative group-hover:drop-shadow-[0_0_8px_rgba(198,40,40,0.3)]"
                                }`}
                            >
                              ₱{p.predictedPrice.toFixed(2)}
                            </span>
                          </td>
                          <td className="px-6 lg:px-8 py-5 text-left">
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
                          <td className="px-6 lg:px-8 py-5 text-center">
                            <Link
                              href={`/Product/${p.id}`}
                              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold text-white bg-primary-800 rounded-xl shadow-md 
                                hover:bg-primary-700 hover:shadow-lg hover:shadow-primary-800/20 active:scale-95 transition-all duration-300"
                              aria-label={`View details for ${p.name}`}
                            >
                              <Eye className="w-4 h-4" />
                              Details
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile Card Layout */}
              <div className="md:hidden divide-y divide-black/5 bg-white/20">
                {sortedProducts.map((p) => {
                  const change =
                    ((p.predictedPrice - p.currentPrice) / p.currentPrice) *
                    100;
                  const isUp = change >= 0;

                  return (
                    <div
                      key={p.id}
                      className="p-5 active:bg-white/40 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3 mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-12 h-12 rounded-2xl bg-white shadow-sm flex items-center justify-center text-2xl">
                            {p.emoji}
                          </div>
                          <div>
                            <div className="text-base font-bold text-gray-900">{p.name}</div>
                            <span className="text-[10px] font-bold text-primary-700 bg-primary-100 px-2 py-0.5 rounded-lg">
                              {p.category}
                            </span>
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
                      <div className="grid grid-cols-2 gap-4 mb-5">
                        <div className="bg-white/40 p-3 rounded-xl border border-white/60">
                          <div className="text-[9px] text-gray-400 uppercase tracking-widest font-black mb-1">
                            Current
                          </div>
                          <div className="text-sm font-bold text-gray-900 tabular-nums">
                            ₱{p.currentPrice.toFixed(2)}
                          </div>
                        </div>
                        <div className="bg-white/40 p-3 rounded-xl border border-white/60">
                          <div className="text-[9px] text-gray-400 uppercase tracking-widest font-black mb-1">
                            Predicted
                          </div>
                          <div className={`text-sm font-black tabular-nums ${isUp ? "text-positive" : "text-negative"}`}>
                            ₱{p.predictedPrice.toFixed(2)}
                          </div>
                        </div>
                      </div>
                      <Link
                        href={`/Product/${p.id}`}
                        className="flex items-center justify-center gap-2 w-full py-3 text-xs font-bold text-white bg-primary-800 rounded-xl shadow-md active:scale-[0.98] transition-all"
                        aria-label={`View details for ${p.name}`}
                      >
                        <Eye className="w-4 h-4" />
                        View Full Analysis
                      </Link>
                    </div>
                  );
                })}
              </div>

              {sortedProducts.length === 0 && (
                <div className="text-center py-12 sm:py-16">
                  <div className="text-3xl sm:text-4xl mb-3">📊</div>
                  <h3 className="text-sm sm:text-base font-semibold text-gray-700 mb-1">
                    No results found
                  </h3>
                  <p className="text-gray-500 text-xs sm:text-sm">
                    Try different filters or search terms
                  </p>
                </div>
              )}

              {/* Summary row */}
              <div className="px-4 sm:px-5 py-3 bg-gray-50/50 border-t border-gray-100 flex items-center justify-between">
                <span className="text-[11px] sm:text-xs text-gray-500">
                  Showing {sortedProducts.length} of {products.length} products
                </span>
                <span className="text-[11px] sm:text-xs text-gray-400">
                  Data refreshed hourly
                </span>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </main>
      <Footer />
    </>
  );
}
