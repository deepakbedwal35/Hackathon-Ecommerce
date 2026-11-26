import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");

const violations = [];

function recordViolation(file, line, message) {
  violations.push(`${file}:${line} - ${message}`);
}

// 1. Check required public files
const requiredPublicFiles = [
  "public/favicon.svg",
  "public/favicon.ico",
  "public/apple-touch-icon.png",
  "public/site.webmanifest",
  "public/robots.txt",
];

for (const relPath of requiredPublicFiles) {
  const fullPath = path.join(rootDir, relPath);
  if (!fs.existsSync(fullPath)) {
    violations.push(`MISSING FILE: ${relPath} does not exist`);
  }
}

// 2. Check legal config
const legalPath = path.join(rootDir, "src/config/legal.js");
if (!fs.existsSync(legalPath)) {
  violations.push("MISSING FILE: src/config/legal.js does not exist");
} else {
  const legalContent = fs.readFileSync(legalPath, "utf-8");
  if (legalContent.includes("REPLACE_ME")) {
    recordViolation("src/config/legal.js", 1, "Contains forbidden placeholder 'REPLACE_ME'");
  }
  // Check for empty string values
  const lines = legalContent.split("\n");
  lines.forEach((line, idx) => {
    if (/:\s*["']\s*["']/.test(line)) {
      recordViolation("src/config/legal.js", idx + 1, "Empty configuration value found");
    }
  });
}

// 3. Check routes exist for /privacy and /terms
const routerOrAppFiles = ["src/App.jsx", "src/main.jsx"];
let foundPrivacyRoute = false;
let foundTermsRoute = false;

for (const rel of routerOrAppFiles) {
  const p = path.join(rootDir, rel);
  if (fs.existsSync(p)) {
    const code = fs.readFileSync(p, "utf-8");
    if (code.includes("/privacy")) foundPrivacyRoute = true;
    if (code.includes("/terms")) foundTermsRoute = true;
  }
}
if (!foundPrivacyRoute) {
  violations.push("ROUTING: /privacy route definition not found in App.jsx or main.jsx");
}
if (!foundTermsRoute) {
  violations.push("ROUTING: /terms route definition not found in App.jsx or main.jsx");
}

// 4. Scan files in src/ and index.html
const bannedWords = [
  "lorem",
  "ipsum",
  "TODO",
  "FIXME",
  "placeholder",
  "Made with",
  "Powered by",
  "seamless",
  "effortless",
  "supercharge",
  "unlock",
  "elevate",
  "revolutionize",
];

const emojiRegex = /[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{1F600}-\u{1F64F}]|[\u{1F680}-\u{1F6FF}]|[\u{1F1E0}-\u{1F1FF}]/u;

function scanFile(filePath, isUserFacing) {
  const relPath = path.relative(rootDir, filePath);
  const content = fs.readFileSync(filePath, "utf-8");
  const lines = content.split("\n");

  lines.forEach((line, idx) => {
    const lineNum = idx + 1;

    // A. Em dash (— \u2014) or En dash (– \u2013)
    if (line.includes("\u2014") || line.includes("—")) {
      recordViolation(relPath, lineNum, "Forbidden em dash (—) character found. Use commas, periods, or colons.");
    }
    if (line.includes("\u2013") || line.includes("–")) {
      recordViolation(relPath, lineNum, "Forbidden en dash (–) character found. Use commas, periods, or colons.");
    }

    // B. Emojis
    if (emojiRegex.test(line)) {
      recordViolation(relPath, lineNum, "Forbidden emoji character detected.");
    }

    // C. Banned words (case-insensitive for marketing terms, exact for TODO/FIXME)
    for (const word of bannedWords) {
      if (word === "TODO" || word === "FIXME") {
        if (line.includes(word)) {
          recordViolation(relPath, lineNum, `Forbidden token '${word}' found.`);
        }
      } else {
        const regex = new RegExp(`\\b${word}\\b`, "i");
        if (regex.test(line)) {
          // Exclude check-launch.js itself or HTML placeholder attribute
          if (!relPath.includes("check-launch.js") && !line.includes('placeholder="') && !line.includes("placeholder=")) {
            recordViolation(relPath, lineNum, `Forbidden word/phrase '${word}' found.`);
          }
        }
      }
    }

    // D. Gradients (no gradient in classes or CSS)
    if (!relPath.includes("check-launch.js")) {
      if (/\b(?:bg-gradient|from-|to-|via-|linear-gradient|radial-gradient)\b/i.test(line)) {
        recordViolation(relPath, lineNum, "Forbidden gradient styling detected.");
      }
    }

    // E. rounded-full: only allowed for spinner and status dot
    if (line.includes("rounded-full")) {
      const isAllowedComponent =
        relPath.includes("LoadingSpinner.jsx") ||
        relPath.includes("StatusBadge.jsx") ||
        line.includes("status-dot") ||
        line.includes("spinner") ||
        line.includes("allowed rounded-full");
      if (!isAllowedComponent) {
        recordViolation(relPath, lineNum, "Forbidden rounded-full class used. Pill shapes are banned on buttons, tags, and inputs.");
      }
    }

    // F. Scaffold leftovers
    if (line.includes("vite.svg") || line.includes("react.svg")) {
      recordViolation(relPath, lineNum, "Scaffold asset reference (vite.svg or react.svg) detected.");
    }
    if (line.includes("<title>Vite + React</title>")) {
      recordViolation(relPath, lineNum, "Default Vite + React title detected.");
    }
  });
}

function walkDir(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "node_modules" && entry.name !== "dist" && entry.name !== ".git" && entry.name !== "tests") {
        walkDir(full);
      }
    } else if (entry.isFile()) {
      if (/\.(jsx?|tsx?|html|css)$/.test(entry.name) && !entry.name.includes("check-launch.js") && !entry.name.includes(".test.")) {
        scanFile(full, true);
      }
    }
  }
}

// Scan index.html and src/
scanFile(path.join(rootDir, "index.html"), true);
walkDir(path.join(rootDir, "src"));

// Also scan dist/index.html if built
const distHtml = path.join(rootDir, "dist/index.html");
if (fs.existsSync(distHtml)) {
  scanFile(distHtml, true);
}

if (violations.length > 0) {
  console.error("\n=======================================================");
  console.error(" LAUNCH VERIFICATION FAILED: Violations detected!");
  console.error("=======================================================\n");
  for (const v of violations) {
    console.error(` ✗ ${v}`);
  }
  console.error(`\nTotal violations: ${violations.length}\n`);
  process.exit(1);
} else {
  console.log("\n[OK] Launch check passed: 0 design or quality violations detected.\n");
  process.exit(0);
}
