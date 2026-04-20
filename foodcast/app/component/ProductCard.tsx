"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, Eye } from "lucide-react";

interface ProductCardProps {
  id: string;
  name: string;
  emoji: string;
  image: string;
  category: string;
  currentPrice: number;
  predictedPrice: number;
  compact?: boolean;
}

const ProductCard = ({
  id,
  name,
  emoji,
  image,
  category,
  currentPrice,
  predictedPrice,
  compact = false,
}: ProductCardProps) => {
  const [isHovered, setIsHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const change = currentPrice === 0 ? 0 : ((predictedPrice - currentPrice) / currentPrice) * 100;
  const isUp = change >= 0;

  return (
    <Link
      href={`/Product/${id}`}
      className="product-card group relative block w-full bg-white rounded-2xl border border-gray-100/80 
        overflow-hidden transition-all duration-500 ease-out
        hover:shadow-[0_12px_48px_rgba(11,61,46,0.12)] hover:-translate-y-1.5 hover:border-accent/25
        focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
      aria-label={`View forecast for ${name} — current price ₱${currentPrice.toFixed(2)}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Top accent line */}
      <div
        className={`absolute top-0 left-0 right-0 h-[3px] transition-all duration-500 ${isUp
          ? "bg-gradient-to-r from-accent/0 via-accent to-accent/0"
          : "bg-gradient-to-r from-negative/0 via-negative to-negative/0"
          }`}
        style={{
          opacity: isHovered ? 1 : 0,
          transform: isHovered ? "scaleX(1)" : "scaleX(0)",
        }}
      />

      <div className={`${compact ? "p-3" : "p-4 sm:p-5"}`}>
        {/* Row 1: Category + Change Badge */}
        <div className="flex items-center justify-between mb-2 sm:mb-3">
          <span className="inline-flex items-center text-[9px] sm:text-[11px] font-semibold text-primary-600 
            bg-primary-50/80 px-1.5 sm:px-2.5 py-0.5 sm:py-1 rounded-md sm:rounded-lg 
            uppercase tracking-wider">
            {category}
          </span>
          <span
            className={`inline-flex items-center gap-0.5 text-[9px] 
              sm:text-[11px] font-bold px-1.5 sm:px-2 py-0.5 sm:py-1 
              rounded-md sm:rounded-lg transition-all duration-300 ${isUp
                ? "text-positive bg-positive/8 group-hover:bg-positive/15"
                : "text-negative bg-negative/8 group-hover:bg-negative/15"
              }`}
          >
            {isUp ? (
              <ArrowUpRight className="w-3 h-3" />
            ) : (
              <ArrowDownRight className="w-3 h-3" />
            )}
            {Math.abs(change).toFixed(1)}%
          </span>
        </div>

        {/* Row 2: Product Image */}
        <div className={`relative rounded-lg sm:rounded-xl bg-gradient-to-br from-gray-50 to-gray-100/60 overflow-hidden 
        flex items-center justify-center transition-all duration-300 
        group-hover:from-primary-50/40 group-hover:to-primary-100/30 ${compact
            ? 'mb-2 sm:mb-4 h-[75px] sm:h-[100px] w-[100%]' : 'mb-4 h-[120px] w-[100%]'}`}
        >
          {!imgError ? (
            <img
              src={image}
              alt={name}
              className="w-full h-full object-contain p-3 transition-transform duration-500 group-hover:scale-110"
              onError={() => setImgError(true)}
            />
          ) : (
            <span className="text-5xl transition-transform duration-500 group-hover:scale-110 group-hover:rotate-[6deg]">
              {emoji}
            </span>
          )}
        </div>

        {/* Row 3: Product Name */}
        <h3
          className={`font-bold text-gray-900 leading-tight group-hover:text-primary-800 transition-colors duration-300 ${compact ? 'text-[12px] sm:text-[14px] mb-2 sm:mb-3' : 'text-[14px] sm:text-[15px] mb-3'}`}
          style={{ fontFamily: "var(--font-display)" }}
        >
          {name}
        </h3>

        {/* Row 4: Price Section */}
        <div className={`flex items-end justify-between border-t border-gray-100/80 ${compact ? 'pt-2 sm:pt-3' : 'pt-3'}`}>
          <div>
            <div className="text-[8px] sm:text-[10px] text-gray-400 uppercase tracking-widest font-semibold mb-0.5">
              Current
            </div>
            <div className={`font-bold text-gray-900 tabular-nums ${compact ? 'text-xs sm:text-base' : 'text-base'}`}>
              ₱{currentPrice.toFixed(2)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[8px] sm:text-[10px] text-gray-400 uppercase tracking-widest font-semibold mb-0.5">
              Predicted
            </div>
            <div
              className={`font-bold tabular-nums ${compact ? 'text-xs sm:text-base' : 'text-base'} ${isUp ? "text-positive" : "text-negative"
                }`}
            >
              ₱{predictedPrice.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* Hover reveal: View button */}
      <div
        className="absolute bottom-0 left-0 right-0 flex items-center justify-center py-2.5 bg-gradient-to-t from-primary-800/95 via-primary-800/80 to-transparent
          transition-all duration-400 ease-out"
        style={{
          opacity: isHovered ? 1 : 0,
          transform: isHovered ? "translateY(0)" : "translateY(100%)",
        }}
      >
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-white">
          <Eye className="w-3.5 h-3.5" />
          View Forecast
        </span>
      </div>
    </Link>
  );
};

export default ProductCard;
