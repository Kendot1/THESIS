import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-surface flex flex-col items-center justify-center px-5 pt-20">
      <div className="max-w-md w-full bg-white rounded-3xl border border-gray-100 p-8 shadow-sm text-center">
        <div className="text-4xl mb-4 font-black text-gray-300">404</div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">Page Not Found</h2>
        <p className="text-sm text-gray-500 mb-6">
          The requested page could not be located.
        </p>
        <Link
          href="/"
          className="inline-flex px-5 py-2.5 bg-primary-800 text-white rounded-xl text-sm font-semibold hover:bg-primary-700 transition-colors"
        >
          Return Home
        </Link>
      </div>
    </main>
  );
}
