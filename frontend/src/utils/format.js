export function formatMoney(amount) {
  const num = Number(amount) || 0;
  return `INR ${num.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatDate(isoString) {
  if (!isoString) return "Pending";
  const date = new Date(isoString);
  return date.toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatAge(isoString, nowMs = Date.now()) {
  if (!isoString) return "None";
  const createdMs = new Date(isoString).getTime();
  if (Number.isNaN(createdMs)) return "Unknown";
  const diffSec = Math.max(0, Math.floor((nowMs - createdMs) / 1000));
  const days = Math.floor(diffSec / 86400);
  const hours = Math.floor((diffSec % 86400) / 3600);
  const mins = Math.floor((diffSec % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  if (mins > 0) return `${mins}m`;
  return "Just now";
}

export function formatRefundReviewNotice(config) {
  if (!config) return "";
  const mode = String(config.refund_review_mode || "above_limit").toLowerCase();
  if (mode === "all") {
    return "Every refund is reviewed and approved by our team before it is issued.";
  }
  const limitNum = Number(config.auto_refund_limit);
  const formattedLimit = Number.isFinite(limitNum)
    ? limitNum.toLocaleString("en-IN")
    : String(config.auto_refund_limit || "5,000");
  return `Refunds above INR ${formattedLimit} are reviewed by our team.`;
}

export function getRoleHomePath(user) {
  const role = String(user?.role || "").toLowerCase();
  return role === "agent" || role === "admin" ? "/staff" : "/";
}

export function getEnumLabel(options, value) {
  if (Array.isArray(options)) {
    const match = options.find((opt) => opt.value === value);
    if (match && match.label) return match.label;
  }
  return String(value || "").replace(/_/g, " ");
}

export function mergeMessagesById(existing, incoming) {
  const map = new Map();
  for (const m of existing || []) {
    map.set(m.id, m);
  }
  for (const m of incoming || []) {
    map.set(m.id, m);
  }
  return Array.from(map.values()).sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}
