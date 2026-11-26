import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { InlineAlert } from "../components/InlineAlert";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { legalConfig } from "../config/legal";

export function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!agreed) {
      setError("You must agree to the Terms of service and Privacy policy to create an account.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      await register(name, email, password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err.code === "EMAIL_TAKEN") {
        setError("An account with this email address already exists.");
      } else {
        setError(err.message || "Failed to create account. Check your input.");
      }
    } finally {
      setLoading(false);
    }
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
          <h1 className="text-xl font-semibold text-slate-900">Create account</h1>
          <p className="text-xs text-slate-500 mt-1">
            Register to manage orders and submit support inquiries.
          </p>
        </div>

        {error && (
          <InlineAlert type="error" className="mb-4">
            {error}
          </InlineAlert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="register-name" className="block text-xs font-medium text-slate-700 mb-1">
              Full name
            </label>
            <input
              id="register-name"
              type="text"
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:border-teal-700 bg-white"
            />
          </div>

          <div>
            <label htmlFor="register-email" className="block text-xs font-medium text-slate-700 mb-1">
              Email address
            </label>
            <input
              id="register-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:border-teal-700 bg-white"
            />
          </div>

          <div>
            <label htmlFor="register-password" className="block text-xs font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              id="register-password"
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:border-teal-700 bg-white"
            />
          </div>

          <div className="flex items-start gap-2 pt-1">
            <input
              id="agree-terms"
              type="checkbox"
              required
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 rounded border-slate-300 text-teal-700 focus:ring-teal-700"
            />
            <label htmlFor="agree-terms" className="text-xs text-slate-600 leading-normal">
              By creating an account you agree to the{" "}
              <Link to="/terms" target="_blank" className="text-teal-700 underline font-medium">
                Terms of service
              </Link>{" "}
              and{" "}
              <Link to="/privacy" target="_blank" className="text-teal-700 underline font-medium">
                Privacy policy
              </Link>
              .
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full text-xs font-medium py-2 px-4 bg-teal-700 text-white rounded-md hover:bg-teal-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading ? <LoadingSpinner size="sm" label="Creating account..." /> : "Create account"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-100 text-center">
          <p className="text-xs text-slate-600">
            Already have an account?{" "}
            <Link to="/login" className="text-teal-700 font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
