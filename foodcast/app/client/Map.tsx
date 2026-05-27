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
      <span className="text-gray-400 font-bold text-sm tracking-widest uppercase">Loading Map Data...</span>
    </div>
  )
});

interface MapProps {
  marketStats: Record<string, { count: number; avgChange: number }>;
  initialMarkets: MarketLocation[];
}

export default function MapClient({ marketStats, initialMarkets }: MapProps) {
  const { t, isTransitioning } = useLanguage();
  const router = useRouter();
  const [userLoc, setUserLoc] = useState<{ lat: number, lng: number } | null>(null);
  const [locError, setLocError] = useState<string | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);
  const [markets, setMarkets] = useState<(MarketLocation & { distance?: number })[]>(initialMarkets);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false); // Mobile drawer state

  // Helper: apply location result
  const applyLocation = (lat: number, lng: number, isApproximate = false) => {
    setUserLoc({ lat, lng });
    setLocError(isApproximate ? "Showing approximate location (IP-based). For accurate location, enable Location Services in your device settings." : null);
    const sorted = getNearestMarkets(initialMarkets, lat, lng);
    setMarkets(sorted);
    setIsLocating(false);
  };

  // Tier 3 Fallback: IP-based geolocation
  const fallbackToIPLocation = async (): Promise<boolean> => {
    try {
      const res = await fetch("https://ipapi.co/json/");
      if (!res.ok) throw new Error("IP lookup failed");
      const data = await res.json();
      if (data.latitude && data.longitude) {
        applyLocation(data.latitude, data.longitude, true);
        return true;
      }
      throw new Error("No coordinates");
    } catch {
      return false;
    }
  };

  // Tier 2 Fallback: Browser geolocation WITHOUT high accuracy (uses Wi-Fi/cell, faster)
  const tryLowAccuracy = (): Promise<boolean> => {
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          applyLocation(pos.coords.latitude, pos.coords.longitude);
          resolve(true);
        },
        async () => {
          // Both browser methods failed — try IP as last resort
          const ipSuccess = await fallbackToIPLocation();
          if (!ipSuccess) {
            setLocError("Could not determine location. Please enable Location Services in your device settings.");
            setIsLocating(false);
          }
          resolve(ipSuccess);
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
      );
    });
  };

  // Function to manually request location when user clicks the button
  const requestLocation = () => {
    setIsLocating(true);
    setLocError(null);
    setSelectedMarketId(null);

    if ("geolocation" in navigator) {
      // Tier 1: Try high-accuracy first (GPS on phones)
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          applyLocation(pos.coords.latitude, pos.coords.longitude);
        },
        () => {
          // High accuracy failed — try low accuracy (Tier 2)
          console.warn("High-accuracy geolocation failed, trying low accuracy...");
          tryLowAccuracy();
        },
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
      );
    } else {
      // No browser geolocation at all — try IP fallback
      fallbackToIPLocation().then(success => {
        if (!success) {
          setLocError("Geolocation not supported by this browser.");
          setIsLocating(false);
        }
      });
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
      <div className="h-[calc(100vh-72px)] bg-surface flex flex-col overflow-hidden">
        <div className="flex-1 flex items-center justify-center">
          <div className="w-12 h-12 border-4 border-primary-200 border-t-primary-800 rounded-full animate-spin" />
        </div>
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
            title="Find my current location"
          >
            <Locate className={`w-5 h-5 lg:w-5 lg:h-5 ${isLocating ? 'animate-spin' : userLoc ? 'text-white' : 'text-primary-600 group-hover:text-primary-700'}`} />
            <span className="hidden lg:inline text-sm font-bold">
              {isLocating ? 'Locating...' : userLoc ? 'Location Found' : 'Find My Location'}
            </span>
          </button>

          {/* Location error toast on map - only show if no location found */}
          {locError && !userLoc && (
            <div className="absolute bottom-24 lg:bottom-6 left-6 z-[1001] bg-red-50 border border-red-200 text-red-700 text-xs font-medium px-4 py-3 rounded-xl shadow-lg max-w-xs">
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
                NCR Market Locator
              </h1>
              <p className="hidden lg:block text-sm text-gray-500 font-medium">
                Find nearest markets and live commodity prices.
              </p>
              {locError && !userLoc && (
                <p className="text-xs text-orange-600 mt-2 font-medium bg-orange-50 px-3 py-2 rounded-lg">
                  {locError}
                </p>
              )}
              {userLoc && (
                <p className="text-xs text-primary-600 mt-2 font-medium bg-primary-50 px-3 py-2 rounded-lg flex items-center gap-1.5">
                  <Locate className="w-3 h-3" />
                  Location active — sorted by nearest
                </p>
              )}
            </div>

            <h2 className="text-xs lg:text-sm font-bold text-gray-400 uppercase tracking-widest mb-2 lg:mb-3 flex items-center justify-between">
              Search Location
              <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full text-[10px]">
                {filteredMarkets.length}
              </span>
            </h2>

            <div className="relative group">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-primary-600 transition-colors" />
              <input
                type="text"
                placeholder="Starting point, market, or city..."
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

                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-2 pr-10 relative">
                      {market.description}
                      
                      {/* Action button directly on the list item when selected */}
                      {isSelected && (
                        <div
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/MarketData?origin=${encodeURIComponent(market.name)}`);
                          }}
                          className="absolute right-0 top-1/2 -translate-y-1/2 w-8 h-8 bg-white rounded-full border border-primary-200 flex items-center justify-center text-primary-600 hover:bg-primary-600 hover:text-white transition-colors cursor-pointer shadow-sm"
                          title="View Market Data"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </div>
                      )}
                    </p>
                  </div>
                </button>
              );
            })}

            {filteredMarkets.length === 0 && (
              <div className="text-center py-10 px-4">
                <div className="w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mx-auto mb-3">
                  <MapPin className="w-5 h-5 text-gray-300" />
                </div>
                <p className="text-sm font-bold text-gray-900 mb-1">No locations found</p>
                <p className="text-xs text-gray-500">Try adjusting your search</p>
              </div>
            )}
          </div>
        </div>

      </main>

    </div>
  );
}
