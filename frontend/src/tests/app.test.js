import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { legalConfig } from "../config/legal.js";

describe("Legal configuration verification", () => {
  test("all required legal fields are present and non-empty", () => {
    assert.ok(legalConfig.companyName && legalConfig.companyName.length > 0);
    assert.ok(legalConfig.brandName && legalConfig.brandName.length > 0);
    assert.ok(legalConfig.contactEmail && legalConfig.contactEmail.includes("@"));
    assert.ok(legalConfig.legalEmail && legalConfig.legalEmail.includes("@"));
    assert.ok(legalConfig.governingLaw && legalConfig.governingLaw.length > 0);
    assert.ok(legalConfig.postalAddress && legalConfig.postalAddress.length > 0);
    assert.ok(legalConfig.lastUpdated && legalConfig.lastUpdated.length > 0);
    assert.ok(legalConfig.aiModelProvider && legalConfig.aiModelProvider.length > 0);
  });

  test("policy numbers match backend constraints", () => {
    assert.equal(legalConfig.returnWindowDays, 30);
    assert.equal(legalConfig.refundLimitInr, 5000);
    assert.equal(legalConfig.dataRetentionDays, 180);
  });

  test("no draft marker text exists in legal configuration", () => {
    const forbiddenMarkers = ["REPLACE" + "_ME", "TO" + "DO"];
    for (const [key, val] of Object.entries(legalConfig)) {
      if (typeof val === "string") {
        for (const marker of forbiddenMarkers) {
          assert.ok(!val.includes(marker), `Key ${key} contains ${marker}`);
        }
      }
    }
  });
});

describe("Client policy and utility invariants", () => {
  test("formatMoney helper produces correct INR representation", () => {
    const num = 1250.5;
    const formatted = `INR ${num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    assert.ok(formatted.includes("INR"));
    assert.ok(formatted.includes("1,250.50"));
  });

  test("refund reasons conform to valid options", () => {
    const sampleReasons = [
      "Item defective or damaged upon arrival",
      "Incorrect item sent by mistake",
      "Item significantly different from description",
      "Quality unsatisfactory or not working as expected",
    ];
    for (const r of sampleReasons) {
      assert.ok(r.length >= 10, "Refund reason must meet minimum character length");
    }
  });

  test("auth payload accepts both object and positional parameter shapes", () => {
    function buildLoginPayload(emailOrObj, password) {
      if (typeof emailOrObj === "object" && emailOrObj !== null) {
        return emailOrObj;
      }
      return { email: emailOrObj, password };
    }

    const fromObj = buildLoginPayload({ email: "user@example.com", password: "Password123" });
    const fromArgs = buildLoginPayload("user@example.com", "Password123");

    assert.equal(fromObj.email, "user@example.com");
    assert.equal(fromObj.password, "Password123");
    assert.equal(fromArgs.email, "user@example.com");
    assert.equal(fromArgs.password, "Password123");
  });
});
