import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { LoadingSpinner } from "./LoadingSpinner.jsx";
import { getRoleHomePath } from "../utils/format.js";

export function ProtectedRoute({ children, allowedRoles = null }) {
  const { isAuthenticated, user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="py-24 flex items-center justify-center">
        <LoadingSpinner size="lg" label="Checking credentials..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const role = String(user?.role || "").toLowerCase();
  if (Array.isArray(allowedRoles) && !allowedRoles.includes(role)) {
    return <Navigate to={getRoleHomePath(user)} replace />;
  }

  return children;
}
