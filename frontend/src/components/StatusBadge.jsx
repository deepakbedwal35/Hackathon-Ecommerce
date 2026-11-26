import React from "react";

const STATUS_CONFIGS = {
  // Orders
  placed: { text: "Placed", bg: "bg-slate-100", textCol: "text-slate-800", dot: "bg-slate-500" },
  shipped: { text: "Shipped", bg: "bg-amber-50", textCol: "text-amber-900", dot: "bg-amber-600" },
  delivered: { text: "Delivered", bg: "bg-emerald-50", textCol: "text-emerald-900", dot: "bg-emerald-600" },
  cancelled: { text: "Cancelled", bg: "bg-rose-50", textCol: "text-rose-900", dot: "bg-rose-600" },

  // Refunds
  pending_review: { text: "Under review", bg: "bg-amber-50", textCol: "text-amber-900", dot: "bg-amber-600" },
  approved: { text: "Approved", bg: "bg-emerald-50", textCol: "text-emerald-900", dot: "bg-emerald-600" },
  processed: { text: "Completed", bg: "bg-emerald-50", textCol: "text-emerald-900", dot: "bg-emerald-600" },
  rejected: { text: "Rejected", bg: "bg-rose-50", textCol: "text-rose-900", dot: "bg-rose-600" },
  failed: { text: "Failed", bg: "bg-rose-50", textCol: "text-rose-900", dot: "bg-rose-600" },

  // Tickets
  open: { text: "Open", bg: "bg-slate-100", textCol: "text-slate-800", dot: "bg-slate-600" },
  awaiting_customer: { text: "Awaiting response", bg: "bg-amber-50", textCol: "text-amber-900", dot: "bg-amber-600" },
  escalated: { text: "Escalated to team", bg: "bg-amber-50", textCol: "text-amber-900", dot: "bg-amber-600" },
  resolved: { text: "Resolved", bg: "bg-emerald-50", textCol: "text-emerald-900", dot: "bg-emerald-600" },
  closed: { text: "Closed", bg: "bg-slate-100", textCol: "text-slate-700", dot: "bg-slate-500" },
};

export function StatusBadge({ status, label }) {
  const key = String(status || "").toLowerCase();
  const cfg = STATUS_CONFIGS[key] || {
    text: label || key.replace(/_/g, " "),
    bg: "bg-slate-100",
    textCol: "text-slate-800",
    dot: "bg-slate-500",
  };

  const displayText = label || cfg.text;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border border-slate-200 ${cfg.bg} ${cfg.textCol}`}
    >
      {/* allowed rounded-full for status dot */}
      <span className={`status-dot w-1.5 h-1.5 rounded-full ${cfg.dot}`} aria-hidden="true" />
      <span>{displayText}</span>
    </span>
  );
}
