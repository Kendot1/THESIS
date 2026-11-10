export default function AboutLoading() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Hero Skeleton */}
      <section className="relative bg-primary-900 pt-32 pb-20 px-5 lg:px-10 overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="h-6 w-32 bg-white/10 rounded-full mb-6 skeleton-shimmer-dark" />
          <div className="h-12 sm:h-16 w-3/4 max-w-2xl bg-white/15 rounded-2xl mb-6 skeleton-shimmer-dark" />
          <div className="h-20 w-full max-w-3xl bg-white/10 rounded-2xl mb-12 skeleton-shimmer-dark" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-6 border-t border-white/10">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white/10 skeleton-shimmer-dark" />
                <div className="space-y-1.5">
                  <div className="h-5 w-16 bg-white/10 rounded-lg skeleton-shimmer-dark" />
                  <div className="h-3 w-20 bg-white/5 rounded-md skeleton-shimmer-dark" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Content Section Skeleton */}
      <section className="py-16 px-5 lg:px-10 max-w-7xl mx-auto">
        <div className="h-10 w-64 bg-gray-200 rounded-xl mb-12 skeleton-shimmer" />
        <div className="grid md:grid-cols-3 gap-8">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm">
              <div className="w-12 h-12 rounded-2xl bg-gray-100 mb-6 skeleton-shimmer" />
              <div className="h-6 w-3/4 bg-gray-200 rounded-lg mb-2 skeleton-shimmer" />
              <div className="h-5 w-1/2 bg-gray-100 rounded-lg mb-4 skeleton-shimmer" />
              <div className="space-y-2">
                <div className="h-3 w-full bg-gray-100 rounded-md skeleton-shimmer" />
                <div className="h-3 w-2/3 bg-gray-100 rounded-md skeleton-shimmer" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
