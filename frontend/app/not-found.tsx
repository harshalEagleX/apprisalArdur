import Link from "next/link";

export default function NotFound() {
  return (
    <div className="foundation-grid flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
      <div className="foundation-fade-in max-w-sm rounded-lg border border-white/10 bg-[#11161C]/90 p-8 text-center shadow-[0_20px_55px_rgba(0,0,0,0.36)]">
        <div className="mb-4 text-5xl font-semibold tabular-nums text-blue-400">404</div>
        <h1 className="mb-2 text-2xl font-semibold tracking-normal">Page not found</h1>
        <p className="mb-6 text-sm text-slate-400">The route does not exist or is no longer available.</p>
        <Link href="/" className="rounded-md bg-blue-600 px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500">
          Go Home
        </Link>
      </div>
    </div>
  );
}
