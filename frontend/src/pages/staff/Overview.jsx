import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client.js";
import { useMetaEnums } from "../../hooks/useMeta.js";
import { formatAge, formatDateTime, formatMoney, getEnumLabel } from "../../utils/format.js";
import { StatusBadge } from "../../components/StatusBadge.jsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.jsx";
import { InlineAlert } from "../../components/InlineAlert.jsx";

export function Overview() {
  const { enums } = useMetaEnums();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadOverview() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.staff.overview();
      setData(res);
    } catch (err) {
      setError(err.message || "Unable to load staff overview.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadOverview();
  }, []);

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading overview..." />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold text-slate-900">Staff overview</h1>
        <InlineAlert type="error" title="Unable to load overview">
          <div className="flex items-center justify-between">
            <span>{error || "Unexpected server response."}</span>
            <button
              type="button"
              onClick={loadOverview}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      </div>
    );
  }

  const counts = data.ticket_counts || {};
  const statusEntries = Object.entries(counts);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            Staff overview
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Live queue depth, pending refund approvals, and recent customer activity across all accounts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/staff/tickets"
            className="text-xs font-medium px-3 py-1.5 bg-white border border-slate-200 text-slate-700 rounded-md hover:bg-slate-50 transition-colors"
          >
            All tickets
          </Link>
          <Link
            to="/staff/approvals"
            className="text-xs font-medium px-3 py-1.5 bg-teal-700 text-white rounded-md hover:bg-teal-800 transition-colors"
          >
            Review approvals
          </Link>
        </div>
      </div>

      {/* Primary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Awaiting approval</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {data.awaiting_approval_count}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {data.unassigned_count} unassigned
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Pending refund total</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1 font-mono">
            {formatMoney(data.pending_refund_total)}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Total value in pending review
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Oldest pending approval</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {data.oldest_pending_approval_created_at
              ? formatAge(data.oldest_pending_approval_created_at)
              : "None"}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {data.oldest_pending_approval_created_at
              ? formatDateTime(data.oldest_pending_approval_created_at)
              : "No pending requests"}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Open tickets</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {(counts.open || 0) + (counts.escalated || 0) + (counts.awaiting_customer || 0)}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {counts.resolved || 0} resolved, {counts.closed || 0} closed
          </div>
        </div>
      </div>

      {/* Status breakdown strip */}
      <div className="bg-white border border-slate-200 rounded-md p-4">
        <div className="text-xs font-medium text-slate-700 mb-3">Tickets by status</div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {statusEntries.map(([statusKey, count]) => (
            <Link
              key={statusKey}
              to={`/staff/tickets?status=${encodeURIComponent(statusKey)}`}
              className="p-2.5 bg-slate-50 border border-slate-200 rounded-md hover:bg-slate-100 transition-colors"
            >
              <div className="text-[11px] text-slate-600">
                {getEnumLabel(enums?.ticket_statuses, statusKey)}
              </div>
              <div className="text-base font-semibold text-slate-900 mt-0.5">{count}</div>
            </Link>
          ))}
        </div>
      </div>

      {/* Queues grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 5 Oldest Pending Approvals */}
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">
              Oldest pending approvals
            </h2>
            <Link to="/staff/approvals" className="text-xs text-teal-700 hover:underline font-medium">
              View queue
            </Link>
          </div>

          {!data.top_5_pending_approvals || data.top_5_pending_approvals.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">
              No pending refund approvals.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              {data.top_5_pending_approvals.map((item) => (
                <Link
                  key={item.escalation_id}
                  to={`/staff/approvals/${item.escalation_id}`}
                  className="py-2.5 flex items-center justify-between text-xs hover:bg-slate-50 px-1 rounded-md transition-colors"
                >
                  <div className="min-w-0 pr-3">
                    <div className="font-medium text-slate-900 truncate">
                      {item.order_number || "Order"} - {item.customer_name}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      Priority: {getEnumLabel(enums?.ticket_priorities, item.priority)} | Waiting {formatAge(item.created_at)}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-mono font-semibold text-slate-900">
                      {formatMoney(item.amount)}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* 5 Most Recent Tickets */}
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">
              Recent tickets
            </h2>
            <Link to="/staff/tickets" className="text-xs text-teal-700 hover:underline font-medium">
              View all tickets
            </Link>
          </div>

          {!data.top_5_recent_tickets || data.top_5_recent_tickets.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">
              No support tickets recorded.
            </p>
          ) : (
            <div className="divide-y divide-slate-100">
              {data.top_5_recent_tickets.map((t) => (
                <Link
                  key={t.ticket_id}
                  to={`/staff/tickets/${t.ticket_id}`}
                  className="py-2.5 flex items-center justify-between text-xs hover:bg-slate-50 px-1 rounded-md transition-colors"
                >
                  <div className="min-w-0 pr-3">
                    <div className="font-medium text-slate-900 truncate">{t.subject}</div>
                    <div className="text-[11px] text-slate-500">
                      {t.customer_name} | {formatDateTime(t.created_at)}
                    </div>
                  </div>
                  <div className="shrink-0">
                    <StatusBadge status={t.status} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
