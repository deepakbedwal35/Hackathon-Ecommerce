import React from "react";
import { legalConfig } from "../config/legal";
import { InlineAlert } from "../components/InlineAlert";

export function Terms() {
  return (
    <div className="max-w-3xl mx-auto py-8">
      <div className="bg-white border border-slate-200 rounded-md p-6 sm:p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Terms of service</h1>
          <div className="text-xs text-slate-500 mt-1">
            Last updated: {legalConfig.lastUpdated}
          </div>
        </div>

        <InlineAlert type="warning">
          Draft terms notice: This text is a starting draft and must be reviewed by a qualified lawyer
          before commercial launch. It outlines the terms of using {legalConfig.brandName}.
        </InlineAlert>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">1. Acceptance of terms</h2>
          <p>
            By accessing or using the support portal and services provided by {legalConfig.companyName} ("we",
            "us", or "our"), you agree to be bound by these Terms of service and all policies referenced herein.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">2. Customer accounts</h2>
          <p>
            To access order tracking and ticket submission, you must register an account. You agree to provide
            accurate, current information and maintain the security of your authentication credentials. You are
            responsible for all activities conducted under your credentials.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">3. Refund and return policy</h2>
          <p>
            Our customer return policy operates under clear standard parameters:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li>
              Return window: Return or refund requests must be initiated within {legalConfig.returnWindowDays} days
              of confirmed delivery.
            </li>
            <li>
              Non-returnable categories: Perishable items and groceries are strictly non-returnable.
            </li>
            <li>
              Approval limits: Orders with refund values up to INR {legalConfig.refundLimitInr} that meet standard criteria
              are eligible for automated processing. Requests exceeding INR {legalConfig.refundLimitInr} require human staff
              evaluation and manual decision.
            </li>
            <li>
              Single refund limit: Each order allows one active or completed refund record.
            </li>
          </ul>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">4. AI assistance disclosures</h2>
          <p>
            Our customer care platform integrates artificial intelligence tools to review ticket details and
            suggest resolutions. Responses provided by the AI assistant are automated and may occasionally contain
            inaccuracies. You have the right to request human review of any ticket or dispute.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">5. Limitation of liability</h2>
          <p>
            To the maximum extent permitted by applicable law, {legalConfig.companyName} shall not be liable for
            any indirect, incidental, punitive, or consequential damages resulting from portal downtime, service
            interruptions, or delays in refund disbursements.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">6. Governing law and dispute resolution</h2>
          <p>
            These Terms are governed by the {legalConfig.governingLaw}. Any disputes arising from these terms or
            your use of the service shall be subject to the exclusive jurisdiction of the competent courts in
            Bangalore, India.
          </p>
        </section>

        <section className="space-y-2 text-xs leading-relaxed text-slate-700">
          <h2 className="text-sm font-semibold text-slate-900">7. Contact information</h2>
          <p>
            For questions regarding these Terms, contact us at {legalConfig.contactEmail} or by mail at:
          </p>
          <p className="font-mono text-[11px] text-slate-600">
            {legalConfig.companyName}<br />
            {legalConfig.postalAddress}
          </p>
        </section>
      </div>
    </div>
  );
}
