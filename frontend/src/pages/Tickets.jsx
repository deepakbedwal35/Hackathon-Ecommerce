import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { StatusBadge } from "../components/StatusBadge.jsx";
import { LoadingSpinner } from "../components/LoadingSpinner.jsx";
import { InlineAlert } from "../components/InlineAlert.jsx";
import { IconChevronRight, IconTicket } from "../components/Icons.jsx";

export function Tickets() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadTickets();
  }, []);

  async function loadTickets() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.tickets.list();
      setTickets(data);
    } catch (err) {
      setError(err.message || "Failed to load support tickets.");
    } finally {
      setLoading(false);
    }
  }

  function formatDate(isoString) {
    if (!isoString) return "N/A";
    const date = new Date(isoString);
    return date.toLocaleDateString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            Support tickets
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Track inquiries, automated agent resolutions, and staff escalations.
          </p>
        </div>
        <Link
          to="/tickets/new"
          className="px-3 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md transition-colors self-start sm:self-auto"
        >
          Create ticket
        </Link>
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

      {!loading && !error && tickets.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center">
          <div className="w-10 h-10 mx-auto text-slate-400 mb-3 flex items-center justify-center">
            <IconTicket className="w-8 h-8" />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">
            No support tickets open
          </h3>
          <p className="text-xs text-slate-500 mt-1 mb-4">
            If you need assistance with an order or account issue, create a new ticket.
          </p>
          <Link
            to="/tickets/new"
            className="inline-flex px-3 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md transition-colors"
          >
            Create ticket
          </Link>
        </div>
      )}

      {!loading && !error && tickets.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-medium">
                <tr>
                  <th scope="col" className="px-4 py-3">Subject</th>
                  <th scope="col" className="px-4 py-3">Category</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3">Staff review</th>
                  <th scope="col" className="px-4 py-3">Last updated</th>
                  <th scope="col" className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tickets.map((ticket) => (
                  <tr key={ticket.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-900 max-w-xs truncate">
                      {ticket.subject}
                    </td>
                    <td className="px-4 py-3 text-slate-600 capitalize">
                      {String(ticket.category).replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={ticket.status} />
                    </td>
                    <td className="px-4 py-3">
                      {ticket.review_status ? (
                        <span className="text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-md">
                          {ticket.review_status}
                        </span>
                      ) : (
                        <span className="text-slate-400">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {formatDate(ticket.updated_at || ticket.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/tickets/${ticket.id}`}
                        className="inline-flex items-center gap-1 font-medium text-teal-700 hover:text-teal-900"
                      >
                        <span>Open</span>
                        <IconChevronRight className="w-3.5 h-3.5" />
                      </Link>
                    </td>
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
