"use client";
import React, { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, Eye } from "lucide-react";
import { DEFAULT_PRODUCT_IMAGE } from "../lib/data";

interface ProductVariant {
  id: string;
  variant: string;
  origin?: string;
  image?: string;
  currentPrice: number;
  predictedPrice: number;
}

interface ProductCardProps {
  name: string;
  emoji: string;
  image: string;
  category: string;
  variants: ProductVariant[];
  compact?: boolean;
  initialVariantId?: string;
}

const ProductCard = ({
  name,
  emoji,
  image,
  category,
  variants,
  compact = false,
  initialVariantId,
}: ProductCardProps) => {
  const [selectedVariantId, setSelectedVariantId] = useState(initialVariantId || variants[0]?.id);

  const getCleanVariant = (vStr: string) => {
    const match = vStr.match(/\((.*?)\)/);
    return match ? match[1] : vStr;
  };

  // Sync state if initialVariantId changes from parent
  useEffect(() => {
    if (initialVariantId) {
      setSelectedVariantId(initialVariantId);
    }
  }, [initialVariantId]);
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [isOriginDropdownOpen, setIsOriginDropdownOpen] = useState(false);

  const selectedVariant = variants.find(v => v.id === selectedVariantId) || variants[0];
  const { currentPrice, predictedPrice, variant, origin, id } = selectedVariant;

  const currentOrigin = origin || "Local";
  const uniqueOrigins = Array.from(new Set(variants.map(v => v.origin || "Local")));
  const availableVariantsForOrigin = variants.filter(v => (v.origin || "Local") === currentOrigin);

  const handleOriginChange = (newOrigin: string) => {
    const sameVariety = variants.find(v => (v.origin || "Local") === newOrigin && v.variant === variant);
    const fallback = variants.find(v => (v.origin || "Local") === newOrigin);
    if (sameVariety) {
      setSelectedVariantId(sameVariety.id);
    } else if (fallback) {
      setSelectedVariantId(fallback.id);
    }
  };

  const change = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
  const isUp = change >= 0;

  return (
    <div
      className="product-card group relative flex flex-col h-full bg-white rounded-[2rem] border-2 border-gray-100/80 
        overflow-hidden transition-all duration-500 ease-out
        md:hover:shadow-[0_25px_60px_rgba(0,0,0,0.08)] md:hover:border-primary-100/50
        active:scale-[0.98] active:bg-gray-50/30"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Row 1: Product Image Container (Flush with edges) */}
      <div className={`relative overflow-hidden bg-gray-50 transition-all duration-700 ${compact ? "h-[140px] mb-4" : "h-[180px] mb-5"}`}>
        <img
          key={selectedVariant.image || image || DEFAULT_PRODUCT_IMAGE} // Force re-render of img tag to trigger animation if needed, or at least change instantly
          src={selectedVariant.image || image || DEFAULT_PRODUCT_IMAGE}
          alt={name}
          loading="lazy"
          decoding="async"
          className="w-full h-full object-cover transition-transform duration-1000 md:group-hover:scale-110"
          onError={(e) => {
            const target = e.target as HTMLImageElement;
            if (target.src !== DEFAULT_PRODUCT_IMAGE) {
              target.src = DEFAULT_PRODUCT_IMAGE;
            }
          }}
        />

        {/* Rate Change Badge (Pill Style) */}
        <div className="absolute top-3 right-3 z-10">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full backdrop-blur-md border border-white/20 shadow-sm ${isUp ? "bg-white/90 text-positive" : "bg-white/90 text-negative"}`}>
            <span className="text-[10px] font-black uppercase tracking-wider">
              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Sentiment Dot (Top Left) */}
        <div className="absolute top-4 left-4 z-10 transition-transform duration-300 md:group-hover:scale-110">
          <div className={`w-3 h-3 rounded-full border-2 border-white shadow-sm ${isUp ? "bg-positive" : "bg-negative"}`} />
        </div>
      </div>

      <div className="flex flex-col flex-grow px-4 sm:px-5 pb-4 sm:pb-5">
        {/* Row 2: Origin Label (SOURCE style) */}
        <div className="min-h-[16px] mb-1 relative z-40">
          {uniqueOrigins.length > 1 ? (
            <div className="relative inline-block">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsOriginDropdownOpen(!isOriginDropdownOpen);
                }}
                className="flex items-center gap-1.5 text-[10px] font-bold text-gray-400 uppercase tracking-widest bg-transparent cursor-pointer hover:text-primary-800 transition-colors focus:outline-none"
              >
                <span>{currentOrigin}</span>
                <svg className={`w-3 h-3 transition-transform ${isOriginDropdownOpen ? 'rotate-180' : ''}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isOriginDropdownOpen && (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsOriginDropdownOpen(false);
                    }}
                  />
                  <div className="absolute top-full left-0 mt-2 w-[140px] bg-white rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-gray-100 z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                    <div className="p-1 space-y-0.5">
                      {uniqueOrigins.map((o) => (
                        <button
                          key={o}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            handleOriginChange(o);
                            setIsOriginDropdownOpen(false);
                          }}
                          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-all text-left ${currentOrigin === o
                              ? "bg-primary-50 text-primary-900"
                              : "hover:bg-gray-50 text-gray-600"
                            }`}
                        >
                          <span className="text-[10px] font-bold uppercase tracking-widest">{o}</span>
                          {currentOrigin === o && (
                            <svg className="w-3.5 h-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : (
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
              {currentOrigin}
            </span>
          )}
        </div>

        {/* Row 3: Product Name */}
        <div>
          <h3
            className={`font-bold text-gray-900 md:group-hover:text-primary-800 transition-colors duration-300 ${compact ? 'text-[18px] mb-2' : 'text-[22px] mb-2'}`}
            style={{ fontFamily: "var(--font-display)" }}
          >
            {variant && variant !== "Standard" ? `${variant} ${name}` : name}
          </h3>
        </div>

        {/* Row 4: Variant Pills */}
        <div className="mb-3 relative z-30 min-h-[32px]">
          {availableVariantsForOrigin.length > 1 && (
            <div className="flex flex-wrap gap-2 overflow-hidden max-h-[32px]">
              {availableVariantsForOrigin.map((v) => (
                <button
                  key={v.id}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setSelectedVariantId(v.id);
                  }}
                  className={`text-[10px] font-semibold tracking-wider px-3 py-1.5 rounded-full transition-all duration-300 border-2 flex-shrink-0 ${selectedVariantId === v.id
                    ? "bg-primary-900 text-white border-primary-900 shadow-md"
                    : "bg-white text-gray-600 border-gray-100 hover:border-primary-200 hover:text-primary-700 active:bg-primary-50"
                    }`}
                >
                  {getCleanVariant(v.variant || "Standard")}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Row 5: Side-by-side Prices */}
        <div className="mt-auto mb-5 grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-0.5">
            <span className="text-[9px] text-gray-400 uppercase font-semibold tracking-widest">Market</span>
            <span className="text-base font-black text-gray-900">₱{currentPrice.toFixed(1)}</span>
          </div>
          <div className="flex flex-col gap-0.5 items-end text-right">
            <span className="text-[9px] text-gray-400 uppercase font-semibold tracking-widest">Predicted</span>
            <span className={`text-base font-black ${isUp ? "text-positive" : "text-negative"}`}>₱{predictedPrice.toFixed(1)}</span>
          </div>
        </div>

        {/* Row 6: View Button (Mockup Style) */}
        <div className="relative z-30">
          <Link
            prefetch={false}
            href={`/Product/${id}`}
            className="flex items-center justify-center w-full py-3.5 bg-primary-900 text-white rounded-full font-bold text-xs 
            transition-all duration-300 shadow-lg shadow-primary-900/10 
            md:hover:bg-primary-800 md:hover:shadow-primary-900/25 md:hover:-translate-y-0.5 active:scale-[0.97]"
          >
            View Forecast
          </Link>
        </div>
      </div>

      {/* Subtle Link for the whole card area (excluding buttons) */}
      <Link
        prefetch={false}
        href={`/Product/${id}`}
        className="absolute inset-0 z-20 rounded-[2rem]"
        aria-label={`View details for ${name}`}
      />
    </div>
  );
};

export default React.memo(ProductCard);
