#!/usr/bin/env python3
"""
Browser chat UI for the Singapore Weather Agent (standard library only, no extra installs).

    python web_app.py              # http://127.0.0.1:8501
    python web_app.py --port 8600

In a browser-based VS Code / Code Editor, open the forwarded port, usually
https://<your-editor-host>/proxy/8501/ (the trailing slash matters).

Each browser tab is a separate conversation. Toggles choose local tools vs the AgentCore
Gateway and whether the Bedrock Guardrail is attached (both need `python infra.py deploy`).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from weather_agent import DEFAULT_PROMPT, base_tool_name, open_agent

HERE = Path(__file__).resolve().parent
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()
MAX_SESSIONS = 200

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Singapore Weather Agent</title>
<style>
 :root{--bg:#f6f7f9;--card:#fff;--ink:#1d2433;--muted:#667085;--accent:#0b6bcb;--line:#e4e7ec;--warn:#b54708}
 *{box-sizing:border-box} body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
 header{padding:14px 20px;background:var(--card);border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 header h1{font-size:17px;margin:0;flex:1} label{color:var(--muted);font-size:13px;display:flex;gap:6px;align-items:center}
 #log{max-width:860px;margin:0 auto;padding:20px 16px 140px}
 .msg{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
 .user{background:#eaf2fb;border-color:#cfe0f5;margin-left:15%} .meta{color:var(--muted);font-size:12px;margin-top:8px}
 .blocked{color:var(--warn)} table{border-collapse:collapse;margin:8px 0;font-size:14px} td,th{border:1px solid var(--line);padding:4px 8px;text-align:left}
 th{background:#f2f4f7} h3,h4{margin:10px 0 4px} ul{margin:4px 0 4px 18px;padding:0} p{margin:6px 0}
 form{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:12px}
 .row{max-width:860px;margin:0 auto;display:flex;gap:8px} textarea{flex:1;resize:none;height:52px;padding:10px;border:1px solid var(--line);border-radius:8px;font:inherit}
 button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:0 18px;font:inherit;cursor:pointer} button:disabled{opacity:.5}
 .chips{max-width:860px;margin:0 auto 8px;display:flex;gap:6px;flex-wrap:wrap} .chip{background:#f2f4f7;color:var(--ink);padding:4px 10px;font-size:13px;border-radius:14px}
</style></head><body>
<header><h1>🌦️ Singapore Weather Agent <span style="color:var(--muted);font-weight:400;font-size:13px">NEA forecasts &amp; haze</span></h1>
 <label><input type="checkbox" id="gateway" __GW__> AgentCore Gateway</label>
 <label><input type="checkbox" id="guardrail" __GR__> Bedrock Guardrail</label>
 <button type="button" id="reset" style="background:#f2f4f7;color:var(--ink);padding:6px 12px">New chat</button></header>
<div id="log"><div class="msg">Hi! Ask me about Singapore weather forecasts, the 2-hour nowcast for your town, the 4-day outlook, or haze (PSI / PM2.5). __NOTE__</div></div>
<form id="f"><div class="chips">
 <button type="button" class="chip">Weather and haze across Singapore today?</button>
 <button type="button" class="chip">Will it rain in Tampines in the next 2 hours?</button>
 <button type="button" class="chip">4-day outlook</button>
 <button type="button" class="chip">Is it okay to jog in Jurong this evening?</button></div>
 <div class="row"><textarea id="q" placeholder="Ask about Singapore weather or haze…"></textarea><button id="send">Send</button></div></form>
<script>
let sid = crypto.randomUUID ? crypto.randomUUID() : String(Math.random());
const log = document.getElementById('log'), q = document.getElementById('q'), send = document.getElementById('send');
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/\*(.+?)\*/g,'<i>$1</i>').replace(/`(.+?)`/g,'<code>$1</code>');
function md(text){ // small markdown subset: headings, tables, lists, bold, paragraphs
  const lines = text.split('\n'); let out = '', i = 0;
  while (i < lines.length){
    const l = lines[i];
    if (/^\s*\|/.test(l) && i+1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i+1])){
      const cells = r => r.trim().replace(/^\||\|$/g,'').split('|').map(c => inline(c.trim()));
      out += '<table><tr>' + cells(l).map(c=>'<th>'+c+'</th>').join('') + '</tr>'; i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) { out += '<tr>' + cells(lines[i]).map(c=>'<td>'+c+'</td>').join('') + '</tr>'; i++; }
      out += '</table>'; continue;
    }
    if (/^\s*[-*] /.test(l)){ out += '<ul>'; while (i < lines.length && /^\s*[-*] /.test(lines[i])) { out += '<li>'+inline(lines[i].replace(/^\s*[-*] /,''))+'</li>'; i++; } out += '</ul>'; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)/); if (h){ out += '<h4>'+inline(h[2])+'</h4>'; i++; continue; }
    if (l.trim()) out += '<p>'+inline(l)+'</p>'; i++;
  }
  return out;
}
function add(cls, html){ const d = document.createElement('div'); d.className = 'msg ' + cls; d.innerHTML = html; log.appendChild(d); d.scrollIntoView({behavior:'smooth', block:'end'}); return d; }
async function ask(text){
  if (!text.trim()) return; add('user', esc(text)); q.value = ''; send.disabled = true;
  const pending = add('', '<span class="meta">Checking NEA data…</span>');
  try {
    const r = await fetch('api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
      session_id: sid, message: text, gateway: document.getElementById('gateway').checked, guardrail: document.getElementById('guardrail').checked})});
    const j = await r.json();
    if (j.error) { pending.innerHTML = '<span class="blocked">Error: ' + esc(j.error) + '</span>'; }
    else {
      pending.innerHTML = md(j.answer) + '<div class="meta">' + (j.guardrail_intervened ? '<span class="blocked">🛡️ Guardrail intervened · </span>' : '') +
        (j.tools.length ? 'Tools: ' + j.tools.join(', ') : 'No tools called') + ' · ' + j.mode + ' · ' + j.latency_s + 's</div>';
    }
  } catch (e) { pending.innerHTML = '<span class="blocked">Request failed: ' + esc(String(e)) + '</span>'; }
  send.disabled = false; q.focus();
}
document.getElementById('f').onsubmit = e => { e.preventDefault(); ask(q.value); };
q.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(q.value); } };
document.querySelectorAll('.chip').forEach(b => b.onclick = () => ask(b.textContent));
document.getElementById('reset').onclick = () => { sid = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()); log.innerHTML = ''; add('', 'New chat started.'); };
</script></body></html>"""


