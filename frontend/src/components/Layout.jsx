import React from "react";
import { DemoBanner } from "./DemoBanner.jsx";
import { OfflineNotice } from "./OfflineNotice.jsx";
import { Header } from "./Header.jsx";
import { Footer } from "./Footer.jsx";

export function Layout({ children }) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <OfflineNotice />
      <DemoBanner />
      <Header />
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
        {children}
      </main>
      <Footer />
    </div>
  );
}
