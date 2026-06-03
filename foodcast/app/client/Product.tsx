"use client";
import { use, useMemo, useState, useRef, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowLeft,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Calendar,
  Layers,
  CheckCircle2,
  AlertCircle,
  ArrowRightLeft,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Activity,
  Tag,
} from "lucide-react";


import dynamic from "next/dynamic";
const ForecastChart = dynamic(() => import("../components/ForecastChart"), {
  ssr: false,
  loading: () => (
    <div className="w-full animate-pulse" style={{ minHeight: 380 }}>
      <div className="h-full w-full bg-gray-50 rounded-2xl" />
    </div>
  ),
});
import ProductCard from "../components/ProductCard";
import ScrollReveal from "../components/ScrollReveal";
import { Product as ProductType, fetchNews, DEFAULT_PRODUCT_IMAGE } from "../lib/data";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { useProducts, useNews } from "../lib/hooks";
import { encryptId, decryptId } from "../../lib/idCipher";
import { getInheritedTags } from "../lib/tags";

// Helper to find logically related products based on culinary usage
function getRelatedProducts(current: ProductType, allProducts: ProductType[]): ProductType[] {
  const name = current.name.toLowerCase();

  // 1. Meats (Cross-substitutable for protein)
  const meatCategories = ["Meat", "Poultry"];
  if (meatCategories.includes(current.category)) {
    return allProducts.filter(p => meatCategories.includes(p.category));
  }

  // 2. Fish & Seafood
  if (current.category === "Fish" || current.category === "Seafood") {
    return allProducts.filter(p => p.category === "Fish" || p.category === "Seafood");
  }

  // 3. Rice
  if (current.category === "Rice") {
    return allProducts.filter(p => p.category === "Rice");
  }

  // 4. Souring agents / Citrus
  const souring = ['kalamansi', 'calamansi', 'lemon', 'sampaloc', 'tamarind', 'kamias'];
  if (souring.some(s => name.includes(s))) {
    return allProducts.filter(p => souring.some(s => p.name.toLowerCase().includes(s)));
  }

  // 5. Alliums & Aromatics
  const aromatics = ['onion', 'garlic', 'sibuyas', 'bawang', 'ginger', 'luya'];
  if (aromatics.some(s => name.includes(s))) {
    return allProducts.filter(p => aromatics.some(s => p.name.toLowerCase().includes(s)));
  }

  // 6. Leafy greens
  const leafy = ['cabbage', 'pechay', 'kangkong', 'repolyo', 'mustasa', 'spinach'];
  if (leafy.some(s => name.includes(s))) {
    return allProducts.filter(p => leafy.some(s => p.name.toLowerCase().includes(s)));
  }

  // 7. Fruiting / Stew vegetables
  const fruitingVeggies = ['eggplant', 'talong', 'squash', 'kalabasa', 'tomato', 'kamatis', 'bitter gourd', 'ampalaya', 'string beans', 'sitaw', 'okra', 'sayote', 'chayote'];
  if (fruitingVeggies.some(s => name.includes(s))) {
    return allProducts.filter(p => fruitingVeggies.some(s => p.name.toLowerCase().includes(s)));
  }

  // 8. Root crops
  const roots = ['potato', 'patatas', 'carrot', 'sweet potato', 'kamote', 'radish', 'labanos'];
  if (roots.some(s => name.includes(s))) {
    return allProducts.filter(p => roots.some(s => p.name.toLowerCase().includes(s)));
  }

  // 9. Dessert Fruits
  const dessertFruits = ['banana', 'saba', 'lakatan', 'latundan', 'mango', 'mangga', 'papaya', 'watermelon', 'pakwan', 'pineapple', 'pinya', 'melon', 'apple', 'orange'];
  if (dessertFruits.some(s => name.includes(s))) {
    return allProducts.filter(p => dessertFruits.some(s => p.name.toLowerCase().includes(s)));
  }

  // Fallback: Just return same category if it didn't match any specific grouping
  return allProducts.filter(p => p.category === current.category);
}

