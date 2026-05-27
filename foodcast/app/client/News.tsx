"use client";
import { useState, useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import Header from "../components/Header";
import Footer from "../components/Footer";
import NewsCard from "../components/NewsCard";
import ScrollReveal from "../components/ScrollReveal";
import Image from "next/image";
import { Search, Filter, Calendar, Newspaper, ArrowLeft, TrendingUp, Clock, Tag, ExternalLink, ChevronDown } from "lucide-react";
import { fetchPaginatedNews, toEventTypeKey, NewsArticle } from "../lib/data";
import Link from "next/link";
import { useLanguage } from "../lib/i18n/LanguageContext";

interface NewsProps {
  initialNews: NewsArticle[];
  initialTotal: number;
  initialCategories: string[];
}

export default function News({ initialNews, initialTotal, initialCategories }: NewsProps) {
  const [news, setNews] = useState<NewsArticle[]>(initialNews);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [isFeaturedOpen, setIsFeaturedOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const { t, isTransitioning } = useLanguage();

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [dateFilter, setDateFilter] = useState("All");
  const [totalRecords, setTotalRecords] = useState(initialTotal);
  const PAGE_SIZE = 10;

  const [isCategoryOpen, setIsCategoryOpen] = useState(false);
  const [isDateOpen, setIsDateOpen] = useState(false);
  const categoryRef = useRef<HTMLDivElement>(null);
  const dateRef = useRef<HTMLDivElement>(null);
  const isInitialMount = useRef(true);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (categoryRef.current && !categoryRef.current.contains(event.target as Node)) setIsCategoryOpen(false);
      if (dateRef.current && !dateRef.current.contains(event.target as Node)) setIsDateOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const [categories, setCategories] = useState<string[]>(initialCategories);

  // Filter changes
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    setLoading(true);
    const dbCategory = selectedCategory === "All" ? "All" : toEventTypeKey(selectedCategory);
    fetchPaginatedNews(0, PAGE_SIZE, searchQuery, dbCategory, dateFilter).then(({ data, total }) => {
      setNews(data);
      setTotalRecords(total);
      setLoading(false);
    });
  }, [searchQuery, selectedCategory, dateFilter]);

  const handleLoadMore = async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    const start = news.length;
    const dbCategory = selectedCategory === "All" ? "All" : toEventTypeKey(selectedCategory);
    const { data } = await fetchPaginatedNews(start, PAGE_SIZE, searchQuery, dbCategory, dateFilter);
    setNews(prev => [...prev, ...data]);
    setLoadingMore(false);
  };

  const featuredArticle = news.length > 0 ? news[0] : null;
  const displayNews = searchQuery || selectedCategory !== "All" || dateFilter !== "All"
    ? news
    : news.slice(1);

  // Lock body scroll when featured modal is open
  useEffect(() => {
    if (isFeaturedOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isFeaturedOpen]);

  return (
    <>
      <Header />
      <main className="min-h-screen bg-surface">
        {/* Premium Hero Section */}
        <section className="relative bg-primary-900 pt-30 md:pt-40 pb-10 md:pb-20 overflow-hidden">
          <div className="absolute inset-0 z-0">
            <Image 
              src="/Bg-4.jpg" 
              alt="" 
              fill
              priority
              className="object-cover opacity-40 blur-[2px]" 
            />
            <div className="absolute inset-0 bg-gradient-to-b from-primary-900/80 via-primary-900/90 to-surface" />
          </div>

          <div className="relative z-10 max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                <TrendingUp className="w-4 h-4 text-accent" />
                <span className="text-white/80 text-[10px] font-bold uppercase tracking-widest">{t("marketIntelligence")}</span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-5xl font-black text-white mb-3 sm:mb-6 leading-[0.9]" style={{ fontFamily: "var(--font-display)" }}>
                {t("the")} <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">{t("feed")}</span>
              </h1>
              <p className="text-white/50 max-w-2xl text-sm sm:text-base mb-12 font-light leading-relaxed">
                {t("feedDesc")}
              </p>
            </ScrollReveal>

            {/* Featured Article - Only show if no filters active */}
            {!searchQuery && selectedCategory === "All" && dateFilter === "All" && featuredArticle && (
              <ScrollReveal delay={200}>
                <div 
                  onClick={() => setIsFeaturedOpen(true)}
                  className="group relative bg-white rounded-[2.5rem] overflow-hidden shadow-2xl border border-white/20 flex flex-col lg:flex-row transition-all duration-500 hover:shadow-accent/10 cursor-pointer"
                >
                  <div className="relative lg:w-1/2 h-[200px] lg:h-auto overflow-hidden">
                    <Image 
                      src={featuredArticle.image} 
                      alt={featuredArticle.title} 
                      fill
                      className="object-cover transition-transform duration-1000 group-hover:scale-105" 
                    />
                  </div>
                  <div className="lg:w-1/2 p-4 md:p-8 flex flex-col justify-center">
                    <div className="flex items-center gap-4 mb-6">
                      <span className="px-3 py-1 bg-primary-900 text-white text-[10px] font-bold rounded-lg uppercase tracking-wider">{featuredArticle.category}</span>
                      <span className="text-gray-400 text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5">
                        <Clock className="w-3 h-3" /> {featuredArticle.date}
                      </span>
                    </div>
                    <h2 className="text-2xl md:text-4xl font-black text-gray-900 mb-6 leading-tight group-hover:text-primary-800 transition-colors">
                      {featuredArticle.title}
                    </h2>
                    <p className="text-gray-500 text-sm md:text-base mb-8 line-clamp-3 leading-relaxed">
                      {featuredArticle.excerpt}
                    </p>
                    <a
                      href={featuredArticle.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-3 text-primary-800 font-black uppercase tracking-widest text-xs hover:text-accent-dark transition-colors group/btn z-10"
                    >
                      {t("readFullReport")}
                      <span className="w-8 h-8 rounded-full bg-primary-50 flex items-center justify-center transition-all group-hover/btn:translate-x-2 group-hover/btn:bg-accent group-hover/btn:text-white">
                        <ArrowLeft className="w-4 h-4 rotate-180" />
                      </span>
                    </a>
                  </div>
                </div>

                {/* Featured Modal Overlay via Portal */}
                {isMounted && isFeaturedOpen && createPortal(
                  <div
                    className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
                    onClick={(e) => { e.stopPropagation(); setIsFeaturedOpen(false); }}
                  >
                    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in" />
                    <div
                      onClick={(e) => e.stopPropagation()}
                      className="relative z-10 bg-white rounded-[2rem] w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl animate-modal-in flex flex-col"
                    >
                      <div className="relative h-56 sm:h-64 flex-shrink-0 overflow-hidden">
                        <Image
                          src={featuredArticle.image}
                          alt={featuredArticle.title}
                          fill
                          className="object-cover"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
                        <div className="absolute bottom-5 left-6 right-6 flex items-center gap-3">
                          <span className="px-3 py-1.5 bg-white/20 backdrop-blur-md rounded-full text-[10px] font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                            <Tag className="w-3 h-3" />
                            {featuredArticle.category}
                          </span>
                          <span className="text-white/70 text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5">
                            <Clock className="w-3 h-3" />
                            {featuredArticle.date}
                          </span>
                        </div>
                      </div>

                      <div className="p-6 sm:p-8 overflow-y-auto flex-1">
                        <h2 className="text-xl sm:text-2xl font-black text-gray-900 mb-2 leading-tight" style={{ fontFamily: "var(--font-display)" }}>
                          {featuredArticle.title}
                        </h2>
                        <div className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.2em] mb-6">
                          {t("source")}: {featuredArticle.source || t("marketNews")}
                        </div>
                        <div className="w-12 h-0.5 bg-gradient-to-r from-primary-700 to-accent rounded-full mb-6" />
                        <div className="text-gray-600 text-sm sm:text-base leading-relaxed whitespace-pre-line">
                          {featuredArticle.content || featuredArticle.excerpt}
                        </div>
                      </div>

                      <div className="flex-shrink-0 px-6 sm:px-8 py-5 border-t border-gray-100 flex items-center justify-between bg-gray-50/50">
                        <button
                          onClick={() => setIsFeaturedOpen(false)}
                          className="px-6 py-2.5 bg-gray-200 text-gray-700 hover:bg-gray-300 text-xs font-bold uppercase tracking-widest rounded-xl transition-all active:scale-95"
                        >
                          {t("close")}
                        </button>
                        {featuredArticle.url && (
                          <a
                            href={featuredArticle.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 px-6 py-2.5 bg-primary-900 text-white text-xs font-bold uppercase tracking-widest rounded-xl hover:bg-primary-800 transition-all shadow-lg hover:shadow-primary-900/30 active:scale-95"
                          >
                            {t("visitSource")}
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                , document.body)}
              </ScrollReveal>
            )}
          </div>
        </section>

        {/* Interactive Filter Bar */}
        <section className="sticky top-[72px] z-40 bg-surface/90 backdrop-blur-xl border-b border-gray-100 py-6 transition-all duration-300">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <div className="flex flex-col lg:flex-row gap-6 items-center justify-between">
              <div className="relative w-full lg:max-w-xl group">
                <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 group-focus-within:text-primary-700 transition-colors" />
                <input
                  type="text"
                placeholder={t("searchNewsPlaceholder")}
                  className="w-full pl-14 pr-6 py-4 bg-white border border-gray-200 rounded-3xl text-sm font-medium transition-all focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 shadow-sm"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="flex flex-wrap items-center gap-4 w-full lg:w-auto">
                <div className="flex flex-wrap items-center bg-white border border-gray-200 rounded-2xl shadow-sm">
                  
                  {/* Category Dropdown */}
                  <div className="relative border-r border-gray-100" ref={categoryRef}>
                    <button
                      onClick={() => setIsCategoryOpen(!isCategoryOpen)}
                      className="flex items-center gap-2 px-4 py-3 hover:bg-gray-50 rounded-l-2xl transition-colors focus:outline-none"
                    >
                      <Filter className="w-4 h-4 text-primary-700" />
                      <span className="text-xs font-bold text-gray-700">{selectedCategory}</span>
                      <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${isCategoryOpen ? "rotate-180" : ""}`} />
                    </button>
                    {isCategoryOpen && (
                      <div className="absolute top-full left-0 mt-2 w-48 bg-white border border-gray-100 rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.1)] z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex flex-col py-1">
                          {categories.map((cat) => (
                            <button
                              key={cat}
                              onClick={() => {
                                setSelectedCategory(cat);
                                setIsCategoryOpen(false);
                              }}
                              className={`px-4 py-2 text-left text-xs font-bold transition-colors ${
                                selectedCategory === cat ? "bg-primary-50 text-primary-800" : "text-gray-600 hover:bg-gray-50 hover:text-primary-700"
                              }`}
                            >
                              {cat}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Date Dropdown */}
                  <div className="relative" ref={dateRef}>
                    <button
                      onClick={() => setIsDateOpen(!isDateOpen)}
                      className="flex items-center gap-2 px-4 py-3 hover:bg-gray-50 rounded-r-2xl transition-colors focus:outline-none"
                    >
                      <Calendar className="w-4 h-4 text-primary-700" />
                      <span className="text-xs font-bold text-gray-700">
                        {dateFilter === "All" ? t("allTime") : dateFilter === "Today" ? t("last24Hours") : t("last30Days")}
                      </span>
                      <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${isDateOpen ? "rotate-180" : ""}`} />
                    </button>
                    {isDateOpen && (
                      <div className="absolute top-full right-0 mt-2 w-44 bg-white border border-gray-100 rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.1)] z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex flex-col py-1">
                          {[
                            { value: "All", label: t("allTime") },
                            { value: "Today", label: t("last24Hours") },
                            { value: "Recent", label: t("last30Days") }
                          ].map((option) => (
                            <button
                              key={option.value}
                              onClick={() => {
                                setDateFilter(option.value);
                                setIsDateOpen(false);
                              }}
                              className={`px-4 py-2 text-left text-xs font-bold transition-colors ${
                                dateFilter === option.value ? "bg-primary-50 text-primary-800" : "text-gray-600 hover:bg-gray-50 hover:text-primary-700"
                              }`}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Article Grid */}
        <section className="py-5 max-w-7xl mx-auto px-5 lg:px-10">
          {loading || isTransitioning ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
              {[1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} className="bg-white rounded-3xl border border-gray-100 p-4 h-[380px] flex flex-col shadow-sm">
                  <div className="h-48 w-full bg-gray-100 rounded-2xl mb-5 animate-pulse" />
                  <div className="flex gap-2 mb-4">
                     <div className="h-5 w-20 bg-gray-200 rounded-lg animate-pulse" />
                    <div className="h-5 w-24 bg-gray-100 rounded-lg animate-pulse" />
                  </div>
                  <div className="h-6 w-full bg-gray-200 rounded-lg mb-3 animate-pulse" />
                  <div className="h-6 w-3/4 bg-gray-200 rounded-lg mb-auto animate-pulse" />
                  <div className="h-4 w-32 bg-gray-100 rounded-md animate-pulse mt-4" />
                </div>
              ))}
            </div>
          ) : displayNews.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xs font-black text-gray-400 uppercase tracking-[0.3em]">
                  {searchQuery || selectedCategory !== "All" || dateFilter !== "All" ? `${t("resultsFound")} (${totalRecords})` : t("latestReports")}
                </h3>
                <div className="h-[1px] flex-1 bg-gray-100 mx-8 hidden md:block" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
                {displayNews.map((article, i) => (
                  <ScrollReveal key={article.id} delay={(i % PAGE_SIZE) * 30} animation="fade-up">
                    <NewsCard {...article} content={article.content} />
                  </ScrollReveal>
                ))}
              </div>

              {news.length < totalRecords && (
                <div className="mt-16 text-center">
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="group relative px-10 py-5 bg-white border border-gray-200 rounded-[2rem] text-primary-900 font-black uppercase tracking-[0.2em] text-[10px] hover:text-white transition-all duration-500 overflow-hidden shadow-lg hover:shadow-primary-900/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="relative z-10">{loadingMore ? t("loading") : t("loadMore")}</span>
                    <div className="absolute inset-0 bg-primary-900 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
                  </button>
                </div>
              )}
            </>
          ) : (
            <ScrollReveal animation="scale-in">
              <div className="text-center py-32 bg-white rounded-[3rem] border border-dashed border-gray-200 shadow-inner">
                <div className="w-20 h-20 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-8">
                  <Newspaper className="w-8 h-8 text-gray-300" />
                </div>
                <h3 className="text-2xl font-black text-gray-900 mb-3">{t("noMatchingReports")}</h3>
                <p className="text-gray-500 mb-10 max-w-xs mx-auto text-sm">{t("noMatchingReportsDesc")}</p>
                <button
                  onClick={() => { setSearchQuery(""); setSelectedCategory("All"); setDateFilter("All"); }}
                  className="px-8 py-4 bg-primary-900 text-white rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-accent transition-all shadow-lg hover:shadow-accent/20 active:scale-95"
                >
                  Reset Search Filter
                </button>
              </div>
            </ScrollReveal>
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
