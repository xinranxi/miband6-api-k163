"""
Local web dashboard.

`miband6 serve` starts a small HTTP server. Open the page in a browser:
- if you have the pairing key, enter MAC + key and click "connect" — the
  server (which has BLE access) fetches the data and draws the dashboard;
- if you don't, the "how to get the key" panel explains how, and can try
  to pull it from a USB-connected phone over adb.

Browsers can't talk to BLE directly, so the Python process is the backend.
"""
import asyncio
import datetime
import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import dashboard


CONTROL_CSS = r"""
  .panel{background:rgba(255,255,255,.05);border:1px solid var(--line);
    border-radius:18px;padding:26px 28px;max-width:760px;margin:30px auto}
  .panel h2{font-size:18px;margin-bottom:6px}
  .panel .hint{color:var(--dim);font-size:13px;margin-bottom:20px}
  .field{display:flex;align-items:center;gap:14px;margin-bottom:16px}
  .field label{width:112px;color:var(--dim);font-size:14px;flex:none}
  .field input{flex:1;background:rgba(0,0,0,.35);border:1px solid var(--line);
    border-radius:10px;padding:11px 14px;color:var(--txt);font-size:14px;outline:none}
  .field input:focus{border-color:var(--cyan);box-shadow:0 0 0 2px rgba(34,224,255,.15)}
  .btn{background:linear-gradient(90deg,#22e0ff,#39ff88);color:#04121f;border:none;
    border-radius:11px;padding:12px 26px;font-size:15px;font-weight:700;cursor:pointer}
  .btn:disabled{opacity:.5;cursor:not-allowed}
  .btn.ghost{background:transparent;border:1px solid var(--line);color:var(--cyan);
    font-weight:500;padding:8px 16px;font-size:13px}
  .status{margin-top:16px;font-size:14px;min-height:20px}
  .status.err{color:var(--pink)} .status.ok{color:var(--green)}
  .help{margin-top:18px;border-top:1px dashed var(--line);padding-top:16px;
    color:var(--dim);font-size:13px;line-height:1.9;display:none}
  .help code{background:rgba(0,0,0,.4);padding:2px 7px;border-radius:6px;color:var(--cyan);
    font-size:12px}
  .help ol{margin-left:18px}
  .spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);
    border-top-color:var(--cyan);border-radius:50%;animation:sp .8s linear infinite;
    vertical-align:-2px;margin-right:8px}
  @keyframes sp{to{transform:rotate(360deg)}}
  .quick{display:flex;gap:8px;flex-wrap:wrap}
  .qbtn{background:rgba(255,255,255,.06);border:1px solid var(--line);color:var(--dim);
    border-radius:9px;padding:8px 14px;font-size:13px;cursor:pointer}
  .qbtn.active{background:rgba(34,224,255,.15);border-color:var(--cyan);color:var(--cyan)}
  input[type=date]{color-scheme:dark}
"""

PAGE_JS = r"""
function status(msg, cls){
  const el=document.getElementById('status');
  el.className='status '+(cls||''); el.innerHTML=msg;
}
function toggleHelp(force){
  const h=document.getElementById('help');
  const show = force===true ? true : h.style.display!=='block';
  h.style.display = show?'block':'none';
}
async function scanDevices(){
  status('<span class="spin"></span>正在扫描附近蓝牙设备（约 10 秒）…');
  try{
    const r=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const j=await r.json();
    if(!j.ok) throw new Error(j.error||'扫描失败');
    if(!j.devices.length){ status('未发现手环，请确认手环在附近且已开机','err'); return; }
    const sel=document.getElementById('macSel');
    sel.innerHTML=j.devices.map(d=>`<option value="${d.address}">${(d.name||'未知设备')} — ${d.address} (${d.rssi}dBm)</option>`).join('');
    document.getElementById('selWrap').style.display='flex';
    pickDevice(j.devices[0].address);
    status('发现 '+j.devices.length+' 个设备','ok');
  }catch(e){ status('扫描失败：'+e.message,'err'); }
}
function pickDevice(addr){ document.getElementById('mac').value=addr; }

let selDays = 3;
document.querySelectorAll('.qbtn').forEach(function(b){
  b.addEventListener('click', function(){
    document.querySelectorAll('.qbtn').forEach(function(x){ x.classList.remove('active'); });
    b.classList.add('active');
    selDays = parseInt(b.dataset.days);
    document.getElementById('since').value = '';
  });
});
document.getElementById('since').addEventListener('change', function(){
  if (this.value) document.querySelectorAll('.qbtn').forEach(function(x){ x.classList.remove('active'); });
});
async function extractKey(){
  status('<span class="spin"></span>正在从已连接的手机提取密钥…');
  try{
    const r=await fetch('/api/extract_key',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const j=await r.json();
    if(j.ok && j.key){ document.getElementById('key').value=j.key; status('已自动填入密钥 ✓','ok'); }
    else{ status('自动提取失败：'+(j.error||'未知')+' —— 请按下面手动获取','err'); toggleHelp(true); }
  }catch(e){ status('自动提取失败：'+e.message,'err'); }
}
async function connect(){
  const mac=document.getElementById('mac').value.trim();
  const key=document.getElementById('key').value.trim();
  const sinceVal=document.getElementById('since').value;
  if(!mac){ status('请先点击「扫描」发现手环','err'); return; }
  if(!key){ status('还没有配对密钥，请先获取 ↓','err'); toggleHelp(true); return; }
  if(!/^[0-9a-fA-F]{32}$/.test(key)){ status('配对密钥应为 32 位十六进制','err'); return; }
  const btn=document.getElementById('btn'); btn.disabled=true;
  status('<span class="spin"></span>正在连接手环并拉取数据，约需 20–30 秒，请勿关闭页面…');
  try{
    const r=await fetch('/api/fetch',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mac,key,days:selDays,since:sinceVal||null})});
    const j=await r.json();
    if(!j.ok) throw new Error(j.error||'拉取失败');
    document.getElementById('control').style.display='none';
    document.getElementById('dash').style.display='block';
    renderDashboard(j.agg);
    window.scrollTo(0,0);
  }catch(e){ status('失败：'+e.message,'err'); }
  finally{ btn.disabled=false; }
}
"""


