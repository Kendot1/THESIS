export default function NewsLoading() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Hero Skeleton */}
      <section className="relative bg-primary-900 pt-30 md:pt-40 pb-10 md:pb-20 overflow-hidden">
        <div className="absolute inset-0 bg-primary-900" />
        <div className="relative z-10 max-w-7xl mx-auto px-5 lg:px-10">
          <div className="h-7 w-44 bg-white/10 rounded-full mb-8 skeleton-shimmer-dark" />
          <div className="h-10 sm:h-14 w-72 sm:w-96 bg-white/15 rounded-xl mb-4 skeleton-shimmer-dark" />
          <div className="space-y-2 mb-12 max-w-2xl">
            <div className="h-4 w-full bg-white/10 rounded-lg skeleton-shimmer-dark" />
            <div className="h-4 w-3/4 bg-white/10 rounded-lg skeleton-shimmer-dark" />
          </div>
          {/* Featured Article Skeleton */}
          <div className="bg-white rounded-[2.5rem] overflow-hidden shadow-2xl flex flex-col lg:flex-row">
            <div className="lg:w-1/2 h-[200px] lg:h-[320px] bg-gray-100 skeleton-shimmer" />
            <div className="lg:w-1/2 p-6 md:p-8 flex flex-col justify-center space-y-4">
              <div className="flex items-center gap-4">
                <div className="h-6 w-20 bg-gray-200 rounded-lg skeleton-shimmer" />
                <div className="h-4 w-28 bg-gray-100 rounded-lg skeleton-shimmer" />
              </div>
              <div className="space-y-3">
                <div className="h-7 w-full bg-gray-200 rounded-lg skeleton-shimmer" />
                <div className="h-7 w-4/5 bg-gray-200 rounded-lg skeleton-shimmer" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-full bg-gray-100 rounded-md skeleton-shimmer" />
                <div className="h-4 w-5/6 bg-gray-100 rounded-md skeleton-shimmer" />
              </div>
              <div className="h-5 w-36 bg-gray-200 rounded-lg skeleton-shimmer" />
            </div>
          </div>
        </div>
      </section>

      {/* Filter Bar Skeleton */}
      <section className="sticky top-[72px] z-40 bg-surface/90 backdrop-blur-xl border-b border-gray-100 py-6">
        <div className="max-w-7xl mx-auto px-5 lg:px-10">
          <div className="flex flex-col lg:flex-row gap-6 items-center justify-between">
            <div className="w-full lg:max-w-xl h-14 bg-white border border-gray-200 rounded-3xl skeleton-shimmer" />
            <div className="flex items-center gap-4">
              <div className="h-12 w-32 bg-white border border-gray-200 rounded-2xl skeleton-shimmer" />
              <div className="h-12 w-32 bg-white border border-gray-200 rounded-2xl skeleton-shimmer" />
            </div>
          </div>
        </div>
      </section>

      {/* Article Grid Skeleton */}
      <section className="py-8 max-w-7xl mx-auto px-5 lg:px-10">
        <div className="flex items-center justify-between mb-6">
          <div className="h-4 w-32 bg-gray-200 rounded-lg skeleton-shimmer" />
          <div className="h-px flex-1 bg-gray-100 mx-8 hidden md:block" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 lg:gap-10">
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div key={i} className="bg-white rounded-3xl border border-gray-100 p-4 h-[380px] flex flex-col shadow-sm justify-between">
              <div>
                <div className="h-48 w-full bg-gray-100 rounded-2xl mb-5 skeleton-shimmer" />
                <div className="flex gap-2 mb-4">
                  <div className="h-5 w-20 bg-gray-200 rounded-lg skeleton-shimmer" />
                  <div className="h-5 w-24 bg-gray-100 rounded-lg skeleton-shimmer" />
                </div>
                <div className="space-y-2 mb-4">
                  <div className="h-5 w-full bg-gray-200 rounded-lg skeleton-shimmer" />
                  <div className="h-5 w-3/4 bg-gray-200 rounded-lg skeleton-shimmer" />
                </div>
              </div>
              <div className="h-4 w-32 bg-gray-100 rounded skeleton-shimmer" />
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
