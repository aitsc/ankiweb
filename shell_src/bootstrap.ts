import { Bridge } from "./pycmd_shim";

// Context resolution order: explicit page global, then ?context= (the spike), then "default".
const ctx =
  (window as any).__ankiwebContext ||
  new URLSearchParams(location.search).get("context") ||
  "default";

const bridge = new Bridge(ctx);
(window as any).__ankiwebBridge = bridge;

// Server-invokable navigation/reload helpers (called via {type:"call"}).
bridge.registerCalls({
  ankiwebNavigate: (url: unknown) => {
    location.href = String(url);
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

// Cross-screen refresh: reload when another screen's op changed our data.
// Skip our own changes (initiator === ctx) — self-initiated refreshes use ankiwebReload.
window.addEventListener("anki-opchanges", (e: Event) => {
  const detail = (e as CustomEvent).detail;
  const flags = detail.flags || {};
  if (detail.initiator !== ctx && (flags.study_queues || flags.deck || flags.card || flags.note)) {
    location.reload();
  }
});

// Night-mode hash convention.
if (location.hash.includes("night")) {
  document.documentElement.classList.add("night-mode");
  document.documentElement.setAttribute("data-bs-theme", "dark");
}

window.addEventListener("load", () => bridge.ready());
