import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { IconPackage, IconTicket, IconChevronRight } from "../components/Icons";

export function Dashboard() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [refunds, setRefunds] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [ordersData, ticketsData, refundsData] = await Promise.all([
          api.orders.list().catch(() => []),
          api.tickets.list().catch(() => []),
          api.refunds.list().catch(() => []),
        ]);
        setOrders(ordersData || []);
        setTickets(ticketsData || []);
        setRefunds(refundsData || []);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="py-16 flex justify-center">
        <LoadingSpinner size="lg" label="Loading dashboard..." />
      </div>
    );
  }

  const activeTickets = tickets.filter(
    (t) => t.status !== "resolved" && t.status !== "closed"
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Welcome back, {user?.name || "Customer"}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage your purchases, request returns, or chat with support.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/tickets/new"
            className="text-xs font-medium px-3.5 py-2 bg-teal-700 text-white rounded-md hover:bg-teal-800 transition-colors"
          >
            Create ticket
          </Link>
          <Link
            to="/orders"
            className="text-xs font-medium px-3.5 py-2 bg-white border border-slate-200 text-slate-700 rounded-md hover:bg-slate-50 transition-colors"
          >
            View orders
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Active tickets</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {activeTickets.length}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {tickets.length} total tickets recorded
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Total orders</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {orders.length}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Past purchases and delivery tracking
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="text-xs font-medium text-slate-500">Refund requests</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1">
            {refunds.length}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Completed and pending refunds
          </div>
        </div>
      </div>

      {/* Recent Orders & Tickets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Orders */}
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <IconPackage className="w-4 h-4 text-slate-500" />
              <span>Recent orders</span>
            </h2>
            <Link to="/orders" className="text-xs text-teal-700 hover:underline font-medium">
              View all ({orders.length})
            </Link>
          </div>

          {orders.length === 0 ? (
            <p className="text-xs text-slate-500 py-4 text-center">No recent orders.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {orders.slice(0, 4).map((order) => (
                <div key={order.id} className="py-2.5 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-medium text-slate-900">
                      {order.order_number || order.id.slice(0, 8)}
                    </div>
                    <div className="text-slate-500 text-[11px]">
                      {new Date(order.created_at).toLocaleDateString()} &bull; ₹{Number(order.total_amount).toFixed(2)}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={order.status} />
                    <Link
                      to={`/orders/${order.id}`}
                      className="text-teal-700 hover:text-teal-900"
                    >
                      <IconChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Tickets */}
        <div className="bg-white border border-slate-200 rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <IconTicket className="w-4 h-4 text-slate-500" />
              <span>Recent tickets</span>
            </h2>
            <Link to="/tickets" className="text-xs text-teal-700 hover:underline font-medium">
              View all ({tickets.length})
            </Link>
          </div>

          {tickets.length === 0 ? (
            <p className="text-xs text-slate-500 py-4 text-center">No recent support tickets.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {tickets.slice(0, 4).map((ticket) => (
                <div key={ticket.id} className="py-2.5 flex items-center justify-between text-xs">
                  <div className="max-w-[200px] truncate">
                    <div className="font-medium text-slate-900 truncate">
                      {ticket.subject}
                    </div>
                    <div className="text-slate-500 text-[11px]">
                      Updated {new Date(ticket.updated_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={ticket.status} />
                    <Link
                      to={`/tickets/${ticket.id}`}
                      className="text-teal-700 hover:text-teal-900"
                    >
                      <IconChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
