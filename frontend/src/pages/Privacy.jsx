import React from "react";
import { legalConfig } from "../config/legal";
import { InlineAlert } from "../components/InlineAlert";

export function Privacy() {
  return (
    <div className="max-w-3xl mx-auto py-8">
      <div className="bg-white border border-slate-200 rounded-md p-6 sm:p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Privacy policy</h1>
          <div className="text-xs text-slate-500 mt-1">
            Last updated: {legalConfig.lastUpdated}
          </div>
        </div>

        <InlineAlert type="warning">
          Draft policy notice: This text is a starting draft and must be reviewed by a qualified lawyer
          before commercial launch. It describes data handling practices of {legalConfig.brandName}.
        </InlineAlert>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">1. Data controller information</h2>
          <p>
            {legalConfig.companyName} ("we", "us", or "our"), operating {legalConfig.brandName}, acts as the
            data controller responsible for your personal information.
          </p>
          <p>
            Registered postal address: {legalConfig.postalAddress}.
          </p>
          <p>
            Contact email for privacy and data questions: {legalConfig.legalEmail}.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">2. Personal information we collect</h2>
          <p>
            We collect personal information necessary to deliver customer support and manage orders:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Account credentials: full name, email address, password verification hash.</li>
            <li>Order and transaction history: order numbers, item details, delivery timestamps, totals.</li>
            <li>Support correspondence: customer tickets, conversation transcripts, attachments.</li>
            <li>Technical metadata: IP addresses, session identifiers, audit event trails.</li>
          </ul>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">3. Artificial intelligence and automated processing</h2>
          <p>
            Customer support conversations are processed with automated tools utilizing {legalConfig.aiModelProvider}.
            When you interact with our support desk:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Your inquiries are analyzed by AI tools strictly to determine order context and suggest resolutions.</li>
            <li>The automated assistant operates under strict policy boundaries defined in code.</li>
            <li>Refund requests exceeding INR {legalConfig.refundLimitInr} or involving special conditions are escalated to human staff.</li>
            <li>Transcripts may be reviewed by human support agents to ensure quality and compliance.</li>
          </ul>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">4. Data retention schedule</h2>
          <p>
            We retain account data and customer conversation histories for {legalConfig.dataRetentionDays} days
            following the resolution of a support request, or as long as required to fulfill statutory tax,
            accounting, and consumer protection mandates.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">5. Your data rights</h2>
          <p>
            Subject to applicable data protection regulations, you possess rights to:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Request access to copies of your personal information.</li>
            <li>Request correction of inaccurate or incomplete records.</li>
            <li>Request deletion of your information when retention is no longer necessary.</li>
            <li>Object to or restrict specific processing activities.</li>
          </ul>
          <p>
            To exercise these rights, submit a written inquiry to {legalConfig.legalEmail}.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">6. Governing law</h2>
          <p>
            This Privacy policy is governed by and construed in accordance with the {legalConfig.governingLaw}.
          </p>
        </section>
      </div>
    </div>
  );
}
