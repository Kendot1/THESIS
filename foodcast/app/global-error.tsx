"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface flex flex-col items-center justify-center px-5">
        <div className="max-w-md w-full bg-white rounded-3xl border border-gray-100 p-8 shadow-sm text-center">
          <h2 className="text-xl font-bold text-gray-900 mb-2">Application Error</h2>
          <p className="text-sm text-gray-500 mb-6">
            A critical error occurred. Please try refreshing the application.
          </p>
          <button
            onClick={() => reset()}
            className="px-5 py-2.5 bg-primary-800 text-white rounded-xl text-sm font-semibold hover:bg-primary-700 transition-colors"
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
