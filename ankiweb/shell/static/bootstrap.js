(() => {
  var __defProp = Object.defineProperty;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

  // shell_src/pycmd_shim.ts
  var Bridge = class {
    constructor(ctx2) {
      this.ctx = ctx2;
      __publicField(this, "ws");
      __publicField(this, "nextId", 1);
      __publicField(this, "cbs", /* @__PURE__ */ new Map());
      __publicField(this, "domDone", false);
      __publicField(this, "queue", []);
      __publicField(this, "calls", {});
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws?context=${ctx2}`);
      this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
      const fn = (arg, cb) => {
        const id = cb ? this.nextId++ : null;
        if (id !== null && cb) this.cbs.set(id, cb);
        this.send({ type: "cmd", id, ctx: this.ctx, arg });
        return false;
      };
      window.pycmd = window.bridgeCommand = fn;
    }
    /** Register named functions the server may invoke via {type:"call"}. */
    registerCalls(map) {
      Object.assign(this.calls, map);
    }
    /** Signal the page is ready; flush queued server messages. */
    ready() {
      this.send({ type: "ready", ctx: this.ctx });
      this.domDone = true;
      for (const m of this.queue) this.handle(m);
      this.queue = [];
    }
    send(obj) {
      if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
      else this.ws.addEventListener("open", () => this.ws.send(JSON.stringify(obj)), { once: true });
    }
    onMessage(msg) {
      if (msg.type === "result" && this.cbs.has(msg.id)) {
        this.cbs.get(msg.id)(msg.value);
        this.cbs.delete(msg.id);
        return;
      }
      if (!this.domDone && (msg.type === "call" || msg.type === "eval")) {
        this.queue.push(msg);
        return;
      }
      this.handle(msg);
    }
    handle(msg) {
      if (msg.type === "call") {
        const f = this.calls[msg.fn];
        const value = f ? f(...msg.args || []) : void 0;
        if (msg.id != null) this.send({ type: "result", id: msg.id, value });
      } else if (msg.type === "eval") {
        const value = (0, eval)(msg.js);
        if (msg.id != null) this.send({ type: "result", id: msg.id, value });
      } else if (msg.type === "opchanges") {
        window.dispatchEvent(new CustomEvent("anki-opchanges", { detail: msg }));
      }
    }
  };

  // shell_src/bootstrap.ts
  var ctx = window.__ankiwebContext || new URLSearchParams(location.search).get("context") || "default";
  var bridge = new Bridge(ctx);
  window.__ankiwebBridge = bridge;
  bridge.registerCalls({
    ankiwebNavigate: (url) => {
      location.href = String(url);
    },
    ankiwebReload: () => {
      location.reload();
    }
  });
  window.ankiwebCreateDeck = () => {
    const name = window.prompt("Deck name:");
    if (name) window.pycmd("create:" + name);
  };
  window.ankiwebImportFile = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.tsv,.txt,.apkg,.zip";
    input.onchange = async () => {
      const f = input.files && input.files[0];
      if (!f) return;
      const fd = new FormData();
      fd.append("file", f);
      const resp = await fetch("/import/upload", { method: "POST", body: fd });
      if (!resp.ok) {
        window.alert("Import failed: " + await resp.text());
        return;
      }
      const { route, path } = await resp.json();
      window.location.href = "/" + route + "/" + encodeURIComponent(path);
    };
    input.click();
  };
  window.addEventListener("anki-opchanges", (e) => {
    const detail = e.detail;
    const flags = detail.flags || {};
    if (detail.initiator === ctx) return;
    const custom = window.__ankiwebOnOpchanges;
    if (typeof custom === "function") {
      custom(detail);
      return;
    }
    if (flags.study_queues || flags.deck || flags.card || flags.note) {
      location.reload();
    }
  });
  if (location.hash.includes("night")) {
    document.documentElement.classList.add("night-mode");
    document.documentElement.setAttribute("data-bs-theme", "dark");
  }
  window.addEventListener("load", () => bridge.ready());
})();
