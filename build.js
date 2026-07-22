import { execSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { join } from "node:path";

const STATIC = join("src", "meshcore_hub", "web", "static");
const VENDOR = join(STATIC, "vendor");
const DIST = join(STATIC, "dist");

function vendor(pkg, files, dest) {
  const out = join(VENDOR, dest);
  mkdirSync(out, { recursive: true });
  for (const f of files) {
    const src = join("node_modules", pkg, f);
    if (!existsSync(src)) {
      console.error(`  MISSING: ${src}`);
      process.exit(1);
    }
    cpSync(src, join(out, f.split("/").pop()), { recursive: true });
  }
}

console.log("Building Tailwind CSS...");
execSync(
  `npx @tailwindcss/cli build --input ${join(STATIC, "css", "input.css")} --output ${join(STATIC, "css", "tailwind.css")} --minify`,
  { stdio: "inherit" },
);

console.log("Copying vendor files...");

vendor(
  "@fontsource-variable/ibm-plex-sans",
  [
    "files/ibm-plex-sans-latin-wght-normal.woff2",
    "files/ibm-plex-sans-latin-ext-wght-normal.woff2",
  ],
  "fonts",
);
vendor(
  "@fontsource/ibm-plex-mono",
  [
    "files/ibm-plex-mono-latin-400-normal.woff2",
    "files/ibm-plex-mono-latin-ext-400-normal.woff2",
  ],
  "fonts",
);

console.log("Bundling SPA with Vite...");
execSync("npx vite build", { stdio: "inherit" });

// Vite emits a copy of the input HTML preserving its path relative to the
// project root (dist/src/…/index.html).  The Jinja2 template is the real
// HTML shell, so remove the artifact.
import { rmSync } from "node:fs";
const staleHtmlDir = join(DIST, "src");
if (existsSync(staleHtmlDir)) {
  rmSync(staleHtmlDir, { recursive: true, force: true });
}

console.log("Generating assets manifest...");

const viteManifestPath = join(DIST, ".vite", "manifest.json");
const assets = {};

if (existsSync(viteManifestPath)) {
  const viteManifest = JSON.parse(readFileSync(viteManifestPath, "utf-8"));
  for (const [, info] of Object.entries(viteManifest)) {
    if (!info.isEntry) continue;
    assets["app.js"] = info.file;
    if (info.css && info.css.length > 0) {
      assets["app.css"] = info.css[0];
    }
  }
}

const vendorFiles = {};

const vendorHashes = {};
for (const [name, path] of Object.entries(vendorFiles)) {
  if (existsSync(path)) {
    const hash = createHash("sha256")
      .update(readFileSync(path))
      .digest("hex")
      .slice(0, 8);
    vendorHashes[name] = hash;
  }
}

const localesDir = join(STATIC, "locales");
let localeContent = "";
if (existsSync(localesDir)) {
  const localeFiles = readdirSync(localesDir)
    .filter((f) => f.endsWith(".json"))
    .sort();
  for (const f of localeFiles) {
    localeContent += readFileSync(join(localesDir, f), "utf-8");
  }
}
const localeVersion =
  localeContent.length > 0
    ? createHash("sha256").update(localeContent).digest("hex").slice(0, 8)
    : "";

const manifest = {
  ...assets,
  vendor: vendorHashes,
  locale_version: localeVersion,
};

writeFileSync(join(DIST, "assets.json"), JSON.stringify(manifest, null, 2));
console.log("  Manifest:", JSON.stringify(manifest, null, 2));

console.log("Done.");
