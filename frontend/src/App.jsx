import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { Layout } from "./components/Layout";
import { StaffLayout } from "./components/staff/StaffLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";

// Customer & Public Pages
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Dashboard } from "./pages/Dashboard";
import { Orders } from "./pages/Orders";
import { OrderDetail } from "./pages/OrderDetail";
import { Tickets } from "./pages/Tickets";
import { NewTicket } from "./pages/NewTicket";
import { TicketChat } from "./pages/TicketChat";
import { Privacy } from "./pages/Privacy";
import { Terms } from "./pages/Terms";
import { NotFound } from "./pages/NotFound";

// Staff Pages
import { Overview } from "./pages/staff/Overview";
import { StaffTickets } from "./pages/staff/StaffTickets";
import { StaffTicketDetail } from "./pages/staff/StaffTicketDetail";
import { Approvals } from "./pages/staff/Approvals";
import { ApprovalDetail } from "./pages/staff/ApprovalDetail";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Staff routes */}
          <Route
            path="/staff"
            element={
              <ProtectedRoute allowedRoles={["agent", "admin"]}>
                <StaffLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Overview />} />
            <Route path="tickets" element={<StaffTickets />} />
            <Route path="tickets/:ticketId" element={<StaffTicketDetail />} />
            <Route path="approvals" element={<Approvals />} />
            <Route path="approvals/:escalationId" element={<ApprovalDetail />} />
          </Route>

          {/* Customer & public routes */}
          <Route element={<Layout />}>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />

            <Route
              path="/"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <Orders />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders/:orderId"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <OrderDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="/tickets"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <Tickets />
                </ProtectedRoute>
              }
            />
            <Route
              path="/tickets/new"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <NewTicket />
                </ProtectedRoute>
              }
            />
            <Route
              path="/tickets/:ticketId"
              element={
                <ProtectedRoute allowedRoles={["customer"]}>
                  <TicketChat />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
