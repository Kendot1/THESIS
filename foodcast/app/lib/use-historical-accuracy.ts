"use client";
import useSWR from 'swr';
export function useHistoricalAccuracy(): number | null {
  const { data } = useSWR('/api/forecast/performance', async (url: string) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Historical accuracy unavailable');
    return response.json();
  });
  // Current local rolling periods are open; historical daily MAPE is not their accuracy.
  if (process.env.NODE_ENV === 'development' && process.env.NEXT_PUBLIC_FOODCAST_LOCAL_MODEL === 'current-hybrid') return null;
  const value = data?.historical_forecast_accuracy_pct;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