export default function Product({
  params,
  initialProducts,
}: {
  params: Promise<{ id: string }>;
  initialProducts?: ProductType[];
}) {
  const { id: encryptedId } = use(params);
  const id = decryptId(encryptedId);
  const { t, language, isTransitioning } = useLanguage();
  const { data: products = [] } = useProducts(initialProducts);
  const { data: newsList = [] } = useNews(10);
  const product = useMemo(() => products.find((p) => p.id === id) || null, [products, id]);

  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [aiReasoning, setAiReasoning] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Fetch AI Reasoning manually on button click to save tokens
  const generateAnalysis = async () => {
    if (!product) return;
    setIsAnalyzing(true);
    try {
      const news = await fetchNews(3); // Get 3 latest news
      const newsContext = news.map(n => `- ${n.title}: ${n.excerpt}`).join("\n");

      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName: product.variant && product.variant !== "Standard" ? `${product.name} (${product.variant})` : product.name,
          currentPrice: product.currentPrice,
          predictedPrice: product.predictedPrice,
          newsContext: newsContext || "No recent news available.",
          language: language,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.reasoning) {
          setAiReasoning(data.reasoning);
        }
      } else {
        console.error("Failed to fetch AI analysis");
      }
    } catch (error) {
      console.error("Error generating analysis:", error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Track daily user interaction for trending algorithm
  useEffect(() => {
    if (!product) return;

    try {
      // Create a unique key per product per day
      const today = new Date().toISOString().split('T')[0];
      const storageKey = `foodcast_viewed_${product.id}_${today}`;

      if (!localStorage.getItem(storageKey)) {
        // Send interaction tracking request
        fetch(`/api/products/${product.id}/interact`, { method: "POST" })
          .then(res => {
            if (res.ok) {
              localStorage.setItem(storageKey, "true");
            }
          })
          .catch(err => console.error("Failed to track interaction", err));
      }
    } catch (e) {
      // Ignore localStorage errors in incognito/restricted mode
    }
  }, [product]);

  const variants = useMemo(() => {
    if (!product) return [];
    return products.filter((p) => p.name === product.name);
  }, [product, products]);


  const smartAlternatives = useMemo(() => {
    if (!product) return [];

    const variantIds = variants.map(v => v.id);
    const relatedProducts = getRelatedProducts(product, products);

    return relatedProducts
      .filter((p) => p.id !== product.id)
      .filter((p) => !variantIds.includes(p.id))
      // Ensure apples-to-apples comparison by matching units
      .filter((p) => p.unit === product.unit)
      // Must be strictly cheaper than the current product
      .filter((p) => p.currentPrice < product.currentPrice)
      // Sort by price ascending to show the absolute cheapest alternatives first
      .sort((a, b) => a.currentPrice - b.currentPrice)
      .slice(0, 3);
  }, [product, variants, products]);

  const suggestedProducts = useMemo(() => {
    if (!product) return [];
    const excludeIds = [product.id, ...variants.map(v => v.id), ...smartAlternatives.map(a => a.id)];
    return products
      .filter((p) => !excludeIds.includes(p.id))
      .filter(
        (p) =>
          p.category === product.category ||
          p.sentiment === product.sentiment
      )
      .slice(0, 4);
  }, [product, variants, smartAlternatives, products]);

  const [chartPeriod, setChartPeriod] = useState("Daily");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isOriginDropdownOpen, setIsOriginDropdownOpen] = useState(false);
  const aiConfidence = useMemo(() => Math.floor(Math.random() * (98 - 85 + 1) + 85), [id]);

  const [forecastRange, setForecastRange] = useState<"3" | "7" | "month" | "all">("all");
  const [mobileForecastExpanded, setMobileForecastExpanded] = useState(false);

  const filteredForecasts = useMemo(() => {
    if (!product || !product.dailyForecast) return [];
    const forecasts = product.dailyForecast;
    if (forecastRange === "3") {
      return forecasts.slice(0, 3);
    }
    if (forecastRange === "7") {
      return forecasts.slice(0, 7);
    }
    if (forecastRange === "month") {
      if (forecasts.length === 0) return [];
      const firstDate = new Date(forecasts[0].date);
      const currentYear = firstDate.getFullYear();
      const currentMonth = firstDate.getMonth();
      return forecasts.filter((f) => {
        const d = new Date(f.date);
        return d.getFullYear() === currentYear && d.getMonth() === currentMonth;
      });
    }
    return forecasts;
  }, [product, forecastRange]);

  /* ─── Slider Logic (Predict style) ──────────── */
  const sliderRef = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(true);

  const checkScroll = () => {
    const el = sliderRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 10);
    setCanRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  const scrollSlider = (dir: "left" | "right") => {
    const el = sliderRef.current;
    if (!el) return;
    const cardWidth = window.innerWidth < 640 ? 200 : 260;
    el.scrollBy({ left: dir === "left" ? -cardWidth : cardWidth, behavior: "smooth" });
  };

  useEffect(() => {
    checkScroll();
    const el = sliderRef.current;
    if (el) {
      el.addEventListener("scroll", checkScroll, { passive: true });
      window.addEventListener("resize", checkScroll);
    }
    return () => {
      el?.removeEventListener("scroll", checkScroll);
      window.removeEventListener("resize", checkScroll);
    };
  }, [suggestedProducts]);

  if (products.length === 0 || isTransitioning) {
    return (
      <>

        <main className="min-h-screen bg-surface pt-20">
          <div className="border-b border-gray-100/50 bg-white/5">
            <div className="max-w-7xl mx-auto px-5 lg:px-10 pt-3 h-10 flex items-center">
              <div className="h-4 w-48 bg-gray-200 rounded-md animate-pulse" />
            </div>
          </div>

          <div className="max-w-7xl mx-auto px-5 lg:px-10 pt-3 sm:py-5">
            {/* Header Skeleton */}
            <div className="bg-primary-900 mb-6 sm:mb-8 rounded-2xl p-5 sm:p-8">
              <div className="flex flex-col sm:flex-row items-center sm:items-end gap-6 sm:gap-10 mb-8">
                <div className="shrink-0 w-25 h-25 sm:w-35 sm:h-35 rounded-xl bg-white/10 animate-pulse border-4 border-white/20" />
                <div className="flex-1 w-full space-y-4">
                  <div className="flex gap-2">
                    <div className="h-6 w-24 bg-white/10 rounded-full animate-pulse" />
                    <div className="h-6 w-20 bg-white/10 rounded-full animate-pulse" />
                  </div>
                  <div className="h-10 sm:h-12 w-3/4 sm:w-1/2 bg-white/20 rounded-xl animate-pulse" />
                  <div className="h-4 w-32 bg-white/10 rounded-md animate-pulse" />
                </div>
              </div>
              <div className="pt-8 border-t border-white/10 space-y-2">
                <div className="h-4 w-full bg-white/10 rounded-md animate-pulse" />
                <div className="h-4 w-5/6 bg-white/10 rounded-md animate-pulse" />
                <div className="h-4 w-4/6 bg-white/10 rounded-md animate-pulse" />
              </div>
            </div>

            <div className="grid lg:grid-cols-12 gap-8 items-start">
              {/* Left Column */}
              <div className="lg:col-span-8 space-y-8">
                {/* Chart Skeleton */}
                <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm h-[400px] flex flex-col">
                  <div className="flex justify-between items-center mb-8">
                    <div className="space-y-2">
                      <div className="h-6 w-48 bg-gray-200 rounded-lg animate-pulse" />
                      <div className="h-4 w-64 bg-gray-100 rounded-md animate-pulse" />
                    </div>
                    <div className="h-8 w-40 bg-gray-100 rounded-xl animate-pulse" />
                  </div>
                  <div className="flex-1 bg-gray-50 rounded-2xl animate-pulse" />
                </div>

                {/* AI Reasoning Skeleton */}
                <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-10 h-10 rounded-xl bg-gray-100 animate-pulse" />
                    <div className="h-6 w-48 bg-gray-200 rounded-lg animate-pulse" />
                  </div>
                  <div className="space-y-3">
                    <div className="h-4 w-full bg-gray-100 rounded-md animate-pulse" />
                    <div className="h-4 w-full bg-gray-100 rounded-md animate-pulse" />
                    <div className="h-4 w-5/6 bg-gray-100 rounded-md animate-pulse" />
                    <div className="h-4 w-4/6 bg-gray-100 rounded-md animate-pulse" />
                  </div>
                </div>
              </div>

              {/* Right Column */}
              <div className="lg:col-span-4 space-y-6">
                {/* Metrics Skeleton */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white rounded-3xl border border-gray-100 p-5 h-32 flex flex-col justify-center gap-3 animate-pulse">
                    <div className="h-4 w-20 bg-gray-100 rounded-md" />
                    <div className="h-8 w-24 bg-gray-200 rounded-lg" />
                  </div>
                  <div className="bg-white rounded-3xl border border-gray-100 p-5 h-32 flex flex-col justify-center gap-3 animate-pulse">
                    <div className="h-4 w-20 bg-gray-100 rounded-md" />
                    <div className="h-8 w-24 bg-gray-200 rounded-lg" />
                  </div>
                </div>

                {/* News Skeleton */}
                <div className="bg-white rounded-3xl border border-gray-100 p-6">
                  <div className="h-5 w-40 bg-gray-200 rounded-lg mb-6 animate-pulse" />
                  <div className="space-y-4">
                    {[1, 2, 3].map(i => (
                      <div key={i} className="flex gap-3">
                        <div className="w-16 h-16 rounded-xl bg-gray-100 animate-pulse shrink-0" />
                        <div className="flex-1 space-y-2">
                          <div className="h-3 w-full bg-gray-200 rounded-md animate-pulse" />
                          <div className="h-3 w-2/3 bg-gray-200 rounded-md animate-pulse" />
                          <div className="h-2 w-20 bg-gray-100 rounded-md animate-pulse" />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>

      </>
    );
  }

  if (!product) {
    return (
      <>

        <main className="pt-20 min-h-screen bg-surface flex flex-col items-center justify-center">
          <div className="text-6xl mb-4">🔍</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            {t("productNotFound")}
          </h1>
          <p className="text-gray-500 mb-6">
            {t("productNotFoundDesc")}
          </p>
          <Link
            href="/Predict"
            className="px-6 py-3 bg-primary-800 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors"
          >
            {t("backToPredict")}
          </Link>
        </main>

      </>
    );
  }

  const priceChange = product.predictedPrice - product.currentPrice;
  const combinedName = product.variant && product.variant !== "Standard" ? `${product.name} (${product.variant})` : product.name;
  const priceChangePercent =
    ((priceChange) / product.currentPrice) * 100;
  const isUp = priceChange >= 0;

  const sentimentIcon =
    product.sentiment === "Bullish" ? (
      <TrendingUp className="w-4 h-4" />
    ) : product.sentiment === "Bearish" ? (
      <TrendingDown className="w-4 h-4" />
    ) : (
      <Minus className="w-4 h-4" />
    );

  const sentimentColor =
    product.sentiment === "Bullish"
      ? "text-positive bg-positive/10"
      : product.sentiment === "Bearish"
        ? "text-negative bg-negative/10"
        : "text-gray-600 bg-gray-100";

  const trendLabel = product.sentiment === "Bullish" ? t("priceRising") : product.sentiment === "Bearish" ? t("priceDropping") : t("stable");


  const uniqueOrigins = Array.from(new Set(variants.map(v => v.origin || "Local")));

  const availableVariantsForOrigin = product
    ? variants.filter(v => (v.origin || "Local") === (product.origin || "Local"))
    : [];

  const getProductForNewOrigin = (newOrigin: string) => {
    if (!product) return null;
    const sameVariety = variants.find(v => (v.origin || "Local") === newOrigin && v.variant === product.variant);
    if (sameVariety) return sameVariety.id;
    const fallback = variants.find(v => (v.origin || "Local") === newOrigin);
    return fallback ? fallback.id : null;
  };

  return (
    <>

      <main id="main-content" className="relative pt-20 min-h-screen bg-surface overflow-hidden">
        {/* ─── Page Top Design ────────────────────────── */}
        <div className="absolute top-0 left-0 right-0 h-[500px] pointer-events-none overflow-hidden" aria-hidden="true">
          {/* Subtle Color Wash */}
          <div className="absolute inset-0 bg-gradient-to-b from-primary-50/30 via-surface/80 to-surface" />

          {/* Animated Atmospheric Orbs */}
          <div className="absolute top-[-10%] left-[15%] w-[45%] h-[60%] bg-accent/8 rounded-full blur-[120px] animate-pulse opacity-60" />
          <div className="absolute top-[5%] right-[10%] w-[35%] h-[50%] bg-orange/5 rounded-full blur-[100px] animate-float opacity-50" style={{ animationDelay: '-3s' }} />
        </div>

        <div className="relative z-10">
          {/* ─── Breadcrumb + Back ──────────────────────── */}
          <div className="border-b border-gray-100/50 backdrop-blur-sm bg-white/5">
            <div className="max-w-7xl mx-auto px-5 lg:px-10 pt-3">
              <div className="flex items-center gap-3">
                <Link
                  href="/Predict"
                  className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-primary-800 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  {t("backToPredict")}
                </Link>
                <span className="text-gray-300" aria-hidden="true">/</span>
                <span className="text-sm font-medium text-gray-900">
                  {product.variant && product.variant !== "Standard" ? `${product.name} (${product.variant})` : product.name}
                </span>
              </div>
            </div>
          </div>

          <div className="max-w-7xl mx-auto px-5 lg:px-10 pt-3 sm:py-5">
            {/* ─── Product Header ──────────────────────────── */}
            {/* ─── Product Header ──────────────────────────── */}
            <ScrollReveal delay={200} className="relative z-40">
              <div className="relative bg-gradient-to-br from-primary-800 to-primary-900 mb-6 sm:mb-8 rounded-2xl sm:rounded-3xl p-4 sm:p-6 lg:p-8 shadow-2xl border border-white/10 overflow-hidden">
                {/* Background Atmospheric Effects */}
                <div className="absolute top-0 right-0 w-64 h-64 bg-accent/20 rounded-full blur-[80px] -mr-20 -mt-20 pointer-events-none" />
                <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/10 rounded-full blur-[60px] -ml-10 -mb-10 pointer-events-none" />

                <div className="relative space-y-4 sm:space-y-6">
                  {/* Top Row: Image + Details */}
                  <div className="flex flex-row gap-4 sm:gap-6 lg:gap-8 items-center sm:items-start">
                    {/* 1. Image */}
                    <div className="shrink-0 relative w-20 h-20 sm:w-28 sm:h-28 lg:w-36 lg:h-36 rounded-xl sm:rounded-2xl bg-white overflow-hidden shadow-xl border-[3px] sm:border-4 border-white/20 transform hover:scale-105 transition-transform duration-500">
                      <Image
                        src={product.image || DEFAULT_PRODUCT_IMAGE}
                        alt={product.name}
                        fill
                        priority
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

                    {/* 2. Details (Title, Badges, Selectors) */}
                    <div className="flex-1 flex flex-col justify-center sm:justify-start min-w-0">
                      {/* Badges */}
                      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-1.5 sm:mb-3">
                        <span className={`inline-flex items-center gap-1 text-[8px] sm:text-[10px] font-bold px-2 sm:px-3 py-1 rounded-full shadow-lg ${sentimentColor} backdrop-blur-md`}>
                          {sentimentIcon}
                          {trendLabel}
                        </span>
                        <span className="text-[8px] sm:text-[10px] font-bold text-accent bg-accent/10 px-2 sm:px-3 py-1 rounded-full border border-accent/20">
                          {t(product.category)}
                        </span>
                      </div>

                      {/* Title */}
                      <h1
                        className="text-2xl sm:text-4xl lg:text-5xl font-bold text-white leading-tight mb-0.5 sm:mb-1 truncate drop-shadow-sm"
                        style={{ fontFamily: "var(--font-display)" }}
                      >
                        {t(product.name)}
                      </h1>

                      <span className="text-white/40 text-[9px] sm:text-[10px] font-mono tracking-widest mb-0 sm:mb-4 block uppercase">
                        NCR-ID: {product.id.split('-')[0]}
                      </span>

                      {/* Selectors - Desktop only (Inline) */}
                      <div className="hidden sm:flex flex-row flex-wrap gap-2 lg:gap-3">
                        {/* Origin Selector */}
                        <div className="relative">
                          <button
                            onClick={() => uniqueOrigins.length > 1 && setIsOriginDropdownOpen(!isOriginDropdownOpen)}
                            className={`flex items-center gap-2 px-3 py-2 lg:px-4 lg:py-2.5 rounded-xl transition-all backdrop-blur-md border shadow-sm ${uniqueOrigins.length > 1
                              ? "bg-white/10 hover:bg-white/20 border-white/20 cursor-pointer"
                              : "bg-white/5 border-white/5 cursor-default"
                              }`}
                          >
                            <span className="text-[10px] text-white/50 font-bold uppercase tracking-widest pr-1">{t("origin")}</span>
                            <span className="text-xs font-bold text-white uppercase">{t(product.origin || "Local")}</span>
                            {uniqueOrigins.length > 1 && (
                              <ChevronDown className={`w-4 h-4 text-white/60 transition-transform ${isOriginDropdownOpen ? 'rotate-180' : ''}`} />
                            )}
                          </button>

                          {uniqueOrigins.length > 1 && isOriginDropdownOpen && (
                            <>
                              <div className="fixed inset-0 z-40" onClick={() => setIsOriginDropdownOpen(false)} />
                              <div className="absolute top-full left-0 mt-2 w-[160px] bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] border border-gray-100 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                                <div className="p-2 space-y-1">
                                  {uniqueOrigins.map((origin) => {
                                    const targetId = getProductForNewOrigin(origin);
                                    return targetId ? (
                                      <Link
                                        key={origin}
                                        href={`/Product/${encryptId(targetId as string)}`}
                                        onClick={() => setIsOriginDropdownOpen(false)}
                                        className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-all ${(product.origin || "Local") === origin
                                          ? "bg-primary-50 text-primary-900 shadow-sm"
                                          : "hover:bg-gray-50 text-gray-600"
                                          }`}
                                      >
                                        <span className="text-xs font-bold uppercase tracking-widest">{t(origin)}</span>
                                        {(product.origin || "Local") === origin && <CheckCircle2 className="w-4 h-4 text-accent" />}
                                      </Link>
                                    ) : null;
                                  })}
                                </div>
                              </div>
                            </>
                          )}
                        </div>

                        {/* Variant Selector */}
                        <div className="relative">
                          <button
                            onClick={() => availableVariantsForOrigin.length > 1 && setIsDropdownOpen(!isDropdownOpen)}
                            className={`flex items-center gap-2 px-3 py-2 lg:px-4 lg:py-2.5 rounded-xl transition-all backdrop-blur-md border shadow-sm ${availableVariantsForOrigin.length > 1
                              ? "bg-white/10 hover:bg-white/20 border-white/20 cursor-pointer"
                              : "bg-white/5 border-white/5 cursor-default"
                              }`}
                          >
                            <span className="text-[10px] text-white/50 font-bold uppercase tracking-widest pr-1">{t("variant")}</span>
                            <span className="text-xs font-bold text-white">{t(product.variant || "Standard")}</span>
                            {availableVariantsForOrigin.length > 1 && (
                              <ChevronDown className={`w-4 h-4 text-white/60 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
                            )}
                          </button>

                          {availableVariantsForOrigin.length > 1 && isDropdownOpen && (
                            <>
                              <div className="fixed inset-0 z-40" onClick={() => setIsDropdownOpen(false)} />
                              <div className="absolute top-full left-0 mt-2 w-[240px] bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] border border-gray-100 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                                <div className="max-h-[400px] overflow-y-auto scrollbar-hide p-2 space-y-1">
                                  {availableVariantsForOrigin.map((v) => (
                                    <Link
                                      key={v.id}
                                      href={`/Product/${encryptId(v.id)}`}
                                      onClick={() => setIsDropdownOpen(false)}
                                      className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-all ${v.id === product.id
                                        ? "bg-primary-50 text-primary-900 shadow-sm"
                                        : "hover:bg-gray-50 text-gray-600"
                                        }`}
                                    >
                                      <div className="flex flex-col">
                                        <span className="text-xs font-bold">{v.variant || "Standard"}</span>
                                        <span className="text-[10px] opacity-60">₱{v.currentPrice.toFixed(2)}{v.unit ? ` / ${v.unit}` : ''}</span>
                                      </div>
                                      {v.id === product.id && <CheckCircle2 className="w-4 h-4 text-accent" />}
                                    </Link>
                                  ))}
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Selectors - Mobile only (Full width row) */}
                  <div className="flex sm:hidden flex-row gap-2 w-full pt-1">
                    {/* Origin */}
                    <div className="relative flex-1">
                      <button
                        onClick={() => uniqueOrigins.length > 1 && setIsOriginDropdownOpen(!isOriginDropdownOpen)}
                        className={`flex items-center justify-between w-full px-3 py-2 rounded-xl transition-all backdrop-blur-md border shadow-sm ${uniqueOrigins.length > 1
                          ? "bg-white/10 hover:bg-white/20 border-white/20 cursor-pointer"
                          : "bg-white/5 border-white/5 cursor-default"
                          }`}
                      >
                        <div className="flex flex-col items-start">
                          <span className="text-[8px] text-white/50 font-bold uppercase tracking-widest">{t("origin")}</span>
                          <span className="text-[10px] font-bold text-white uppercase">{t(product.origin || "Local")}</span>
                        </div>
                        {uniqueOrigins.length > 1 && (
                          <ChevronDown className={`w-3 h-3 text-white/60 transition-transform ${isOriginDropdownOpen ? 'rotate-180' : ''}`} />
                        )}
                      </button>

                      {uniqueOrigins.length > 1 && isOriginDropdownOpen && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setIsOriginDropdownOpen(false)} />
                          <div className="absolute top-full left-0 mt-2 w-[160px] bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] border border-gray-100 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                            <div className="p-2 space-y-1">
                              {uniqueOrigins.map((origin) => {
                                const targetId = getProductForNewOrigin(origin);
                                return targetId ? (
                                  <Link
                                    key={origin}
                                    href={`/Product/${encryptId(targetId as string)}`}
                                    onClick={() => setIsOriginDropdownOpen(false)}
                                    className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-all ${(product.origin || "Local") === origin
                                      ? "bg-primary-50 text-primary-900 shadow-sm"
                                      : "hover:bg-gray-50 text-gray-600"
                                      }`}
                                  >
                                    <span className="text-xs font-bold uppercase tracking-widest">{t(origin)}</span>
                                    {(product.origin || "Local") === origin && <CheckCircle2 className="w-4 h-4 text-accent" />}
                                  </Link>
                                ) : null;
                              })}
                            </div>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Variant */}
                    <div className="relative flex-1">
                      <button
                        onClick={() => availableVariantsForOrigin.length > 1 && setIsDropdownOpen(!isDropdownOpen)}
                        className={`flex items-center justify-between w-full px-3 py-2 rounded-xl transition-all backdrop-blur-md border shadow-sm ${availableVariantsForOrigin.length > 1
                          ? "bg-white/10 hover:bg-white/20 border-white/20 cursor-pointer"
                          : "bg-white/5 border-white/5 cursor-default"
                          }`}
                      >
                        <div className="flex flex-col items-start overflow-hidden">
                          <span className="text-[8px] text-white/50 font-bold uppercase tracking-widest">{t("variant")}</span>
                          <span className="text-[10px] font-bold text-white truncate w-full text-left">{t(product.variant || "Standard")}</span>
                        </div>
                        {availableVariantsForOrigin.length > 1 && (
                          <ChevronDown className={`w-3 h-3 text-white/60 transition-transform ${isDropdownOpen ? 'rotate-180' : ''} shrink-0`} />
                        )}
                      </button>

                      {availableVariantsForOrigin.length > 1 && isDropdownOpen && (
                        <>
                          <div className="fixed inset-0 z-40" onClick={() => setIsDropdownOpen(false)} />
                          <div className="absolute top-full right-0 mt-2 w-[240px] bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.3)] border border-gray-100 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                            <div className="max-h-[400px] overflow-y-auto scrollbar-hide p-2 space-y-1">
                              {availableVariantsForOrigin.map((v) => (
                                <Link
                                  key={v.id}
                                  href={`/Product/${encryptId(v.id)}`}
                                  onClick={() => setIsDropdownOpen(false)}
                                  className={`flex items-center justify-between px-3 py-2.5 rounded-xl transition-all ${v.id === product.id
                                    ? "bg-primary-50 text-primary-900 shadow-sm"
                                    : "hover:bg-gray-50 text-gray-600"
                                    }`}
                                >
                                  <div className="flex flex-col">
                                    <span className="text-xs font-bold">{v.variant || "Standard"}</span>
                                    <span className="text-[10px] opacity-60">₱{v.currentPrice.toFixed(2)}{v.unit ? ` / ${v.unit}` : ''}</span>
                                  </div>
                                  {v.id === product.id && <CheckCircle2 className="w-4 h-4 text-accent" />}
                                </Link>
                              ))}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Description - Full width bottom */}
                  <div className="mt-2 sm:mt-4 pt-3 sm:pt-4 border-t border-white/10">
                    {(() => {
                      try {
                        const desc = typeof product.description === "string"
                          ? JSON.parse(product.description)
                          : product.description;

                        if (desc && typeof desc === "object" && desc.short_description) {
                          const parts: string[] = [];
                          const productName = product.variant && product.variant !== "Standard" ? `${product.name} (${product.variant})` : product.name;

                          if (desc.health_benefits && desc.health_benefits.length > 0) {
                            const benefits = desc.health_benefits as string[];
                            if (benefits.length === 1) {
                              parts.push(`**${productName}** ${t("highlyRegardedFor")} ${benefits[0].toLowerCase()}.`);
                            } else {
                              const last = benefits[benefits.length - 1].toLowerCase();
                              const rest = benefits.slice(0, -1).map((b: string) => b.toLowerCase()).join(", ");
                              parts.push(`**${productName}** ${t("highlyRegardedFor")} ${rest}, ${t("andWord")} ${last}.`);
                            }
                          } else if (desc.short_description) {
                            parts.push(desc.short_description);
                          } else {
                            parts.push(`**${productName}** ${t("premiumQuality")} ${t(product.category).toLowerCase()} ${t("productWord")}.`);
                          }

                          if (desc.recommended_uses && desc.recommended_uses.length > 0) {
                            const uses = desc.recommended_uses as string[];
                            if (uses.length === 1) {
                              parts.push(`${t("frequentlyFeaturedIn")} ${uses[0].toLowerCase()}.`);
                            } else {
                              const last = uses[uses.length - 1].toLowerCase();
                              const rest = uses.slice(0, -1).map((u: string) => u.toLowerCase()).join(", ");
                              parts.push(`${t("frequentlyFeaturedIn")} ${rest}, ${t("andWord")} ${last}.`);
                            }
                          }

                          if (desc.consumer_segment) {
                            parts.push(`${t("excellentChoiceFor")} ${desc.consumer_segment.toLowerCase()} ${t("consumersWord")}.`);
                          }

                          return (
                            <p className="text-white/80 text-[11px] sm:text-sm lg:text-[15px] leading-relaxed max-w-5xl">
                              {parts.map((part, index) => (
                                <span key={index}>
                                  {part.split("**").map((text, i) => (
                                    i % 2 === 1 ? <strong key={i} className="text-white font-semibold">{text}</strong> : text
                                  ))}
                                  {index < parts.length - 1 ? " " : ""}
                                </span>
                              ))}
                            </p>
                          );
                        }
                      } catch {
                        // Fallback
                      }

                      return (
                        <p className="text-white/80 text-[11px] sm:text-sm lg:text-[15px] leading-relaxed max-w-5xl">
                          {product.description}
                        </p>
                      );
                    })()}

                    {/* Inherited Tags */}
                    {(() => {
                      const tags = getInheritedTags(product.name, newsList);
                      if (tags.length === 0) return null;
                      
                      const tagColors = [
                        "bg-blue-500/20 text-blue-100 border-blue-400/30 hover:bg-blue-500/40",
                        "bg-amber-500/20 text-amber-100 border-amber-400/30 hover:bg-amber-500/40",
                        "bg-emerald-500/20 text-emerald-100 border-emerald-400/30 hover:bg-emerald-500/40",
                        "bg-rose-500/20 text-rose-100 border-rose-400/30 hover:bg-rose-500/40",
                        "bg-violet-500/20 text-violet-100 border-violet-400/30 hover:bg-violet-500/40",
                        "bg-cyan-500/20 text-cyan-100 border-cyan-400/30 hover:bg-cyan-500/40",
                        "bg-orange-500/20 text-orange-100 border-orange-400/30 hover:bg-orange-500/40",
                        "bg-teal-500/20 text-teal-100 border-teal-400/30 hover:bg-teal-500/40",
                      ];

                      return (
                        <div className="mt-4 pt-1">
                          <h4 className="text-[10px] font-bold text-white/50 uppercase tracking-widest mb-2 flex items-center gap-1.5">
                            <Tag className="w-3 h-3" />
                            {t("relatedTags") || "Related Tags"}
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {tags.map((tag, idx) => (
                              <Link
                                key={idx}
                                href={`/tags/${encodeURIComponent(tag)}`}
                                className={`px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest rounded-md border transition-colors ${tagColors[idx % tagColors.length]}`}
                              >
                                {tag}
                              </Link>
                            ))}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              </div>
            </ScrollReveal>

            {/* ─── Main Content Layout (Dashboard Style) ──────── */}
            <div className="grid lg:grid-cols-12 gap-8 items-start">
              {/* Left Column: Forecast & Core Stats */}
              <div className="lg:col-span-8 space-y-8">
                {/* Price Forecast Chart */}
                <ScrollReveal>
                  <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm hover:shadow-md transition-shadow">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
                      <div>
                        <h2
                          className="text-2xl sm:text-2xl font-bold text-gray-900 mb-1"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          {t("marketPriceForecast")}
                        </h2>
                        <p className="text-gray-500 text-xs sm:text-sm">
                          {t("marketPriceForecastDesc")}
                        </p>
                      </div>
                      <div className="flex items-center p-1 bg-gray-50 rounded-xl border border-gray-100 w-fit">
                        {["Daily", "Weekly", "Monthly"].map((period) => (
                          <button
                            key={period}
                            onClick={() => setChartPeriod(period)}
                            className={`px-3 sm:px-4 py-1.5 sm:py-2 text-[10px] sm:text-xs font-bold rounded-lg transition-all ${chartPeriod === period ? "bg-white text-primary-800 shadow-sm border border-gray-100" : "text-gray-400 hover:text-gray-600"}`}
                          >
                            {t(period.toLowerCase() as any)}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="relative">
                      <ForecastChart
                        data={product.forecastData}
                        showGrid
                        showLegend
                        productName={product.variant && product.variant !== "Standard" ? `${product.name} (${product.variant})` : product.name}
                        period={chartPeriod}
                      />
                    </div>
                  </div>
                </ScrollReveal>



                {/* AI Market Analysis */}
                <ScrollReveal delay={150}>
                  <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
                    <div className="flex items-center justify-between gap-3 mb-8">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-positive/10 flex items-center justify-center text-positive shadow-inner">
                          <Activity className="w-5 h-5" />
                        </div>
                        <div>
                          <h2
                            className="text-lg font-bold text-gray-900"
                            style={{ fontFamily: "var(--font-display)" }}
                          >
                            {t("aiMarketAnalysis")}
                          </h2>
                          <p className="text-[10px] text-gray-500 font-bold uppercase tracking-tighter">
                            {t("aiMarketAnalysisDesc")}
                          </p>
                        </div>
                      </div>
                      <div className="hidden sm:flex flex-col items-end">
                        <div className="flex items-center gap-1.5 px-3 py-1 bg-accent/10 border border-accent/20 rounded-full">
                          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                          <span className="text-[10px] font-bold text-accent uppercase tracking-wider">
                            {aiConfidence}% Confidence
                          </span>
                        </div>
                        <span className="text-[8px] text-gray-400 font-bold mt-1 uppercase">{t("updatedAgo")}</span>
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-8 items-stretch">
                      {/* Market Reasoning */}
                      <div className="flex flex-col">
                        <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">
                          {t("marketReasoning")}
                        </h3>
                        <div className="bg-gray-50 rounded-2xl p-6 border border-gray-100 h-full relative">
                          {isAnalyzing ? (
                            <div className="flex flex-col items-center justify-center h-full gap-3 opacity-50 min-h-[120px]">
                              <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                              <span className="text-xs font-medium text-gray-500">{t("aiAnalyzing")}</span>
                            </div>
                          ) : aiReasoning ? (
                            <p className="text-sm text-gray-600 leading-relaxed text-justify animate-in fade-in duration-500">
                              {aiReasoning}
                            </p>
                          ) : (
                            <div className="flex flex-col h-full gap-4 relative min-h-[120px]">
                              <p className="text-sm text-gray-600 leading-relaxed text-justify">
                                {t("aiFallbackIntro")} <span className="font-bold">{product.variant && product.variant !== "Standard" ? `${t(product.name)} (${product.variant})` : t(product.name)}</span> {t("showsA")}
                                <span className="font-bold">{isUp ? t("strongUpward") : t("moderateDownward")}</span> {t("trend")}
                                {isUp ? t("supplyConstraints") : t("inflowHarvests")}
                              </p>

                              <button
                                onClick={generateAnalysis}
                                className="mt-auto w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-primary-50 text-primary-800 font-bold text-xs rounded-xl border border-primary-100 hover:bg-primary-100 transition-colors"
                              >

                                {t("generateAnalysis")}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Daily Forecast */}
                      <div className="flex flex-col h-full">
                        {/* Interactive date range filters replacing static title */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pr-2 border-b border-gray-50 pb-4">
                          <div className="flex items-center p-1 bg-gray-50 rounded-xl border border-gray-100 w-fit">
                            {[
                              { label: "3 Days", value: "3" },
                              { label: "7 Days", value: "7" },
                              { label: "This Month", value: "month" },
                              { label: "All Time", value: "all" },
                            ].map((item) => (
                              <button
                                key={item.value}
                                onClick={() => setForecastRange(item.value as any)}
                                className={`px-2.5 py-1.5 text-[10px] font-bold rounded-lg transition-all ${forecastRange === item.value
                                  ? "bg-white text-primary-800 shadow-sm border border-gray-100"
                                  : "text-gray-400 hover:text-gray-600"
                                  }`}
                              >
                                {item.label}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Collapsible dropdown button for mobile view only */}
                        <div className="block md:hidden mb-4">
                          <button
                            onClick={() => setMobileForecastExpanded(!mobileForecastExpanded)}
                            className="w-full flex items-center justify-between p-2 bg-white hover:bg-gray-50 border border-gray-100 rounded-2xl shadow-sm transition-all text-left group active:scale-[0.99]"
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center text-accent">
                                <Calendar className="w-5 h-5" />
                              </div>
                              <span className="text-xs font-bold text-gray-900">
                                {t("viewDailyForecast")}
                              </span>
                            </div>
                            <ChevronDown
                              className={`w-5 h-5 text-gray-400 group-hover:text-gray-600 transition-transform duration-300 ${mobileForecastExpanded ? "rotate-180" : ""
                                }`}
                            />
                          </button>
                        </div>

                        {/* Scrollable list container - limited to 5 rows and scrollable on mobile, absolute on desktop */}
                        <div className={`flex-1 relative ${mobileForecastExpanded ? "block animate-in fade-in slide-in-from-top-4 duration-300" : "hidden md:block"} min-h-[300px] md:min-h-0`}>
                          <div className="max-h-[300px] overflow-y-auto md:max-h-none md:absolute md:inset-0 space-y-3 scrollbar-hide pr-2">
                            {filteredForecasts.map((forecast, i) => {
                              const dateObj = new Date(forecast.date);
                              const dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
                              const isExpanded = expandedDate === forecast.date;
                              return (
                                <div
                                  key={i}
                                  onClick={() => setExpandedDate(isExpanded ? null : forecast.date)}
                                  className={`group flex flex-col p-4 rounded-2xl border transition-colors cursor-pointer ${isExpanded ? "border-accent/40 bg-gray-50" : "border-gray-100 hover:border-accent/40 hover:bg-gray-50"}`}
                                >
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <Calendar className={`w-3.5 h-3.5 ${isExpanded ? "text-accent" : "text-gray-400"}`} />
                                      <span className={`text-xs font-bold ${isExpanded ? "text-gray-900" : "text-gray-700"}`}>{dateStr}</span>
                                    </div>
                                    <span className="text-xs font-black text-gray-900 tabular-nums">
                                      ₱{forecast.predicted_price.toFixed(2)}
                                      {product.unit && <span className="text-[10px] text-gray-500 font-medium ml-0.5">/ {product.unit}</span>}
                                    </span>
                                  </div>
                                  {isExpanded && (
                                    <div className="text-[10px] text-gray-500 leading-relaxed border-t border-gray-100/50 pt-3 mt-3 animate-in fade-in slide-in-from-top-2 duration-200">
                                      {forecast.reasoning}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </ScrollReveal>
              </div>

              {/* Side Column (Market Pulse) */}
              <div className="lg:col-span-4 space-y-5">
                {/* Price Overview Stats */}
                <ScrollReveal delay={100}>
                  <div className="grid grid-cols-2 sm:grid-cols-2 gap-4">
                    {[
                      {
                        label: t("marketPrice"),
                        value: `₱${product.currentPrice.toFixed(2)}${product.unit ? ` / ${product.unit}` : ''}`,
                        icon: <BarChart3 className="w-4 h-4" />,
                        sub: t("liveNCRRate"),
                        color: "text-primary-800",
                        bg: "bg-primary-50/50",
                        border: "border-primary-100",
                      },
                      {
                        label: t("volatility"),
                        value: `${isUp ? "+" : ""}${priceChangePercent.toFixed(1)}%`,
                        icon: isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />,
                        sub: t("weeklyChange"),
                        color: isUp ? "text-positive" : "text-negative",
                        bg: isUp ? "bg-positive/5" : "bg-negative/5",
                        border: isUp ? "border-positive/20" : "border-negative/20",
                      },
                    ].map((stat) => (
                      <div
                        key={stat.label}
                        className={`rounded-2xl border ${stat.border} p-5 shadow-sm transition-all hover:shadow-md ${stat.bg}`}
                      >
                        <div className="flex items-center gap-2 text-gray-500 mb-3">
                          <span className="p-1.5 rounded-lg bg-white shadow-sm">{stat.icon}</span>
                          <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">
                            {stat.label}
                          </span>
                        </div>
                        <div className={`text-xl sm:text-2xl font-black ${stat.color}`}>
                          {stat.value}
                        </div>
                        <div className="text-[10px] font-bold text-gray-400 mt-1 uppercase tracking-tight opacity-70">{stat.sub}</div>
                      </div>
                    ))}
                  </div>
                </ScrollReveal>
                <ScrollReveal delay={200}>
                  {(() => {
                    const isBullish = product.sentiment === "Bullish";
                    const isBearish = product.sentiment === "Bearish";
                    const insight = isBullish
                      ? {
                        title: t("buyingOpportunity"),
                        message: `${t("pricesRisingBy")} ${priceChangePercent.toFixed(1)}%. ${t("marketsTighter")}`,
                        action: "buyNow",
                        recommendation: t("increaseStock"),
                        status: t("suggestedBuy"),
                        statusBg: "bg-positive/10 text-positive",
                        pulseColor: "bg-positive",
                        glowColor: "from-positive/10 to-accent/5",
                      }
                      : isBearish
                        ? {
                          title: t("waitToPurchase"),
                          message: `${t("pricesDroppingBy")} ${Math.abs(priceChangePercent).toFixed(1)}%.`,
                          action: "waitAction",
                          recommendation: t("waitForDrop"),
                          status: t("holdOff"),
                          statusBg: "bg-negative/10 text-negative",
                          pulseColor: "bg-negative",
                          glowColor: "from-negative/10 to-accent/5",
                        }
                        : {
                          title: t("stableMarket"),
                          message: t("normalSeasonal"),
                          action: "noAction",
                          recommendation: t("continueNormal"),
                          status: t("monitor"),
                          statusBg: "bg-gray-100 text-gray-600",
                          pulseColor: "bg-gray-400",
                          glowColor: "from-gray-100 to-transparent",
                        };

                    return (
                      <div className="relative group">
                        <div className={`absolute inset-0 bg-gradient-to-br ${insight.glowColor} opacity-50 rounded-[2rem] blur-xl transition-opacity duration-700`} />
                        <div className="relative bg-white/70 backdrop-blur-xl border border-white/80 rounded-[2rem] p-6 sm:p-8 shadow-xl flex flex-col items-center text-center overflow-hidden">
                          <div className="relative mb-6">
                            <div className={`w-20 h-20 rounded-full ${insight.pulseColor}/20 flex items-center justify-center animate-pulse`}>
                              <div className={`w-10 h-10 rounded-full ${insight.pulseColor} shadow-lg flex items-center justify-center`}>
                                {isBullish ? <TrendingUp className="w-5 h-5 text-white" /> : isBearish ? <TrendingDown className="w-5 h-5 text-white" /> : <Minus className="w-5 h-5 text-white" />}
                              </div>
                            </div>
                            <div className={`absolute inset-0 rounded-full border-2 border-dashed ${insight.pulseColor}/30 animate-spin-slow`} />
                          </div>

                          <span className={`px-4 py-1 rounded-full text-[10px] font-black uppercase tracking-widest shadow-sm mb-3 ${insight.statusBg}`}>
                            {insight.status}
                          </span>

                          <h3 className="text-xl font-bold text-gray-900 mb-3" style={{ fontFamily: "var(--font-display)" }}>
                            {insight.title}
                          </h3>

                          <p className="text-gray-600 text-sm leading-relaxed mb-6">
                            {insight.message} <span className="font-bold text-gray-900">{insight.recommendation}</span>
                          </p>

                          <div className="w-full pt-6 border-t border-gray-100 flex flex-col gap-4">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t("nextAction")}</span>
                              <span className="text-xs font-black text-primary-800 uppercase tracking-tight">{t(insight.action)}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t("confidenceLevel")}</span>
                              <div className="flex gap-1">
                                {[1, 2, 3, 4, 5].map((s) => (
                                  <div key={s} className={`w-2 h-2 rounded-full ${s <= 4 ? "bg-accent" : "bg-gray-200"}`} />
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </ScrollReveal>

                {/* Alternatives */}
                {smartAlternatives.length > 0 && (
                  <ScrollReveal delay={400}>
                    <div className="bg-primary-900 rounded-3xl p-6 shadow-xl relative overflow-hidden">
                      <div className="absolute top-0 right-0 w-24 h-24 bg-accent/20 rounded-full blur-2xl -mr-12 -mt-12" />

                      <div className="relative flex items-center gap-3 mb-5">
                        <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center text-accent">
                          <Sparkles className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-white" style={{ fontFamily: "var(--font-display)" }}>
                            {t("smartAlternatives")}
                          </h3>
                          <p className="text-[10px] text-white/50 font-bold uppercase tracking-tighter">{t("betterValue")}</p>
                        </div>
                      </div>

                      <div className="relative space-y-2">
                        {smartAlternatives.map(a => (
                          <Link
                            key={a.id}
                            href={`/Product/${encryptId(a.id)}`}
                            className="group flex items-center justify-between p-3.5 rounded-2xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-accent/40 transition-all duration-300"
                          >
                            <div className="flex items-center gap-3">
                              <div className="relative w-9 h-9 rounded-xl overflow-hidden border border-white/10 shrink-0 bg-white/5">
                                <Image
                                  src={a.image || DEFAULT_PRODUCT_IMAGE}
                                  alt={a.name}
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
                                <div className="text-xs font-bold text-white group-hover:text-accent transition-colors">
                                  {a.variant && a.variant !== "Standard" ? `${a.name} (${a.variant})` : a.name}
                                </div>
                                <div className="text-[9px] text-white/40 font-black uppercase tracking-widest">₱{a.currentPrice.toFixed(2)}</div>
                              </div>
                            </div>
                            <ArrowRight className="w-3.5 h-3.5 text-white/30 group-hover:text-accent group-hover:translate-x-1 transition-all" />
                          </Link>
                        ))}
                      </div>
                    </div>
                  </ScrollReveal>
                )}
              </div>
            </div>

            {/* ─── Suggested Products ───────────────────────── */}
            {suggestedProducts.length > 0 && (
              <section aria-labelledby="suggested-heading" className="mt-16 sm:mt-24">
                <ScrollReveal className="flex items-end justify-between mb-6">
                  <div>
                    <h2
                      id="suggested-heading"
                      className="text-xl sm:text-2xl font-bold text-gray-900"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      {t("suggestedProducts")}
                    </h2>
                    <p className="text-gray-500 text-xs mt-1">{t("suggestedProductsDesc")}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Link
                      href="/MarketData"
                      className="flex items-center gap-1.5 text-xs sm:text-sm font-medium text-primary-800 hover:text-accent transition-colors"
                    >
                      {t("viewAll")} <ArrowRight className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                    </Link>
                  </div>
                </ScrollReveal>

                {/* Slider Container */}
                <div
                  ref={sliderRef}
                  className="flex gap-4 sm:gap-6 overflow-x-auto pt-4 pb-12 px-10 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
                  aria-label="Suggested products slider"
                  role="region"
                >
                  {(() => {
                    const groupedMap = new Map<string, any>();

                    suggestedProducts.forEach(p => {
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

                    return Array.from(groupedMap.values()).map((product, i) => (
                      <div
                        key={i}
                        className="snap-start shrink-0 w-[180px] sm:w-[240px] lg:w-[280px]"
                      >
                        <ScrollReveal delay={i * 80} animation="fade-up" className="h-full">
                          <ProductCard
                            name={product.name}
                            image={product.image}
                            category={product.category}
                            variants={product.variants}
                            unit={product.unit}
                            compact
                          />
                        </ScrollReveal>
                      </div>
                    ));
                  })()}
                </div>
              </section>
            )}
          </div>
        </div>
      </main>

    </>
  );
}
