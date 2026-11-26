import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { useMetaEnums } from "../../hooks/useMeta.js";
import { formatAge, formatMoney, getEnumLabel } from "../../utils/format.js";
import { StatusBadge } from "../../components/StatusBadge.jsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.jsx";
import { InlineAlert } from "../../components/InlineAlert.jsx";

export function Approvals() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { enums, error: enumsError, refetch: refetchEnums } = useMetaEnums();

  const decisionFilter = searchParams.get("decision") || "";
  const priorityFilter = searchParams.get("priority") || "";
  const assignedToMe = searchParams.get("assigned_to") === "me";
  const searchQuery = searchParams.get("q") || "";
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadQueue(silent = false) {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const params = { page, page_size: 20 };
      if (decisionFilter) params.decision = decisionFilter;
      if (priorityFilter) params.priority = priorityFilter;
      if (assignedToMe) params.assigned_to = "me";
      const res = await api.staff.listEscalations(params);
      setData(res);
    } catch (err) {
      setError(err.message || "Unable to load approvals queue.");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadQueue(false);
  }, [decisionFilter, priorityFilter, assignedToMe, page]);

  // Poll queue every 15s while visible
  useEffect(() => {
    const intervalId = setInterval(() => {
      if (document.visibilityState === "visible") {
        loadQueue(true);
      }
    }, 15000);
    return () => clearInterval(intervalId);
  }, [decisionFilter, priorityFilter, assignedToMe, page]);

  function updateParam(key, value) {
    const next = new URLSearchParams(searchParams);
    if (!value) {
      next.delete(key);
    } else {
      next.set(key, String(value));
    }
    if (key !== "page") {
      next.delete("page");
    }
    setSearchParams(next);
  }

  const rawItems = data?.items || [];
  const trimmedQ = searchQuery.trim().toLowerCase();
  const items = trimmedQ
    ? rawItems.filter(
        (it) =>
          String(it.ticket_subject || "").toLowerCase().includes(trimmedQ) ||
          String(it.customer_name || "").toLowerCase().includes(trimmedQ) ||
          String(it.order_number || "").toLowerCase().includes(trimmedQ) ||
          String(it.id || "").toLowerCase().includes(trimmedQ)
      )
    : rawItems;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            Refund approvals queue
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Escalated refund requests sorted by priority then oldest. Auto-refreshes every 15 seconds.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadQueue(false)}
          className="self-start sm:self-auto px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors"
        >
          Refresh
        </button>
      </div>

      {enumsError && (
        <InlineAlert type="error" title="Unable to load filter options">
          <div className="flex items-center justify-between">
            <span>{enumsError}</span>
            <button
              type="button"
              onClick={refetchEnums}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      )}

      {/* Filters */}
      <div className="bg-white border border-slate-200 rounded-md p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-center">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => updateParam("q", e.target.value)}
          placeholder="Search order number, customer, subject"
          aria-label="Search approvals"
          className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
        />

        <select
          aria-label="Filter by decision"
          value={decisionFilter}
          disabled={!enums}
          onChange={(e) => updateParam("decision", e.target.value)}
          className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
        >
          <option value="">Open queue (pending / more info)</option>
          {(enums?.escalation_decisions || []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          aria-label="Filter by priority"
          value={priorityFilter}
          disabled={!enums}
          onChange={(e) => updateParam("priority", e.target.value)}
          className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
        >
          <option value="">All priorities</option>
          {(enums?.ticket_priorities || []).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={assignedToMe}
            onChange={(e) => updateParam("assigned_to", e.target.checked ? "me" : "")}
            className="rounded border-slate-300 text-teal-700 focus:ring-teal-700"
          />
          <span>Assigned to me</span>
        </label>
      </div>

      {loading && (
        <div className="py-16 flex justify-center">
          <LoadingSpinner size="lg" label="Loading approvals queue..." />
        </div>
      )}

      {error && (
        <InlineAlert type="error" title="Unable to load approvals queue">
          <div className="flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => loadQueue(false)}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center">
          <h3 className="text-sm font-semibold text-slate-900">No escalations in this view</h3>
          <p className="text-xs text-slate-500 mt-1">
            Refund requests requiring human review will appear here.
          </p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-medium">
                <tr>
                  <th scope="col" className="px-4 py-3">Subject</th>
                  <th scope="col" className="px-4 py-3">Customer</th>
                  <th scope="col" className="px-4 py-3">Order</th>
                  <th scope="col" className="px-4 py-3">Amount</th>
                  <th scope="col" className="px-4 py-3">Priority</th>
                  <th scope="col" className="px-4 py-3">Decision</th>
                  <th scope="col" className="px-4 py-3">Age</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((esc) => (
                  <tr key={esc.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 max-w-xs">
                      <Link
                        to={`/staff/approvals/${esc.id}`}
                        className="font-medium text-teal-800 hover:underline block truncate"
                      >
                        {esc.ticket_subject}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-800">{esc.customer_name}</td>
                    <td className="px-4 py-3 font-mono text-slate-600">
                      {esc.order_number || (esc.order_id ? esc.order_id.slice(0, 8) : "None")}
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold text-slate-900">
                      {esc.amount !== null && esc.amount !== undefined ? formatMoney(esc.amount) : "None"}
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {getEnumLabel(enums?.ticket_priorities, esc.priority)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge
                        status={esc.decision}
                        label={getEnumLabel(enums?.escalation_decisions, esc.decision)}
                      />
                    </td>
                    <td className="px-4 py-3 text-slate-500">{formatAge(esc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
