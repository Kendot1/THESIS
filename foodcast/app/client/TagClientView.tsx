"use client";
import { useState, useMemo, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Tag, MoreHorizontal, ChevronLeft, ChevronRight } from "lucide-react";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { useProducts, useNews } from "../lib/hooks";
import { DEFAULT_PRODUCT_IMAGE } from "../lib/data";
import { encryptId } from "../../lib/idCipher";
import { getInheritedTags } from "../lib/tags";
import ScrollReveal from "../components/ScrollReveal";
import ProductCard from "../components/ProductCard";
import NewsCard from "../components/NewsCard";

export default function TagClientView({ tagId }: { tagId: string }) {
  const tag = decodeURIComponent(tagId);
  const { t, isTransitioning } = useLanguage();
  const { data: products = [], isLoading: isLoadingProducts } = useProducts();
  const { data: newsList = [], isLoading: isLoadingNews } = useNews(50);

  const productsRef = useRef<HTMLDivElement>(null);
  const scrollProducts = (direction: "left" | "right") => {
    if (productsRef.current) {
      const cardWidth = window.innerWidth < 640 ? 216 : 260; // 200px width + 16px gap
      productsRef.current.scrollBy({ left: direction === "left" ? -cardWidth : cardWidth, behavior: "smooth" });
    }
  };

  const newsRef = useRef<HTMLDivElement>(null);
  const scrollNews = (direction: "left" | "right") => {
    if (newsRef.current) {
      const cardWidth = window.innerWidth < 640 ? 300 : 380;
      newsRef.current.scrollBy({ left: direction === "left" ? -cardWidth : cardWidth, behavior: "smooth" });
    }
  };

  const isLoading = isLoadingProducts || isLoadingNews || isTransitioning;

  // Find all products that have this tag via getInheritedTags (same logic used on product pages)
  const productsWithThisTag = useMemo(() => {
    const tagUpper = tag.trim().toUpperCase();
    const uniqueNames = new Set<string>();
    products.forEach((p) => {
      if (uniqueNames.has(p.name)) return;
      const tags = getInheritedTags(p.name, newsList);
      if (tags.some((t) => t === tagUpper)) {
        uniqueNames.add(p.name);
      }
    });
    return uniqueNames;
  }, [products, newsList, tag]);

  // News related to this tag: ONLY articles that have this exact tag as a keyword
  const relatedNews = useMemo(() => {
    const tagUpper = tag.trim().toUpperCase();
    return newsList.filter((n) => {
      // Direct keyword match only
      return n.keywords?.some((k) => k.trim().toUpperCase() === tagUpper);
    });
  }, [newsList, tag]);

  // Group products affected by this tag for the ProductCard
  const groupedProducts = useMemo(() => {
    // Combine: products that inherit this tag + products from related news
    const allProductNames = new Set<string>(productsWithThisTag);
    relatedNews.forEach((n) => {
      n.affectedProducts?.forEach((name) => allProductNames.add(name));
    });

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

    products
      .filter((p) => allProductNames.has(p.name))
      .forEach((p) => {
        if (!groupedMap.has(p.name)) {
          groupedMap.set(p.name, {
            name: p.name,
            category: p.category,
            image: p.image,
            unit: p.unit,
            variants: [],
          });
        }
        groupedMap.get(p.name)!.variants.push({
          id: p.id,
          variant: p.variant,
          origin: p.origin,
          image: p.image,
          currentPrice: p.currentPrice,
          predictedPrice: p.predictedPrice,
        });
      });

    return Array.from(groupedMap.values());
  }, [relatedNews, products, productsWithThisTag]);

  if (isLoading) {
    return (
      <main className="min-h-screen bg-surface">
        {/* Skeleton Header */}
        <section className="relative pt-28 pb-12 sm:pt-32 sm:pb-16 bg-primary-900 overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-accent/10 rounded-full blur-[120px] -mr-48 -mt-48 pointer-events-none" />
          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <div className="h-4 w-24 bg-white/10 rounded-md mb-8 animate-pulse" />
            <div className="h-6 w-16 bg-white/10 rounded-full mb-4 animate-pulse" />
            <div className="h-10 sm:h-14 w-64 sm:w-96 bg-white/20 rounded-xl mb-3 animate-pulse" />
            <div className="h-4 w-48 sm:w-72 bg-white/10 rounded-lg animate-pulse" />
          </div>
        </section>

        <div className="max-w-7xl mx-auto px-5 lg:px-10 py-12 space-y-16">
          {/* Skeleton News */}
          <section>
            <div className="flex items-center gap-3 mb-8">
              <div className="h-8 w-48 bg-gray-200 rounded-lg animate-pulse" />
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3].map(i => (
                <div key={i} className="group flex gap-4 p-4 bg-white rounded-2xl border border-gray-100">
                  <div className="relative w-20 h-20 rounded-xl bg-gray-100 animate-pulse shrink-0" />
                  <div className="flex-1 space-y-2 py-1">
                    <div className="h-4 w-full bg-gray-200 rounded-md animate-pulse" />
                    <div className="h-3 w-3/4 bg-gray-100 rounded-md animate-pulse" />
                    <div className="h-3 w-1/2 bg-gray-100 rounded-md animate-pulse" />
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Skeleton Products */}
          <section>
            <div className="flex items-center gap-3 mb-8">
              <div className="h-8 w-48 bg-gray-200 rounded-lg animate-pulse" />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-6">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="bg-white rounded-[1.5rem] border border-gray-100 p-4 h-[220px] flex flex-col">
                  <div className="h-24 w-full bg-gray-100 rounded-xl mb-4 animate-pulse" />
                  <div className="h-4 w-3/4 bg-gray-200 rounded-lg mb-2 animate-pulse" />
                  <div className="h-3 w-1/2 bg-gray-100 rounded-md animate-pulse" />
                  <div className="mt-auto flex justify-between items-end">
                    <div className="h-4 w-12 bg-gray-100 rounded-lg animate-pulse" />
                    <div className="h-6 w-16 bg-gray-100 rounded-xl animate-pulse" />
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
    <main className="min-h-screen bg-surface">
      {/* Header */}
      <section className="relative pt-28 pb-12 sm:pt-32 sm:pb-16 bg-primary-900 overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-accent/10 rounded-full blur-[120px] -mr-48 -mt-48 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
          <div className="mb-6 sm:mb-8">
            <Link
              href="/News"
              className="inline-flex items-center gap-1.5 text-white/50 hover:text-white text-sm transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              {t("latestNews")}
            </Link>
          </div>

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-white/10 text-white/70 mb-4">
            <Tag className="w-3.5 h-3.5" />
            {t("tagIndicator")}
          </div>

          <h1
            className="text-3xl md:text-5xl font-black text-white tracking-tight mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {tag}
          </h1>
          <p className="text-white/50 text-sm sm:text-base max-w-2xl">
            {t("tagDesc")}
          </p>
        </div>
      </section>

      <div className="max-w-7xl mx-auto px-5 lg:px-10 py-12 space-y-16">
        {/* Related News */}
        <ScrollReveal>
          <section>
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2
                  className="text-xl font-bold text-gray-900 leading-tight"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {t("latestNews")}
                </h2>
                <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mt-0.5">
                  {relatedNews.length} {relatedNews.length === 1 ? t("articleCount") : t("articlesCount")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => scrollNews("left")}
                  className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                    hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                  aria-label="Scroll news left"
                >
                  <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                </button>
                <button
                  onClick={() => scrollNews("right")}
                  className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                    hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                  aria-label="Scroll news right"
                >
                  <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                </button>
              </div>
            </div>

            {relatedNews.length === 0 ? (
              <div className="text-center py-16 text-gray-400 text-sm bg-white rounded-[2rem] border border-gray-100">
                {t("noNewsForTag")}
              </div>
            ) : (
              <div
                ref={newsRef}
                className="news-slider flex gap-4 sm:gap-6 overflow-x-auto pt-2 pb-12 px-10 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
              >
                {relatedNews.map((article, i) => (
                  <div
                    key={article.id}
                    className="snap-start shrink-0 w-[280px] sm:w-[350px]"
                    style={{ animationDelay: `${i * 100}ms` }}
                  >
                    <NewsCard {...article} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </ScrollReveal>

        {/* Related Products */}
        <ScrollReveal delay={100}>
          <section>
            <div className="flex items-center justify-between mb-8">
              <div>
                <h2
                  className="text-xl font-bold text-gray-900 leading-tight"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  {t("affectedProducts")}
                </h2>
                <div className="text-xs font-bold text-gray-400 uppercase tracking-widest mt-0.5">
                  {groupedProducts.length} {groupedProducts.length === 1 ? t("product") : t("products")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => scrollProducts("left")}
                  className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                    hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                  aria-label="Scroll products left"
                >
                  <ChevronLeft className="w-4 h-4 sm:w-5 sm:h-5" />
                </button>
                <button
                  onClick={() => scrollProducts("right")}
                  className="p-1.5 sm:p-2 rounded-xl bg-white border border-gray-200 text-gray-600
                    hover:bg-primary-50 hover:border-primary-200 hover:text-primary-800 transition-all"
                  aria-label="Scroll products right"
                >
                  <ChevronRight className="w-4 h-4 sm:w-5 sm:h-5" />
                </button>
              </div>
            </div>

            {groupedProducts.length === 0 ? (
              <div className="text-center py-16 text-gray-400 text-sm bg-white rounded-[2rem] border border-gray-100">
                {t("noProductsForTag")}
              </div>
            ) : (
              <div
                ref={productsRef}
                className="flex gap-4 sm:gap-6 overflow-x-auto pt-2 pb-12 px-10 -mx-10 scroll-px-10 snap-x snap-mandatory scrollbar-hide"
              >
                {groupedProducts.map((product, idx) => (
                  <div
                    key={idx}
                    className="snap-start shrink-0 w-[200px] sm:w-[240px] lg:w-[280px]"
                  >
                    <ProductCard
                      name={product.name}
                      image={product.image}
                      category={product.category}
                      variants={product.variants}
                      unit={product.unit}
                      compact
                    />
                  </div>
                ))}
              </div>
            )}
          </section>
        </ScrollReveal>
      </div>
    </main>
  );
}
