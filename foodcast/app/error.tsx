"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("App Router caught error:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-surface flex flex-col items-center justify-center px-5 pt-20">
      <div className="max-w-md w-full bg-white rounded-3xl border border-gray-100 p-8 shadow-sm text-center">
        <div className="w-12 h-12 rounded-2xl bg-primary-50 text-primary-800 flex items-center justify-center mx-auto mb-4 font-bold text-xl">
          !
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">Something went wrong</h2>
        <p className="text-sm text-gray-500 mb-6">
          An error occurred while loading this page. You can try refreshing or returning home.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => reset()}
            className="px-5 py-2.5 bg-primary-800 text-white rounded-xl text-sm font-semibold hover:bg-primary-700 transition-colors"
          >
            Try again
          </button>
          <Link
            href="/"
            className="px-5 py-2.5 bg-gray-100 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-200 transition-colors"
          >
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
