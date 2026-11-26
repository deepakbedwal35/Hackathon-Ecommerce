import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { useAuth } from "../../context/AuthContext.jsx";
import { useMetaEnums } from "../../hooks/useMeta.js";
import { formatDate, formatDateTime, formatMoney, getEnumLabel } from "../../utils/format.js";
import { StatusBadge } from "../../components/StatusBadge.jsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.jsx";
import { InlineAlert } from "../../components/InlineAlert.jsx";
import { ConfirmationModal } from "../../components/staff/ConfirmationModal.jsx";
import { IconArrowLeft } from "../../components/Icons.jsx";

export function ApprovalDetail() {
  const { escalationId } = useParams();
  const { user } = useAuth();
  const { enums } = useMetaEnums();

  const isAdmin = String(user?.role || "").toLowerCase() === "admin";

  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Action states
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [modalError, setModalError] = useState(null);

  // Reject / Request info form state
  const [activeActionMode, setActiveActionMode] = useState(null); // "reject" | "request_info" | null
  const [internalNote, setInternalNote] = useState("");
  const [customerMessage, setCustomerMessage] = useState("");

  // Internal ticket note state
  const [newTicketNote, setNewTicketNote] = useState("");
  const [addingNote, setAddingNote] = useState(false);

  async function loadDetail() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.staff.getEscalation(escalationId);
      setDetail(res);
    } catch (err) {
      setError(err.message || "Unable to load approval details.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDetail();
  }, [escalationId]);

  async function handleAssignToMe() {
    if (submitting) return;
    setSubmitting(true);
    setActionError(null);
    try {
      await api.staff.assignEscalation(escalationId, user?.id || null);
      await loadDetail();
      setActionSuccess("Escalation assigned to you.");
    } catch (err) {
      setActionError(err.message || "Unable to assign escalation.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApproveConfirm(note) {
    if (submitting) return;
    setSubmitting(true);
    setModalError(null);
    setActionError(null);
    setActionSuccess(null);

    try {
      await api.staff.decideEscalation(escalationId, {
        decision: "approve",
        note,
      });
      setShowApproveModal(false);
      await loadDetail();
      setActionSuccess("Refund approved and payment processed.");
    } catch (err) {
      if (err.code === "ALREADY_DECIDED" || err.status === 409) {
        setShowApproveModal(false);
        await loadDetail();
        setActionError("Another admin already decided this escalation.");
      } else if (err.status === 502 || err.code === "PAYMENT_FAILED") {
        setShowApproveModal(false);
        await loadDetail();
        setActionError("The refund was NOT completed. The request is still open, you can retry.");
      } else {
        setModalError(err.message || "Failed to approve refund.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSecondaryDecision(e) {
    e.preventDefault();
    if (submitting || !activeActionMode) return;
    if (internalNote.trim().length < 5) {
      setActionError("Internal note must be at least 5 characters.");
      return;
    }
    if (customerMessage.trim().length < 5) {
      setActionError("Customer message must be at least 5 characters.");
      return;
    }

    setSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      await api.staff.decideEscalation(escalationId, {
        decision: activeActionMode,
        note: internalNote.trim(),
        message_to_customer: customerMessage.trim(),
      });
      setActiveActionMode(null);
      setInternalNote("");
      setCustomerMessage("");
      await loadDetail();
      setActionSuccess(
        activeActionMode === "reject"
          ? "Refund request rejected and customer notified."
          : "Requested additional information from customer."
      );
    } catch (err) {
      if (err.code === "ALREADY_DECIDED" || err.status === 409) {
        setActiveActionMode(null);
        await loadDetail();
        setActionError("Another admin already decided this escalation.");
      } else {
        setActionError(err.message || "Unable to submit decision.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddTicketNote(e) {
    e.preventDefault();
    if (!detail?.ticket_id || !newTicketNote.trim() || addingNote) return;
    setAddingNote(true);
    setActionError(null);
    try {
      await api.staff.postNote(detail.ticket_id, { note: newTicketNote.trim() });
      setNewTicketNote("");
      await loadDetail();
    } catch (err) {
      setActionError(err.message || "Failed to save note.");
    } finally {
      setAddingNote(false);
    }
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading escalation review..." />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <Link
          to="/staff/approvals"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to approvals</span>
        </Link>
        <InlineAlert type="error" title="Unable to load escalation">
          <div className="flex items-center justify-between">
            <span>{error || "Escalation not found."}</span>
            <button
              type="button"
              onClick={loadDetail}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      </div>
    );
  }

  const { ticket, order, refund, checks_passed: checksPassed = [], messages = [], notes = [] } = detail;
  const isOpenForDecision =
    detail.decision === "pending" || detail.decision === "more_info_requested";
  const orderLabel = order?.order_number || (order?.id ? order.id.slice(0, 8) : "Order");
  const amountLabel = refund ? formatMoney(refund.amount) : "N/A";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link
          to="/staff/approvals"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to approvals</span>
        </Link>

        {detail.ticket_id && (
          <Link
            to={`/staff/tickets/${detail.ticket_id}`}
            className="text-xs font-medium text-teal-700 hover:underline"
          >
            Open linked ticket
          </Link>
        )}
      </div>

      {/* Summary & Action Header */}
      <div className="bg-white border border-slate-200 rounded-md p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-slate-900">
                {ticket?.subject || "Escalation review"}
              </h1>
              <StatusBadge
                status={detail.decision}
                label={getEnumLabel(enums?.escalation_decisions, detail.decision)}
              />
            </div>
            <p className="text-xs text-slate-600 mt-1">{detail.summary}</p>
          </div>

          <div className="text-left sm:text-right shrink-0">
            <div className="text-xs text-slate-500">Requested refund</div>
            <div className="text-xl font-semibold font-mono text-slate-900">{amountLabel}</div>
          </div>
        </div>

        {actionError && <InlineAlert type="error" title="Action failed" message={actionError} />}
        {actionSuccess && <InlineAlert type="success" message={actionSuccess} />}

        {!isAdmin && (
          <InlineAlert
            type="info"
            message="Only an admin can approve or reject refunds."
          />
        )}

        {isOpenForDecision && (
          <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-2">
            {isAdmin && (
              <>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => {
                    setModalError(null);
                    setShowApproveModal(true);
                  }}
                  className="px-3.5 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md disabled:opacity-50 transition-colors"
                >
                  Approve refund
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => {
                    setActionError(null);
                    setActiveActionMode(activeActionMode === "reject" ? null : "reject");
                  }}
                  className="px-3.5 py-2 text-xs font-medium text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-md disabled:opacity-50 transition-colors"
                >
                  Reject refund
                </button>
              </>
            )}

            <button
              type="button"
              disabled={submitting}
              onClick={() => {
                setActionError(null);
                setActiveActionMode(activeActionMode === "request_info" ? null : "request_info");
              }}
              className="px-3.5 py-2 text-xs font-medium text-slate-800 bg-white hover:bg-slate-50 border border-slate-300 rounded-md disabled:opacity-50 transition-colors"
            >
              Request more information
            </button>

            {!detail.assigned_to && (
              <button
                type="button"
                disabled={submitting}
                onClick={handleAssignToMe}
                className="px-3.5 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-md disabled:opacity-50 transition-colors ml-auto"
              >
                Assign to me
              </button>
            )}
          </div>
        )}

        {/* Secondary Decision Form (Reject / Request info) */}
        {isOpenForDecision && activeActionMode && (
          <form
            onSubmit={handleSecondaryDecision}
            className="mt-4 pt-4 border-t border-slate-200 space-y-3 bg-slate-50 p-4 rounded-md"
          >
            <h3 className="text-xs font-semibold text-slate-900">
              {activeActionMode === "reject"
                ? "Reject refund request"
                : "Request more information from customer"}
            </h3>

            <div>
              <label htmlFor="decision-internal-note" className="block text-xs font-medium text-slate-700 mb-1">
                Internal note (staff only, min 5 characters)
              </label>
              <textarea
                id="decision-internal-note"
                rows={2}
                required
                minLength={5}
                value={internalNote}
                onChange={(e) => setInternalNote(e.target.value)}
                disabled={submitting}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="decision-customer-msg" className="block text-xs font-medium text-slate-700 mb-1">
                {activeActionMode === "reject"
                  ? "Message to customer explaining rejection (min 5 characters)"
                  : "Question for customer (min 5 characters)"}
              </label>
              <textarea
                id="decision-customer-msg"
                rows={2}
                required
                minLength={5}
                value={customerMessage}
                onChange={(e) => setCustomerMessage(e.target.value)}
                disabled={submitting}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={() => setActiveActionMode(null)}
                className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-3.5 py-1.5 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md disabled:opacity-50"
              >
                {submitting
                  ? "Submitting..."
                  : activeActionMode === "reject"
                  ? "Confirm reject"
                  : "Send question"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Context Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Conversation (Read only) */}
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-2">
            Conversation (read only)
          </h2>
          {messages.length === 0 ? (
            <p className="text-xs text-slate-500 py-6 text-center">No messages recorded.</p>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {messages.map((m) => (
                <div key={m.id} className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span className="font-medium text-slate-800">{m.sender_type}</span>
                    <span>{formatDateTime(m.created_at)}</span>
                  </div>
                  <p className="text-slate-800 whitespace-pre-wrap">{m.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Order, Policy Checks & Notes */}
        <div className="space-y-4">
          {order && (
            <div className="bg-white border border-slate-200 rounded-md p-4 space-y-2 text-xs">
              <h2 className="text-sm font-semibold text-slate-900">
                Order {orderLabel}
              </h2>
              <div>Status: {getEnumLabel(enums?.order_statuses, order.status)}</div>
              <div>Total: <span className="font-mono font-medium">{formatMoney(order.total_amount)}</span></div>
              <div>Delivery date: {order.delivery_date ? formatDate(order.delivery_date) : "Not delivered"}</div>
              {order.items && order.items.length > 0 && (
                <div className="pt-2 border-t border-slate-100 space-y-1">
                  <div className="font-medium text-slate-700">Items</div>
                  {order.items.map((it) => (
                    <div key={it.id} className="flex justify-between text-[11px] text-slate-600">
                      <span>{it.name} x{it.quantity}</span>
                      <span className="font-mono">{formatMoney(it.unit_price)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Policy Checks Passed */}
          <div className="bg-white border border-slate-200 rounded-md p-4 space-y-2 text-xs">
            <h2 className="text-sm font-semibold text-slate-900">Policy checks passed</h2>
            <ul className="space-y-1 text-slate-700">
              {checksPassed.map((chk) => (
                <li key={chk} className="flex items-center gap-2">
                  <span className="text-emerald-700 font-semibold">[OK]</span>
                  <span>{chk.replace(/_/g, " ")}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Notes */}
          <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3 text-xs">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Internal notes</h2>
              <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 mt-1">
                Staff only. Customers cannot see notes.
              </p>
            </div>
            {detail.internal_note && (
              <div className="p-2.5 bg-slate-100 border border-slate-200 rounded-md">
                <div className="text-[11px] font-medium text-slate-600">Decision note:</div>
                <p className="text-slate-800 mt-0.5">{detail.internal_note}</p>
              </div>
            )}
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {notes.map((n) => (
                <div key={n.id} className="p-2 bg-slate-50 border border-slate-200 rounded-md">
                  <div className="flex justify-between text-[11px] text-slate-500">
                    <span className="font-medium text-slate-700">{n.author_name}</span>
                    <span>{formatDateTime(n.created_at)}</span>
                  </div>
                  <p className="text-slate-800 mt-0.5 whitespace-pre-wrap">{n.note}</p>
                </div>
              ))}
            </div>
            {detail.ticket_id && (
              <form onSubmit={handleAddTicketNote} className="space-y-2 pt-2 border-t border-slate-100">
                <textarea
                  rows={2}
                  value={newTicketNote}
                  onChange={(e) => setNewTicketNote(e.target.value)}
                  disabled={addingNote}
                  placeholder="Add internal note..."
                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={addingNote || !newTicketNote.trim()}
                  className="px-3 py-1.5 text-xs font-medium text-slate-800 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-md disabled:opacity-50"
                >
                  {addingNote ? "Saving..." : "Add note"}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>

      {/* Confirmation Dialog for Admin Approve */}
      <ConfirmationModal
        open={showApproveModal}
        title="Confirm refund approval"
        description={`You are approving a refund of ${amountLabel} for order ${orderLabel}. Payment will be issued immediately upon confirmation.`}
        confirmLabel="Approve and issue refund"
        submitting={submitting}
        error={modalError}
        requireNote={true}
        onConfirm={handleApproveConfirm}
        onCancel={() => {
          if (!submitting) setShowApproveModal(false);
        }}
      />
    </div>
  );
}
