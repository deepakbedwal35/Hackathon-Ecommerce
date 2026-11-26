import React, { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { legalConfig } from "../../config/legal.js";
import { OfflineNotice } from "../OfflineNotice.jsx";
import { Footer } from "../Footer.jsx";

export function StaffLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isAdmin = String(user?.role || "").toLowerCase() === "admin";
  const roleLabel = isAdmin ? "Admin" : "Support agent";

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const navLinkClass = ({ isActive }) =>
    `px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
      isActive
        ? "bg-slate-100 text-slate-900"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
    }`;

  return (
    <div className="min-h-screen w-full flex flex-col bg-slate-50 text-slate-900">
      <OfflineNotice />
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-5">
            <Link to="/staff" className="flex items-center gap-2">
              <span className="font-semibold text-slate-900 tracking-tight text-base">
                {legalConfig.brandName}
              </span>
              <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-700 rounded-md border border-slate-200 font-medium">
                {roleLabel}
              </span>
            </Link>

            <nav className="hidden md:flex items-center gap-1" aria-label="Staff navigation">
              <NavLink to="/staff" end className={navLinkClass}>
                Overview
              </NavLink>
              <NavLink to="/staff/tickets" className={navLinkClass}>
                Tickets
              </NavLink>
              <NavLink to="/staff/approvals" className={navLinkClass}>
                Approvals
              </NavLink>
            </nav>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <span className="hidden sm:inline text-slate-600 truncate max-w-[200px]">
              {user?.email}
            </span>
            <button
              type="button"
              onClick={handleLogout}
              className="px-2.5 py-1.5 text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-md transition-colors"
            >
              Sign out
            </button>
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              aria-expanded={mobileMenuOpen}
              aria-label="Toggle navigation menu"
              className="md:hidden px-2.5 py-1.5 text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50"
            >
              Menu
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <nav
            className="md:hidden border-t border-slate-200 bg-white px-4 py-2 flex flex-col gap-1"
            aria-label="Mobile staff navigation"
          >
            <NavLink
              to="/staff"
              end
              className={navLinkClass}
              onClick={() => setMobileMenuOpen(false)}
            >
              Overview
            </NavLink>
            <NavLink
              to="/staff/tickets"
              className={navLinkClass}
              onClick={() => setMobileMenuOpen(false)}
            >
              Tickets
            </NavLink>
            <NavLink
              to="/staff/approvals"
              className={navLinkClass}
              onClick={() => setMobileMenuOpen(false)}
            >
              Approvals
            </NavLink>
          </nav>
        )}
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Outlet />
      </main>

      <Footer />
    </div>
  );
}
