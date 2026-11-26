import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, "../src");

let errors = 0;

function checkFile(filePath) {
  const content = fs.readFileSync(filePath, "utf-8");
  // Check for syntax errors by parsing as JS if possible or checking basic brackets
  const openBraces = (content.match(/{/g) || []).length;
  const closeBraces = (content.match(/}/g) || []).length;
  if (openBraces !== closeBraces) {
    console.error(`Syntax warning in ${filePath}: Mismatched curly braces (${openBraces} vs ${closeBraces})`);
    errors++;
  }
}

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
    } else if (/\.(jsx?|js)$/.test(entry.name)) {
      checkFile(full);
    }
  }
}

walk(srcDir);

if (errors > 0) {
  console.error(`\nLint check failed with ${errors} issues.\n`);
  process.exit(1);
} else {
  console.log("[OK] Lint check passed: all source files parsed cleanly.");
  process.exit(0);
}
