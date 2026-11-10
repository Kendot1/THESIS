export default function MarketDataLoading() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Header Skeleton */}
      <section className="relative bg-gradient-to-br from-primary-800 to-primary-900 py-7 sm:py-10 pt-22 sm:pt-25 overflow-hidden">
        <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
          <div className="h-4 w-32 bg-white/10 rounded-md mb-6 skeleton-shimmer-dark" />
          <div className="h-10 sm:h-12 w-48 sm:w-64 bg-white/10 rounded-xl mb-4 skeleton-shimmer-dark" />
          <div className="h-4 w-64 sm:w-96 bg-white/5 rounded-lg skeleton-shimmer-dark" />
        </div>
      </section>

      <div className="max-w-7xl mx-auto px-5 lg:px-10 py-6 sm:py-8 lg:py-10" aria-hidden="true">
        {/* Filter Skeleton */}
        <div className="mb-5 flex flex-col lg:flex-row gap-4">
          <div className="flex gap-2 flex-1">
            <div className="h-12 flex-1 bg-white border border-gray-100 rounded-2xl skeleton-shimmer" />
            <div className="h-12 w-12 bg-white border border-gray-100 rounded-2xl skeleton-shimmer" />
          </div>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="h-12 w-24 bg-white border border-gray-100 rounded-2xl skeleton-shimmer hidden sm:block" />
            ))}
          </div>
        </div>

        {/* Table Skeleton */}
        <div className="bg-white rounded-[1.5rem] border border-gray-100 shadow-xl overflow-hidden">
          <div className="h-14 bg-primary-700/50 skeleton-shimmer border-b border-black/5" />
          <div className="divide-y divide-gray-50">
            {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
              <div key={i} className="flex items-center justify-between p-4 sm:px-8 py-5">
                <div className="flex items-center gap-1.5 sm:gap-2">
                  <div className="w-2 sm:w-2.5 h-2 sm:h-2.5 rounded-full bg-gray-200 skeleton-shimmer" />
                  <div className="h-4 w-28 bg-gray-200 rounded-md skeleton-shimmer" />
                </div>
                <div className="h-6 w-20 bg-primary-50 rounded-lg skeleton-shimmer hidden sm:block" />
                <div className="h-5 w-16 bg-gray-200 rounded-md skeleton-shimmer" />
                <div className="h-5 w-16 bg-gray-200 rounded-md skeleton-shimmer" />
                <div className="h-6 w-16 bg-gray-100 rounded-full skeleton-shimmer" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
