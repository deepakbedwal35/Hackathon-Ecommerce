import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { InlineAlert } from "../components/InlineAlert";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { legalConfig } from "../config/legal";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || "Failed to sign in. Verify your credentials.");
    } finally {
      setLoading(false);
    }
  }

  function handleQuickFill(demoEmail, demoPassword) {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setError(null);
  }

  return (
    <div className="max-w-md mx-auto py-12 px-4">
      <div className="bg-white border border-slate-200 rounded-md p-6">
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-6 h-6 bg-teal-700 text-white flex items-center justify-center rounded text-xs font-bold">
              A
            </span>
            <span className="font-semibold text-slate-900 text-base">{legalConfig.brandName}</span>
          </div>
          <h1 className="text-xl font-semibold text-slate-900">Sign in</h1>
          <p className="text-xs text-slate-500 mt-1">
            Sign in to view your orders and support tickets.
          </p>
        </div>

        {error && (
          <InlineAlert type="error" className="mb-4">
            {error}
          </InlineAlert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="login-email" className="block text-xs font-medium text-slate-700 mb-1">
              Email address
            </label>
            <input
              id="login-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:border-teal-700 bg-white"
            />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-xs font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:border-teal-700 bg-white"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full text-xs font-medium py-2 px-4 bg-teal-700 text-white rounded-md hover:bg-teal-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading ? <LoadingSpinner size="sm" label="Signing in..." /> : "Sign in"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-100 text-center">
          <p className="text-xs text-slate-600">
            Do not have an account?{" "}
            <Link to="/register" className="text-teal-700 font-medium hover:underline">
              Create account
            </Link>
          </p>
        </div>

        <div className="mt-6 pt-4 border-t border-slate-100">
          <div className="text-[11px] font-medium text-slate-500 mb-2">Demo customer accounts:</div>
          <div className="space-y-1.5">
            <button
              type="button"
              onClick={() => handleQuickFill("customer@example.com", "password123")}
              className="w-full text-left text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:bg-slate-50 transition-colors text-slate-700 flex justify-between"
            >
              <span>customer@example.com</span>
              <span className="text-slate-400">password123</span>
            </button>
            <button
              type="button"
              onClick={() => handleQuickFill("bob@example.com", "password123")}
              className="w-full text-left text-[11px] px-2.5 py-1.5 border border-slate-200 rounded-md hover:bg-slate-50 transition-colors text-slate-700 flex justify-between"
            >
              <span>bob@example.com</span>
              <span className="text-slate-400">password123</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
