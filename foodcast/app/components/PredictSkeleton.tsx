export default function PredictSkeleton() {
  return (
    <main aria-busy="true" className="min-h-screen bg-surface">
      {/* Header Skeleton */}
      <section className="relative bg-primary-900 px-5 pb-10 pt-24 sm:pt-28 overflow-hidden">
        <div className="mx-auto max-w-7xl">
          <div className="h-6 w-36 bg-white/10 rounded-full mb-4 skeleton-shimmer-dark" />
          <div className="h-10 sm:h-12 w-64 sm:w-80 bg-white/15 rounded-xl mb-3 skeleton-shimmer-dark" />
          <div className="h-4 w-48 sm:w-72 bg-white/10 rounded-lg mb-8 skeleton-shimmer-dark" />
          <div className="h-14 max-w-lg bg-white/15 rounded-2xl skeleton-shimmer-dark" />
        </div>
      </section>

      {/* Content Grid Skeleton */}
      <div className="mx-auto max-w-7xl px-5 py-8 sm:py-12 space-y-8" aria-hidden="true">
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="h-96 rounded-3xl border border-gray-100 bg-white skeleton-shimmer lg:col-span-2" />
          <div className="h-96 rounded-3xl border border-gray-100 bg-white skeleton-shimmer" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 pt-4">
          {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
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
    </main>
  );
}
