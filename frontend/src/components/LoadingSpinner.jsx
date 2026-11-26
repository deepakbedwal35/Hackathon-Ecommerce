import React from "react";

export function LoadingSpinner({ size = "md", label = "Loading..." }) {
  const sizeClasses = {
    sm: "w-4 h-4 border-2",
    md: "w-5 h-5 border-2",
    lg: "w-8 h-8 border-3",
  };

  return (
    <div className="flex items-center gap-2" role="status">
      {/* allowed rounded-full */}
      <span
        className={`spinner inline-block ${sizeClasses[size] || sizeClasses.md} rounded-full border-slate-300 border-t-teal-700 animate-spin`}
        aria-hidden="true"
      />
      {label && <span className="text-xs text-slate-600">{label}</span>}
      <span className="sr-only">{label}</span>
    </div>
  );
}
