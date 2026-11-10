export default function MapSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-hidden="true"
      className="h-[calc(100vh-72px)] mt-[72px] w-screen bg-surface flex flex-col overflow-hidden select-none"
    >
      <main className="flex-1 flex flex-col lg:flex-row h-full w-full relative overflow-hidden">
        {/* Left / Full Bleed Map Canvas */}
        <div className="absolute inset-0 lg:relative lg:flex-1 lg:h-full z-0 lg:border-r border-gray-200 bg-gray-100">
          <div className="w-full h-full relative overflow-hidden">
            {/* Shimmering Map Background */}
            <div className="absolute inset-0 skeleton-shimmer-map" />

            {/* Simulated Street Grid / Subtle Lines */}
            <div className="absolute inset-0 opacity-20 pointer-events-none">
              <div className="w-full h-full bg-[linear-gradient(to_right,#cbd5e1_1px,transparent_1px),linear-gradient(to_bottom,#cbd5e1_1px,transparent_1px)] bg-[size:4rem_4rem]" />
            </div>

            {/* Top Right Zoom Controls */}
            <div className="absolute top-4 right-4 lg:top-6 lg:right-6 z-10 flex flex-col gap-3">
              <div className="bg-white rounded-2xl shadow-lg border border-gray-100/60 overflow-hidden p-1 flex flex-col gap-1">
                <div className="w-9 h-9 lg:w-10 lg:h-10 bg-gray-100 rounded-xl skeleton-shimmer" />
                <div
                  className="w-9 h-9 lg:w-10 lg:h-10 bg-gray-100 rounded-xl skeleton-shimmer"
                  style={{ animationDelay: "80ms" }}
                />
              </div>
              <div
                className="w-9 h-9 lg:w-10 lg:h-10 bg-white border border-gray-100/60 rounded-2xl shadow-lg p-1"
                style={{ animationDelay: "160ms" }}
              >
                <div className="w-full h-full bg-gray-100 rounded-xl skeleton-shimmer" />
              </div>
            </div>

            {/* Bottom Left "Find My Location" Button */}
            <div className="absolute bottom-24 lg:bottom-6 left-4 lg:left-6 z-10">
              <div
                className="w-12 h-12 lg:w-48 lg:h-14 bg-white border border-gray-200/80 rounded-full lg:rounded-2xl shadow-lg flex items-center justify-center lg:justify-start px-0 lg:px-4 gap-3"
                style={{ animationDelay: "200ms" }}
              >
                <div className="w-6 h-6 rounded-full bg-primary-100 skeleton-shimmer shrink-0" />
                <div className="hidden lg:block h-3.5 w-24 bg-gray-200 rounded-md skeleton-shimmer" />
              </div>
            </div>

            {/* Simulated Map Market Pins */}
            {[
              { top: "28%", left: "42%", delay: 100 },
              { top: "35%", left: "58%", delay: 180 },
              { top: "45%", left: "38%", delay: 260 },
              { top: "52%", left: "50%", delay: 340 },
              { top: "62%", left: "44%", delay: 420 },
              { top: "38%", left: "68%", delay: 500 },
              { top: "68%", left: "55%", delay: 580 },
            ].map((pin, i) => (
              <div
                key={i}
                className="absolute z-10 -translate-x-1/2 -translate-y-full flex flex-col items-center"
                style={{ top: pin.top, left: pin.left }}
              >
                <div
                  className="w-8 h-10 bg-white rounded-t-full rounded-b-sm shadow-md border border-gray-100 p-1 flex items-center justify-center skeleton-shimmer"
                  style={{ animationDelay: `${pin.delay}ms` }}
                >
                  <div className="w-3.5 h-3.5 rounded-full bg-primary-600/30" />
                </div>
                <div className="w-2.5 h-1 bg-black/20 rounded-full blur-[1px] mt-0.5" />
              </div>
            ))}
          </div>
        </div>

        {/* Right Sidebar / Bottom Drawer (Exact matching geometry) */}
        <div
          className="
            absolute bottom-0 left-0 right-0 lg:relative lg:bottom-auto lg:left-auto lg:right-auto
            w-full lg:w-[340px] xl:w-[380px]
            bg-white shadow-[0_-10px_40px_rgba(0,0,0,0.15)] lg:shadow-[-10px_0_30px_rgba(0,0,0,0.05)]
            z-10 flex flex-col
            h-[80vh] lg:h-full
            rounded-t-3xl lg:rounded-none
          "
        >
          {/* Mobile Handle */}
          <div className="w-full flex justify-center pt-4 pb-3 lg:hidden bg-white shrink-0">
            <div className="w-12 h-1.5 rounded-full bg-gray-200" />
          </div>

          {/* Sidebar Header & Search Section */}
          <div className="px-5 pt-0 pb-4 lg:p-6 border-b border-gray-100 shrink-0 bg-white">
            <div className="mb-4 lg:mb-6">
              <div className="h-6 lg:h-7 w-48 sm:w-56 bg-gray-200 rounded-lg mb-2 skeleton-shimmer" />
              <div
                className="hidden lg:block h-3.5 w-64 bg-gray-100 rounded-md skeleton-shimmer"
                style={{ animationDelay: "80ms" }}
              />
            </div>

            <div className="flex items-center justify-between mb-2 lg:mb-3">
              <div
                className="h-3 w-28 bg-gray-200 rounded skeleton-shimmer"
                style={{ animationDelay: "140ms" }}
              />
              <div
                className="h-5 w-8 bg-gray-100 rounded-full skeleton-shimmer"
                style={{ animationDelay: "180ms" }}
              />
            </div>

            {/* Search Input Skeleton */}
            <div
              className="h-12 w-full bg-gray-50 border border-gray-200 rounded-xl px-4 flex items-center gap-3 skeleton-shimmer"
              style={{ animationDelay: "220ms" }}
            >
              <div className="w-4 h-4 rounded-full bg-gray-200 shrink-0" />
              <div className="h-3 w-40 bg-gray-200 rounded" />
            </div>
          </div>

          {/* Scrollable Market Cards List */}
          <div className="flex-1 overflow-hidden p-4 space-y-3">
            {/* Card 1: Simulates active/selected market card with left green accent bar */}
            <div className="w-full p-4 rounded-2xl border border-primary-200 bg-primary-50/40 relative overflow-hidden">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary-600" />
              <div className="flex justify-between items-start mb-2 pl-1">
                <div>
                  <div className="h-4 w-40 bg-gray-200 rounded-md mb-1.5 skeleton-shimmer" />
                  <div className="h-2.5 w-20 bg-gray-100 rounded skeleton-shimmer" />
                </div>
                <div className="h-5 w-14 bg-accent/20 rounded-lg skeleton-shimmer shrink-0" />
              </div>
              <div className="mt-3 pt-3 border-t border-primary-100/60 pl-1 space-y-2">
                <div className="h-3 w-full bg-gray-200/80 rounded skeleton-shimmer" />
                <div className="h-3 w-4/5 bg-gray-200/80 rounded skeleton-shimmer" />
                <div className="h-7 w-32 bg-primary-600/30 rounded-xl mt-3 skeleton-shimmer" />
              </div>
            </div>

            {/* Cards 2-6: Standard market cards */}
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="w-full p-4 rounded-2xl border border-gray-100 bg-white"
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div
                      className="h-4 w-36 bg-gray-200 rounded-md mb-1.5 skeleton-shimmer"
                      style={{ animationDelay: `${i * 70 + 80}ms` }}
                    />
                    <div
                      className="h-2.5 w-20 bg-gray-100 rounded skeleton-shimmer"
                      style={{ animationDelay: `${i * 70 + 110}ms` }}
                    />
                  </div>
                  <div
                    className="h-5 w-12 bg-gray-100 rounded-lg skeleton-shimmer shrink-0"
                    style={{ animationDelay: `${i * 70 + 140}ms` }}
                  />
                </div>
                <div className="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
                  <div
                    className="h-3 w-full bg-gray-100 rounded skeleton-shimmer"
                    style={{ animationDelay: `${i * 70 + 170}ms` }}
                  />
                  <div
                    className="h-3 w-3/4 bg-gray-100 rounded skeleton-shimmer"
                    style={{ animationDelay: `${i * 70 + 200}ms` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
