export interface GeocodedLocation {
  lat: number;
  lng: number;
  address: string;
}

// In-memory cache to avoid duplicate API requests during the same build/session
const geocodeCache = new Map<string, GeocodedLocation | null>();

/**
 * Geocodes a market origin string using OpenStreetMap Nominatim API.
 * Adheres to the 1 request per second policy.
 */
export async function geocodeOrigin(origin: string): Promise<GeocodedLocation | null> {
  if (!origin || origin === "All") return null;

  // Check cache first
  if (geocodeCache.has(origin)) {
    return geocodeCache.get(origin) || null;
  }

  // Construct a query that targets markets in Metro Manila to improve accuracy
  // e.g., "Divisoria" -> "Divisoria market Metro Manila Philippines"
  const searchQuery = origin.toLowerCase().includes("market") 
    ? `${origin} Metro Manila Philippines`
    : `${origin} market Metro Manila Philippines`;

  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(searchQuery)}&format=json&limit=1`;

  try {
    // 1. Fetch from OSM
    const res = await fetch(url, {
      headers: {
        "User-Agent": "FoodcastApp/1.0 (Thesis Project)",
      },
    });

    if (!res.ok) {
      console.warn(`Geocoding failed for ${origin}: ${res.statusText}`);
      geocodeCache.set(origin, null);
      return null;
    }

    const data = await res.json();

    if (data && data.length > 0) {
      const result = data[0];
      const location = {
        lat: parseFloat(result.lat),
        lng: parseFloat(result.lon),
        address: result.display_name || origin,
      };
      geocodeCache.set(origin, location);
      return location;
    }

    // Fallback if not found with "market", try just the raw name in NCR
    const fallbackUrl = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(origin + " Metro Manila Philippines")}&format=json&limit=1`;
    const fallbackRes = await fetch(fallbackUrl, {
      headers: { "User-Agent": "FoodcastApp/1.0 (Thesis Project)" },
    });
    const fallbackData = await fallbackRes.json();
    
    if (fallbackData && fallbackData.length > 0) {
      const result = fallbackData[0];
      const location = {
        lat: parseFloat(result.lat),
        lng: parseFloat(result.lon),
        address: result.display_name || origin,
      };
      geocodeCache.set(origin, location);
      return location;
    }

    console.warn(`No location found for origin: ${origin}`);
    geocodeCache.set(origin, null);
    return null;
  } catch (error) {
    console.error(`Geocoding error for ${origin}:`, error);
    geocodeCache.set(origin, null);
    return null;
  }
}

/**
 * Utility to wait for a specified number of milliseconds.
 * Useful for rate-limiting API requests.
 */
export const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
