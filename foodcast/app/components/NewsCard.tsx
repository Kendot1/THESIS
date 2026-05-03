"use client";
import React from "react";
import Link from "next/link";
import { Calendar, ArrowRight, Tag } from "lucide-react";

interface NewsCardProps {
  id: string;
  title: string;
  excerpt: string;
  category: string;
  date: string;
  image: string;
  url?: string;
  source?: string;
}

const NewsCard = ({ id, title, excerpt, category, date, image, url, source }: NewsCardProps) => {
  return (
    <div className="group bg-white rounded-3xl overflow-hidden border border-gray-100 shadow-sm hover:shadow-xl transition-all duration-500 flex flex-col h-full">
      {/* Image Container */}
      <div className="relative h-48 overflow-hidden">
        <img
          src={image}
          alt={title}
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
        />
        <div className="absolute top-4 left-4 flex gap-2">
          <span className="px-3 py-1 bg-white/90 backdrop-blur-md rounded-full text-[10px] font-bold text-primary-800 uppercase tracking-wider flex items-center gap-1.5 shadow-sm capitalize">
            <Tag className="w-3 h-3" />
            {category}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-6 flex flex-col flex-1">
        <div className="flex items-center gap-2 text-gray-400 text-[10px] font-medium mb-3">
          <Calendar className="w-3 h-3" />
          {date}
        </div>

        <h3 className="text-lg font-bold text-gray-900 mb-3 leading-tight group-hover:text-primary-800 transition-colors line-clamp-2">
          {title}
        </h3>

        <p className="text-gray-500 text-xs sm:text-sm mb-6 line-clamp-3 leading-relaxed">
          {excerpt}
        </p>

        <div className="mt-auto flex items-center justify-between">
          <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            {source || "Market News"}
          </div>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-xs font-bold text-primary-700 hover:text-primary-900 transition-colors group/link"
            >
              Read Article
              <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover/link:translate-x-1" />
            </a>
          ) : (
            <Link
              prefetch={false}
              href={`/News/${id}`}
              className="inline-flex items-center gap-2 text-xs font-bold text-primary-700 hover:text-primary-900 transition-colors group/link"
            >
              Read Article
              <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover/link:translate-x-1" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
};

export default React.memo(NewsCard);
