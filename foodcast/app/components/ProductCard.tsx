"use client";
import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { ArrowUpRight, ArrowDownRight, Eye } from "lucide-react";
import { preload } from "swr";
import { DEFAULT_PRODUCT_IMAGE, fetchProducts } from "../lib/data";
import { encryptId } from "../../lib/idCipher";
import { useLanguage } from "../lib/i18n/LanguageContext";

const VariantOverflowDropdown = ({ overflow, selectedVariantId, isOpen, onToggle, onSelect, onClose, getCleanVariant }: any) => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 0 });
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setCoords({
        top: rect.bottom + window.scrollY + 8,
        left: rect.left + window.scrollX,
        width: Math.max(140, rect.width)
      });
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClose = (e: any) => {
      if (buttonRef.current && buttonRef.current.contains(e.target)) return;
      onClose();
    };
    window.addEventListener('click', handleClose);
    window.addEventListener('scroll', onClose, { passive: true });
    return () => {
      window.removeEventListener('click', handleClose);
      window.removeEventListener('scroll', onClose);
    };
  }, [isOpen, onClose]);

  return (
    <>
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggle();
        }}
        className={`text-[9px] sm:text-[10px] font-bold px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full transition-all duration-300 border flex-shrink-0 ${overflow.some((v: any) => v.id === selectedVariantId)
          ? "bg-primary-900 text-white border-primary-900 shadow-sm"
          : "bg-gray-50 text-gray-500 border-gray-200 hover:border-primary-200 hover:text-primary-700"
          }`}
      >
        +{overflow.length} more
      </button>
      {isOpen && mounted && createPortal(
        <div
          className="absolute z-[9999] bg-white rounded-xl shadow-[0_20px_50px_rgba(0,0,0,0.15)] border border-gray-100 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200"
          style={{ top: coords.top, left: coords.left, minWidth: coords.width }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-1 space-y-0.5 max-h-[200px] overflow-y-auto">
            {overflow.map((v: any) => (
              <button
                key={v.id}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onSelect(v.id);
                }}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-all text-left ${selectedVariantId === v.id
                  ? "bg-primary-50 text-primary-900"
                  : "hover:bg-gray-50 text-gray-600"
                  }`}
              >
                <span className="text-[10px] font-bold">{getCleanVariant(v.variant || "Standard")}</span>
                {selectedVariantId === v.id && (
                  <svg className="w-3.5 h-3.5 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

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
  image: string;
  category: string;
  variants: ProductVariant[];
  compact?: boolean;
  initialVariantId?: string;
  unit?: string;
}

const ProductCard = ({
  name,
  image,
  category,
  variants,
  compact = false,
  initialVariantId,
  unit,
}: ProductCardProps) => {
  const router = useRouter();
  const [selectedVariantId, setSelectedVariantId] = useState(initialVariantId || variants[0]?.id);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    setIsMobile(window.innerWidth < 640);
    const handleResize = () => setIsMobile(window.innerWidth < 640);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const getCleanVariant = (vStr: string) => {
    // Return the full variant string so we don't lose distinguishing prefixes like "Brown" vs "White"
    return vStr;
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
  const [isVariantDropdownOpen, setIsVariantDropdownOpen] = useState(false);

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

  const { t } = useLanguage();
  const change = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
  const isUp = change >= 0;

  return (
    <div
      className="product-card group relative flex flex-col h-full min-w-[150px] 
      bg-white rounded-[1.5rem] sm:rounded-[2rem] border border-gray-100 shadow-sm
        overflow-hidden transition-all duration-500 ease-out
        md:hover:shadow-[0_25px_60px_rgba(0,0,0,0.08)] md:hover:border-primary-100/50
        active:scale-[0.98] active:bg-gray-50/30"
      onMouseEnter={() => {
        setIsHovered(true);
        // Prefetch the product detail route on hover so it's instant on click
        router.prefetch(`/Product/${encryptId(id)}`);
        // Warm the SWR data cache so products are ready before navigation
        preload("supabase_products", fetchProducts);
      }}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Row 1: Product Image Container (Flush with edges) */}
      <div className={`relative overflow-hidden bg-gray-50 transition-all duration-700 ${compact ? "h-[120px] sm:h-[140px] mb-3" : "h-[150px] sm:h-[180px] mb-4"}`}>
        <Image
          key={selectedVariant.image || image || DEFAULT_PRODUCT_IMAGE} // Force re-render of img tag to trigger animation if needed, or at least change instantly
          src={selectedVariant.image || image || DEFAULT_PRODUCT_IMAGE}
          alt={name}
          fill
          className="object-cover transition-transform duration-1000 md:group-hover:scale-110"
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

        {/* Rate Change Badge (Pill Style) */}
        <div className="absolute top-3 right-3 z-10">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/20 shadow-sm ${isUp ? "bg-white/90 text-positive" : "bg-white/90 text-negative"}`}>
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

      <div className="flex flex-col flex-grow px-3 sm:px-5 pb-3 sm:pb-5">
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
                <span>{t(currentOrigin)}</span>
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
                          <span className="text-[10px] font-bold uppercase tracking-widest">{t(o)}</span>
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
              {t(currentOrigin)}
            </span>
          )}
        </div>

        {/* Row 3: Product Name */}
        <div>
          <h3
            className={`font-bold text-gray-900 md:group-hover:text-primary-800 transition-colors duration-300 leading-tight ${compact ? 'text-[14px] sm:text-[17px] mb-1.5' : 'text-[16px] sm:text-[20px] mb-2'} line-clamp-2`}
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t(name)}
          </h3>
        </div>

        {/* Row 4: Variant Pills with +N more */}
        <div className="min-h-[24px] sm:min-h-[28px] mb-2 sm:mb-3 relative z-30 flex items-start">
          {availableVariantsForOrigin.length > 1 && (() => {
            let maxVisible = 0;
            let charCount = 0;

            // maxChars defines how many characters of text we can fit on screen. 
            // We use 22 for desktop, but on mobile (<640px) cards are narrower, so we use 10.
            const currentMaxChars = isMobile ? 10 : 22;

            for (let i = 0; i < availableVariantsForOrigin.length; i++) {
              const text = getCleanVariant(availableVariantsForOrigin[i].variant || "Standard");
              // Give a little extra width allowance if this is the very last item (since no "+N more" button is needed)
              if (i === availableVariantsForOrigin.length - 1) {
                if (charCount + text.length <= currentMaxChars + 8) maxVisible++;
                break;
              }
              if (charCount + text.length <= currentMaxChars) {
                charCount += text.length;
                maxVisible++;
              } else {
                break;
              }
            }
            maxVisible = Math.max(1, maxVisible);

            const visible = availableVariantsForOrigin.slice(0, maxVisible);
            const overflow = availableVariantsForOrigin.slice(maxVisible);
            return (
              <div className="flex overflow-x-auto scrollbar-hide flex-nowrap items-center gap-1.5 sm:gap-2 pb-0.5 w-full">
                {visible.map((v) => (
                  <button
                    key={v.id}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setSelectedVariantId(v.id);
                    }}
                    className={`text-[9px] sm:text-[10px] font-bold px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full transition-all duration-300 border flex-shrink-0 ${selectedVariantId === v.id
                      ? "bg-primary-900 text-white border-primary-900 shadow-sm"
                      : "bg-white text-gray-600 border-gray-100 hover:border-primary-200 hover:text-primary-700 active:bg-primary-50"
                      }`}
                  >
                    {getCleanVariant(v.variant || "Standard")}
                  </button>
                ))}
                {overflow.length > 0 && (
                  <VariantOverflowDropdown
                    overflow={overflow}
                    selectedVariantId={selectedVariantId}
                    isOpen={isVariantDropdownOpen}
                    onToggle={() => setIsVariantDropdownOpen(!isVariantDropdownOpen)}
                    onSelect={(id: string) => {
                      setSelectedVariantId(id);
                      setIsVariantDropdownOpen(false);
                    }}
                    onClose={() => setIsVariantDropdownOpen(false)}
                    getCleanVariant={getCleanVariant}
                  />
                )}
              </div>
            );
          })()}
        </div>

        {/* Row 5: Prices (Stacked vertically for tight mobile widths) */}
        <div className="mt-auto mb-4 sm:mb-5 flex flex-col gap-1.5 sm:gap-2 min-w-0">
          <div className="flex items-center justify-between gap-1 w-full min-w-0">
            <span className="text-[9px] sm:text-[10px] text-gray-400 uppercase font-bold tracking-wider shrink-0">{t("market")}</span>
            <span className="text-[12px] sm:text-[14px] font-black text-gray-900 truncate">₱{currentPrice.toFixed(1)}{unit ? `/${unit}` : ''}</span>
          </div>
          <div className="flex items-center justify-between gap-1 w-full min-w-0">
            <span className="text-[9px] sm:text-[10px] text-gray-400 uppercase font-bold tracking-wider shrink-0">{t("predicted")}</span>
            <span className={`text-[12px] sm:text-[14px] font-black truncate ${isUp ? "text-positive" : "text-negative"}`}>₱{predictedPrice.toFixed(1)}{unit ? `/${unit}` : ''}</span>
          </div>
        </div>

        {/* Row 6: View Button (Mockup Style) */}
        <div className="relative z-30">
          <Link
            href={`/Product/${encryptId(id)}`}
            className="flex items-center justify-center w-full py-2 sm:py-3 bg-primary-900 text-white rounded-full font-bold text-[10px] sm:text-[12px] 
            transition-all duration-300 shadow-lg shadow-primary-900/10 
            md:hover:bg-primary-800 md:hover:shadow-primary-900/25 md:hover:-translate-y-0.5 active:scale-[0.97]"
          >
            {t("viewForecast")}
          </Link>
        </div>
      </div>

      {/* Subtle Link for the whole card area (excluding buttons) */}
      <Link
        href={`/Product/${encryptId(id)}`}
        className="absolute inset-0 z-20 rounded-[2rem]"
        aria-label={`View details for ${name}`}
      />
    </div>
  );
};

export default React.memo(ProductCard);
