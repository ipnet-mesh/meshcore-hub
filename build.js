import { execSync } from "node:child_process";
import { cpSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const STATIC = join("src", "meshcore_hub", "web", "static");
const VENDOR = join(STATIC, "vendor");

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

vendor("lit-html", ["lit-html.js", "lit-html.js.map"], "lit-html");
vendor(
  "lit-html",
  [
    "directive.js",
    "directive.js.map",
    "directive-helpers.js",
    "directive-helpers.js.map",
    "async-directive.js",
    "async-directive.js.map",
  ],
  "lit-html",
);
vendor(
  "lit-html",
  ["directives/unsafe-html.js", "directives/unsafe-html.js.map"],
  "lit-html/directives",
);

vendor("leaflet", ["dist/leaflet.css", "dist/leaflet.js", "dist/leaflet.js.map"], "leaflet");
mkdirSync(join(VENDOR, "leaflet", "images"), { recursive: true });
cpSync(
  join("node_modules", "leaflet", "dist", "images"),
  join(VENDOR, "leaflet", "images"),
  { recursive: true },
);

vendor("chart.js", ["dist/chart.umd.min.js"], "chart.js");
vendor("qrcodejs", ["qrcode.min.js"], "qrcodejs");

console.log("Done.");
