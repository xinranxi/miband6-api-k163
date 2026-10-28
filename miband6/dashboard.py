"""
Data aggregation + static dashboard rendering.

Aggregation takes a list of normalized samples:
    {"time": datetime, "kind": int, "steps": int,
     "heart_rate": int|None, "deep_sleep": int|None, "rem_sleep": int|None}
"""
import csv
import datetime
import json
from collections import defaultdict


def load_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _to_int(v, default=0):
    if v in ("", None):
        return default
    try:
        return int(v, 16) if isinstance(v, str) and v.lower().startswith("0x") else int(v)
    except (ValueError, TypeError):
        return default


def _to_opt_int(v):
    if v in ("", None):
        return None
    try:
        return int(v, 16) if isinstance(v, str) and v.lower().startswith("0x") else int(v)
    except (ValueError, TypeError):
        return None


def rows_to_samples(rows):
    samples = []
    for r in rows:
        t = r.get("time", "")
        try:
            dt = datetime.datetime.fromisoformat(t)
        except (ValueError, TypeError):
            continue
        samples.append({
            "time": dt,
            "kind": _to_int(r.get("kind")),
            "steps": _to_int(r.get("steps")),
            "heart_rate": _to_opt_int(r.get("heart_rate")),
            "deep_sleep": _to_opt_int(r.get("deep_sleep")),
            "rem_sleep": _to_opt_int(r.get("rem_sleep")),
        })
    return samples


def aggregate(samples):
    hr_points = []
    hr_values = []
    hr_zones = {"rest": 0, "daily": 0, "fat_burn": 0, "cardio": 0}
    steps_by_hour = defaultdict(int)
    steps_by_day = defaultdict(int)
    sleep_minutes = 0
    total_steps = 0

    for s in samples:
        t = s["time"]
        ts = t.strftime("%Y-%m-%d %H:%M:%S")
        hr = s["heart_rate"]
        if hr is not None:
            hr_values.append(hr)
            hr_points.append([ts, hr])
            if hr < 60:
                hr_zones["rest"] += 1
            elif hr < 100:
                hr_zones["daily"] += 1
            elif hr < 140:
                hr_zones["fat_burn"] += 1
            else:
                hr_zones["cardio"] += 1
        total_steps += s["steps"]
        steps_by_hour[t.strftime("%Y-%m-%d %H:00")] += s["steps"]
        steps_by_day[t.strftime("%Y-%m-%d")] += s["steps"]

        # kind 0xF0-0xFF marks night/sleep samples (one per minute)
        if 0xF0 <= (s["kind"] & 0xFFFF) <= 0xFF:
            sleep_minutes += 1

    first = samples[0]["time"].strftime("%Y-%m-%d %H:%M") if samples else ""
    last = samples[-1]["time"].strftime("%Y-%m-%d %H:%M") if samples else ""

    return {
        "hr_points": hr_points,
        "hr_zones": hr_zones,
        "steps_by_hour": dict(sorted(steps_by_hour.items())),
        "steps_by_day": dict(sorted(steps_by_day.items())),
        "sleep_minutes": sleep_minutes,
        "total_steps": total_steps,
        "hr_values": hr_values,
        "first": first,
        "last": last,
        "count": len(samples),
    }


