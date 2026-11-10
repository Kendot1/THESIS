export default function ResourcesSkeleton() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Hero Skeleton */}
      <section className="relative bg-primary-900 pt-32 pb-20 px-5 lg:px-10 overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="h-6 w-32 bg-white/10 rounded-full mb-6 skeleton-shimmer-dark" />
          <div className="h-12 sm:h-16 w-3/4 max-w-2xl bg-white/15 rounded-2xl mb-6 skeleton-shimmer-dark" />
          <div className="h-16 w-full max-w-2xl bg-white/10 rounded-xl skeleton-shimmer-dark" />
        </div>
      </section>

      {/* Grid Skeleton */}
      <section className="py-16 px-5 lg:px-10 max-w-7xl mx-auto space-y-12">
        <div className="space-y-4">
          <div className="h-8 w-64 bg-gray-200 rounded-xl skeleton-shimmer" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm h-64 flex flex-col justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-gray-100 rounded-2xl skeleton-shimmer" />
                  <div className="h-6 w-36 bg-gray-200 rounded-lg skeleton-shimmer" />
                </div>
                <div className="space-y-2">
                  <div className="h-3.5 w-full bg-gray-100 rounded skeleton-shimmer" />
                  <div className="h-3.5 w-4/5 bg-gray-100 rounded skeleton-shimmer" />
                </div>
                <div className="h-4 w-28 bg-gray-100 rounded skeleton-shimmer" />
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
