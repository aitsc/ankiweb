import { build } from "esbuild";
import { mkdirSync } from "node:fs";
mkdirSync("ankiweb/shell/static", { recursive: true });
await build({
  entryPoints: ["shell_src/bootstrap.ts"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: "ankiweb/shell/static/bootstrap.js",
});
console.log("built ankiweb/shell/static/bootstrap.js");
