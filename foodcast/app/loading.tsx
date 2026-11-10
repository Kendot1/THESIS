export default function RootLoading() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Hero Section Skeleton */}
      <section className="relative min-h-[55vh] sm:min-h-[85vh] flex items-center bg-primary-900 overflow-hidden">
        <div className="relative max-w-7xl mx-auto px-5 lg:px-10 sm:px-5 w-full pt-32 pb-20">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <div className="max-w-xl">
              <div className="h-6 w-48 bg-white/10 rounded-full mb-8 skeleton-shimmer-dark" />
              <div className="space-y-4 mb-6">
                <div className="h-12 sm:h-16 w-3/4 bg-white/15 rounded-2xl skeleton-shimmer-dark" />
                <div className="h-12 sm:h-16 w-full bg-white/15 rounded-2xl skeleton-shimmer-dark" />
                <div className="h-12 sm:h-16 w-1/2 bg-white/15 rounded-2xl skeleton-shimmer-dark" />
              </div>
              <div className="h-5 w-5/6 bg-white/10 rounded-lg mb-10 skeleton-shimmer-dark" />
              <div className="h-14 w-full max-w-lg bg-white/20 rounded-2xl skeleton-shimmer-dark" />
              <div className="grid grid-cols-3 gap-4 sm:gap-8 mt-10 max-w-lg">
                <div className="h-12 bg-white/10 rounded-xl skeleton-shimmer-dark" />
                <div className="h-12 bg-white/10 rounded-xl skeleton-shimmer-dark" />
                <div className="h-12 bg-white/10 rounded-xl skeleton-shimmer-dark" />
              </div>
            </div>
            <div className="hidden lg:block">
              <div className="w-full h-[450px] bg-white/5 rounded-[3rem] skeleton-shimmer-dark" />
            </div>
          </div>
        </div>
      </section>

      {/* Daily Movers Skeleton */}
      <section className="py-5 sm:py-10 bg-surface -mt-10 relative z-20">
        <div className="max-w-7xl mx-auto px-5 lg:px-10">
          <div className="flex items-end justify-between mb-4 sm:mb-8">
            <div className="space-y-2">
              <div className="h-8 w-64 bg-gray-200 rounded-xl skeleton-shimmer" />
              <div className="h-4 w-48 bg-gray-100 rounded-lg skeleton-shimmer" />
            </div>
            <div className="flex gap-2">
              <div className="h-10 w-10 bg-gray-100 rounded-xl skeleton-shimmer" />
              <div className="h-10 w-10 bg-gray-100 rounded-xl skeleton-shimmer" />
            </div>
          </div>
          <div className="flex gap-4 sm:gap-6 overflow-hidden">
            {[1, 2, 3].map(i => (
              <div key={i} className="shrink-0 w-[300px] sm:w-[420px] lg:w-[480px] bg-white rounded-3xl border border-gray-100 p-6 h-[220px]">
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-16 h-16 bg-gray-100 rounded-2xl skeleton-shimmer" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-1/3 bg-gray-100 rounded-md skeleton-shimmer" />
                    <div className="h-6 w-3/4 bg-gray-200 rounded-lg skeleton-shimmer" />
                  </div>
                  <div className="h-8 w-20 bg-gray-100 rounded-full skeleton-shimmer" />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-6">
                  <div className="space-y-2">
                    <div className="h-3 w-16 bg-gray-100 rounded-md skeleton-shimmer" />
                    <div className="h-6 w-24 bg-gray-200 rounded-lg skeleton-shimmer" />
                  </div>
                  <div className="space-y-2">
                    <div className="h-3 w-16 bg-gray-100 rounded-md skeleton-shimmer" />
                    <div className="h-6 w-24 bg-gray-200 rounded-lg skeleton-shimmer" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Featured Grid Skeleton */}
      <section className="py-12 max-w-7xl mx-auto px-5 lg:px-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="h-64 rounded-3xl bg-white border border-gray-100 p-6 skeleton-shimmer" />
          ))}
        </div>
      </section>
    </main>
  );
}
