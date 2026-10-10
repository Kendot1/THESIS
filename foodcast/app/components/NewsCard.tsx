"use client";
import React, { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import Link from "next/link";
import { Calendar, ArrowRight, Tag, X, ExternalLink, Clock } from "lucide-react";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { getNewsTagKeywords } from "../lib/tags";

interface NewsCardProps {
  id: string;
  title: string;
  title_tl?: string;
  excerpt: string;
  category: string;
  date: string;
  image: string;
  url?: string;
  source?: string;
  content?: string;
  content_tl?: string;
  sentimentScore?: number;
  keywords?: string[];
  affectedProducts?: string[];
  _compact?: boolean;
}

const NewsCard = ({ id, title, title_tl, excerpt, category, date, image, url, source, content, content_tl, sentimentScore, keywords, affectedProducts, _compact = false }: NewsCardProps) => {
  const { t, language } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [failedImage, setFailedImage] = useState<string | null>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  // Close on Escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") setIsOpen(false);
  }, []);

  useEffect(() => {
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const displayTitle = (language === "tl" && title_tl ? title_tl : title) || t("titleUnavailable");
  const displayContent = language === "tl" && content_tl ? content_tl : content;
  const displayExcerpt = (language === "tl" && content_tl
    ? content_tl.length > 150 ? `${content_tl.substring(0, 150).trimEnd()}...` : content_tl
    : excerpt) || t("descriptionUnavailable");

  const fullContent = displayContent || displayExcerpt;
  const hasImage = Boolean(image) && failedImage !== image;
  const displayDate = !date || date === "Publication date unavailable" ? t("publicationDateUnavailable") : date;
  const relatedKeywords = getNewsTagKeywords({ keywords });

  return (
    <>
      {/* Card */}
      <div
        onClick={() => setIsOpen(true)}
        className={`group bg-white overflow-hidden cursor-pointer ${_compact
          ? "flex h-full w-full flex-row-reverse items-center gap-3 px-4 py-3 transition-all duration-300"
          : "rounded-3xl border border-gray-100 shadow-sm hover:shadow-xl transition-all duration-500 flex flex-col h-full"
          }`}
      >
        {/* Image Container */}
        <div className={`relative overflow-hidden bg-gray-100 shrink-0 ${_compact ? "w-16 h-16 rounded-lg" : "h-48"}`}>
          {hasImage ? (
            <Image
              src={image}
              alt={displayTitle}
              fill
              onError={() => setFailedImage(image)}
              className="object-cover transition-transform duration-700 group-hover:scale-110"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-400">{t("imageUnavailable")}</div>
          )}
        </div>

        {/* Content */}
        <div className={`min-w-0 flex flex-col flex-1 ${_compact ? "py-0" : "p-6"}`}>
          <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-gray-400 text-[10px] font-medium ${_compact ? "mb-1" : "mb-3"}`}>
            <span className={`inline-flex max-w-full items-center gap-1 font-bold uppercase text-primary-800 ${_compact
              ? "text-[9px] tracking-[0.12em]"
              : "rounded-full bg-gray-50 px-2 py-0.5 tracking-wide"
              }`}>
              {!_compact && <Tag className="w-2.5 h-2.5 shrink-0" />}
              <span className="truncate">{t(category)}</span>
            </span>
            {!_compact && (
              <span className="inline-flex min-w-0 items-center gap-1">
                <Calendar className="w-3 h-3 shrink-0" />
                <span className="truncate">{displayDate}</span>
              </span>
            )}
          </div>

          <h3 className={`${_compact ? "text-[13px] mb-1" : "text-lg mb-3"} font-bold text-gray-900 leading-tight group-hover:text-primary-800 transition-colors line-clamp-2`}>
            {displayTitle}
          </h3>

          {!_compact && (
            <p className="text-gray-500 text-xs sm:text-sm mb-6 line-clamp-3 leading-relaxed">
              {displayExcerpt}
            </p>
          )}

          <div className={`mt-auto flex items-center justify-between ${_compact ? "gap-2 pt-1" : ""}`}>
            {_compact ? (
              <div className="min-w-0 truncate text-[9px] font-medium text-gray-400">
                {source || t("marketNews")} · {displayDate}
              </div>
            ) : (
              <>
                <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
                  {source || t("marketNews")}
                </div>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex items-center font-bold text-primary-700 hover:text-primary-900 transition-colors group/link z-10 gap-2 text-xs"
                >
                  {t("readMore")}
                  <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover/link:translate-x-1" />
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Modal Overlay via Portal to escape CSS transform context */}
      {isMounted && isOpen && createPortal(
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
          onClick={() => setIsOpen(false)}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-news-fade-in" />

          {/* Modal Content */}
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative z-10 bg-white rounded-[2rem] w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl animate-news-modal-in flex flex-col"
          >
            {/* Modal Header Image */}
            <div className="relative h-56 sm:h-64 flex-shrink-0 overflow-hidden">
              {hasImage ? (
                <Image src={image} alt={displayTitle} fill onError={() => setFailedImage(image)} className="object-cover" />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center bg-gray-800 text-xs font-medium text-white">{t("imageUnavailable")}</div>
              )}
            </div>

            {/* Modal Body */}
            <div className="p-6 sm:p-8 overflow-y-auto flex-1">
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <span className="px-3 py-1 bg-gray-50 rounded-full text-[10px] font-bold text-primary-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Tag className="w-3 h-3" />
                  {t(category)}
                </span>
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Clock className="w-3 h-3" />
                  {displayDate}
                </span>
              </div>
              <h2 className="text-xl sm:text-2xl font-black text-gray-900 mb-2 leading-tight" style={{ fontFamily: "var(--font-display)" }}>
                {displayTitle}
              </h2>

              <div className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.2em] mb-6">
                {t("source")}: {source || t("marketNews")}
              </div>



              <div className="w-12 h-0.5 bg-gradient-to-r from-primary-700 to-accent rounded-full mb-6" />

              {/* Full article content */}
              <div className="text-gray-600 text-sm sm:text-base leading-relaxed whitespace-pre-line mb-8">
                {fullContent}
              </div>

              {/* Tags Section */}
              {relatedKeywords.length > 0 && (() => {
                const tagColors = [
                  "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100",
                  "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100",
                  "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100",
                  "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100",
                  "bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100",
                  "bg-cyan-50 text-cyan-700 border-cyan-200 hover:bg-cyan-100",
                  "bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100",
                  "bg-teal-50 text-teal-700 border-teal-200 hover:bg-teal-100",
                ];
                return (
                  <div className="pt-6 border-t border-gray-100">
                    <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                      <Tag className="w-3.5 h-3.5" />
                      {t("relatedTags") || "Related Tags"}
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {relatedKeywords.map((kw, idx) => {
                        return (
                          <Link
                            key={idx}
                            href={`/tags/${encodeURIComponent(kw)}`}
                            className={`px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors capitalize ${tagColors[idx % tagColors.length]}`}
                          >
                            {kw}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}
            </div>

            {/* Modal Footer */}
            <div className="flex-shrink-0 px-6 sm:px-8 py-5 border-t border-gray-100 flex items-center justify-between bg-gray-50/50">
              <button
                onClick={() => setIsOpen(false)}
                className="px-6 py-2.5 bg-gray-200 text-gray-700 hover:bg-gray-300 text-xs font-bold uppercase tracking-widest rounded-xl transition-all active:scale-95"
              >
                {t("close")}
              </button>
              {url && (
                <a
                  href={url}
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

    </>
  );
};

export default React.memo(NewsCard);
