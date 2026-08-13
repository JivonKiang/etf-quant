# -*- coding: utf-8 -*-
"""信号监控：每日检测 10 只 ETF 联接的 MA10/30 金叉信号
- 今日金叉 -> BUY（买入信号，邮件通知）
- 金叉后 1~19 天 -> HOLDING（持有中）
- 满 20 天 -> SELL_READY（可卖出）

用法:
  python signal_monitor.py           # 打印报告 + 按需发邮件
  python signal_monitor.py --json    # 输出 JSON（供 CI 判断）
环境变量(邮件, 可选):
  SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS MAIL_TO
"""
import os, sys, json, datetime, re, urllib.request
import config

NOW = datetime.date.today()


def fetch(code):
    cache = os.path.join(os.path.dirname(__file__), "nav_cache", code + ".json")
    if os.path.exists(cache):
        arr = json.load(open(cache, encoding="utf-8"))
    else:
        req = urllib.request.Request(config.FUND_JS.format(code=code),
                                     headers={"User-Agent": "Mozilla/5.0",
                                              "Referer": "http://fund.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8", "ignore")
        m = re.search(r"var Data_ACWorthTrend = (\[.*?\]);", txt, re.S)
        if not m:
            m = re.search(r"var Data_netWorthTrend = (\[.*?\]);", txt, re.S)
            raw = json.loads(m.group(1))
            arr = [{"date": datetime.datetime.utcfromtimestamp(x["x"] / 1000).date().isoformat(),
                    "nav": x["y"]} for x in raw]
        else:
            raw = json.loads(m.group(1))
            arr = [{"date": datetime.datetime.utcfromtimestamp(x[0] / 1000).date().isoformat(),
                    "nav": x[1]} for x in raw]
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(arr, open(cache, "w", encoding="utf-8"))
    return arr


def ma(prices, n):
    out = [None] * len(prices)
    s = 0
    for i, p in enumerate(prices):
        s += p
        if i >= n:
            s -= prices[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals, n):
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def macd_hist(nav):
    """MACD 柱状图 = 2*(DIF - DEA)，DIF=EMA12-EMA26，DEA=EMA9(DIF)"""
    e12 = ema(nav, 12)
    e26 = ema(nav, 26)
    dif = [e12[i] - e26[i] for i in range(len(nav))]
    dea = ema(dif, 9)
    return [2 * (dif[i] - dea[i]) for i in range(len(nav))]


def state_of(arr):
    """返回 (state, detail)，state: BUY/HOLDING/SELL_READY/WAIT
    金叉(MA10上穿MA30) + MACD柱>0 买入 -> 持有 -> 满期卖出 -> 空仓等下一次"""
    nav = [a["nav"] for a in arr]
    dates = [a["date"] for a in arr]
    mf = ma(nav, config.STRATEGY["fast"])
    ms = ma(nav, config.STRATEGY["slow"])
    hist = macd_hist(nav)
    slow = config.STRATEGY["slow"]
    buy_idx = None
    for i in range(len(nav) - 1, slow - 1, -1):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        if mf[i - 1] <= ms[i - 1] and mf[i] > ms[i] and hist[i] > 0:
            buy_idx = i
            break
    if buy_idx is None:
        return "WAIT", {"note": "近期无金叉信号"}
    bd = dates[buy_idx]
    held = (NOW - datetime.date.fromisoformat(bd)).days
    latest_nav = arr[-1]["nav"]
    latest_date = dates[-1]
    detail = {"buy_date": bd, "held_days": held,
              "buy_nav": nav[buy_idx], "latest_nav": latest_nav,
              "ret": latest_nav / nav[buy_idx] - 1,
              "latest_date": latest_date}
    if bd == latest_date:
        return "BUY", detail                      # 最新净值日刚金叉 -> 买入
    tp = config.STRATEGY.get("take_profit")
    if held < config.STRATEGY["hold_days"]:
        if tp and detail["ret"] >= tp:
            detail["reason"] = "止盈"
            return "SELL_READY", detail           # 持有期内达到止盈线 -> 卖出
        return "HOLDING", detail                  # 持有中
    if held == config.STRATEGY["hold_days"]:
        detail["reason"] = "满期"
        return "SELL_READY", detail               # 今日满期，可卖出
    return "WAIT", detail                         # 已了结，等新金叉


def check_all():
    rows = []
    for code, name in config.POOL.items():
        try:
            arr = fetch(code)
        except Exception as e:
            rows.append({"code": code, "name": name, "state": "ERROR", "note": str(e)})
            continue
        st, d = state_of(arr)
        rows.append({"code": code, "name": name, "state": st, **d})
    return rows


def render_markdown(rows):
    L = [f"# ETF 量化信号日报 — {NOW}", ""]
    buy = [r for r in rows if r["state"] == "BUY"]
    hold = [r for r in rows if r["state"] == "HOLDING"]
    sell = [r for r in rows if r["state"] == "SELL_READY"]
    if buy:
        L += ["## 🟢 买入信号", ""]
        for r in buy:
            L.append(f"- **{r['name']}**（{r['code']}）：MA10 上穿 MA30 金叉，建议买入持有 {config.STRATEGY['hold_days']} 天")
        L.append("")
    if hold:
        L += ["## 🟡 持有中", ""]
        for r in hold:
            L.append(f"- {r['name']}（{r['code']}）：持有第 {r['held_days']} 天，收益 {r['ret']*100:+.2f}%")
        L.append("")
    if sell:
        L += ["## 🔵 到持有期（可卖出）", ""]
        for r in sell:
            L.append(f"- {r['name']}（{r['code']}）：已持有 {r['held_days']} 天，收益 {r['ret']*100:+.2f}%")
        L.append("")
    if not (buy or hold or sell):
        L.append("今日无买入信号，也无持仓。")
    L += ["", f"> 策略：MA{config.STRATEGY['fast']}/MA{config.STRATEGY['slow']} 金叉 + MACD 柱>0 买入，持有 {config.STRATEGY['hold_days']} 天或止盈 +15% 卖出；历史综合胜率 66.0%。"]
    return "\n".join(L)


def build_email_html(rows):
    """生成买入信号邮件的 HTML 正文"""
    f, s, hd = config.STRATEGY["fast"], config.STRATEGY["slow"], config.STRATEGY["hold_days"]
    buys = [r for r in rows if r["state"] == "BUY"]
    holds = [r for r in rows if r["state"] == "HOLDING"]
    cards = ""
    for r in buys:
        cards += ('<div style="border:1px solid #e6e8ef;border-left:4px solid #ef4444;border-radius:10px;'
                  'padding:14px;margin-bottom:10px;background:#fff;">'
                  '<div style="font-size:15px;font-weight:700;color:#1e293b;">%s</div>'
                  '<div style="font-size:12px;color:#64748b;margin-top:4px;">代码 %s · 建议买入持有 %d 天（或 +15%% 止盈）· C类≥7天免赎回费</div>'
                  '</div>') % (r["name"], r["code"], hd)
    for r in holds:
        cards += ('<div style="border:1px solid #e6e8ef;border-left:4px solid #2563eb;border-radius:10px;'
                  'padding:14px;margin-bottom:10px;background:#fff;">'
                  '<div style="font-size:15px;font-weight:700;color:#1e293b;">%s</div>'
                  '<div style="font-size:12px;color:#64748b;margin-top:4px;">代码 %s · 持有第 %d 天 · 收益 %+.2f%%</div>'
                  '</div>') % (r["name"], r["code"], r["held_days"], r["ret"] * 100)
    html = ('<div style="background:#eef1f7;padding:24px;font-family:-apple-system,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">'
            '<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(15,23,42,.08);">'
            '<div style="background:linear-gradient(135deg,#1e1b4b,#4f46e5,#7c3aed);padding:24px 22px;color:#fff;">'
            '<div style="font-size:19px;font-weight:800;">&#128200; ETF 买入信号</div>'
            '<div style="font-size:13px;opacity:.85;margin-top:6px;">%s · MA%d/MA%d 金叉 + MACD 过滤 · 持有 %d 天或止盈 15%%</div></div>'
            '<div style="padding:20px 22px;">'
            '<div style="font-size:13px;color:#64748b;margin-bottom:12px;">今日 %d 只标的出现买入信号：</div>'
            '%s'
            '<div style="margin-top:14px;padding:12px 14px;background:#f8fafc;border-radius:10px;font-size:12.5px;color:#475569;line-height:1.7;">'
            '&#128161; <b>操作建议</b>：支付宝搜索对应代码，今日 15:00 前买入按当日净值确认；持有满 %d 天或涨幅达 +15%% 时止盈卖出。<br>'
            '&#128202; <b>策略依据</b>：历史综合胜率 66.0%%，最大回撤 5.8%%，夏普 0.90，卡玛 1.38。</div></div>'
            '<div style="padding:14px 22px;background:#f8fafc;font-size:11px;color:#94a3b8;line-height:1.6;">'
            '本邮件由 ETF 量化系统自动发送 · 数据来源：天天基金 · 仅供研究参考，不构成投资建议 '
            '<a href="https://jivonkiang.github.io/etf-quant/" style="color:#6366f1;">查看完整面板 &rarr;</a></div>'
            '</div></div>') % (NOW, f, s, hd, len(buys), cards, hd)
    return html


def send_mail(subject, body, html=False):
    import smtplib
    from email.mime.text import MIMEText
    host = os.environ.get("MAIL_SERVER")
    if not host:
        return False
    port = int(os.environ.get("MAIL_PORT", 465))
    user = os.environ.get("MAIL_USERNAME", "")
    pwd = os.environ.get("MAIL_PASSWORD", "")
    to = os.environ.get("MAIL_TO", user)
    msg = MIMEText(body, "html" if html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        s = smtplib.SMTP(host, port, timeout=20)
        s.starttls()
    s.login(user, pwd)
    s.sendmail(user, [to], msg.as_string())
    s.quit()
    return True


def load_positions():
    path = os.path.join(os.path.dirname(__file__), "positions.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return []
    return []


def fetch_realtime(codes):
    """腾讯实时行情，返回 {场内code: {name, price, change_pct}}"""
    url = 'http://qt.gtimg.cn/q=' + ','.join(codes)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    txt = urllib.request.urlopen(req, timeout=10).read().decode('gbk', 'ignore')
    result = {}
    for line in txt.strip().split(';'):
        line = line.strip()
        if not line:
            continue
        m = re.search(r'v_(\w+)="(.*?)"', line)
        if not m:
            continue
        code = m.group(1)
        p = m.group(2).split('~')
        if len(p) > 32:
            result[code] = {'name': p[1], 'price': p[3], 'change_pct': p[32]}
    return result


def build_daily_report(rows):
    """生成每日建议邮件（含信号 + 持仓实时走势），无买入信号时也发"""
    f, s, hd = config.STRATEGY["fast"], config.STRATEGY["slow"], config.STRATEGY["hold_days"]
    buys = [r for r in rows if r["state"] == "BUY"]
    lines = ["【ETF 每日建议】%s" % NOW, ""]
    if buys:
        lines.append("今日买入信号：")
        for b in buys:
            lines.append("- %s（%s）：MA%d/MA%d 金叉，建议买入持有 %d 天" % (b["name"], b["code"], f, s, hd))
    else:
        lines.append("今日无买入信号（%d 只标的均为观望/持有）。" % len(config.POOL))
    lines.append("")
    pos = load_positions()
    if pos:
        lines.append("你的持仓（今日实时涨跌）：")
        etf_codes = list(dict.fromkeys(config.ETF_MAP.get(p["code"], p["code"]) for p in pos))
        try:
            rt = fetch_realtime(etf_codes)
        except Exception:
            rt = {}
        for p in pos:
            etf_code = config.ETF_MAP.get(p["code"], p["code"])
            real = rt.get(etf_code)
            held = (datetime.date.today() - datetime.date.fromisoformat(p["buy_date"])).days
            if real:
                lines.append("- %s（%s）：持有%d天，今日 %s%%" % (p["name"], p["code"], held, real["change_pct"]))
            else:
                lines.append("- %s（%s）：持有%d天" % (p["name"], p["code"], held))
    lines.append("")
    lines.append("查看面板 / 回报操作：https://jivonkiang.github.io/etf-quant/")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = check_all()
    out_json = os.path.join(os.path.dirname(__file__), "signals.json")
    json.dump(rows, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    buys = [r for r in rows if r["state"] == "BUY"]
    no_mail = "--no-mail" in sys.argv
    if config.EMAIL_ENABLED and not no_mail:
        if buys:
            body = build_email_html(rows)
            ok = send_mail(f"📈 ETF买入信号 {NOW}：" + "、".join(r["name"] for r in buys), body, html=True)
        else:
            body = build_daily_report(rows)
            ok = send_mail(f"📊 ETF每日建议 {NOW}（无买入信号）", body)
        print("\n[邮件通知]" + ("已发送" if ok else "未配置 SMTP，跳过"))