# JS chart renderer, shared by static and live dashboards.
CHART_JS = r"""
Chart.defaults.color = '#8fa8c8';
Chart.defaults.font.family = "-apple-system,'Segoe UI','Microsoft YaHei',sans-serif";
Chart.defaults.borderColor = 'rgba(120,180,255,.10)';

function fmtT(t){ return t.length>=16 ? t.slice(5,16) : t; }

const _charts = {};
function renderDashboard(agg){
  document.getElementById('s_steps').textContent = agg.total_steps.toLocaleString();
  const hv = agg.hr_values;
  if (hv.length){
    const avg = Math.round(hv.reduce((a,b)=>a+b,0)/hv.length);
    document.getElementById('s_avg').innerHTML = avg + '<span class="u">bpm</span>';
    document.getElementById('s_range').textContent = Math.min(...hv) + ' – ' + Math.max(...hv);
  } else {
    document.getElementById('s_avg').textContent = '–';
    document.getElementById('s_range').textContent = '–';
  }
  const sm = agg.sleep_minutes;
  document.getElementById('s_sleep').innerHTML =
    sm ? (Math.floor(sm/60) + '<span class="u">h</span>' + (sm%60) + '<span class="u">m</span>') : '–';
  document.getElementById('dash_range').textContent = agg.first.slice(0,16) + ' ~ ' + agg.last.slice(0,16);

  Object.values(_charts).forEach(c=>c.destroy());
  const hrPts = agg.hr_points;
  // adaptive y-range + average line
  let ymin = 40, ymax = 140, avgLine = null;
  if (hrPts.length) {
    let lo = hrPts[0][1], hi = hrPts[0][1], sum = 0;
    for (const p of hrPts){ if(p[1]<lo)lo=p[1]; if(p[1]>hi)hi=p[1]; sum+=p[1]; }
    avgLine = Math.round(sum/hrPts.length);
    ymin = Math.max(25, Math.floor((lo-8)/10)*10);
    ymax = Math.min(210, Math.ceil((hi+8)/10)*10);
  }
  _charts.hr = new Chart(document.getElementById('hr'), {
    type:'line',
    data:{ labels: hrPts.map(p=>fmtT(p[0])),
      datasets:[
        { data: hrPts.map(p=>p[1]), borderColor:'#22e0ff', borderWidth:1.4,
          pointRadius:0, tension:.25, fill:true,
          backgroundColor:(c)=>{ const g=c.chart.ctx.createLinearGradient(0,0,0,320);
            g.addColorStop(0,'rgba(34,224,255,.35)'); g.addColorStop(1,'rgba(34,224,255,0)'); return g;} },
        { data: hrPts.map(()=>avgLine), borderColor:'rgba(255,176,32,.7)',
          borderDash:[6,6], borderWidth:1, pointRadius:0, fill:false }
      ] },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:(c)=>c.datasetIndex===1?'平均 '+avgLine:'心率 '+c.parsed.y+' bpm'}}},
      scales:{ x:{ticks:{maxTicksLimit:8,font:{size:10}}},
               y:{min:ymin,max:ymax,ticks:{stepSize:10}} } }
  });

  const sh = agg.steps_by_hour, shKeys = Object.keys(sh);
  _charts.steps = new Chart(document.getElementById('steps'), {
    type:'bar',
    data:{ labels: shKeys.map(k=>k.slice(5)), datasets:[{ data: shKeys.map(k=>sh[k]),
      backgroundColor:'rgba(57,255,136,.55)', borderRadius:4 }] },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{legend:{display:false}},
      scales:{ x:{ticks:{maxTicksLimit:6,font:{size:9}}}, y:{beginAtZero:true} } }
  });

  const sd = agg.steps_by_day, sdKeys = Object.keys(sd);
  _charts.days = new Chart(document.getElementById('days'), {
    type:'bar',
    data:{ labels: sdKeys, datasets:[{ data: sdKeys.map(k=>sd[k]),
      backgroundColor:'rgba(255,176,32,.6)', borderRadius:6 }] },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{legend:{display:false}}, scales:{ x:{ticks:{font:{size:10}}}, y:{beginAtZero:true} } }
  });

  const z = agg.hr_zones;
  _charts.sleep = new Chart(document.getElementById('sleep'), {
    type:'doughnut',
    data:{ labels:['静息 <60','日常 60–100','燃脂 100–140','高强度 >140'],
      datasets:[{ data:[z.rest, z.daily, z.fat_burn, z.cardio],
        backgroundColor:['#3a6bff','#22e0ff','#39ff88','#ff4d8d'], borderWidth:0 }] },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      cutout:'62%', plugins:{legend:{position:'right',labels:{boxWidth:10,font:{size:11}}}} }
  });
}
"""

