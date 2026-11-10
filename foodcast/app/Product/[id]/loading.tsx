export default function ProductLoading() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Hero Header Skeleton */}
      <section className="relative bg-primary-900 py-10 pt-24 sm:pt-28 overflow-hidden">
        <div className="max-w-7xl mx-auto px-5 lg:px-10">
          <div className="h-4 w-24 bg-white/10 rounded skeleton-shimmer-dark mb-6" />
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-3 max-w-xl w-full">
              <div className="h-6 w-28 bg-white/10 rounded-full skeleton-shimmer-dark" />
              <div className="h-10 sm:h-14 w-72 sm:w-96 bg-white/15 rounded-2xl skeleton-shimmer-dark" />
              <div className="h-4 w-full max-w-md bg-white/10 rounded skeleton-shimmer-dark" />
              <div className="h-4 w-3/4 max-w-sm bg-white/10 rounded skeleton-shimmer-dark" />
            </div>
            <div className="h-20 w-full sm:w-80 bg-white/10 rounded-3xl skeleton-shimmer-dark" />
          </div>
        </div>
      </section>

      {/* Main Content Area Skeleton */}
      <div className="max-w-7xl mx-auto px-5 lg:px-10 py-8 sm:py-12 space-y-8" aria-hidden="true">
        {/* Chart Card Skeleton */}
        <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="h-8 w-48 bg-gray-200 rounded-xl skeleton-shimmer" />
            <div className="h-10 w-72 bg-gray-100 rounded-2xl skeleton-shimmer" />
          </div>
          <div className="h-[360px] sm:h-[420px] w-full bg-gray-100 rounded-2xl skeleton-shimmer" />
        </div>

        {/* AI Market Analysis Skeleton */}
        <div className="bg-white rounded-3xl border border-gray-100 p-6 sm:p-8 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <div className="h-7 w-52 bg-gray-200 rounded-xl skeleton-shimmer" />
            <div className="h-8 w-28 bg-gray-100 rounded-full skeleton-shimmer" />
          </div>
          <div className="grid md:grid-cols-2 gap-8">
            <div className="h-[180px] bg-gray-50 rounded-2xl p-6 skeleton-shimmer" />
            <div className="h-[180px] bg-gray-50 rounded-2xl p-6 skeleton-shimmer" />
          </div>
        </div>

        {/* Related Commodities Skeleton */}
        <div className="space-y-6 pt-4">
          <div className="h-8 w-56 bg-gray-200 rounded-xl skeleton-shimmer" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-[380px] rounded-3xl border border-gray-100 bg-white p-5 flex flex-col justify-between">
                <div>
                  <div className="aspect-4/3 rounded-2xl bg-gray-100 skeleton-shimmer mb-4" />
                  <div className="flex justify-between mb-2">
                    <div className="h-3 w-16 bg-gray-100 rounded skeleton-shimmer" />
                    <div className="h-3 w-12 bg-gray-100 rounded skeleton-shimmer" />
                  </div>
                  <div className="h-5 w-3/4 bg-gray-200 rounded-lg skeleton-shimmer mb-2" />
                  <div className="h-6 w-20 bg-gray-100 rounded-md skeleton-shimmer" />
                </div>
                <div className="space-y-2 mt-auto pt-4">
                  <div className="h-4 w-full bg-gray-100 rounded skeleton-shimmer" />
                  <div className="h-10 w-full bg-gray-100 rounded-full skeleton-shimmer" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
