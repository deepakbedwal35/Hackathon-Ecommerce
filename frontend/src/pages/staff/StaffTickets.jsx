import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { useMetaEnums } from "../../hooks/useMeta.js";
import { formatDateTime, getEnumLabel } from "../../utils/format.js";
import { StatusBadge } from "../../components/StatusBadge.jsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.jsx";
import { InlineAlert } from "../../components/InlineAlert.jsx";

export function StaffTickets() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { enums, error: enumsError, refetch: refetchEnums } = useMetaEnums();

  const statusFilter = searchParams.get("status") || "";
  const priorityFilter = searchParams.get("priority") || "";
  const categoryFilter = searchParams.get("category") || "";
  const awaitingApproval = searchParams.get("awaiting_approval") === "true";
  const assignedToMe = searchParams.get("assigned_to") === "me";
  const queryFilter = searchParams.get("q") || "";
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);

  const [searchInput, setSearchInput] = useState(queryFilter);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setSearchInput(queryFilter);
  }, [queryFilter]);

  async function loadTickets() {
    setLoading(true);
    setError(null);
    try {
      const params = {
        sort: "sla",
        page,
        page_size: 20,
      };
      if (statusFilter) params.status = statusFilter;
      if (priorityFilter) params.priority = priorityFilter;
      if (categoryFilter) params.category = categoryFilter;
      if (awaitingApproval) {
        params.has_escalation = "true";
        params.escalation_decision = "pending";
      }
      if (assignedToMe) {
        params.assigned_to = "me";
      }
      if (queryFilter.trim()) {
        params.q = queryFilter.trim();
      }
      const res = await api.staff.listTickets(params);
      setData(res);
    } catch (err) {
      setError(err.message || "Unable to load tickets.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTickets();
  }, [statusFilter, priorityFilter, categoryFilter, awaitingApproval, assignedToMe, queryFilter, page]);

  function updateParam(key, value) {
    const next = new URLSearchParams(searchParams);
    if (value === "" || value === false || value === null || value === undefined) {
      next.delete(key);
    } else {
      next.set(key, String(value));
    }
    if (key !== "page") {
      next.delete("page");
    }
    setSearchParams(next);
  }

  function handleSearchSubmit(e) {
    e.preventDefault();
    updateParam("q", searchInput.trim());
  }

  function clearFilters() {
    setSearchInput("");
    setSearchParams({});
  }

  const items = data?.items || [];
  const total = data?.total || 0;
  const pageSize = data?.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            All support tickets
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Sorted by priority then oldest open time. Showing tickets across all customer accounts.
          </p>
        </div>
        <button
          type="button"
          onClick={loadTickets}
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

      {/* Filter Bar */}
      <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
        <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by subject, customer email, or ticket ID"
            aria-label="Search tickets"
            className="flex-1 px-3 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
          />
          <button
            type="submit"
            className="px-3 py-1.5 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md transition-colors"
          >
            Search
          </button>
          {(statusFilter || priorityFilter || categoryFilter || awaitingApproval || assignedToMe || queryFilter) && (
            <button
              type="button"
              onClick={clearFilters}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-md transition-colors"
            >
              Clear filters
            </button>
          )}
        </form>

        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3 items-center">
          <select
            aria-label="Filter by status"
            value={statusFilter}
            disabled={!enums}
            onChange={(e) => updateParam("status", e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
          >
            <option value="">All statuses</option>
            {(enums?.ticket_statuses || []).map((opt) => (
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

          <select
            aria-label="Filter by category"
            value={categoryFilter}
            disabled={!enums}
            onChange={(e) => updateParam("category", e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
          >
            <option value="">All categories</option>
            {(enums?.ticket_categories || []).map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={awaitingApproval}
              onChange={(e) => updateParam("awaiting_approval", e.target.checked ? "true" : "")}
              className="rounded border-slate-300 text-teal-700 focus:ring-teal-700"
            />
            <span>Awaiting approval</span>
          </label>

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
      </div>

      {loading && (
        <div className="py-16 flex justify-center">
          <LoadingSpinner size="lg" label="Loading tickets..." />
        </div>
      )}

      {error && (
        <InlineAlert type="error" title="Unable to load tickets">
          <div className="flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={loadTickets}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center">
          <h3 className="text-sm font-semibold text-slate-900">No tickets match these filters</h3>
          <p className="text-xs text-slate-500 mt-1">
            Adjust your filter criteria or clear filters to see all customer tickets.
          </p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          {/* Desktop Table */}
          <div className="hidden md:block bg-white border border-slate-200 rounded-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-700">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-medium">
                  <tr>
                    <th scope="col" className="px-4 py-3">Subject</th>
                    <th scope="col" className="px-4 py-3">Customer</th>
                    <th scope="col" className="px-4 py-3">Category</th>
                    <th scope="col" className="px-4 py-3">Priority</th>
                    <th scope="col" className="px-4 py-3">Status</th>
                    <th scope="col" className="px-4 py-3">Order</th>
                    <th scope="col" className="px-4 py-3">Last activity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 max-w-xs">
                        <Link
                          to={`/staff/tickets/${t.id}`}
                          className="font-medium text-teal-800 hover:underline block truncate"
                        >
                          {t.subject}
                        </Link>
                        {t.awaiting_admin_approval && (
                          <span className="inline-block mt-1 text-[11px] px-1.5 py-0.5 bg-amber-50 text-amber-900 border border-amber-200 rounded-md font-medium">
                            Awaiting admin approval
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-800">{t.customer_name}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {getEnumLabel(enums?.ticket_categories, t.category)}
                      </td>
                      <td className="px-4 py-3 text-slate-700 font-medium">
                        {getEnumLabel(enums?.ticket_priorities, t.priority)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={t.status} label={getEnumLabel(enums?.ticket_statuses, t.status)} />
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-600">
                        {t.order_number || (t.order_id ? t.order_id.slice(0, 8) : "None")}
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                        {formatDateTime(t.updated_at || t.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mobile Cards */}
          <div className="md:hidden space-y-3">
            {items.map((t) => (
              <Link
                key={t.id}
                to={`/staff/tickets/${t.id}`}
                className="block bg-white border border-slate-200 rounded-md p-4 space-y-2 hover:bg-slate-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium text-sm text-teal-800">{t.subject}</div>
                  <StatusBadge status={t.status} label={getEnumLabel(enums?.ticket_statuses, t.status)} />
                </div>
                <div className="text-xs text-slate-600">
                  {t.customer_name} | {getEnumLabel(enums?.ticket_categories, t.category)} | Priority:{" "}
                  {getEnumLabel(enums?.ticket_priorities, t.priority)}
                </div>
                {t.awaiting_admin_approval && (
                  <div>
                    <span className="inline-block text-[11px] px-1.5 py-0.5 bg-amber-50 text-amber-900 border border-amber-200 rounded-md font-medium">
                      Awaiting admin approval
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                  <span className="font-mono">{t.order_number || "No order"}</span>
                  <span>{formatDateTime(t.updated_at || t.created_at)}</span>
                </div>
              </Link>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-slate-600 pt-2">
            <div>
              Showing page {page} of {totalPages} ({total} tickets total)
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => updateParam("page", page - 1)}
                className="px-3 py-1.5 bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => updateParam("page", page + 1)}
                className="px-3 py-1.5 bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
