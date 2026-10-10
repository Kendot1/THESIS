"use client";
import React from "react";
import Link from "next/link";
import Image from "next/image";
import { TrendingUp, TrendingDown, ChevronRight } from "lucide-react";
import { encryptId } from "../../lib/idCipher";
import { DEFAULT_PRODUCT_IMAGE } from "../lib/data";
import { useLanguage } from "../lib/i18n/LanguageContext";

interface DailyMoverCardProps {
  id: string;
  name: string;
  category: string;
  image?: string;
  currentPrice: number;
  predictedPrice: number;
  forecastDate: string | null;
  lastActualDate?: string;
  forecastSource?: "model" | "trend_fallback";
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
  forecastDate,
  lastActualDate,
  forecastSource,
  variant,
  origin,
  unit,
}: DailyMoverCardProps) => {
  const { t, language } = useLanguage();
  const change = currentPrice > 0 ? ((predictedPrice - currentPrice) / currentPrice) * 100 : 0;
  const priceChange = predictedPrice - currentPrice;
  const isUp = change >= 0;
  const formatDate = (date: string) => new Date(`${date}T00:00:00Z`).toLocaleDateString(
    language === "tl" ? "fil-PH" : "en-PH",
    { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" },
  );

  const displayName = t(name) + (variant && variant !== "Standard" ? ` (${variant})` : "");

  // Describe the forecast without inventing supply causes or buying advice.
  const getInsight = () => {
    if (!forecastDate) return t("dailyForecastUnavailable");
    if (forecastSource === "trend_fallback") return t("dailyForecastFallback");
    if (Math.abs(priceChange) < 0.005) return t("dailyForecastUnchanged");
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
      className="daily-mover-card group relative flex flex-col rounded-2xl border border-gray-100
        bg-white overflow-hidden transition-all duration-500
        shadow-sm hover:shadow-xl hover:-translate-y-1
        focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 h-full"
    >
      {/* Product Image Banner */}
      <div className="relative h-[120px] sm:h-[135px] w-full overflow-hidden bg-gray-100">
        <Image
          src={image || DEFAULT_PRODUCT_IMAGE}
          alt={displayName}
          fill
          sizes="(max-width: 639px) 280px, (max-width: 1023px) 50vw, (max-width: 1279px) 33vw, 390px"
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
        {forecastDate && <div className={`absolute top-3 right-3 flex items-center gap-1 text-[10px] sm:text-xs font-bold px-2.5 py-1 rounded-full
          ${isUp
            ? "bg-price-up/80 text-white border border-price-up/30"
            : "bg-price-down/80 text-white border border-price-down/30"
          }`}
        >
          {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          {isUp ? "+" : ""}{change.toFixed(2)}%
        </div>}

        {unit && (
          <span className="absolute bottom-3 right-3 max-w-20 truncate rounded-full bg-white/95 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-gray-700 shadow-sm">
            {unit}
          </span>
        )}

        {/* Product name overlaid at bottom of image */}
        <div className={`absolute bottom-3 left-3 ${unit ? "right-16" : "right-3"}`}>
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
            <span className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider block mb-0.5">{t("dailyLastObserved")}</span>
            <span className="block whitespace-nowrap text-xl sm:text-2xl font-black text-gray-900 tabular-nums leading-none">
              ₱{currentPrice.toFixed(2)}
            </span>

          </div>
          <div className="text-right">
            <span className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider block mb-0.5">{t("dailyNextForecast")}</span>
            {forecastDate ? <>
            <span className={`block whitespace-nowrap text-xl sm:text-2xl font-black tabular-nums leading-none ${isUp ? 'text-price-up' : 'text-price-down'}`}>
              ₱{predictedPrice.toFixed(2)}
            </span>
            </> : <span className="text-sm text-gray-500">{t("dailyForecastUnavailable")}</span>}
          </div>
        </div>

        <div className="flex justify-between gap-2 text-[10px] text-gray-500 mb-3">
          <span>{lastActualDate ? formatDate(lastActualDate) : "—"}</span>
          <span>{forecastDate ? formatDate(forecastDate) : "—"}</span>
        </div>

        {/* Divider */}
        <div className="h-px bg-gray-100 mb-3" />

        {/* Insight */}
        <p className="text-xs sm:text-sm text-gray-500 leading-relaxed mb-4 flex-1">
          {getInsight()}
        </p>

        {/* Bottom CTA */}
        <div className="flex items-center justify-between mt-auto pt-2">
          {forecastDate && <div className={`inline-flex items-center gap-1.5 text-[10px] sm:text-xs font-bold px-2.5 py-1.5 rounded-lg
            ${isUp
              ? 'text-price-up bg-price-up/10'
              : 'text-price-down bg-price-down/10'
            }`}
          >
            {isUp ? "+" : ""}₱{priceChange.toFixed(2)} {t("expectedChange")}
          </div>}
          <span className="text-xs text-gray-400 font-medium flex items-center gap-0.5 group-hover:text-primary-700 transition-colors">
            {t("details")} <ChevronRight className="w-3.5 h-3.5" />
          </span>
        </div>
      </div>
    </Link>
  );
};

export default React.memo(DailyMoverCard);
