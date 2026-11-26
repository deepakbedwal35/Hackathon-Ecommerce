import React from "react";

export function DemoBanner() {
  const isDemo = import.meta.env.VITE_DEMO_MODE !== "false";
  if (!isDemo) return null;

  return (
    <aside
      aria-label="Demo environment notice"
      className="bg-slate-100 border-b border-slate-200 px-4 py-1.5 text-xs text-slate-600 text-center"
    >
      <div className="max-w-5xl mx-auto">
        Demo environment. Orders and refunds shown here are sample data and no real payments are made.
      </div>
    </aside>
  );
}
