#!/usr/bin/env python3
"""
Browser chat UI for the Singapore Weather Agent (standard library only, no extra installs).

    python web_app.py              # http://127.0.0.1:8501
    python web_app.py --port 8600

In a browser-based VS Code / Code Editor, open the forwarded port, e.g.
https://<your-editor-host>/ports/8501/  (or /proxy/8501/, depending on the editor)

Each browser tab is a separate conversation. Toggles choose local tools vs the AgentCore
Gateway and whether the Bedrock Guardrail is attached (both need `python infra.py deploy`).

Location guardrail: the agent can use your current location, but every lookup needs your
confirmation in the page first (see location_guardrail.py).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from location_guardrail import LOCATION_INSTRUCTIONS, LocationConsent, make_location_tool
from weather_agent import DEFAULT_PROMPT, base_tool_name, open_agent

HERE = Path(__file__).resolve().parent
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()
MAX_SESSIONS = 200

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Singapore Weather Agent</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🌦️</text></svg>">
<style>
 /* Palette: Singapore red (flag, #EF3340), white, and M1 Sunshine (#FFB81C). Change --red / --sun to retune. */
 :root{--red:#EF3340;--red-deep:#C8102E;--sun:#FFB81C;--sun-soft:#FFF4D6;
   --bg:#FFFFFF;--card:#FFFFFF;--ink:#2B1A1C;--muted:#7A5F62;--accent:var(--red);--accent-ink:#fff;--line:#F1DEDF;--warn:#B54708;
   --user:#FDE8EA;--user-line:#F7C3C8;--chip:#fff;--th:var(--sun-soft);
   --sky:linear-gradient(135deg,var(--red-deep) 0%,var(--red) 60%,#F4683A 85%,var(--sun) 100%)}
 @media (prefers-color-scheme:dark){:root{--bg:#1A1214;--card:#251A1C;--ink:#F6ECEC;--muted:#C2A6A9;--line:#3D2A2D;--warn:#FFB81C;
   --user:#3E1C21;--user-line:#5E2A31;--chip:#2D2022;--th:#3A2E1A;--sun-soft:#3A2E1A;
   --sky:linear-gradient(135deg,#7E0F1F 0%,#B3172E 60%,#C2532D 85%,#C98A12 100%)}}
 *{box-sizing:border-box} body{margin:0;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
 header{position:relative;overflow:hidden;background:var(--sky);color:#fff;padding:16px 20px 64px}
 .bar{position:relative;z-index:1;max-width:900px;margin:0 auto;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 header h1{font-size:20px;margin:0;flex:1;letter-spacing:.2px;text-shadow:0 1px 2px rgba(0,0,0,.25)}
 header h1 small{display:block;font-weight:400;font-size:13px;opacity:.9}
 .sun{position:absolute;right:9%;top:-30px;width:120px;height:120px;border-radius:50%;background:radial-gradient(circle,#FFE7A3 0%,var(--sun) 45%,rgba(255,184,28,0) 70%);opacity:.95}
 .skyline{position:absolute;left:0;right:0;bottom:0;width:100%;height:78px;color:rgba(255,255,255,.32)}
 .toggle{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:5px 12px;font-size:13px;display:flex;gap:6px;align-items:center;cursor:pointer;backdrop-filter:blur(4px)}
 .toggle input{accent-color:var(--sun);margin:0}
 #reset{background:#fff;color:var(--red-deep);border-radius:999px;padding:6px 14px;font-weight:600}
 #log{max-width:900px;margin:-36px auto 0;padding:0 16px 170px;position:relative;z-index:2}
 .row-msg{display:flex;gap:10px;align-items:flex-start;margin:12px 0}
 .row-msg.user{flex-direction:row-reverse}
 .avatar{flex:none;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-size:19px;background:var(--card);border:1px solid var(--line);box-shadow:0 1px 3px rgba(120,20,30,.10)}
 .bot .avatar{background:var(--sun);border-color:var(--sun)} .user .avatar{background:var(--accent);border-color:var(--accent)}
 .msg{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--sun);border-radius:14px;padding:12px 15px;max-width:calc(100% - 46px);box-shadow:0 2px 8px rgba(120,20,30,.07)}
 .bot .msg{border-top-left-radius:4px} .user .msg{background:var(--user);border-color:var(--user-line);border-left-width:1px;border-top-right-radius:4px;max-width:80%}
 .welcome h2{margin:0 0 4px;font-size:18px} .tiles{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 2px}
 .tile{flex:1 1 150px;background:var(--sun-soft);border:1px solid rgba(255,184,28,.45);border-radius:10px;padding:8px 10px;font-size:13px} .tile b{display:block;font-size:20px;line-height:1.2}
 .meta{color:var(--muted);font-size:12px;margin-top:8px;border-top:1px dashed var(--line);padding-top:6px}
 .blocked{color:var(--warn);font-weight:600}
 table{border-collapse:separate;border-spacing:0;margin:8px 0;font-size:14px;border:1px solid var(--line);border-radius:10px;overflow:hidden}
 td,th{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left} tr:last-child td{border-bottom:0}
 th{background:var(--th);font-weight:600} tr:nth-child(odd) td{background:rgba(239,51,64,.035)}
 h3,h4{margin:12px 0 4px} ul{margin:4px 0 4px 20px;padding:0} p{margin:6px 0} code{background:var(--th);padding:1px 5px;border-radius:5px}
 .band{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:700;color:#fff}
 .b-good{background:#2e9e5b}.b-moderate{background:#2f80c8}.b-unhealthy{background:#e0a100;color:#1d1d1d}.b-very{background:#d4452c}.b-hazardous{background:#7b2d8b}
 .typing .dots::after{content:'';animation:dots 1.2s steps(4) infinite} @keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
 form{position:fixed;bottom:0;left:0;right:0;background:color-mix(in srgb,var(--card) 92%,transparent);backdrop-filter:blur(8px);border-top:1px solid var(--line);padding:12px;z-index:3}
 .row{max-width:900px;margin:0 auto;display:flex;gap:8px}
 textarea{flex:1;resize:none;height:52px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font:inherit;background:var(--card);color:var(--ink)}
 textarea:focus{outline:2px solid var(--sun);outline-offset:0;border-color:transparent}
 button{background:var(--accent);color:var(--accent-ink);border:0;border-radius:12px;padding:0 20px;font:inherit;font-weight:600;cursor:pointer;transition:transform .1s,filter .1s}
 button:hover{filter:brightness(1.07)} button:active{transform:scale(.97)} button:disabled{opacity:.5;cursor:wait}
 .chips{max-width:900px;margin:0 auto 8px;display:flex;gap:6px;flex-wrap:wrap}
 .chip{background:var(--chip);color:var(--ink);border:1px solid var(--line);padding:5px 12px;font-size:13px;font-weight:500;border-radius:999px}
 .chip:hover{border-color:var(--sun);background:var(--sun-soft);filter:none}
 .consent{margin-top:10px;padding:12px;border:1px solid var(--sun);background:var(--sun-soft);border-radius:12px}
 .consent b{display:block;margin-bottom:4px} .consent small{color:var(--muted);display:block;margin:4px 0 8px}
 .consent button{padding:7px 14px;margin-right:6px} .consent .no{background:var(--chip);color:var(--ink);border:1px solid var(--line)}
</style></head><body>
<header>
 <div class="sun"></div>
 <svg class="skyline" viewBox="0 0 1200 100" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
  <g fill="currentColor">
   <rect x="20" y="52" width="34" height="48"/><rect x="60" y="30" width="26" height="70"/><rect x="92" y="44" width="40" height="56"/>
   <rect x="140" y="18" width="30" height="82"/><rect x="176" y="38" width="24" height="62"/><rect x="206" y="8" width="34" height="92"/>
   <rect x="246" y="28" width="28" height="72"/><rect x="280" y="48" width="44" height="52"/><rect x="330" y="22" width="22" height="78"/>
   <rect x="358" y="36" width="36" height="64"/><rect x="400" y="56" width="50" height="44"/>
   <path d="M470 100 L452 72 L488 72 Z"/><rect x="465" y="72" width="10" height="28"/>
   <polygon points="560,100 566,30 588,30 590,100"/><polygon points="610,100 614,30 636,30 640,100"/><polygon points="660,100 662,30 684,30 690,100"/>
   <path d="M548 24 H712 Q722 24 724 30 H548 Z"/>
   <path d="M1010 100 L1000 56 Q1015 46 1030 56 L1020 100 Z"/><path d="M1060 100 L1046 44 Q1066 32 1086 44 L1072 100 Z"/>
   <path d="M1112 100 L1104 62 Q1116 54 1128 62 L1120 100 Z"/><rect x="1140" y="50" width="30" height="50"/>
   <rect x="0" y="96" width="1200" height="4" opacity=".6"/>
  </g>
  <g fill="none" stroke="currentColor" stroke-width="3">
   <circle cx="860" cy="48" r="38"/><path d="M860 10 V86 M822 48 H898 M833 21 L887 75 M887 21 L833 75"/>
   <path d="M846 100 L860 86 L874 100" stroke-width="5"/>
  </g>
 </svg>
 <div class="bar">
  <h1>🇸🇬 Singapore Weather Agent<small>⛅ NEA forecasts · ☔ 2-hour nowcast · 😷 haze (PSI / PM2.5)</small></h1>
  <label class="toggle"><input type="checkbox" id="gateway" __GW__> 🔌 AgentCore Gateway</label>
  <label class="toggle"><input type="checkbox" id="guardrail" __GR__> 🛡️ Bedrock Guardrail</label>
  <button type="button" id="reset">✨ New chat</button>
 </div>
</header>
<div id="log"></div>
<form id="f"><div class="chips">
 <button type="button" class="chip" data-q="Weather and haze across Singapore today?">🌏 Weather and haze across Singapore today?</button>
 <button type="button" class="chip" data-q="Will it rain in Tampines in the next 2 hours?">☔ Will it rain in Tampines in the next 2 hours?</button>
 <button type="button" class="chip" data-q="4-day outlook">📅 4-day outlook</button>
 <button type="button" class="chip" data-q="Is it okay to jog in Jurong this evening?">🏃 Is it okay to jog in Jurong this evening?</button>
 <button type="button" class="chip" data-q="What are the PSI and PM2.5 readings right now?">😷 PSI &amp; PM2.5 right now</button>
 <button type="button" class="chip" data-q="What's the weather like near me right now?">📍 Weather near me</button></div>
 <div class="row"><textarea id="q" placeholder="Ask about Singapore weather or haze… 🌤️"></textarea><button id="send">Send ➤</button></div></form>
<script>
let sid = crypto.randomUUID ? crypto.randomUUID() : String(Math.random());
const log = document.getElementById('log'), q = document.getElementById('q'), send = document.getElementById('send');
const WELCOME = `<div class="welcome"><h2>Selamat datang! 👋</h2>
 Ask me about Singapore weather forecasts, the 2-hour nowcast for your town, the 4-day outlook, or haze.
 <div class="tiles"><div class="tile"><b>⛈️</b>2-hour nowcast by town</div><div class="tile"><b>📅</b>24-hour &amp; 4-day outlook</div>
 <div class="tile"><b>😷</b>PSI &amp; PM2.5 by region</div><div class="tile"><b>📍</b>Near you (asks first)</div></div>__NOTE__</div>`;
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/\*(.+?)\*/g,'<i>$1</i>').replace(/`(.+?)`/g,'<code>$1</code>');
// Weather icons for short table cells that name an NEA forecast; first match wins.
const WX = [[/thunder/i,'⛈️'],[/heavy (rain|shower)/i,'🌧️'],[/shower|light rain|drizzle/i,'🌦️'],[/rain/i,'🌧️'],[/haz[ey]|mist|fog|smok/i,'🌫️'],
  [/partly cloudy/i,'⛅'],[/cloudy|overcast/i,'☁️'],[/fair|sunny|clear/i,'☀️'],[/wind/i,'🌬️']];
const BANDS = [[/\bhazardous\b/i,'hazardous'],[/\bvery unhealthy\b/i,'very'],[/\bunhealthy\b/i,'unhealthy'],[/\bmoderate\b(?!\s+(rain|shower))/i,'moderate'],[/\bgood\b/i,'good']];
function cell(html){
  const text = html.replace(/<[^>]+>/g,'');
  if (text.length > 40) return html;
  for (const [re, cls] of BANDS) if (re.test(text) && !/rain|shower/i.test(text)) return html.replace(re, m => '<span class="band b-'+cls+'">'+m+'</span>');
  if (/^\p{Extended_Pictographic}/u.test(text)) return html;
  for (const [re, e] of WX) if (re.test(text)) return e + ' ' + html;
  return html;
}
function md(text){ // small markdown subset: headings, tables, lists, bold, paragraphs
  const lines = text.split('\n'); let out = '', i = 0;
  while (i < lines.length){
    const l = lines[i];
    if (/^\s*\|/.test(l) && i+1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i+1])){
      const cells = r => r.trim().replace(/^\||\|$/g,'').split('|').map(c => inline(c.trim()));
      out += '<table><tr>' + cells(l).map(c=>'<th>'+c+'</th>').join('') + '</tr>'; i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) { out += '<tr>' + cells(lines[i]).map(c=>'<td>'+cell(c)+'</td>').join('') + '</tr>'; i++; }
      out += '</table>'; continue;
    }
    if (/^\s*[-*] /.test(l)){ out += '<ul>'; while (i < lines.length && /^\s*[-*] /.test(lines[i])) { out += '<li>'+inline(lines[i].replace(/^\s*[-*] /,''))+'</li>'; i++; } out += '</ul>'; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)/); if (h){ out += '<h4>'+inline(h[2])+'</h4>'; i++; continue; }
    if (l.trim()) out += '<p>'+inline(l)+'</p>'; i++;
  }
  return out;
}
function add(cls, html){
  const row = document.createElement('div'); row.className = 'row-msg ' + (cls === 'user' ? 'user' : 'bot');
  row.innerHTML = '<div class="avatar">' + (cls === 'user' ? '🙂' : '🌦️') + '</div><div class="msg"></div>';
  const d = row.lastChild; d.innerHTML = html; log.appendChild(row); row.scrollIntoView({behavior:'smooth', block:'end'}); return d;
}
async function ask(text){
  if (!text.trim()) return; add('user', esc(text)); q.value = ''; send.disabled = true;
  const pending = add('', '<span class="meta typing" style="border:0;padding:0">🛰️ Checking NEA data<span class="dots"></span></span>');
  try {
    const r = await fetch('api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({
      session_id: sid, message: text, gateway: document.getElementById('gateway').checked, guardrail: document.getElementById('guardrail').checked})});
    const j = await r.json();
    if (j.error) { pending.innerHTML = '<span class="blocked">⚠️ Error: ' + esc(j.error) + '</span>'; }
    else {
      pending.innerHTML = md(j.answer) + '<div class="meta">' + (j.guardrail_intervened ? '<span class="blocked">🛡️ Guardrail intervened · </span>' : '') +
        (j.tools.length ? '🔧 ' + j.tools.join(', ') : '💬 No tools called') + ' · ' + (j.mode.startsWith('Gateway') ? '🔌 ' : '💻 ') + j.mode + ' · ⏱️ ' + j.latency_s + 's</div>';
      if (j.location_request) consentCard(pending);
    }
  } catch (e) { pending.innerHTML = '<span class="blocked">⚠️ Request failed: ' + esc(String(e)) + '</span>'; }
  send.disabled = false; q.focus();
}
// Location guardrail: nothing leaves the browser until the user clicks Allow on this card.
function consentCard(bubble){
  const c = document.createElement('div'); c.className = 'consent';
  c.innerHTML = '<b>📍 Allow the agent to use your current location?</b><small>Used once for this answer, matched to the nearest NEA town. ' +
    'Your coordinates are not shown to the AI model or stored.</small><button class="yes">Allow once</button><button class="no">Don\'t allow</button>';
  bubble.appendChild(c);
  const done = msg => { c.innerHTML = '<small>' + msg + '</small>'; };
  const decide = async body => (await fetch('api/location', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid, ...body})})).json();
  c.querySelector('.no').onclick = async () => { done('🚫 Location not shared.'); await decide({decision:'deny'}); ask("No, don't use my location."); };
  c.querySelector('.yes').onclick = () => {
    if (!navigator.geolocation) { done('⚠️ This browser can\'t share location.'); decide({decision:'deny'}).then(() => ask('My browser could not share my location.')); return; }
    done('📡 Getting your location…');
    navigator.geolocation.getCurrentPosition(async p => {
      const r = await decide({decision:'allow', latitude: p.coords.latitude, longitude: p.coords.longitude});
      if (!r.ok) { done('⚠️ ' + esc(r.error || 'This request has expired.')); return; }
      done('✅ Location shared once.'); ask('Yes, use my current location.');
    }, async err => { done('⚠️ Location unavailable: ' + esc(err.message)); await decide({decision:'deny'}); ask('My browser could not share my location.'); },
    {enableHighAccuracy:false, timeout:15000, maximumAge:60000});
  };
}
document.getElementById('f').onsubmit = e => { e.preventDefault(); ask(q.value); };
q.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(q.value); } };
document.querySelectorAll('.chip').forEach(b => b.onclick = () => ask(b.dataset.q || b.textContent));
document.getElementById('reset').onclick = () => { sid = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()); log.innerHTML = ''; add('', '✨ New chat started. What would you like to know?'); };
add('', WELCOME);
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
        sess = get_session(session_id, mode)
        if sess["mode"] != mode:  # switching modes starts a fresh conversation (tool names differ)
            sess.update(messages=[], mode=mode)
            sess["consent"].reset()
    with sess["lock"]:
        variant = {"prompt": DEFAULT_PROMPT, "tools": "gateway" if gateway else "local", "guardrail": guardrail}
        consent: LocationConsent = sess["consent"]
        with open_agent(variant, extra_tools=[make_location_tool(consent)],
                        extra_instructions=LOCATION_INSTRUCTIONS) as agent:
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
            "location_request": consent.pending,  # the UI shows the Allow / Don't allow prompt
        }


def get_session(session_id: str, mode: str = "local tools") -> dict:
    """Caller holds SESSIONS_LOCK."""
    return SESSIONS.setdefault(session_id, {"messages": [], "lock": threading.Lock(), "mode": mode,
                                            "consent": LocationConsent()})


def location_decision(session_id: str, req: dict) -> dict:
    """The user's answer to a pending location request. Rejected unless the agent asked."""
    with SESSIONS_LOCK:
        sess = SESSIONS.get(session_id)
    if sess is None or not sess["consent"].pending:
        return {"ok": False, "error": "No location request is waiting for confirmation."}
    if req.get("decision") == "allow":
        ok = sess["consent"].grant(req.get("latitude"), req.get("longitude"))
    else:
        ok = sess["consent"].deny()
    return {"ok": ok}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        # Works behind path-prefix proxies (e.g. /ports/8501/ or /proxy/8501/), with or without prefix stripping.
        path = self.path.split("?", 1)[0]
        if path.endswith("healthz"):
            self._send(200, b'{"ok": true}', "application/json")
            return
        if not path.endswith("/") and not path.endswith(".html"):
            # Relative redirect so the page's relative 'api/chat' URL resolves under the same prefix.
            self.send_response(301)
            self.send_header("Location", path.rsplit("/", 1)[-1] + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        on = infra_available()
        page = (PAGE.replace("__GW__", "checked" if on else "")
                .replace("__GR__", "checked" if on else "")
                .replace("__NOTE__", "" if on else "<br><i>Gateway/Guardrail not deployed, so local tools are used.</i>"))
        self._send(200, page.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if not (path.endswith("api/chat") or path.endswith("api/location")):
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 20_000:
                raise ValueError("message too long")
            req = json.loads(self.rfile.read(length) or b"{}")
            if path.endswith("api/location"):
                out = location_decision(str(req.get("session_id", "")), req)
                self._send(200, json.dumps(out).encode(), "application/json")
                return
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
        if args and "api/" in str(args[0]):
            print(f"{self.address_string()} {args[0]} -> {args[1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Singapore Weather Agent UI on http://{args.host}:{args.port}/")
    print(f"In a browser-based editor, open: https://<your-editor-host>/ports/{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
