import { Bridge } from "./pycmd_shim";

// Context resolution order: explicit page global, then ?context= (the spike), then "default".
const ctx =
  (window as any).__ankiwebContext ||
  new URLSearchParams(location.search).get("context") ||
  "default";

const bridge = new Bridge(ctx);
(window as any).__ankiwebBridge = bridge;

// SvelteKit SPA pages don't load this bootstrap; they read a #night hash for dark mode.
// So when night mode is on, append #night to navigations INTO those SPA routes.
const SPA_NIGHT_PREFIXES = [
  "/graphs", "/deck-options", "/change-notetype",
  "/import-csv", "/import-anki-package", "/image-occlusion",
];
function nightOn(): boolean {
  return location.hash.includes("night") || localStorage.getItem("ankiweb-night") === "1";
}
function withNight(url: string): string {
  if (!nightOn() || url.includes("#")) return url;
  const path = url.split("?")[0];
  if (SPA_NIGHT_PREFIXES.some((p) => path === p || path.startsWith(p + "/"))) {
    return url + "#night";
  }
  return url;
}

// Server-invokable navigation/reload helpers (called via {type:"call"}).
bridge.registerCalls({
  ankiwebNavigate: (url: unknown) => {
    location.href = withNight(String(url));
  },
  ankiwebReload: () => {
    location.reload();
  },
});

// Client-side helper for the "Create Deck" button (prompt then send create:<name>).
(window as any).ankiwebCreateDeck = () => {
  const name = window.prompt("Deck name:");
  if (name) (window as any).pycmd("create:" + name);
};

(window as any).ankiwebImportFile = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".csv,.tsv,.txt,.apkg,.zip";
  input.onchange = async () => {
    const f = input.files && input.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const resp = await fetch("/import/upload", { method: "POST", body: fd });
    if (!resp.ok) { window.alert("Import failed: " + (await resp.text())); return; }
    const { route, path } = await resp.json();
    window.location.href = "/" + route + "/" + encodeURIComponent(path);
  };
  input.click();
};

(window as any).ankiwebImageOcclusion = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async () => {
    const f = input.files && input.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const resp = await fetch("/image-occlusion/upload", { method: "POST", body: fd });
    if (!resp.ok) { window.alert("Image occlusion upload failed: " + (await resp.text())); return; }
    const { path } = await resp.json();
    window.location.href = "/image-occlusion/" + encodeURIComponent(path);
  };
  input.click();
};

// Cross-screen refresh: a screen may set window.__ankiwebOnOpchanges to handle this
// itself (e.g. the Browser re-searches in place to keep an embedded editor iframe alive);
// otherwise reload when another screen's op changed our data.
window.addEventListener("anki-opchanges", (e: Event) => {
  const detail = (e as CustomEvent).detail;
  const flags = detail.flags || {};
  if (detail.initiator === ctx) return;
  const custom = (window as any).__ankiwebOnOpchanges;
  if (typeof custom === "function") {
    custom(detail);
    return;
  }
  if (flags.study_queues || flags.deck || flags.card || flags.note) {
    location.reload();
  }
});

// Night-mode: the #night hash convention OR the persisted preference. Applied
// synchronously in <head> (before <body>) so server-rendered screens don't flash.
if (nightOn()) {
  document.documentElement.classList.add("night-mode");
  document.documentElement.setAttribute("data-bs-theme", "dark");
}

// When night mode is on, rewrite static links into the SvelteKit SPA pages so they
// carry #night (those pages don't load this bootstrap — they rely on the hash).
window.addEventListener("DOMContentLoaded", () => {
  if (!nightOn()) return;
  document.querySelectorAll("a[href]").forEach((a) => {
    const el = a as HTMLAnchorElement;
    const href = el.getAttribute("href") || "";
    if (href.startsWith("/")) {
      const patched = withNight(href);
      if (patched !== href) el.setAttribute("href", patched);
    }
  });
});

(window as any).ankiwebToggleNight = () => {
  const on = localStorage.getItem("ankiweb-night") === "1";
  localStorage.setItem("ankiweb-night", on ? "0" : "1");
  location.reload();
};

window.addEventListener("load", () => bridge.ready());
