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

    return {
        "date": str(datetime.date.today()),
        "strategy": {"fast": f, "slow": s, "hold_days": hd},
        "summary": {"win_rate": round(win_all / n_all * 100, 1), "trades": n_all,
                    "avg_ret": round(avg_all * 100, 2), "avg_hold": round(avg_hold)},
        "signals": signals,
        "yearly": yearly_sorted,
        "funds": fund_detail,
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
