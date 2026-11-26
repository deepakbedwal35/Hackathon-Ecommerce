import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client.js";
import { useMetaEnums } from "../../hooks/useMeta.js";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  getEnumLabel,
  mergeMessagesById,
} from "../../utils/format.js";
import { StatusBadge } from "../../components/StatusBadge.jsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.jsx";
import { InlineAlert } from "../../components/InlineAlert.jsx";
import { IconArrowLeft } from "../../components/Icons.jsx";

function getStaffSenderLabel(senderType) {
  const key = String(senderType || "").toLowerCase();
  if (key === "customer") return "Customer";
  if (key === "agent_ai" || key === "agent") return "AI assistant";
  if (key === "staff") return "Support team";
  if (key === "system") return "System";
  return "Unknown";
}

export function StaffTicketDetail() {
  const { ticketId } = useParams();
  const { enums } = useMetaEnums();

  const [detail, setDetail] = useState(null);
  const [messages, setMessages] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [mobileTab, setMobileTab] = useState("conversation");

  // Reply composer
  const [replyText, setReplyText] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [replyError, setReplyError] = useState(null);

  // Status / priority update
  const [updatingTicket, setUpdatingTicket] = useState(false);
  const [patchError, setPatchError] = useState(null);
  const [patchSuccess, setPatchSuccess] = useState(null);

  // Internal note composer
  const [noteText, setNoteText] = useState("");
  const [addingNote, setAddingNote] = useState(false);
  const [noteError, setNoteError] = useState(null);

  const messagesRef = useRef([]);
  messagesRef.current = messages;

  async function loadDetail() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.staff.getTicket(ticketId);
      setDetail(res);
      setMessages(res.messages || []);
      setNotes(res.notes || []);
    } catch (err) {
      setError(err.message || "Unable to load ticket details.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDetail();
  }, [ticketId]);

  // Poll messages every 4s while tab is visible
  useEffect(() => {
    let active = true;
    const intervalId = setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const currentMsgs = messagesRef.current;
        const lastTimestamp =
          currentMsgs.length > 0 ? currentMsgs[currentMsgs.length - 1].created_at : null;
        const incoming = await api.staff.getMessages(ticketId, lastTimestamp);
        if (active && Array.isArray(incoming) && incoming.length > 0) {
          setMessages((prev) => mergeMessagesById(prev, incoming));
        }
      } catch {
        // Silent background poll retry on next tick
      }
    }, 4000);

    return () => {
      active = false;
      clearInterval(intervalId);
    };
  }, [ticketId]);

  async function handleSendReply(e) {
    e.preventDefault();
    const content = replyText.trim();
    if (!content) return;
    setSendingReply(true);
    setReplyError(null);
    try {
      const newMsg = await api.staff.postMessage(ticketId, { content });
      setMessages((prev) => mergeMessagesById(prev, [newMsg]));
      setReplyText("");
    } catch (err) {
      setReplyError(err.message || "Failed to send staff reply.");
    } finally {
      setSendingReply(false);
    }
  }

  async function handlePatchTicket(payload) {
    setUpdatingTicket(true);
    setPatchError(null);
    setPatchSuccess(null);
    try {
      await api.staff.patchTicket(ticketId, payload);
      await loadDetail();
      setPatchSuccess("Ticket updated.");
    } catch (err) {
      setPatchError(err.message || "Unable to update ticket.");
    } finally {
      setUpdatingTicket(false);
    }
  }

  async function handleAddNote(e) {
    e.preventDefault();
    const text = noteText.trim();
    if (!text) return;
    setAddingNote(true);
    setNoteError(null);
    try {
      const created = await api.staff.postNote(ticketId, { note: text });
      setNotes((prev) => [...prev, created]);
      setNoteText("");
    } catch (err) {
      setNoteError(err.message || "Failed to save internal note.");
    } finally {
      setAddingNote(false);
    }
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading ticket..." />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <Link
          to="/staff/tickets"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to all tickets</span>
        </Link>
        <InlineAlert type="error" title="Unable to open ticket">
          <div className="flex items-center justify-between">
            <span>{error || "Ticket not found."}</span>
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

  const { ticket, customer, order, refunds, escalations, allowed_transitions: allowedTransitions = [] } = detail;
  const statusOptions = [ticket.status, ...allowedTransitions.filter((s) => s !== ticket.status)];

  const conversationSection = (
    <div className="space-y-4">
      <div className="bg-white border border-slate-200 rounded-md p-4 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2">
          <h2 className="text-sm font-semibold text-slate-900">Conversation</h2>
          <span className="text-[11px] text-slate-500">{messages.length} messages</span>
        </div>

        <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <p className="text-xs text-slate-500 py-8 text-center">No messages yet.</p>
          ) : (
            messages.map((m) => {
              const sType = String(m.sender_type || "").toLowerCase();
              const isCustomer = sType === "customer";
              const isStaff = sType === "staff";
              const isSystem = sType === "system";

              return (
                <div
                  key={m.id}
                  className={`flex flex-col ${isStaff ? "items-end" : "items-start"}`}
                >
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 mb-1">
                    <span className="font-medium text-slate-700">
                      {getStaffSenderLabel(m.sender_type)}
                    </span>
                    <span>{formatDateTime(m.created_at)}</span>
                  </div>
                  <div
                    className={`max-w-[90%] rounded-md px-3.5 py-2.5 text-xs leading-relaxed border ${
                      isStaff
                        ? "bg-teal-50 border-teal-200 text-teal-950"
                        : isCustomer
                        ? "bg-white border-slate-200 text-slate-900"
                        : isSystem
                        ? "bg-slate-100 border-slate-200 text-slate-700"
                        : "bg-slate-50 border-slate-200 text-slate-900"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {replyError && (
        <InlineAlert type="error" title="Reply failed" message={replyError} />
      )}

      {ticket.status === "closed" ? (
        <div className="bg-slate-100 border border-slate-200 rounded-md p-3 text-xs text-slate-600 text-center">
          This ticket is closed. Reopen the ticket to send a new message.
        </div>
      ) : (
        <form onSubmit={handleSendReply} className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <label htmlFor="staff-reply" className="block text-xs font-medium text-slate-700">
            Reply as support team (visible to customer)
          </label>
          <textarea
            id="staff-reply"
            rows={3}
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            disabled={sendingReply}
            placeholder="Write a helpful, clear reply for the customer..."
            className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={sendingReply || !replyText.trim()}
              className="px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 disabled:bg-slate-300 rounded-md transition-colors inline-flex items-center gap-1.5"
            >
              {sendingReply ? <LoadingSpinner size="sm" label="Sending..." /> : "Send reply"}
            </button>
          </div>
        </form>
      )}
    </div>
  );

  const detailsSection = (
    <div className="space-y-4">
      {/* Ticket Status & Priority Controls */}
      <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-900">Ticket controls</h2>
        {patchError && <InlineAlert type="error" message={patchError} />}
        {patchSuccess && <InlineAlert type="success" message={patchSuccess} />}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3 text-xs">
          <div>
            <label htmlFor="ticket-status-select" className="block font-medium text-slate-700 mb-1">
              Status
            </label>
            <select
              id="ticket-status-select"
              value={ticket.status}
              disabled={updatingTicket || allowedTransitions.length === 0}
              onChange={(e) => {
                if (e.target.value !== ticket.status) {
                  handlePatchTicket({ status: e.target.value });
                }
              }}
              className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
            >
              {statusOptions.map((stVal) => (
                <option key={stVal} value={stVal}>
                  {getEnumLabel(enums?.ticket_statuses, stVal)}
                </option>
              ))}
            </select>
            {allowedTransitions.length === 0 && (
              <p className="text-[11px] text-slate-500 mt-1">
                No manual status transitions available in current state.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="ticket-priority-select" className="block font-medium text-slate-700 mb-1">
              Priority
            </label>
            <select
              id="ticket-priority-select"
              value={ticket.priority}
              disabled={updatingTicket || !enums}
              onChange={(e) => {
                if (e.target.value !== ticket.priority) {
                  handlePatchTicket({ priority: e.target.value });
                }
              }}
              className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none disabled:bg-slate-100"
            >
              {(enums?.ticket_priorities || [{ value: ticket.priority, label: ticket.priority }]).map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Customer Summary */}
      <div className="bg-white border border-slate-200 rounded-md p-4 space-y-2 text-xs">
        <h2 className="text-sm font-semibold text-slate-900">Customer</h2>
        <div>
          <span className="text-slate-500">Name: </span>
          <span className="font-medium text-slate-900">{customer?.name}</span>
        </div>
        <div>
          <span className="text-slate-500">Email: </span>
          <span className="font-mono text-slate-800">{customer?.email}</span>
        </div>
      </div>

      {/* Linked Order */}
      {order && (
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">
              Order {order.order_number || order.id.slice(0, 8)}
            </h2>
            <StatusBadge status={order.status} label={getEnumLabel(enums?.order_statuses, order.status)} />
          </div>
          <div className="space-y-1 text-slate-600">
            <div>
              Total: <span className="font-mono font-medium text-slate-900">{formatMoney(order.total_amount)}</span>
            </div>
            <div>
              Delivery date: {order.delivery_date ? formatDate(order.delivery_date) : "Not delivered"}
            </div>
            <div>
              Return window:{" "}
              {order.return_window?.is_returnable
                ? `Eligible until ${formatDate(order.return_window.last_eligible_date)} (${order.return_window.return_window_days} days)`
                : "Not returnable"}
            </div>
          </div>
          {order.items && order.items.length > 0 && (
            <div className="pt-2 border-t border-slate-100 space-y-1">
              <div className="font-medium text-slate-700">Items</div>
              {order.items.map((it) => (
                <div key={it.id} className="flex justify-between text-[11px] text-slate-600">
                  <span>
                    {it.name} x{it.quantity} ({it.category})
                  </span>
                  <span className="font-mono">{formatMoney(it.unit_price)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Refunds on Order */}
      {refunds && refunds.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-2 text-xs">
          <h2 className="text-sm font-semibold text-slate-900">Refunds</h2>
          <div className="space-y-2">
            {refunds.map((r) => (
              <div key={r.id} className="p-2.5 bg-slate-50 border border-slate-200 rounded-md space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold text-slate-900">{formatMoney(r.amount)}</span>
                  <StatusBadge status={r.status} label={getEnumLabel(enums?.refund_statuses, r.status)} />
                </div>
                <div className="text-slate-600">{r.reason}</div>
                {r.payment_reference && (
                  <div className="font-mono text-[11px] text-slate-500">Ref: {r.payment_reference}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Escalations */}
      {escalations && escalations.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3 text-xs">
          <h2 className="text-sm font-semibold text-slate-900">Escalations</h2>
          {escalations.map((esc) => (
            <div key={esc.id} className="p-3 bg-slate-50 border border-slate-200 rounded-md space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-800">
                  Decision: {getEnumLabel(enums?.escalation_decisions, esc.decision)}
                </span>
                <Link
                  to={`/staff/approvals/${esc.id}`}
                  className="text-teal-700 hover:underline font-medium"
                >
                  Open review
                </Link>
              </div>
              <p className="text-slate-600">{esc.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const notesSection = (
    <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3 text-xs">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">Internal staff notes</h2>
        <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 mt-1">
          Staff only. Customers cannot see these internal notes.
        </p>
      </div>

      {noteError && <InlineAlert type="error" message={noteError} />}

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {notes.length === 0 ? (
          <p className="text-slate-500 py-2">No internal notes recorded.</p>
        ) : (
          notes.map((n) => (
            <div key={n.id} className="p-2.5 bg-slate-50 border border-slate-200 rounded-md space-y-1">
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span className="font-medium text-slate-800">{n.author_name}</span>
                <span>{formatDateTime(n.created_at)}</span>
              </div>
              <p className="text-slate-700 whitespace-pre-wrap">{n.note}</p>
            </div>
          ))
        )}
      </div>

      <form onSubmit={handleAddNote} className="space-y-2 pt-2 border-t border-slate-100">
        <textarea
          rows={2}
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          disabled={addingNote}
          placeholder="Add an internal note for other staff..."
          aria-label="Internal note"
          className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
        />
        <button
          type="submit"
          disabled={addingNote || !noteText.trim()}
          className="px-3 py-1.5 text-xs font-medium text-slate-800 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-md disabled:opacity-50 transition-colors"
        >
          {addingNote ? "Saving..." : "Add internal note"}
        </button>
      </form>
    </div>
  );

  return (
    <div className="space-y-4">
      <Link
        to="/staff/tickets"
        className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
      >
        <IconArrowLeft className="w-3.5 h-3.5" />
        <span>Back to all tickets</span>
      </Link>

      {/* Header card */}
      <div className="bg-white border border-slate-200 rounded-md p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 tracking-tight">
            {ticket.subject}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Category: {getEnumLabel(enums?.ticket_categories, ticket.category)} | Ticket ID:{" "}
            <span className="font-mono">{ticket.id.slice(0, 8)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            status={ticket.status}
            label={getEnumLabel(enums?.ticket_statuses, ticket.status)}
          />
          {detail.awaiting_admin_approval && (
            <span className="text-xs px-2 py-0.5 bg-amber-50 text-amber-900 border border-amber-200 rounded-md font-medium">
              Awaiting admin approval
            </span>
          )}
        </div>
      </div>

      {/* Mobile Tabs */}
      <div className="flex lg:hidden border-b border-slate-200 gap-1">
        {["conversation", "details", "notes"].map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setMobileTab(tab)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors capitalize ${
              mobileTab === tab
                ? "border-teal-700 text-teal-800"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Mobile Tabbed View */}
      <div className="lg:hidden">
        {mobileTab === "conversation" && conversationSection}
        {mobileTab === "details" && detailsSection}
        {mobileTab === "notes" && notesSection}
      </div>

      {/* Desktop Two-Column Layout */}
      <div className="hidden lg:grid lg:grid-cols-3 gap-6 items-start">
        <div className="lg:col-span-2">{conversationSection}</div>
        <div className="space-y-4">
          {detailsSection}
          {notesSection}
        </div>
      </div>
    </div>
  );
}
