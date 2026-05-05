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

vendor("leaflet", ["dist/leaflet.css", "dist/leaflet.js", "dist/leaflet.js.map"], "leaflet");
mkdirSync(join(VENDOR, "leaflet", "images"), { recursive: true });
cpSync(
  join("node_modules", "leaflet", "dist", "images"),
  join(VENDOR, "leaflet", "images"),
  { recursive: true },
);

vendor("chart.js", ["dist/chart.umd.min.js"], "chart.js");
vendor("qrcodejs", ["qrcode.min.js"], "qrcodejs");

console.log("Bundling SPA with esbuild...");
mkdirSync(DIST, { recursive: true });

const metafilePath = join(DIST, "meta.json");
execSync(
  `npx esbuild ${join(STATIC, "js", "spa", "app.js")}` +
    ` --bundle --format=esm --splitting --minify` +
    ` --outdir=${DIST}` +
    ` --entry-names=[name].[hash]` +
    ` --chunk-names=chunks/[name].[hash]` +
    ` --metafile=${metafilePath}`,
  { stdio: "inherit" },
);

console.log("Generating assets manifest...");

const meta = JSON.parse(readFileSync(metafilePath, "utf-8"));
const assets = {};

for (const [outputPath, info] of Object.entries(meta.outputs)) {
  if (!info.entryPoint) continue;
  const entryName = info.entryPoint.split("/").pop().replace(/\.js$/, ".js");
  const fileName = outputPath.split("/").pop();
  assets[entryName] = fileName;
}

const vendorFiles = {
  "leaflet.css": join(VENDOR, "leaflet", "leaflet.css"),
  "leaflet.js": join(VENDOR, "leaflet", "leaflet.js"),
  "chart.umd.min.js": join(VENDOR, "chart.js", "chart.umd.min.js"),
  "qrcode.min.js": join(VENDOR, "qrcodejs", "qrcode.min.js"),
};

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
