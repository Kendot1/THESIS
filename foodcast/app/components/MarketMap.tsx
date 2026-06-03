"use client";

import { useEffect, useState, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, Circle } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { MarketLocation, getNearestMarkets } from "../lib/markets";
import { MapPin, ExternalLink, Layers } from "lucide-react";
import { useRouter } from "next/navigation";
import { useLanguage } from "../lib/i18n/LanguageContext";

// Map styles configuration
const MAP_STYLES = [
  { id: 'standard', name: 'Standard', url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: '&copy; OpenStreetMap contributors' },
  { id: 'satellite', name: 'Satellite', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attribution: '&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community' },
  { id: 'humanitarian', name: 'Humanitarian', url: 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', attribution: '&copy; OpenStreetMap contributors, Tiles style by Humanitarian OpenStreetMap Team hosted by OpenStreetMap France' },
  { id: 'positron', name: 'Positron (Light)', url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', attribution: '&copy; OpenStreetMap &copy; CARTO' },
  { id: 'dark_matter', name: 'Dark Matter', url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', attribution: '&copy; OpenStreetMap &copy; CARTO' },
  { id: 'esri_street', name: 'Esri Street', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', attribution: '&copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom, 2012' }
];

// Fix Leaflet's default icon path issues in Next.js
const customMarkerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const userMarkerIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

// Pre-create the icons to prevent massive memory leaks and re-renders
const selectedIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const nearestIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const defaultIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-grey.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const getMarkerIcon = (isNearest: boolean, isSelected: boolean) => {
  if (isSelected) return selectedIcon;
  if (isNearest) return nearestIcon;
  return defaultIcon;
};

// Component to handle map view updates when selected market changes
function MapController({ center, zoom }: { center: [number, number] | null, zoom: number }) {
  const map = useMap();

  // Fix leaflet size issues in dynamic containers
  useEffect(() => {
    // Immediate checks after render
    map.invalidateSize();
    const t1 = setTimeout(() => map.invalidateSize(), 100);
    const t2 = setTimeout(() => map.invalidateSize(), 500);
    const t3 = setTimeout(() => map.invalidateSize(), 1500);

    // Continuous observer for flexbox/window resizing
    const container = map.getContainer();
    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize();
    });
    resizeObserver.observe(container);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      resizeObserver.disconnect();
    };
  }, [map]);

  useEffect(() => {
    if (center) {
      map.setView(center, zoom, { animate: true, duration: 1 });
    }
    // Deep equality check on center array to prevent infinite re-renders
  }, [center?.[0], center?.[1], zoom, map]);
  return null;
}

interface MarketMapProps {
  markets: MarketLocation[];
  marketStats: Record<string, { count: number; avgChange: number }>;
  userLocation: { lat: number; lng: number } | null;
  selectedMarketId: string | null;
  onMarketSelect: (id: string) => void;
}



export default function MarketMap({ markets, marketStats, userLocation, selectedMarketId, onMarketSelect }: MarketMapProps) {
  const { t, language } = useLanguage();
  const router = useRouter();
  const [mapStyleId, setMapStyleId] = useState('standard');
  const [isStyleMenuOpen, setIsStyleMenuOpen] = useState(false);
  const activeStyle = MAP_STYLES.find(s => s.id === mapStyleId) || MAP_STYLES[0];

  // NCR Bounds to restrict panning
  const ncrBounds = L.latLngBounds(
    [14.33, 120.88], // SouthWest
    [14.80, 121.15]  // NorthEast
  );

  const selectedMarket = markets.find(m => m.id === selectedMarketId);
  const mapCenter: [number, number] = selectedMarket
    ? [selectedMarket.lat, selectedMarket.lng]
    : userLocation ? [userLocation.lat, userLocation.lng] : [14.5995, 120.9842]; // Default: Manila

  return (
    <div className="absolute inset-0 overflow-hidden z-0 bg-gray-100">
      <MapContainer
        center={mapCenter}
        zoom={selectedMarket ? 15 : 12}
        minZoom={11}
        maxBounds={ncrBounds}
        maxBoundsViscosity={1.0}
        preferCanvas={true} // Performance optimization
        style={{ height: "100%", width: "100%", position: "absolute", top: 0, left: 0, zIndex: 0 }}
        zoomControl={false}
      >
        <MapController center={mapCenter} zoom={selectedMarket ? 15 : 12} />


        {/* Custom Map Controls - Top Right */}
        <div className="leaflet-top leaflet-right absolute z-[1000] pointer-events-none flex flex-col items-end gap-3 pt-4 pr-4 lg:pt-6 lg:pr-6 w-full">
          {/* Zoom Controls */}
          <div className="leaflet-control-zoom leaflet-bar leaflet-control !m-0 border-none shadow-lg rounded-2xl overflow-hidden bg-white pointer-events-auto">
            <a className="leaflet-control-zoom-in !w-8 !h-8 !text-lg lg:!w-10 lg:!h-10 lg:!text-xl flex items-center justify-center hover:bg-gray-50 border-b border-gray-100 text-gray-700" href="#" title="Zoom in" role="button" aria-label="Zoom in" onClick={(e) => e.preventDefault()}>+</a>
            <a className="leaflet-control-zoom-out !w-8 !h-8 !text-lg lg:!w-10 lg:!h-10 lg:!text-xl flex items-center justify-center hover:bg-gray-50 text-gray-700" href="#" title="Zoom out" role="button" aria-label="Zoom out" onClick={(e) => e.preventDefault()}>−</a>
          </div>

          {/* Style Selector */}
          <div className="leaflet-control !m-0 pointer-events-auto relative">
            <button
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsStyleMenuOpen(!isStyleMenuOpen); }}
              className="w-8 h-8 lg:w-10 lg:h-10 bg-white rounded-2xl shadow-lg flex items-center justify-center text-gray-700 hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-200"
              title="Change Map Style"
            >
              <Layers className="w-4 h-4 lg:w-5 lg:h-5" />
            </button>

            {isStyleMenuOpen && (
              <div className="absolute top-0 right-12 lg:right-14 w-44 bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden flex flex-col py-2 animate-in fade-in zoom-in-95 duration-200">
                <div className="px-4 py-2 text-[10px] font-bold text-gray-400 uppercase tracking-widest border-b border-gray-50 mb-1">
                  {t("mapStyle")}
                </div>
                {MAP_STYLES.map(style => (
                  <button
                    key={style.id}
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); setMapStyleId(style.id); setIsStyleMenuOpen(false); }}
                    className={`px-4 py-2.5 text-left text-xs lg:text-sm font-medium transition-colors hover:bg-gray-50 ${mapStyleId === style.id ? 'text-primary-700 bg-primary-50/50' : 'text-gray-700'}`}
                  >
                    {style.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Dynamic Tile Layer */}
        <TileLayer
          key={activeStyle.id}
          attribution={activeStyle.attribution}
          url={activeStyle.url}
          keepBuffer={4} // Performance: Keep tiles loaded off-screen
          updateWhenZooming={false} // Performance: Don't load during zoom animation
          updateWhenIdle={true}
        />

        {/* User Location */}
        {userLocation && (
          <>
            <Marker position={[userLocation.lat, userLocation.lng]} icon={userMarkerIcon}>
              <Popup>
                <div className="text-center">
                  <strong className="text-sm font-bold block mb-1">{t("yourLocation")}</strong>
                  <span className="text-xs text-gray-500">{t("findingNearestMarkets")}</span>
                </div>
              </Popup>
            </Marker>
            <Circle
              center={[userLocation.lat, userLocation.lng]}
              radius={2000}
              pathOptions={{ fillColor: '#3b82f6', fillOpacity: 0.1, color: '#3b82f6', weight: 1 }}
            />
          </>
        )}

        {/* Markets */}
        {markets.map((market, index) => {
          const stats = marketStats[market.name] || { count: 0, avgChange: 0 };
          const hasData = stats.count > 0;

          // Determine states for icon coloring
          const isNearest = userLocation !== null && index === 0;
          const isSelected = market.id === selectedMarketId;

          return (
            <Marker
              key={market.id}
              position={[market.lat, market.lng]}
              icon={getMarkerIcon(isNearest, isSelected)}
              eventHandlers={{
                click: () => onMarketSelect(market.id),
              }}
            >
              <Popup className="market-popup">
                <div className="w-full flex flex-col">
                  {/* Image Header - Edge to Edge */}
                  <div className="w-full h-32 relative bg-gray-100 shrink-0">
                    <img
                      src={market.image || "https://images.unsplash.com/photo-1533900298318-6b8da08a523e?q=80&w=2070&auto=format&fit=crop"}
                      alt={market.name}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />

                    {/* Badge */}
                    <div className="absolute top-3 left-3 text-white">
                      <span className="text-[8px] font-bold uppercase tracking-widest bg-black/40 backdrop-blur-md px-2 py-1 rounded-full border border-white/10">
                        {market.type}
                      </span>
                    </div>

                    {/* Title inside image for dynamic feel */}
                    <div className="absolute bottom-3 left-4 right-4">
                      <h3 className="font-black text-lg text-white leading-tight mb-0.5 drop-shadow-md">{market.name}</h3>
                      <p className="text-[9px] text-white/80 font-medium leading-snug flex items-start gap-1 drop-shadow-sm">
                        <MapPin className="w-3 h-3 shrink-0 text-white/60" />
                        <span className="truncate">{market.address}</span>
                      </p>
                    </div>
                  </div>

                  {/* Body Content */}
                  <div className="p-4 bg-white">
                    <p className="text-[11px] text-gray-500 leading-relaxed mb-3">{language === "tl" && market.description_tl ? market.description_tl : market.description}</p>

                    <button
                      onClick={() => router.push(`/MarketData?origin=${encodeURIComponent(market.name)}`)}
                      className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-bold py-3 rounded-xl transition-all shadow-md shadow-primary-600/20 hover:shadow-lg hover:shadow-primary-600/30 active:scale-[0.98]"
                    >
                      {t("viewMarketDataBtn")}
                      <ExternalLink className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Global styles for leaflet popup customization */}
    </div>
  );
}
