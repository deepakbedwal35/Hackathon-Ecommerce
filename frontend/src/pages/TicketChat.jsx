import React, { useEffect, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api/client.js";
import { StatusBadge } from "../components/StatusBadge.jsx";
import { LoadingSpinner } from "../components/LoadingSpinner.jsx";
import { InlineAlert } from "../components/InlineAlert.jsx";
import { IconArrowLeft, IconRefresh } from "../components/Icons.jsx";

export function TicketChat() {
  const { ticketId } = useParams();

  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Send message state
  const [inputText, setInputText] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(null);
  const [failedMessage, setFailedMessage] = useState("");

  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadTicketAndMessages();
  }, [ticketId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadTicketAndMessages() {
    setLoading(true);
    setError(null);
    try {
      const [ticketData, messagesData] = await Promise.all([
        api.tickets.get(ticketId),
        api.tickets.getMessages(ticketId),
      ]);
      setTicket(ticketData);
      setMessages(messagesData);
    } catch (err) {
      setError(err.message || "Failed to load ticket conversation.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSendMessage(e) {
    if (e) e.preventDefault();
    const textToSend = inputText.trim() || failedMessage;
    if (!textToSend) return;

    setSending(true);
    setSendError(null);
    setFailedMessage("");

    try {
      const res = await api.tickets.sendMessage(ticketId, {
        content: textToSend,
      });

      setInputText("");

      // Refresh messages and ticket details to pick up potential agent or staff reply
      const updatedMessages = await api.tickets.getMessages(ticketId);
      setMessages(updatedMessages);

      if (res.ticket_status && ticket) {
        setTicket((prev) => ({ ...prev, status: res.ticket_status }));
      }
    } catch (err) {
      setSendError(err.message || "Message delivery failed. Please retry.");
      setFailedMessage(textToSend);
    } finally {
      setSending(false);
    }
  }

  function formatDate(isoString) {
    if (!isoString) return "";
    const date = new Date(isoString);
    return date.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      day: "numeric",
      month: "short",
    });
  }

  function getSenderLabel(senderType) {
    const type = String(senderType).toLowerCase();
    if (type === "customer") return "You";
    if (type === "agent") return "AI assistant";
    if (type === "staff") return "Support staff";
    return "Support";
  }

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading conversation..." />
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="space-y-4">
        <Link
          to="/tickets"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to tickets</span>
        </Link>
        <InlineAlert type="error" title="Unable to open ticket">
          <div className="flex items-center justify-between">
            <span>{error || "Ticket not found."}</span>
            <button
              type="button"
              onClick={loadTicketAndMessages}
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link
          to="/tickets"
          className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
        >
          <IconArrowLeft className="w-3.5 h-3.5" />
          <span>Back to tickets</span>
        </Link>
        <button
          type="button"
          onClick={loadTicketAndMessages}
          className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900 px-2 py-1 bg-white border border-slate-200 rounded-md"
        >
          <IconRefresh className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-md p-5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-900 tracking-tight">
              {ticket.subject}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Ticket category: {String(ticket.category).replace(/_/g, " ")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={ticket.status} />
            {ticket.review_status && (
              <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md font-medium">
                {ticket.review_status}
              </span>
            )}
          </div>
        </div>

        {ticket.order_id && (
          <div className="pt-2 border-t border-slate-100 text-xs text-slate-600 flex items-center gap-2">
            <span>Related order:</span>
            <Link
              to={`/orders/${ticket.order_id}`}
              className="font-mono text-teal-700 hover:text-teal-900 underline"
            >
              View order details
            </Link>
          </div>
        )}
      </div>

      {/* AI Assistant Disclosure and Accuracy Disclaimer */}
      <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-600">
        <div className="flex items-center gap-2 mb-1">
          <span className="px-1.5 py-0.5 bg-slate-200 text-slate-800 font-medium rounded-md text-[11px]">
            AI assistant active
          </span>
          <span className="font-medium text-slate-700">Notice</span>
        </div>
        <p className="leading-relaxed">
          Responses marked as AI assistant are generated by an automated language model. Information provided
          may contain inaccuracies. Critical policy actions, including refunds exceeding policy limits, are
          verified by store staff.
        </p>
      </div>

      {/* Message Thread */}
      <div className="bg-white border border-slate-200 rounded-md p-5 space-y-4 min-h-[300px]">
        {messages.length === 0 ? (
          <p className="text-xs text-slate-500 text-center py-12">
            No messages in this ticket yet.
          </p>
        ) : (
          messages.map((msg) => {
            const isCustomer = String(msg.sender_type).toLowerCase() === "customer";
            const isAgent = String(msg.sender_type).toLowerCase() === "agent";
            const isStaff = String(msg.sender_type).toLowerCase() === "staff";

            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isCustomer ? "items-end" : "items-start"}`}
              >
                <div className="flex items-center gap-2 mb-1 text-[11px] text-slate-500">
                  <span
                    className={`font-medium ${
                      isCustomer
                        ? "text-slate-800"
                        : isAgent
                        ? "text-teal-800"
                        : "text-amber-800"
                    }`}
                  >
                    {getSenderLabel(msg.sender_type)}
                  </span>
                  <span>{formatDate(msg.created_at)}</span>
                </div>

                <div
                  className={`max-w-[85%] rounded-md px-3.5 py-2.5 text-xs leading-relaxed ${
                    isCustomer
                      ? "bg-teal-50 border border-teal-200 text-teal-950"
                      : isAgent
                      ? "bg-slate-50 border border-slate-200 text-slate-900"
                      : "bg-amber-50 border border-amber-200 text-amber-950"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Send Error Notice with Retry */}
      {sendError && (
        <InlineAlert type="error" title="Message delivery failure">
          <div className="flex items-center justify-between">
            <span>{sendError}</span>
            <button
              type="button"
              onClick={() => handleSendMessage()}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      )}

      {/* Message Input Form */}
      {ticket.status === "closed" ? (
        <div className="bg-slate-100 border border-slate-200 rounded-md p-4 text-xs text-slate-600 text-center">
          This support ticket is closed. If you require further assistance, please create a new ticket.
        </div>
      ) : (
        <form onSubmit={handleSendMessage} className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <label htmlFor="replyMessage" className="sr-only">
            Reply message
          </label>
          <textarea
            id="replyMessage"
            rows={3}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={sending}
            placeholder="Type your response here..."
            className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-slate-500">
              Your message will be processed immediately.
            </span>
            <button
              type="submit"
              disabled={sending || (!inputText.trim() && !failedMessage)}
              className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 disabled:bg-slate-300 rounded-md transition-colors"
            >
              {sending ? (
                <LoadingSpinner size="sm" label="Sending..." />
              ) : (
                "Send message"
              )}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
