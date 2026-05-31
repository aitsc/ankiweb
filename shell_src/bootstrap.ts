import { Bridge } from "./pycmd_shim";

const ctx = new URLSearchParams(location.search).get("context") || "default";
const bridge = new Bridge(ctx);
(window as any).__ankiwebBridge = bridge;

// Night-mode hash convention (nightmode.ts:6-13)
if (location.hash.includes("night")) {
  document.documentElement.classList.add("night-mode");
  document.documentElement.setAttribute("data-bs-theme", "dark");
}

// Fire ready after the page's own scripts have a chance to register globals.
window.addEventListener("load", () => bridge.ready());