DASH_BODY = r"""
  <div class="stats">
    <div class="stat"><div class="k">总步数</div><div class="v" id="s_steps">–</div></div>
    <div class="stat g"><div class="k">平均心率</div><div class="v" id="s_avg">–</div></div>
    <div class="stat p"><div class="k">心率区间</div><div class="v" id="s_range" style="font-size:22px">–</div></div>
    <div class="stat o"><div class="k">睡眠时长</div><div class="v" id="s_sleep">–</div></div>
  </div>

  <div class="grid">
    <div class="card"><h2>心率趋势</h2><div class="h320"><canvas id="hr"></canvas></div></div>
    <div class="card"><h2>每小时步数</h2><div class="h320"><canvas id="steps"></canvas></div></div>
  </div>
  <div class="grid">
    <div class="card"><h2>每日步数</h2><div class="h180"><canvas id="days"></canvas></div></div>
    <div class="card"><h2>心率区间分布</h2><div class="h180"><canvas id="sleep"></canvas></div></div>
  </div>
"""

BASE_CSS = r"""
  :root{ --bg1:#0a0e27; --bg2:#141a3a; --card:rgba(255,255,255,.04);
    --line:rgba(120,180,255,.18); --cyan:#22e0ff; --green:#39ff88;
    --pink:#ff4d8d; --orange:#ffb020; --txt:#e8f0ff; --dim:#8fa8c8; }
  *{box-sizing:border-box;margin:0;padding:0}
  body{ font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    background:radial-gradient(1200px 700px at 20% -10%,#1b2a5e 0%,transparent 60%),
      radial-gradient(1000px 600px at 100% 0%,#3a1650 0%,transparent 55%),
      linear-gradient(160deg,var(--bg1),var(--bg2));
    color:var(--txt); min-height:100vh; padding:26px 30px 40px; }
  header{display:flex;justify-content:space-between;align-items:flex-end;
    border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:22px}
  h1{font-size:26px;font-weight:800;letter-spacing:1px;
    background:linear-gradient(90deg,var(--cyan),var(--green));
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
  .sub{color:var(--dim);font-size:13px;margin-top:6px}
  .badge{font-size:12px;color:var(--dim);border:1px solid var(--line);border-radius:20px;padding:6px 14px}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:22px}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
    position:relative;overflow:hidden}
  .stat::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--cyan)}
  .stat.g::before{background:var(--green)} .stat.p::before{background:var(--pink)}
  .stat.o::before{background:var(--orange)}
  .stat .k{color:var(--dim);font-size:13px;letter-spacing:.5px}
  .stat .v{font-size:34px;font-weight:800;margin-top:8px;font-variant-numeric:tabular-nums}
  .stat .u{font-size:14px;color:var(--dim);margin-left:4px;font-weight:400}
  .grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
  .card h2{font-size:15px;font-weight:600;color:var(--txt);margin-bottom:14px;
    display:flex;align-items:center;gap:8px}
  .card h2::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--cyan);
    box-shadow:0 0 10px var(--cyan)}
  .h180{height:180px} .h320{height:320px}
  canvas{max-height:100%!important}
  footer{color:var(--dim);font-size:12px;text-align:center;margin-top:24px}
"""


def build_static_html(samples, title="小米手环6 数据大屏"):
    agg = aggregate(samples)
    return """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>%s</style></head>
<body>
  <header><div><h1>小米手环6 · 数据大屏</h1>
    <div class="sub" id="dash_range">%s ~ %s</div></div>
    <div class="badge">%s</div></header>
  %s
  <footer>miband6-pc · 数据直接来自手环，经 PC 蓝牙直连采集</footer>
<script>const AGG = %s;</script>
<script>%s</script>
<script>renderDashboard(AGG);</script>
</body></html>""" % (title, BASE_CSS, agg["first"], agg["last"],
                      "%s ~ %s" % (agg["first"], agg["last"]), DASH_BODY,
                      json.dumps(agg, ensure_ascii=False), CHART_JS)


def write_dashboard(samples, out_path, title="小米手环6 数据大屏"):
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_static_html(samples, title))
    return out_path
