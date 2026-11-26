import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { legalConfig } from "../config/legal.js";

export function Header() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <header className="bg-white border-b border-slate-200">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2">
            <span className="font-semibold text-slate-900 tracking-tight text-base">
              {legalConfig.brandName}
            </span>
            <span className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded-md border border-slate-200">
              Support
            </span>
          </Link>

          {isAuthenticated && (
            <nav className="hidden sm:flex items-center gap-1 text-xs font-medium">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition-colors ${
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  }`
                }
              >
                Dashboard
              </NavLink>
              <NavLink
                to="/orders"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition-colors ${
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  }`
                }
              >
                Orders
              </NavLink>
              <NavLink
                to="/tickets"
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md transition-colors ${
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  }`
                }
              >
                Tickets
              </NavLink>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs">
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <span className="hidden sm:inline text-slate-600 truncate max-w-[180px]">
                {user?.name || user?.email}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className="px-2.5 py-1 text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-md transition-colors"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                to="/login"
                className="px-2.5 py-1 text-slate-700 hover:text-slate-900 font-medium"
              >
                Sign in
              </Link>
              <Link
                to="/register"
                className="px-2.5 py-1 bg-teal-700 hover:bg-teal-800 text-white rounded-md font-medium transition-colors"
              >
                Create account
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
