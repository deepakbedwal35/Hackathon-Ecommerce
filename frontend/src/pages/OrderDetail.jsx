import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api/client.js";
import { StatusBadge } from "../components/StatusBadge.jsx";
import { LoadingSpinner } from "../components/LoadingSpinner.jsx";
import { InlineAlert } from "../components/InlineAlert.jsx";
import { IconArrowLeft } from "../components/Icons.jsx";
import { legalConfig } from "../config/legal.js";

const REFUND_REASONS = [
  "Item defective or damaged upon arrival",
  "Incorrect item sent by mistake",
  "Item significantly different from description",
  "Quality unsatisfactory or not working as expected",
];

export function OrderDetail() {
  const { orderId } = useParams();

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Refund form state
  const [refundAmount, setRefundAmount] = useState("");
  const [selectedReason, setSelectedReason] = useState(REFUND_REASONS[0]);
  const [customReason, setCustomReason] = useState("");
  const [submittingRefund, setSubmittingRefund] = useState(false);
  const [refundOutcome, setRefundOutcome] = useState(null);

  useEffect(() => {
    loadOrderDetail();
  }, [orderId]);

  async function loadOrderDetail() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.orders.get(orderId);
      setOrder(data);
      if (data && data.refundable_amount) {
        setRefundAmount(data.refundable_amount);
      }
    } catch (err) {
      setError(err.message || "Failed to load order details.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefundSubmit(e) {
    e.preventDefault();
    setRefundOutcome(null);

    const finalReason = customReason.trim().length >= 10 ? customReason.trim() : selectedReason;
    if (finalReason.length < 10) {
      setRefundOutcome({
        type: "error",
        title: "Invalid reason",
        message: "Please enter a detailed explanation of at least 10 characters.",
      });
      return;
    }

    const amountNum = parseFloat(refundAmount);
    if (isNaN(amountNum) || amountNum <= 0) {
      setRefundOutcome({
        type: "error",
        title: "Invalid amount",
        message: "Please enter a valid refund amount greater than zero.",
      });
      return;
    }

    setSubmittingRefund(true);
    try {
      const res = await api.refunds.request({
        order_id: order.id,
        amount: amountNum,
        reason: finalReason,
      });

      if (res.status === 201) {
        setRefundOutcome({
          type: "success",
          title: "Refund processed successfully",
          message: `Your refund of INR ${amountNum.toLocaleString("en-IN", { minimumFractionDigits: 2 })} has been processed. Payment reference: ${res.data.payment_reference || "N/A"}.`,
        });
      } else if (res.status === 202) {
        setRefundOutcome({
          type: "warning",
          title: "Request submitted for staff review",
          message: "Your refund request requires evaluation by our support staff according to store policy. We will review your request shortly.",
        });
      } else if (res.status === 200) {
        setRefundOutcome({
          type: "info",
          title: "Duplicate request",
          message: "A refund for this request has already been recorded in our system.",
        });
      }

      await loadOrderDetail();
    } catch (err) {
      if (err.status === 409) {
        setRefundOutcome({
          type: "error",
          title: "Refund request rejected",
          message: err.message || "This order is not eligible for refund under policy rules.",
        });
      } else if (err.status === 502) {
        setRefundOutcome({
          type: "error",
          title: "Payment gateway error",
          message: "The payment service encountered an issue. The refund was not completed. Please retry or contact support.",
        });
      } else {
        setRefundOutcome({
          type: "error",
          title: "Request failed",
          message: err.message || "An unexpected error occurred while submitting your refund request.",
        });
      }
    } finally {
      setSubmittingRefund(false);
    }
  }

  function formatDate(isoString) {
    if (!isoString) return "N/A";
    const date = new Date(isoString);
    return date.toLocaleDateString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function formatMoney(amount) {
    const num = Number(amount) || 0;
    return `INR ${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading order details..." />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="space-y-4">
        <Link
          to="/orders"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to orders</span>
        </Link>
        <InlineAlert type="error" title="Unable to display order">
          <div className="flex items-center justify-between">
            <span>{error || "Order not found."}</span>
            <button
              type="button"
              onClick={loadOrderDetail}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        to="/orders"
        className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
      >
        <IconArrowLeft className="w-3.5 h-3.5" />
        <span>Back to orders</span>
      </Link>

      <div className="bg-white border border-slate-200 rounded-md p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-200">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-slate-900 tracking-tight font-mono">
                {order.order_number}
              </h1>
              <StatusBadge status={order.status} />
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Placed on {formatDate(order.created_at)}
            </p>
          </div>

          <div className="text-right">
            <span className="text-xs text-slate-500 block">Total amount</span>
            <span className="text-lg font-semibold text-slate-900 font-mono">
              {formatMoney(order.total_amount)}
            </span>
          </div>
        </div>

        <div className="py-6 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-900 mb-3">
            Items in this order
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 font-medium">
                <tr>
                  <th scope="col" className="px-3 py-2.5">Item</th>
                  <th scope="col" className="px-3 py-2.5">Category</th>
                  <th scope="col" className="px-3 py-2.5 text-center">Quantity</th>
                  <th scope="col" className="px-3 py-2.5 text-right">Unit price</th>
                  <th scope="col" className="px-3 py-2.5 text-right">Line total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {order.items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-3 py-2.5 font-medium text-slate-900">{item.name}</td>
                    <td className="px-3 py-2.5 text-slate-500 capitalize">{item.category}</td>
                    <td className="px-3 py-2.5 text-center">{item.quantity}</td>
                    <td className="px-3 py-2.5 text-right font-mono">{formatMoney(item.unit_price)}</td>
                    <td className="px-3 py-2.5 text-right font-mono font-medium text-slate-900">
                      {formatMoney(Number(item.unit_price) * item.quantity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="pt-6 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <span className="text-slate-500 block">Delivery status</span>
            <span className="text-slate-800 font-medium">
              {order.delivery_date ? `Delivered on ${formatDate(order.delivery_date)}` : "Awaiting delivery"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block">Return eligibility</span>
            <span className="text-slate-800 font-medium">
              {order.is_returnable
                ? `Eligible until ${formatDate(order.last_eligible_date)}`
                : "Not eligible for return under current policy"}
            </span>
          </div>
        </div>
      </div>

      {order.refunds && order.refunds.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-6">
          <h2 className="text-sm font-semibold text-slate-900 mb-3">
            Recorded refunds
          </h2>
          <div className="space-y-3">
            {order.refunds.map((refund) => (
              <div
                key={refund.id}
                className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 font-mono">
                      {formatMoney(refund.amount)}
                    </span>
                    <StatusBadge status={refund.status} />
                  </div>
                  <span className="text-slate-500">
                    {formatDate(refund.created_at)}
                  </span>
                </div>
                <p className="text-slate-700">Reason: {refund.reason}</p>
                {refund.payment_reference && (
                  <p className="font-mono text-slate-500">
                    Payment reference: {refund.payment_reference}
                  </p>
                )}
                {refund.failure_reason && (
                  <p className="text-rose-700 font-medium">
                    Failure reason: {refund.failure_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {order.is_returnable && Number(order.refundable_amount) > 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-6">
          <h2 className="text-base font-semibold text-slate-900 tracking-tight mb-1">
            Request a refund
          </h2>
          <p className="text-xs text-slate-600 mb-4">
            Orders within {legalConfig.returnWindowDays} days of delivery may be refunded up to the remaining
            balance of {formatMoney(order.refundable_amount)}.
          </p>

          {refundOutcome && (
            <div className="mb-4">
              <InlineAlert
                type={refundOutcome.type}
                title={refundOutcome.title}
                message={refundOutcome.message}
              />
            </div>
          )}

          <form onSubmit={handleRefundSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="amount"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Refund amount (INR)
              </label>
              <input
                id="amount"
                type="number"
                step="0.01"
                min="1"
                max={order.refundable_amount}
                required
                value={refundAmount}
                onChange={(e) => setRefundAmount(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 font-mono focus:border-teal-700 focus:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="reason"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Primary reason
              </label>
              <select
                id="reason"
                value={selectedReason}
                onChange={(e) => setSelectedReason(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              >
                {REFUND_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="notes"
                className="block text-xs font-medium text-slate-700 mb-1"
              >
                Additional explanation (optional if primary reason applies, min 10 characters if provided)
              </label>
              <textarea
                id="notes"
                rows={3}
                value={customReason}
                onChange={(e) => setCustomReason(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
                placeholder="Provide specific notes regarding the issue"
              />
            </div>

            <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-md p-3">
              Requests up to INR {legalConfig.refundLimitInr.toLocaleString()} may be processed automatically.
              Requests exceeding this amount or requiring item returns are routed to support staff for verification.
            </div>

            <button
              type="submit"
              disabled={submittingRefund}
              className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 disabled:bg-slate-300 rounded-md transition-colors"
            >
              {submittingRefund ? (
                <LoadingSpinner size="sm" label="Submitting request..." />
              ) : (
                "Request refund"
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
