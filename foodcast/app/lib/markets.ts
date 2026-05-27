export interface MarketLocation {
  id: string;
  name: string;
  city: string;
  lat: number;
  lng: number;
  address: string;
  type: string;
  description: string;
  image?: string;
}

import marketData from "./markets.json";

export const ncrMarkets: MarketLocation[] = marketData as MarketLocation[];

export function getNearestMarkets(
  markets: MarketLocation[], 
  userLat: number, 
  userLng: number
): (MarketLocation & { distance: number })[] {
  return markets.map(market => {
    // Haversine formula for distance in km
    const R = 6371;
    const dLat = (market.lat - userLat) * Math.PI / 180;
    const dLng = (market.lng - userLng) * Math.PI / 180;
    const a = 
      Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(userLat * Math.PI / 180) * Math.cos(market.lat * Math.PI / 180) * 
      Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const distance = R * c;
    return { ...market, distance };
  }).sort((a, b) => a.distance - b.distance);
}
