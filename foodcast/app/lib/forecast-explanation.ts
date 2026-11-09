export function forecastExplanation(price: number | null, previous: number | null, horizon: string, first: boolean, start: string, end: string, dailyAverage: boolean, language: string): string {
  if (price == null || !Number.isFinite(price)) return language === 'tl' ? 'Walang forecast para sa panahong ito.' : 'No forecast is available for this period.';
  const period = horizon === 'weekly' ? 'week' : horizon === 'monthly' ? 'month' : 'day';
  const basis = dailyAverage
    ? language === 'tl' ? `Average ito ng mga hinulaang arawang presyo mula ${start} hanggang ${end}.` : `This is the average of the daily price forecasts from ${start} to ${end}.`
    : language === 'tl' ? `Forecast ito para sa ${start} hanggang ${end}.` : `This forecast covers ${start} to ${end}.`;
  if (previous == null || !Number.isFinite(previous) || previous <= 0) return basis;
  const change = Math.round((price - previous) * 100) / 100;
  const comparison = language === 'tl' ? first ? 'huling naitalang presyo' : 'nakaraang forecast' : first ? 'last reported price' : `previous ${period}'s forecast`;
  const movement = language === 'tl'
    ? change === 0 ? `Halos kapareho ito ng ${comparison} na ₱${previous.toFixed(2)}.` : `Mas ${change > 0 ? 'mataas' : 'mababa'} ito nang ₱${Math.abs(change).toFixed(2)} kumpara sa ${comparison} na ₱${previous.toFixed(2)}.`
    : change === 0 ? `It is about the same as the ${comparison} of ₱${previous.toFixed(2)}.` : `It is ₱${Math.abs(change).toFixed(2)} ${change > 0 ? 'higher' : 'lower'} than the ${comparison} of ₱${previous.toFixed(2)}.`;
  return `${basis} ${movement}`;
}
