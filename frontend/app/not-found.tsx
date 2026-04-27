export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
      <div className="text-center">
        <div className="text-6xl font-bold text-blue-500 mb-4">404</div>
        <h1 className="text-2xl font-semibold mb-2">Page Not Found</h1>
        <p className="text-slate-400 mb-6">The page you are looking for doesn't exist.</p>
        <a href="/" className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors">
          Go Home
        </a>
      </div>
    </div>
  );
}
