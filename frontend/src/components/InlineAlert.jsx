import React from "react";

const STYLES = {
  info: {
    container: "bg-slate-50 border-slate-200 text-slate-800",
    iconColor: "text-slate-600",
  },
  success: {
    container: "bg-emerald-50 border-emerald-200 text-emerald-900",
    iconColor: "text-emerald-700",
  },
  warning: {
    container: "bg-amber-50 border-amber-200 text-amber-900",
    iconColor: "text-amber-700",
  },
  error: {
    container: "bg-rose-50 border-rose-200 text-rose-900",
    iconColor: "text-rose-700",
  },
};

export function InlineAlert({ type = "info", title, children, message, className = "" }) {
  const style = STYLES[type] || STYLES.info;

  return (
    <div
      role="alert"
      className={`rounded-md border p-3.5 text-xs leading-relaxed ${style.container} ${className}`}
    >
      {title && <div className="font-medium text-sm mb-1">{title}</div>}
      <div>{children || message}</div>
    </div>
  );
}
