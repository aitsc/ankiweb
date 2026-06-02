// Replaces Qt's QWebChannel-injected pycmd/bridgeCommand with a WebSocket shim.
type Cb = (value: unknown) => void;

export class Bridge {
  private ws: WebSocket;
  private nextId = 1;
  private cbs = new Map<number, Cb>();
  private domDone = false;
  private queue: object[] = [];
  private calls: Record<string, (...args: unknown[]) => unknown> = {};

  constructor(private ctx: string) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws?context=${ctx}`);
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
    // expose pycmd/bridgeCommand globally, identical functions (webview.py:92)
    const fn = (arg: string, cb?: Cb) => {
      const id = cb ? this.nextId++ : null;
      if (id !== null && cb) this.cbs.set(id, cb);
      this.send({ type: "cmd", id, ctx: this.ctx, arg });
      return false;
    };
    (window as any).pycmd = (window as any).bridgeCommand = fn;
  }

  /** Register named functions the server may invoke via {type:"call"}. */
  registerCalls(map: Record<string, (...args: unknown[]) => unknown>) {
    Object.assign(this.calls, map);
  }

  /** Signal the page is ready; flush queued server messages. */
  ready() {
    this.send({ type: "ready", ctx: this.ctx });
    this.domDone = true;
    for (const m of this.queue) this.handle(m as any);
    this.queue = [];
  }

  private send(obj: object) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
    else this.ws.addEventListener("open", () => this.ws.send(JSON.stringify(obj)), { once: true });
  }

  private onMessage(msg: any) {
    if (msg.type === "result" && this.cbs.has(msg.id)) {
      this.cbs.get(msg.id)!(msg.value);
      this.cbs.delete(msg.id);
      return;
    }
    // buffer eval/call until the page is ready (domDone queue, webview.py:752-767)
    if (!this.domDone && (msg.type === "call" || msg.type === "eval")) {
      this.queue.push(msg);
      return;
    }
    this.handle(msg);
  }

  private handle(msg: any) {
    if (msg.type === "call") {
      // Resolve against registerCalls first, then fall back to a global window.<fn>
      // (screens like preferences/custom-study/filtered-deck define their error callbacks
      // as window.ankiweb*Error rather than registering them).
      const f = this.calls[msg.fn] || (window as any)[msg.fn];
      const value = typeof f === "function" ? f(...(msg.args || [])) : undefined;
      if (msg.id != null) this.send({ type: "result", id: msg.id, value });
    } else if (msg.type === "eval") {
      // eslint-disable-next-line no-eval
      const value = (0, eval)(msg.js);
      if (msg.id != null) this.send({ type: "result", id: msg.id, value });
    } else if (msg.type === "opchanges") {
      window.dispatchEvent(new CustomEvent("anki-opchanges", { detail: msg }));
    }
  }
}
