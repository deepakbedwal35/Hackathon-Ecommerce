import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { StatusBadge } from "../components/StatusBadge.jsx";
import { LoadingSpinner } from "../components/LoadingSpinner.jsx";
import { InlineAlert } from "../components/InlineAlert.jsx";
import { IconChevronRight, IconPackage } from "../components/Icons.jsx";

export function Orders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadOrders();
  }, []);

  async function loadOrders() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.orders.list();
      setOrders(data);
    } catch (err) {
      setError(err.message || "Failed to load orders. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function formatDate(isoString) {
    if (!isoString) return "Pending";
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight">
            Your orders
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Review purchase history, delivery dates, and return eligibility.
          </p>
        </div>
      </div>

      {loading && (
        <div className="py-16 flex justify-center">
          <LoadingSpinner size="lg" label="Loading orders..." />
        </div>
      )}

      {error && (
        <InlineAlert type="error" title="Unable to load orders">
          <div className="flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={loadOrders}
              className="font-medium underline hover:text-rose-950 ml-4"
            >
              Retry
            </button>
          </div>
        </InlineAlert>
      )}

      {!loading && !error && orders.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center">
          <div className="w-10 h-10 mx-auto text-slate-400 mb-3 flex items-center justify-center">
            <IconPackage className="w-8 h-8" />
          </div>
          <h3 className="text-sm font-semibold text-slate-900">No orders found</h3>
          <p className="text-xs text-slate-500 mt-1">
            Orders associated with your account will appear here.
          </p>
        </div>
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-medium">
                <tr>
                  <th scope="col" className="px-4 py-3">Order</th>
                  <th scope="col" className="px-4 py-3">Placed date</th>
                  <th scope="col" className="px-4 py-3">Delivery date</th>
                  <th scope="col" className="px-4 py-3">Status</th>
                  <th scope="col" className="px-4 py-3">Total</th>
                  <th scope="col" className="px-4 py-3">Eligibility</th>
                  <th scope="col" className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-slate-900">
                      {order.order_number}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatDate(order.created_at)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {order.delivery_date ? formatDate(order.delivery_date) : "Not delivered"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={order.status} />
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {formatMoney(order.total_amount)}
                    </td>
                    <td className="px-4 py-3">
                      {order.is_returnable ? (
                        <span className="inline-block px-1.5 py-0.5 text-xs text-teal-800 bg-teal-50 border border-teal-200 rounded-md">
                          Return eligible
                        </span>
                      ) : (
                        <span className="text-slate-400">Not eligible</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/orders/${order.id}`}
                        className="inline-flex items-center gap-1 font-medium text-teal-700 hover:text-teal-900"
                      >
                        <span>View</span>
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
