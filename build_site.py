# -*- coding: utf-8 -*-
"""生成 GitHub Pages 站点：index.html（响应式，内嵌每日信号 + 回测结果）
数据每天由 GitHub Actions 重新生成并部署。
"""
import json, datetime, os, sys
import config
import signal_monitor
import etf_backtest as BT


def fixed_hold_backtest(arr, fast, slow, hold_days):
    """固定持有 N 天回测：金叉买入，持有满 N 天卖出"""
    dates = [a["date"] for a in arr]
    nav = [a["nav"] for a in arr]
    mf = BT.ma(nav, fast)
    ms = BT.ma(nav, slow)
    trades = []
    pos = None
    for i in range(slow, len(nav)):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        cross_up = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
        if pos is None:
            if cross_up:
                pos = {"bi": i, "bn": nav[i], "bd": dates[i]}
        else:
            d0 = datetime.date.fromisoformat(pos["bd"])
            d1 = datetime.date.fromisoformat(dates[i])
            if (d1 - d0).days >= hold_days:
                trades.append({"ret": nav[i] / pos["bn"] - 1, "bd": pos["bd"],
                               "sd": dates[i], "hold": (d1 - d0).days})
                pos = None
    return trades


def build_data():
    f, s, hd = (config.STRATEGY["fast"], config.STRATEGY["slow"], config.STRATEGY["hold_days"])
    # 1. 今日信号
    signals = signal_monitor.check_all()
    # 2. 回测
    all_trades = []
    fund_detail = []
    yearly = {}
    for code, name in config.POOL.items():
        arr = [a for a in signal_monitor.fetch(code) if a["date"] >= "2020-01-01"]
        tr = fixed_hold_backtest(arr, f, s, hd)
        all_trades += tr
        n = len(tr)
        if n:
            win = sum(1 for t in tr if t["ret"] > 0)
            avg = sum(t["ret"] for t in tr) / n
            cum = 1.0
            for t in tr:
                cum *= (1 + t["ret"])
            fund_detail.append({"code": code, "name": name, "win_rate": round(win / n * 100, 1),
                                "avg_ret": round(avg * 100, 2), "cum_ret": round((cum - 1) * 100, 1),
                                "trades": n})
    for t in all_trades:
        y = t["bd"][:4]
        yearly.setdefault(y, []).append(t["ret"])
    yearly_sorted = [{"year": y, "win_rate": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 0)}
                     for y, rs in sorted(yearly.items())]
    n_all = len(all_trades)
    win_all = sum(1 for t in all_trades if t["ret"] > 0)
    avg_all = sum(t["ret"] for t in all_trades) / n_all if n_all else 0
    avg_hold = sum(t["hold"] for t in all_trades) / n_all if n_all else 0

    # 参数空间：不同持有期的胜率-盈利率（供折线图交互）
    param_space = []
    for hold_days in [7, 10, 12, 15, 20, 25, 30, 45, 60]:
        pts = []
        for code in config.POOL:
            arr = [a for a in signal_monitor.fetch(code) if a["date"] >= "2020-01-01"]
            pts += fixed_hold_backtest(arr, f, s, hold_days)
        if pts:
            pw = sum(1 for t in pts if t["ret"] > 0)
            param_space.append({
                "hold_days": hold_days,
                "win_rate": round(pw / len(pts) * 100, 1),
                "avg_ret": round(sum(t["ret"] for t in pts) / len(pts) * 100, 2),
                "trades": len(pts),
            })

    return {
        "date": str(datetime.date.today()),
        "strategy": {"fast": f, "slow": s, "hold_days": hd},
        "summary": {"win_rate": round(win_all / n_all * 100, 1), "trades": n_all,
                    "avg_ret": round(avg_all * 100, 2), "avg_hold": round(avg_hold)},
        "signals": signals,
        "yearly": yearly_sorted,
        "funds": fund_detail,
        "param_space": param_space,
    }


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 量化信号 · MA10/30 金叉策略</title>
<style>
:root{
  --bg:#f4f6fb; --card:#ffffff; --ink:#1f2430; --sub:#6b7280; --line:#e6e8ef;
  --brand:#4f46e5; --up:#dc2626; --down:#16a34a; --gold:#d97706;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;padding:16px 16px 48px}
header{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;padding:18px 4px}
header h1{font-size:22px;font-weight:800;letter-spacing:.5px}
header .date{color:var(--sub);font-size:13px}
.tag{display:inline-block;font-size:11px;color:var(--brand);background:#eef2ff;border:1px solid #e0e7ff;padding:2px 8px;border-radius:999px;margin-left:6px;vertical-align:middle}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(17,24,39,.05)}
.card h2{font-size:15px;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:6px}
.card h2 .dot{width:8px;height:8px;border-radius:50%;background:var(--brand)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.kpi{background:linear-gradient(135deg,#fafbff,#f4f6ff);border:1px solid var(--line);border-radius:12px;padding:14px;text-align:center}
.kpi .v{font-size:26px;font-weight:800;color:var(--brand)}
.kpi .v.red{color:var(--up)}
.kpi .l{font-size:12px;color:var(--sub);margin-top:2px}
.sig{display:flex;align-items:center;justify-content:space-between;padding:11px 12px;border:1px solid var(--line);border-radius:12px;margin-bottom:8px;gap:10px;flex-wrap:wrap}
.sig .nm{font-weight:600;font-size:14px}
.sig .cd{font-size:12px;color:var(--sub)}
.sig .st{font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;white-space:nowrap}
.st.buy{background:#fef2f2;color:var(--up);border:1px solid #fecaca}
.st.hold{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}
.st.sell{background:#fffbeb;color:var(--gold);border:1px solid #fde68a}
.st.wait{background:#f3f4f6;color:#6b7280;border:1px solid #e5e7eb}
.sig .ret{font-size:13px;font-weight:700}
.ret.pos{color:var(--up)} .ret.neg{color:var(--down)}
.empty{color:var(--sub);font-size:13px;text-align:center;padding:12px}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:9px}
.bar-row .yr{width:44px;font-size:12px;color:var(--sub);text-align:right}
.bar-row .track{flex:1;height:18px;background:#eef0f6;border-radius:6px;position:relative;overflow:hidden}
.bar-row .fill{height:100%;border-radius:6px;background:linear-gradient(90deg,#6366f1,#4f46e5);display:flex;align-items:center;justify-content:flex-end;padding-right:6px;font-size:11px;color:#fff;font-weight:600;min-width:26px}
.line50{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#f59e0b;opacity:.7}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 8px;text-align:center;border-bottom:1px solid var(--line)}
th{color:var(--sub);font-weight:600;font-size:12px}
td:first-child,th:first-child{text-align:left}
.pos{color:var(--up);font-weight:600} .neg{color:var(--down);font-weight:600}
.note{font-size:12px;color:var(--sub);margin-top:10px;line-height:1.7}
footer{text-align:center;color:#9ca3af;font-size:12px;margin-top:20px}
@media(max-width:640px){
  .grid{grid-template-columns:repeat(2,1fr)}
  header h1{font-size:19px}
  .kpi .v{font-size:22px}
}
.sliders{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:6px}
.slider-item{flex:1;min-width:200px}
.slider-item label{font-size:12px;color:var(--sub);display:flex;justify-content:space-between}
.slider-item label b{color:var(--brand)}
.slider-item input{width:100%;margin-top:6px;accent-color:var(--brand)}
.ps-svg{width:100%;height:auto;display:block}
.ps-legend{display:flex;gap:16px;font-size:12px;color:var(--sub);margin-top:8px;flex-wrap:wrap}
.ps-legend .lg{display:flex;align-items:center;gap:5px}
.ps-legend .sw{width:11px;height:11px;border-radius:50%;display:inline-block}
.pick-note{font-size:12px;margin-top:10px;color:var(--sub);line-height:1.7}
.pick-note b{color:var(--brand)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>ETF 量化信号 <span class="tag">MA{fast}/MA{slow} 金叉</span></h1>
    <div class="date">更新于 {date}</div>
  </header>

  <div class="card">
    <h2><span class="dot"></span>策略概览</h2>
    <div class="grid">
      <div class="kpi"><div class="v">{win_rate}%</div><div class="l">历史综合胜率</div></div>
      <div class="kpi"><div class="v red">{avg_ret}%</div><div class="l">平均每笔收益</div></div>
      <div class="kpi"><div class="v">{hold_days}天</div><div class="l">持有周期</div></div>
      <div class="kpi"><div class="v">{n_funds}只</div><div class="l">标的数量</div></div>
    </div>
    <div class="note">策略：MA{fast} 上穿 MA{slow}（金叉）买入，持有 {hold_days} 个自然日卖出；共 {trades} 笔历史交易。标的为支付宝可买、C 类、持有≥7 天免赎回费的 ETF 联接基金。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>今日信号</h2>
    <div id="signals"></div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>历年胜率（按买入年份）</h2>
    <div id="yearly"></div>
    <div class="note">虚线为 50% 胜率线；历年胜率均高于 50%，牛熊震荡市场均有效。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>胜率 × 盈利率（拖动选范围）</h2>
    <div class="sliders">
      <div class="slider-item"><label>最低胜率 <b id="winVal">55%</b></label><input type="range" id="winSlider" min="50" max="66" step="0.5" value="55"></div>
      <div class="slider-item"><label>最低盈利率 <b id="retVal">1.0%</b></label><input type="range" id="retSlider" min="0.4" max="1.9" step="0.05" value="1.0"></div>
    </div>
    <div id="psChart"></div>
    <div class="ps-legend">
      <span class="lg"><span class="sw" style="background:#4f46e5"></span>当前采用（持有{hold_days}天）</span>
      <span class="lg"><span class="sw" style="background:#dc2626"></span>符合所选范围</span>
      <span class="lg"><span class="sw" style="background:#d1d5db"></span>不符合</span>
    </div>
    <div class="pick-note" id="pickNote"></div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>标的池明细</h2>
    <table id="funds"></table>
  </div>

  <footer>数据来源：天天基金 · 自动更新 · 仅供研究参考，不构成投资建议</footer>
</div>
<script>
const DATA = __DATA__;
const ST = {BUY:['buy','买入信号'],HOLDING:['hold','持有中'],SELL_READY:['sell','可卖出'],WAIT:['wait','等待'],ERROR:['wait','数据异常']};
function fmtRet(r){return (r>=0?'+':'')+(r*100).toFixed(2)+'%';}
// 信号
const sg = document.getElementById('signals');
if(!DATA.signals || !DATA.signals.length){ sg.innerHTML='<div class="empty">暂无数据</div>'; }
else{
  let html='';
  DATA.signals.forEach(s=>{
    const [cls,label]=ST[s.state]||['wait',s.state];
    const r=s.ret!=null?('<span class="ret '+(s.ret>=0?'pos':'neg')+'">'+fmtRet(s.ret)+'</span>'):'';
    const extra=(s.held_days!=null?'<span class="cd">持有'+s.held_days+'天</span>':'');
    html+='<div class="sig"><div><div class="nm">'+s.name+'</div><div class="cd">'+s.code+'</div></div><div style="display:flex;align-items:center;gap:8px">'+extra+r+'<span class="st '+cls+'">'+label+'</span></div></div>';
  });
  sg.innerHTML=html;
}
// 历年胜率
const yr = document.getElementById('yearly');
let yh='';
DATA.yearly.forEach(d=>{
  yh+='<div class="bar-row"><span class="yr">'+d.year+'</span><div class="track"><div class="line50"></div><div class="fill" style="width:'+d.win_rate+'%">'+d.win_rate+'%</div></div></div>';
});
yr.innerHTML=yh;
// 标的明细
const fd = document.getElementById('funds');
let fh='<tr><th>基金</th><th>代码</th><th>胜率</th><th>平均收益</th><th>累计收益</th><th>交易数</th></tr>';
DATA.funds.forEach(f=>{
  fh+='<tr><td>'+f.name+'</td><td>'+f.code+'</td><td>'+f.win_rate+'%</td><td class="'+(f.avg_ret>=0?'pos':'neg')+'">'+(f.avg_ret>=0?'+':'')+f.avg_ret+'%</td><td class="'+(f.cum_ret>=0?'pos':'neg')+'">'+(f.cum_ret>=0?'+':'')+f.cum_ret+'%</td><td>'+f.trades+'</td></tr>';
});
fd.innerHTML=fh;
// 胜率-盈利率散点图（拖动阈值选范围）
const ps = document.getElementById('psChart');
const XMIN=0.4, XMAX=1.9, YMIN=50, YMAX=66;
const L=52, R=660, T=18, B=278;
function px(v){ return L + (v-XMIN)/(XMAX-XMIN)*(R-L); }
function py(v){ return T + (YMAX-v)/(YMAX-YMIN)*(B-T); }
let winThr=55, retThr=1.0;
function renderPS(){
  const curHold = DATA.strategy.hold_days;
  let svg = '<svg class="ps-svg" viewBox="0 0 680 318">';
  svg += '<line x1="'+L+'" y1="'+B+'" x2="'+R+'" y2="'+B+'" stroke="#e5e7eb"/>';
  svg += '<line x1="'+L+'" y1="'+T+'" x2="'+L+'" y2="'+B+'" stroke="#e5e7eb"/>';
  for(let x=XMIN; x<=XMAX+0.001; x+=0.3){
    svg += '<text x="'+px(x)+'" y="'+(B+15)+'" font-size="10" fill="#9ca3af" text-anchor="middle">'+x.toFixed(1)+'%</text>';
  }
  for(let y=YMIN; y<=YMAX+0.001; y+=4){
    svg += '<text x="'+(L-8)+'" y="'+(py(y)+3)+'" font-size="10" fill="#9ca3af" text-anchor="end">'+y+'%</text>';
  }
  svg += '<line x1="'+px(retThr)+'" y1="'+T+'" x2="'+px(retThr)+'" y2="'+B+'" stroke="#dc2626" stroke-dasharray="4,3" opacity="0.55"/>';
  svg += '<line x1="'+L+'" y1="'+py(winThr)+'" x2="'+R+'" y2="'+py(winThr)+'" stroke="#dc2626" stroke-dasharray="4,3" opacity="0.55"/>';
  DATA.param_space.forEach(p=>{
    const cx=px(p.avg_ret), cy=py(p.win_rate);
    const ok = p.win_rate>=winThr && p.avg_ret>=retThr;
    const isCur = p.hold_days===curHold;
    const r = isCur?6:4;
    const color = isCur?'#4f46e5':(ok?'#dc2626':'#d1d5db');
    svg += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+color+'"/>';
    svg += '<text x="'+cx+'" y="'+(cy-8)+'" font-size="9" fill="#6b7280" text-anchor="middle">'+p.hold_days+'d</text>';
  });
  svg += '</svg>';
  ps.innerHTML = svg;
  const okList = DATA.param_space.filter(p=>p.win_rate>=winThr && p.avg_ret>=retThr);
  document.getElementById('winVal').textContent = winThr+'%';
  document.getElementById('retVal').textContent = retThr.toFixed(2)+'%';
  let note='';
  if(okList.length){
    note = '符合范围（胜率≥'+winThr+'% 且 盈利率≥'+retThr.toFixed(2)+'%）的持有期：<b>'+okList.map(p=>p.hold_days+'天').join('、')+'</b>。';
    note += okList.some(p=>p.hold_days===curHold) ? ' 当前采用的 <b>'+curHold+'天</b> 满足你的要求。' : ' 当前采用的 '+curHold+'天 不在此范围内。';
  } else {
    note = '当前筛选过严，无满足的持有期，请放宽阈值。';
  }
  document.getElementById('pickNote').innerHTML = note;
}
document.getElementById('winSlider').addEventListener('input', e=>{winThr=parseFloat(e.target.value); renderPS();});
document.getElementById('retSlider').addEventListener('input', e=>{retThr=parseFloat(e.target.value); renderPS();});
renderPS();
</script>
</body>
</html>
"""


def main():
    data = build_data()
    data["n_funds"] = len(config.POOL)
    # 填充静态占位符
    html = (HTML
            .replace("{fast}", str(data["strategy"]["fast"]))
            .replace("{slow}", str(data["strategy"]["slow"]))
            .replace("{hold_days}", str(data["strategy"]["hold_days"]))
            .replace("{date}", data["date"])
            .replace("{win_rate}", str(data["summary"]["win_rate"]))
            .replace("{avg_ret}", str(data["summary"]["avg_ret"]))
            .replace("{trades}", str(data["summary"]["trades"]))
            .replace("{n_funds}", str(data["n_funds"])))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = os.path.join(os.path.dirname(__file__), "index.html")
    open(out, "w", encoding="utf-8").write(html)
    print("生成 index.html 完成,", len(html), "字节")
    print("胜率", data["summary"]["win_rate"], "% | 平均收益", data["summary"]["avg_ret"], "%")


if __name__ == "__main__":
    main()
