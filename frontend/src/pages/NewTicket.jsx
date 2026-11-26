import React, { useEffect, useState } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client.js";
import { LoadingSpinner } from "../components/LoadingSpinner.jsx";
import { InlineAlert } from "../components/InlineAlert.jsx";
import { IconArrowLeft } from "../components/Icons.jsx";

const CATEGORIES = [
  { value: "refund_request", label: "Refund request" },
  { value: "return_request", label: "Return inquiry" },
  { value: "order_inquiry", label: "Order tracking or status" },
  { value: "cancellation", label: "Order cancellation" },
  { value: "account", label: "Account or login issue" },
  { value: "other", label: "Other inquiry" },
];

export function NewTicket() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedOrderId = searchParams.get("order_id") || "";

  const [orders, setOrders] = useState([]);
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("order_inquiry");
  const [selectedOrderId, setSelectedOrderId] = useState(preselectedOrderId);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchOrders() {
      try {
        const data = await api.orders.list();
        setOrders(data);
      } catch {
        // Optional failure, order list is non-critical
      }
    }
    fetchOrders();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!subject.trim()) {
      setError("Please provide a subject for your ticket.");
      return;
    }

    if (!description.trim()) {
      setError("Please provide a description explaining your request.");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        subject: subject.trim(),
        description: description.trim(),
        category,
        order_id: selectedOrderId || null,
      };

      const res = await api.tickets.create(payload);
      const ticketId = res.ticket ? res.ticket.id : res.id;
      navigate(`/tickets/${ticketId}`, { replace: true });
    } catch (err) {
      setError(err.message || "Failed to create support ticket. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Link
        to="/tickets"
        className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
      >
        <IconArrowLeft className="w-3.5 h-3.5" />
        <span>Back to tickets</span>
      </Link>

      <div className="bg-white border border-slate-200 rounded-md p-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            Create support ticket
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Our automated assistant evaluates your request immediately. Complex cases are escalated to staff.
          </p>
        </div>

        {error && (
          <div className="mb-4">
            <InlineAlert type="error" title="Submission error" message={error} />
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="subject"
              className="block text-xs font-medium text-slate-700 mb-1"
            >
              Subject
            </label>
            <input
              id="subject"
              type="text"
              required
              maxLength={255}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              placeholder="Summary of your question or issue"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="category"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Category
              </label>
              <select
                id="category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="orderId"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Related order (optional)
              </label>
              <select
                id="orderId"
                value={selectedOrderId}
                onChange={(e) => setSelectedOrderId(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 font-mono focus:border-teal-700 focus:outline-none"
              >
                <option value="">None / general inquiry</option>
                {orders.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.order_number} (INR {Number(o.total_amount).toFixed(2)})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-xs font-medium text-slate-700 mb-1"
            >
              Description
            </label>
            <textarea
              id="description"
              rows={5}
              required
              maxLength={4000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              placeholder="Describe your inquiry in detail. Include any relevant delivery or order details."
            />
          </div>

          <div className="pt-2 flex items-center justify-end gap-3">
            <Link
              to="/tickets"
              className="px-3 py-2 text-xs font-medium text-slate-700 hover:text-slate-900"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 disabled:bg-slate-300 rounded-md transition-colors"
            >
              {submitting ? (
                <LoadingSpinner size="sm" label="Creating ticket..." />
              ) : (
                "Create ticket"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
