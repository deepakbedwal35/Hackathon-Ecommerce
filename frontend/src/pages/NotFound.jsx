import React from "react";
import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <div className="max-w-md mx-auto py-16 text-center space-y-4">
      <div className="text-4xl font-bold text-slate-300 font-mono">404</div>
      <h1 className="text-lg font-semibold text-slate-900">Page not found</h1>
      <p className="text-xs text-slate-500 leading-relaxed">
        The requested page does not exist or may have been moved.
      </p>
      <div>
        <Link
          to="/"
          className="inline-block text-xs font-medium px-4 py-2 bg-teal-700 text-white rounded-md hover:bg-teal-800 transition-colors"
        >
          Return to dashboard
        </Link>
      </div>
    </div>
  );
}
