"use client";

import { useState, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import { useLanguage } from "../lib/i18n/LanguageContext";
import { MarketLocation, getNearestMarkets } from "../lib/markets";
import { Search, Navigation, MapPin, TrendingUp, TrendingDown, ExternalLink, Crosshair, Locate } from "lucide-react";
import { useRouter } from "next/navigation";

// Leaflet uses the window object, so we must dynamically import the map component with SSR disabled.
const MarketMap = dynamic(() => import("../components/MarketMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-gray-50 flex flex-col items-center justify-center">
      <div className="w-12 h-12 border-4 border-primary-200 border-t-primary-800 rounded-full animate-spin mb-4" />
      {/* We can't use useLanguage here easily as it's outside the component, so we keep this as is or make a wrapper. Since it's dynamic loading, a brief hardcoded English is fine, but we'll stick to what we can. */}
      <span className="text-gray-400 font-bold text-sm tracking-widest uppercase">Loading Map Data...</span>
    </div>
  )
});

interface MapProps {
  marketStats: Record<string, { count: number; avgChange: number }>;
  initialMarkets: MarketLocation[];
}

export default function MapClient({ marketStats, initialMarkets }: MapProps) {
  const { t, language, isTransitioning } = useLanguage();
  const router = useRouter();
  const [userLoc, setUserLoc] = useState<{ lat: number, lng: number } | null>(null);
  const [locError, setLocError] = useState<string | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [markets, setMarkets] = useState<(MarketLocation & { distance?: number })[]>(initialMarkets);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false); // Mobile drawer state

  // Auto-dismiss location error after 4 seconds
  useEffect(() => {
    if (locError) {
      const timer = setTimeout(() => setLocError(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [locError]);

  // Helper: check accuracy and apply location result
  const applyLocation = (pos: GeolocationPosition, resolve?: (val: boolean) => void) => {
    // Reject locations that are not precise (e.g. IP-based desktop locations)
    // 2000 meters is a reasonable cutoff for GPS/Wi-Fi vs IP-based accuracy.
    if (pos.coords.accuracy > 2000) {
      setLocError(t("enableGpsError"));
      setIsLocating(false);
      if (resolve) resolve(false);
      return;
    }

    const lat = pos.coords.latitude;
    const lng = pos.coords.longitude;
    setUserLoc({ lat, lng });
    setLocError(null);
    setSelectedMarketId(null);
    const sorted = getNearestMarkets(initialMarkets, lat, lng);
    setMarkets(sorted);
    setIsLocating(false);
    if (resolve) resolve(true);
  };

  // Fallback: Browser geolocation WITHOUT high accuracy (uses Wi-Fi/cell, faster)
  const tryLowAccuracy = (): Promise<boolean> => {
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => applyLocation(pos, resolve),
        () => {
          // Both browser methods failed
          setLocError(t("enableGpsError"));
          setIsLocating(false);
          resolve(false);
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
      );
    });
  };

  // Function to manually request location when user clicks the button
  const requestLocation = () => {
    setIsLocating(true);
    setLocError(null);

    if ("geolocation" in navigator) {
      // Try high-accuracy first (GPS on phones)
      navigator.geolocation.getCurrentPosition(
        (pos) => applyLocation(pos),
        () => {
          // High accuracy failed — try low accuracy
          console.warn("High-accuracy geolocation failed, trying low accuracy...");
          tryLowAccuracy();
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
      );
    } else {
      // No browser geolocation at all
      setLocError(t("enableGpsError"));
      setIsLocating(false);
    }
  };

  // Filter markets based on search
  const filteredMarkets = useMemo(() => {
    if (!searchQuery) return markets;
    const lower = searchQuery.toLowerCase();
    return markets.filter(m =>
      m.name.toLowerCase().includes(lower) ||
      m.city.toLowerCase().includes(lower) ||
      m.address.toLowerCase().includes(lower)
    );
  }, [searchQuery, markets]);

  const handleMarketClick = (id: string) => {
    setSelectedMarketId(id);

    // On mobile, collapse the drawer to show the map when a market is selected
    if (window.innerWidth < 1024) {
      setIsDrawerOpen(false);
    }
  };

  if (isTransitioning) {
    return (
      <div className="h-[calc(100vh-72px)] mt-[72px] w-screen bg-surface flex flex-col overflow-hidden">
        <main className="flex-1 flex lg:flex-row h-full w-full relative overflow-hidden">
          {/* Map Area Skeleton */}
          <div className="absolute inset-0 lg:relative lg:flex-1 lg:h-full z-0 lg:border-r border-gray-200 bg-gray-100">
            <div className="w-full h-full relative overflow-hidden">
              <div className="absolute inset-0 skeleton-shimmer-map" />
              {/* Zoom Controls */}
              <div className="absolute top-4 right-4 lg:top-6 lg:right-6 z-10 flex flex-col gap-3">
                <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
                  <div className="w-8 h-8 lg:w-10 lg:h-10 bg-gray-100 border-b border-gray-50 skeleton-shimmer" />
                  <div className="w-8 h-8 lg:w-10 lg:h-10 bg-gray-100 skeleton-shimmer" style={{ animationDelay: "80ms" }} />
                </div>
                <div className="w-8 h-8 lg:w-10 lg:h-10 bg-white rounded-2xl shadow-lg skeleton-shimmer" style={{ animationDelay: "160ms" }} />
              </div>
              {/* Location Button */}
              <div className="absolute bottom-24 lg:bottom-6 left-4 lg:left-6 z-10">
                <div className="w-12 h-12 lg:w-44 lg:h-14 bg-white rounded-full lg:rounded-2xl shadow-lg skeleton-shimmer" style={{ animationDelay: "240ms" }} />
              </div>
              {/* Fake map markers */}
              {[
                { top: "30%", left: "45%" },
                { top: "50%", left: "55%" },
                { top: "40%", left: "35%" },
                { top: "60%", left: "48%" },
                { top: "25%", left: "60%" },
              ].map((pos, i) => (
                <div key={i} className="absolute w-6 h-8 z-10" style={{ top: pos.top, left: pos.left }}>
                  <div className="w-full h-full bg-gray-300/60 rounded-t-full rounded-b-sm skeleton-shimmer" style={{ animationDelay: `${i * 100 + 300}ms` }} />
                </div>
              ))}
            </div>
          </div>

          {/* Sidebar Skeleton */}
          <div className="absolute bottom-0 left-0 right-0 lg:relative lg:bottom-auto lg:left-auto lg:right-auto w-full lg:w-[340px] xl:w-[380px] bg-white shadow-[0_-10px_40px_rgba(0,0,0,0.15)] lg:shadow-[-10px_0_30px_rgba(0,0,0,0.05)] z-10 flex flex-col translate-y-[calc(100%-40px)] lg:translate-y-0 h-[80vh] lg:h-full rounded-t-3xl lg:rounded-none">
            <div className="w-full flex justify-center pt-4 pb-3 lg:hidden bg-white shrink-0">
              <div className="w-12 h-1.5 rounded-full bg-gray-200" />
            </div>
            <div className="px-5 pt-0 pb-4 lg:p-6 border-b border-gray-100 shrink-0 bg-white">
              <div className="mb-4 lg:mb-6">
                <div className="h-7 w-52 bg-gray-200 rounded-lg mb-2 skeleton-shimmer" />
                <div className="hidden lg:block h-4 w-72 bg-gray-100 rounded-md skeleton-shimmer" style={{ animationDelay: "80ms" }} />
              </div>
              <div className="flex items-center justify-between mb-3">
                <div className="h-3 w-28 bg-gray-200 rounded skeleton-shimmer" style={{ animationDelay: "160ms" }} />
                <div className="h-5 w-8 bg-gray-100 rounded-full skeleton-shimmer" style={{ animationDelay: "200ms" }} />
              </div>
              <div className="h-12 w-full bg-gray-50 border border-gray-200 rounded-xl skeleton-shimmer" style={{ animationDelay: "240ms" }} />
            </div>
            <div className="flex-1 overflow-hidden p-4 space-y-3">
              {[0, 1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} className="w-full p-4 rounded-2xl border border-gray-100 bg-white">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="h-4 w-36 bg-gray-200 rounded-md mb-1.5 skeleton-shimmer" style={{ animationDelay: `${i * 60}ms` }} />
                      <div className="h-2.5 w-20 bg-gray-100 rounded skeleton-shimmer" style={{ animationDelay: `${i * 60 + 30}ms` }} />
                    </div>
                  </div>
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <div className="h-3 w-full bg-gray-100 rounded mb-1.5 skeleton-shimmer" style={{ animationDelay: `${i * 60 + 60}ms` }} />
                    <div className="h-3 w-4/5 bg-gray-100 rounded skeleton-shimmer" style={{ animationDelay: `${i * 60 + 90}ms` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-72px)] mt-[72px] w-screen bg-surface flex flex-col overflow-hidden">

      {/* Main Content Layout - Full Screen (h-screen minus Header 72px) */}
      <main className="flex-1 flex lg:flex-row h-full w-full relative overflow-hidden">

        {/* Left Side / Top - Map Container (Full Bleed) */}
        <div id="map-container" className="absolute inset-0 lg:relative lg:flex-1 lg:h-full z-0 lg:border-r border-gray-200">
          <MarketMap
            markets={markets}
            marketStats={marketStats}
            userLocation={userLoc}
            selectedMarketId={selectedMarketId}
            onMarketSelect={setSelectedMarketId}
          />

          {/* Floating "Find My Location" Button on the Map */}
          <button
            onClick={requestLocation}
            disabled={isLocating}
            className={`absolute bottom-24 lg:bottom-6 left-4 lg:left-6 z-[1000] flex items-center justify-center gap-0 lg:gap-2.5 w-12 h-12 lg:w-auto lg:h-auto lg:px-5 lg:py-3.5 rounded-full lg:rounded-2xl shadow-lg border transition-all duration-300 group ${userLoc
                ? 'bg-primary-600 text-white border-primary-700 hover:bg-primary-700 shadow-primary-600/30'
                : 'bg-white text-gray-700 border-gray-200 hover:bg-primary-50 hover:border-primary-300 hover:text-primary-700 shadow-black/10'
              } disabled:opacity-60 disabled:cursor-wait`}
            title={t("findMyLocation")}
          >
            <Locate className={`w-5 h-5 lg:w-5 lg:h-5 ${isLocating ? 'animate-spin' : userLoc ? 'text-white' : 'text-primary-600 group-hover:text-primary-700'}`} />
            <span className="hidden lg:inline text-sm font-bold">
              {isLocating ? t("locating") : userLoc ? t("locationFound") : t("findMyLocation")}
            </span>
          </button>

          {/* Location error toast - Top Center */}
          {locError && !userLoc && (
            <div className="absolute top-6 left-1/2 -translate-x-1/2 z-[2000] bg-red-50 border border-red-200 text-red-700 text-xs lg:text-sm font-bold px-6 py-3 rounded-full shadow-2xl flex items-center gap-2 max-w-[90vw] text-center w-max transition-all duration-300 ease-out animate-in fade-in slide-in-from-top-4">
              <span className="relative flex h-2.5 w-2.5 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span>
              </span>
              {locError}
            </div>
          )}
        </div>

        {/* Right Sidebar / Bottom Drawer */}
        <div className={`
          absolute bottom-0 left-0 right-0 lg:relative lg:bottom-auto lg:left-auto lg:right-auto
          w-full lg:w-[340px] xl:w-[380px] 
          bg-white shadow-[0_-10px_40px_rgba(0,0,0,0.15)] lg:shadow-[-10px_0_30px_rgba(0,0,0,0.05)] 
          z-10 flex flex-col 
          transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]
          ${isDrawerOpen ? 'translate-y-0' : 'translate-y-[calc(100%-40px)]'} 
          lg:translate-y-0
          h-[80vh] lg:h-full 
          rounded-t-3xl lg:rounded-none
        `}>

          {/* Mobile Handle (Clickable) */}
          <div
            className="w-full flex justify-center pt-4 pb-3 lg:hidden bg-white shrink-0 cursor-pointer touch-none"
            onClick={() => setIsDrawerOpen(!isDrawerOpen)}
          >
            <div className={`w-12 h-1.5 rounded-full transition-colors ${isDrawerOpen ? 'bg-gray-200' : 'bg-primary-300'}`} />
          </div>

          {/* Sidebar Header & Search */}
          <div
            className="px-5 pt-0 pb-4 lg:p-6 border-b border-gray-100 shrink-0 bg-white"
            onClick={() => !isDrawerOpen && window.innerWidth < 1024 && setIsDrawerOpen(true)}
          >
            <div className="mb-4 lg:mb-6">


              <h1 className="text-xl lg:text-2xl font-black text-gray-900 leading-tight mb-0.5 lg:mb-1">
                {t("ncrMarketLocator")}
              </h1>
              <p className="hidden lg:block text-sm text-gray-500 font-medium">
                {t("findNearestMarkets")}
              </p>
              {userLoc && (
                <p className="text-xs text-primary-600 mt-2 font-medium bg-primary-50 px-3 py-2 rounded-lg flex items-center gap-1.5">
                  <Locate className="w-3 h-3" />
                  {t("locationActive")}
                </p>
              )}
            </div>

            <h2 className="text-xs lg:text-sm font-bold text-gray-400 uppercase tracking-widest mb-2 lg:mb-3 flex items-center justify-between">
              {t("searchLocation")}
              <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full text-[10px]">
                {filteredMarkets.length}
              </span>
            </h2>

            <div className="relative group">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-primary-600 transition-colors" />
              <input
                type="text"
                placeholder={t("searchLocationPlaceholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-11 pr-4 py-3.5 bg-gray-50 border border-gray-200 rounded-xl text-sm font-medium transition-all focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 focus:bg-white"
              />
            </div>
          </div>

          {/* Scrollable Market List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-gray-200 scrollbar-track-transparent">
            {filteredMarkets.map(market => {
              const isSelected = selectedMarketId === market.id;
              const stats = marketStats[market.name] || { count: 0, avgChange: 0 };
              const hasData = stats.count > 0;

              return (
                <button
                  key={market.id}
                  onClick={() => handleMarketClick(market.id)}
                  className={`w-full text-left p-4 rounded-2xl transition-all duration-300 border relative overflow-hidden group ${isSelected
                      ? "bg-primary-50 border-primary-200 shadow-sm"
                      : "bg-white border-gray-100 hover:border-primary-100 hover:bg-primary-50/50"
                    }`}
                >
                  {/* Left accent line for selected state */}
                  {isSelected && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary-600" />
                  )}

                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h3 className={`font-bold text-sm mb-0.5 transition-colors ${isSelected ? "text-primary-900" : "text-gray-900 group-hover:text-primary-700"}`}>
                        {market.name}
                      </h3>
                      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{market.city}</span>
                    </div>
                    {market.distance !== undefined && (
                      <div className={`flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-lg shrink-0 ${market.distance < 5 ? "bg-accent/10 text-accent-dark" : "bg-gray-100 text-gray-500"
                        }`}>
                        <Navigation className="w-3 h-3" />
                        {market.distance < 1 ? "< 1 km" : `${market.distance.toFixed(1)} km`}
                      </div>
                    )}
                  </div>

                  <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col gap-3">
                    <p className={`text-[11px] text-gray-500 leading-relaxed ${isSelected ? '' : 'line-clamp-2'}`}>
                      {language === "tl" && market.description_tl ? market.description_tl : market.description}
                    </p>
                      
                    {/* Action button directly on the list item when selected */}
                    {isSelected && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          router.push(`/MarketData?origin=${encodeURIComponent(market.name)}`);
                        }}
                        className="self-start px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-xl flex items-center gap-1.5 text-[11px] font-bold transition-all shadow-sm active:scale-95"
                        title="View Market Data"
                      >
                        {t("viewMarketDataBtn")}
                        <ExternalLink className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </button>
              );
            })}

            {filteredMarkets.length === 0 && (
              <div className="text-center py-10 px-4">
                <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-3">
                  <MapPin className="w-5 h-5 text-gray-300" />
                </div>
                <p className="text-sm font-bold text-gray-900 mb-1">{t("noLocationsFound")}</p>
                <p className="text-xs text-gray-500">{t("tryAdjustingSearch")}</p>
              </div>
            )}
          </div>
        </div>

      </main>

    </div>
  );
}
