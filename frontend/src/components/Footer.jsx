import React from "react";
import { Link } from "react-router-dom";
import { legalConfig } from "../config/legal.js";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-white py-6 text-xs text-slate-500">
      <div className="max-w-5xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p>
          &copy; {new Date().getFullYear()} {legalConfig.companyName}. All rights reserved.
        </p>
        <div className="flex items-center gap-4">
          <Link to="/privacy" className="hover:text-slate-700 underline">
            Privacy policy
          </Link>
          <Link to="/terms" className="hover:text-slate-700 underline">
            Terms of service
          </Link>
        </div>
      </div>
    </footer>
  );
}
