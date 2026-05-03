"use client";
import { useState, useEffect, useMemo } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import NewsCard from "../components/NewsCard";
import ScrollReveal from "../components/ScrollReveal";
import { Search, Filter, Calendar, Newspaper, ArrowLeft, TrendingUp, Clock } from "lucide-react";
import { fetchNews, NewsArticle } from "../lib/data";
import Link from "next/link";

export default function NewsPage() {
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [dateFilter, setDateFilter] = useState("All");
  const [visibleCount, setVisibleCount] = useState(6);

  useEffect(() => {
    fetchNews(100).then((data) => {
      setNews(data);
      setLoading(false);
    });
  }, []);

  const categories = useMemo(() => {
    const cats = new Set(news.map((item) => item.category));
    return ["All", ...Array.from(cats)];
  }, [news]);

  const filteredNews = useMemo(() => {
    return news.filter((item) => {
      const matchesSearch =
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.excerpt.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.source && item.source.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesCategory = selectedCategory === "All" || item.category === selectedCategory;

      let matchesDate = true;
      if (dateFilter === "Recent") {
        const itemDate = new Date(item.date);
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        matchesDate = itemDate >= thirtyDaysAgo;
      } else if (dateFilter === "Today") {
        const itemDate = new Date(item.date).toDateString();
        const today = new Date().toDateString();
        matchesDate = itemDate === today;
      }

      return matchesSearch && matchesCategory && matchesDate;
    });
  }, [news, searchQuery, selectedCategory, dateFilter]);

  const featuredArticle = news[0];
  const displayNews = searchQuery || selectedCategory !== "All" || dateFilter !== "All"
    ? filteredNews
    : filteredNews.slice(1);

  return (
    <>
      <Header />
      <main className="min-h-screen bg-surface">
        {/* Premium Hero Section */}
        <section className="relative bg-primary-900 pt-30 md:pt-40 pb-10 md:pb-20 overflow-hidden">
          <div className="absolute inset-0 z-0">
            <img src="/Bg-4.jpg" alt="" className="w-full h-full object-cover opacity-40 blur-[2px]" />
            <div className="absolute inset-0 bg-gradient-to-b from-primary-900/80 via-primary-900/90 to-surface" />
          </div>

          <div className="relative z-10 max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                <TrendingUp className="w-4 h-4 text-accent" />
                <span className="text-white/80 text-[10px] font-bold uppercase tracking-widest">Market Intelligence</span>
              </div>
              <h1 className="text-2xl sm:text-3xl lg:text-5xl font-black text-white mb-3 sm:mb-6 leading-[0.9]" style={{ fontFamily: "var(--font-display)" }}>
                The <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">Feed</span>
              </h1>
              <p className="text-white/50 max-w-2xl text-sm sm:text-base mb-12 font-light leading-relaxed">
                Stay updated with real-time agricultural intelligence, policy changes, and price alerts across the NCR market ecosystem.
              </p>
            </ScrollReveal>

            {/* Featured Article - Only show if no filters active */}
            {!searchQuery && selectedCategory === "All" && dateFilter === "All" && featuredArticle && (
              <ScrollReveal delay={200}>
                <div className="group relative bg-white rounded-[2.5rem] overflow-hidden shadow-2xl border border-white/20 flex flex-col lg:flex-row transition-all duration-500 hover:shadow-accent/10">
                  <div className="lg:w-1/2 h-[200px] lg:h-auto overflow-hidden">
                    <img src={featuredArticle.image} alt={featuredArticle.title} className="w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105" />
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
                    <a href={featuredArticle.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-3 text-primary-800 font-black uppercase tracking-widest text-xs hover:text-accent-dark transition-colors group/btn">
                      Read Full Report
                      <span className="w-8 h-8 rounded-full bg-primary-50 flex items-center justify-center transition-all group-hover/btn:translate-x-2 group-hover/btn:bg-accent group-hover/btn:text-white">
                        <ArrowLeft className="w-4 h-4 rotate-180" />
                      </span>
                    </a>
                  </div>
                </div>
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
                  placeholder="Search market news, sources, or categories..."
                  className="w-full pl-14 pr-6 py-4 bg-white border border-gray-200 rounded-3xl text-sm font-medium transition-all focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 shadow-sm"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-4 w-full lg:w-auto">
                <div className="flex items-center gap-2 p-2 bg-white border border-gray-200 rounded-2xl shadow-sm">
                  <div className="flex items-center gap-2 px-3 py-2 border-r border-gray-100">
                    <Filter className="w-4 h-4 text-primary-700" />
                    <select
                      className="bg-transparent text-xs font-bold text-gray-700 focus:outline-none appearance-none cursor-pointer"
                      value={selectedCategory}
                      onChange={(e) => setSelectedCategory(e.target.value)}
                    >
                      {categories.map(cat => <option key={cat} value={cat}>{cat}</option>)}
                    </select>
                  </div>
                  <div className="flex items-center gap-2 px-3 py-2">
                    <Calendar className="w-4 h-4 text-primary-700" />
                    <select
                      className="bg-transparent text-xs font-bold text-gray-700 focus:outline-none appearance-none cursor-pointer"
                      value={dateFilter}
                      onChange={(e) => setDateFilter(e.target.value)}
                    >
                      <option value="All">All Time</option>
                      <option value="Today">Today</option>
                      <option value="Recent">Last 30 Days</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Article Grid */}
        <section className="py-5 max-w-7xl mx-auto px-5 lg:px-10">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-32">
              <div className="w-12 h-12 border-4 border-gray-100 border-t-accent rounded-full animate-spin mb-6" />
              <p className="text-gray-400 font-bold uppercase tracking-widest text-[10px]">Updating Intelligence Feed</p>
            </div>
          ) : displayNews.length > 0 ? (
            <>
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xs font-black text-gray-400 uppercase tracking-[0.3em]">
                  {searchQuery || selectedCategory !== "All" || dateFilter !== "All" ? `Results Found (${displayNews.length})` : "Latest Reports"}
                </h3>
                <div className="h-[1px] flex-1 bg-gray-100 mx-8 hidden md:block" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
                {displayNews.slice(0, visibleCount).map((article, i) => (
                  <ScrollReveal key={article.id} delay={i * 30} animation="fade-up">
                    <NewsCard {...article} />
                  </ScrollReveal>
                ))}
              </div>

              {visibleCount < displayNews.length && (
                <div className="mt-16 text-center">
                  <button
                    onClick={() => setVisibleCount(prev => prev + 6)}
                    className="group relative px-10 py-5 bg-white border border-gray-200 rounded-[2rem] text-primary-900 font-black uppercase tracking-[0.2em] text-[10px] hover:text-white transition-all duration-500 overflow-hidden shadow-lg hover:shadow-primary-900/20 active:scale-95"
                  >
                    <span className="relative z-10">Load More</span>
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
                <h3 className="text-2xl font-black text-gray-900 mb-3">No matching reports found</h3>
                <p className="text-gray-500 mb-10 max-w-xs mx-auto text-sm">We couldn't find any articles matching your current search parameters.</p>
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
