"use client";
import React, { useId } from "react";
import Link from "next/link";
import Image from "next/image";
import { TrendingUp, TrendingDown, ChevronRight, ArrowUpRight, ArrowDownRight } from "lucide-react";
import SparklineChart from "./SparklineChart";
import { encryptId } from "../../lib/idCipher";
import { DEFAULT_PRODUCT_IMAGE, ForecastDataPoint } from "../lib/data";
import { encryptId } from "../../lib/idCipher";
import { useLanguage } from "../lib/i18n/LanguageContext";

interface DailyMoverCardProps {
  id: string;
  name: string;
  category: string;
  image?: string;
  currentPrice: number;
  predictedPrice: number;
  forecastData: ForecastDataPoint[];
  variant?: string;
  origin?: string;
  unit: string;
}

const DailyMoverCard = ({
  id,
  name,
  category,
  image,
  currentPrice,
  predictedPrice,
  forecastData,
  variant,
  origin,
  unit,
}: DailyMoverCardProps) => {
  const { t } = useLanguage();
  const change = ((predictedPrice - currentPrice) / currentPrice) * 100;
  const priceChange = predictedPrice - currentPrice;
  const isUp = change >= 0;
  const baseId = useId();

  const displayName = t(name) + (variant && variant !== "Standard" ? ` (${variant})` : "");

  // Generate a practical market insight
  const getInsight = () => {
    const absChange = Math.abs(change);
    if (isUp) {
      if (absChange > 5) return t("insightSurging");
      if (absChange > 2) return t("insightModerateUp");
      return t("insightSlightUp");
    } else {
      if (absChange > 5) return t("insightDrop");
      if (absChange > 2) return t("insightModerateDown");
      return t("insightSlightDown");
    }
  };

  return (
    <Link
      href={`/Product/${encryptId(id)}`}
      className="daily-mover-card group relative flex flex-col rounded-2xl border border-gray-100/80
        bg-white overflow-hidden
        transition-all duration-400 ease-out
        hover:shadow-[0_12px_40px_rgba(0,0,0,0.08)] hover:-translate-y-1
        focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 h-full"
    >
      {/* Product Image Banner */}
      <div className="relative h-[120px] sm:h-[135px] w-full overflow-hidden bg-gray-100">
        <Image
          src={image || DEFAULT_PRODUCT_IMAGE}
          alt={displayName}
          fill
          className="object-cover transition-transform duration-500 group-hover:scale-105"
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
        {/* Dark gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-transparent" />
        
        {/* Category & Origin badge on image */}
        <div className="absolute top-3 left-3 flex items-center gap-1.5">
          <span className="text-[10px] sm:text-[11px] font-bold text-white/95 bg-black/60 px-2.5 py-1 rounded-full uppercase tracking-wider">
            {t(category)}
          </span>
          {origin && (
            <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-500 font-bold uppercase tracking-widest text-[8px] sm:text-[9px]">
              {t(origin)}
            </span>
          )}
        </div>

        {/* Trend badge on image */}
        <div className={`absolute top-3 right-3 flex items-center gap-1 text-[10px] sm:text-xs font-bold px-2.5 py-1 rounded-full
          ${isUp
            ? "bg-positive/25 text-green-100 border border-positive/10"
            : "bg-negative/25 text-red-100 border border-negative/10"
          }`}
        >
          {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          {isUp ? "+" : ""}{change.toFixed(2)}%
        </div>

        {/* Product name overlaid at bottom of image */}
        <div className="absolute bottom-3 left-3 right-3">
          <h3
            className="font-bold text-white text-base sm:text-lg leading-tight truncate drop-shadow-sm"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {displayName}
          </h3>
        </div>
      </div>

      {/* Card Body */}
      <div className="flex flex-col flex-1 p-4 sm:p-5">
        {/* Price Row */}
        <div className="flex items-baseline justify-between gap-2 mb-3">
          <div>
            <span className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider block mb-0.5">{t("currentPrice")}</span>
            <span className="text-2xl sm:text-3xl font-black text-gray-900 tabular-nums leading-none">
              ₱{currentPrice.toFixed(2)}
              {unit && <span className="text-sm sm:text-base text-gray-500 ml-1 font-medium">/ {unit}</span>}
            </span>
            
          </div>
          <div className="text-right">
            <span className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider block mb-0.5">{t("tomorrow")}</span>
            <span className={`text-lg sm:text-xl font-bold tabular-nums leading-none ${isUp ? 'text-positive' : 'text-negative'}`}>
              ₱{predictedPrice.toFixed(2)}
              {unit && <span className="text-xs sm:text-sm opacity-70 ml-1 font-medium">/ {unit}</span>}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px bg-gray-100 mb-3" />

        {/* Insight */}
        <p className="text-xs sm:text-sm text-gray-500 leading-relaxed mb-4 flex-1">
          {getInsight()}
        </p>

        {/* Bottom CTA */}
        <div className="flex items-center justify-between mt-auto pt-2">
          <div className={`inline-flex items-center gap-1.5 text-[10px] sm:text-xs font-bold px-2.5 py-1.5 rounded-lg
            ${isUp
              ? 'text-positive bg-positive/8'
              : 'text-negative bg-negative/8'
            }`}
          >
            {isUp ? "+" : ""}₱{priceChange.toFixed(2)} {t("expectedChange")}
          </div>
          <span className="text-xs text-gray-400 font-medium flex items-center gap-0.5 group-hover:text-primary-700 transition-colors">
            {t("details")} <ChevronRight className="w-3.5 h-3.5" />
          </span>
        </div>
      </div>
    </Link>
  );
};

export default React.memo(DailyMoverCard);