def build_page():
    return """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>小米手环6 · 数据大屏</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>%s%s</style></head>
<body>
  <header><div><h1>小米手环6 · 数据大屏</h1>
    <div class="sub" id="dash_range">PC 蓝牙直连手环 · 本地采集</div></div>
    <div class="badge">miband6-pc</div></header>

  <section id="control" class="panel">
    <h2>连接手环</h2>
    <div class="hint">填写手环 MAC 与配对密钥，直接从手环拉取数据（不经过手机 App）。</div>
    <div class="field"><label>手环</label>
      <input id="mac" placeholder="点击右侧「扫描」发现附近手环" readonly>
      <button class="btn ghost" onclick="scanDevices()">扫描</button></div>
    <div class="field" id="selWrap" style="display:none"><label>选择设备</label>
      <select id="macSel" onchange="pickDevice(this.value)"></select></div>
    <div class="field"><label>配对密钥</label>
      <input id="key" placeholder="32 位十六进制配对密钥">
      <button class="btn ghost" onclick="toggleHelp()">如何获取？</button></div>
    <div class="field"><label>时间范围</label>
      <div class="quick" id="quick">
        <button class="qbtn" data-days="0">今天</button>
        <button class="qbtn active" data-days="3">近 3 天</button>
        <button class="qbtn" data-days="7">近 7 天</button>
        <button class="qbtn" data-days="30">近 30 天</button>
      </div></div>
    <div class="field"><label>或起始日期</label>
      <input id="since" type="date" style="max-width:200px"></div>
    <button id="btn" class="btn" onclick="connect()">连接并拉取</button>
    <div id="status" class="status"></div>

    <div id="help" class="help">
      <b>获取配对密钥（auth_key）</b>
      <ol>
        <li>手机打开「小米运动健康」→ 我的 → 关于 → 连续点击图标开启日志</li>
        <li>连接手环同步一次</li>
        <li>在电脑上执行：<code>adb pull /sdcard/Android/data/com.mi.health/files/log/XiaomiFit.device.log</code></li>
        <li>日志中搜索 <code>huamiAuthKey=</code>，等号后 32 位即密钥</li>
      </ol>
      若手机已用 USB 连接并已开日志，可点此自动提取：
      <button class="btn ghost" onclick="extractKey()">从已连接手机提取</button>
    </div>
  </section>

  <section id="dash" style="display:none">
    %s
  </section>

  <footer>miband6-pc · 数据直接来自手环，经 PC 蓝牙直连采集</footer>
<script>%s</script>
<script>%s</script>
</body></html>""" % (dashboard.BASE_CSS, CONTROL_CSS, dashboard.DASH_BODY,
                      dashboard.CHART_JS, PAGE_JS)


# ---------------- backend ----------------

async def _run_fetch(mac, key_hex, days, since=None):
    from .device import MiBand6
    band = MiBand6(mac, bytes.fromhex(key_hex))
    if since:
        since_dt = datetime.datetime.fromisoformat(since)
    else:
        since_dt = (datetime.datetime.now()
                    - datetime.timedelta(days=days)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
    await band.connect()
    try:
        await band.authenticate()
        samples = await band.fetch_activity(since_dt)
    finally:
        await band.disconnect()
    return dashboard.aggregate(samples)


def _extract_key_adb():
    try:
        out = subprocess.check_output(
            ["adb", "shell", "su", "-c",
             "grep -rhoE 'huamiAuthKey=[0-9a-fA-F]{32}' "
             "/sdcard/Android/data/com.mi.health/files/log/ 2>/dev/null | head -1"],
            stderr=subprocess.DEVNULL, timeout=15).decode("utf-8", "ignore").strip()
    except FileNotFoundError:
        raise RuntimeError("未找到 adb")
    except subprocess.TimeoutExpired:
        raise RuntimeError("adb 超时")
    m = re.search(r"huamiAuthKey=([0-9a-fA-F]{32})", out)
    if not m:
        raise RuntimeError("日志中未找到 huamiAuthKey")
    return m.group(1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, build_page(), "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            req = json.loads(raw or b"{}")
        except Exception:
            req = {}

        if self.path == "/api/fetch":
            try:
                mac = req["mac"].strip()
                key = req["key"].strip()
                days = int(req.get("days", 3))
                since = req.get("since") or None
                agg = asyncio.run(_run_fetch(mac, key, days, since))
                self._json({"ok": True, "agg": agg})
            except Exception as e:
                self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
        elif self.path == "/api/scan":
            try:
                from .device import scan
                devices = asyncio.run(scan(10.0))
                self._json({"ok": True, "devices": devices})
            except Exception as e:
                self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
        elif self.path == "/api/extract_key":
            try:
                self._json({"ok": True, "key": _extract_key_adb()})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
        else:
            self._send(404, "{}")


def serve(host="127.0.0.1", port=8080):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d" % (host, port)
    print("miband6 web dashboard running at %s" % url)
    print("Open it in a browser. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