def infra_available() -> bool:
    return (HERE / "infra_state.json").exists()


def chat(session_id: str, message: str, gateway: bool, guardrail: bool) -> dict:
    if (gateway or guardrail) and not infra_available():
        return {"error": "Gateway/Guardrail aren't deployed. Untick them, or run `python infra.py deploy`."}
    mode = ("Gateway" if gateway else "local tools") + (" + Guardrail" if guardrail else "")
    with SESSIONS_LOCK:
        if len(SESSIONS) > MAX_SESSIONS:
            SESSIONS.pop(next(iter(SESSIONS)))
        sess = SESSIONS.setdefault(session_id, {"messages": [], "lock": threading.Lock(), "mode": mode})
        if sess["mode"] != mode:  # switching modes starts a fresh conversation (tool names differ)
            sess.update(messages=[], mode=mode)
    with sess["lock"]:
        variant = {"prompt": DEFAULT_PROMPT, "tools": "gateway" if gateway else "local", "guardrail": guardrail}
        with open_agent(variant) as agent:
            agent.messages = sess["messages"]
            t0 = time.time()
            result = agent(message)
            latency = round(time.time() - t0, 1)
            sess["messages"] = agent.messages
        return {
            "answer": str(result).strip(),
            "tools": sorted({base_tool_name(t) for t in result.metrics.tool_metrics}),
            "guardrail_intervened": result.stop_reason == "guardrail_intervened",
            "latency_s": latency,
            "mode": mode,
        }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/index.html") or path.endswith("/index.html"):
            on = infra_available()
            page = (PAGE.replace("__GW__", "checked" if on else "")
                    .replace("__GR__", "checked" if on else "")
                    .replace("__NOTE__", "" if on else "<br><i>Gateway/Guardrail not deployed, so local tools are used.</i>"))
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif path.endswith("/healthz") or path == "/healthz":
            self._send(200, b'{"ok": true}', "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if not self.path.split("?", 1)[0].endswith("api/chat"):
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 20_000:
                raise ValueError("message too long")
            req = json.loads(self.rfile.read(length) or b"{}")
            message = str(req.get("message", "")).strip()[:2000]
            if not message:
                raise ValueError("empty message")
            out = chat(str(req.get("session_id") or uuid.uuid4()), message,
                       bool(req.get("gateway")), bool(req.get("guardrail")))
            self._send(200, json.dumps(out, ensure_ascii=False).encode(), "application/json")
        except Exception as e:
            print(f"chat error: {type(e).__name__}: {e}")
            self._send(200, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")

    def log_message(self, fmt: str, *args) -> None:  # quieter logs
        if "api/chat" in (args[0] if args else ""):
            print(f"{self.address_string()} {args[0]} -> {args[1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Singapore Weather Agent UI on http://{args.host}:{args.port}/")
    print(f"In a browser-based editor, open: https://<your-editor-host>/proxy/{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
