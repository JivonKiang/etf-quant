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


def state_of(arr):
    """返回 (state, detail)，state: BUY/HOLDING/SELL_READY/WAIT
    固定持有 hold_days 天：金叉买入 -> 持有 -> 满期卖出 -> 空仓等下一次金叉"""
    nav = [a["nav"] for a in arr]
    dates = [a["date"] for a in arr]
    mf = ma(nav, config.STRATEGY["fast"])
    ms = ma(nav, config.STRATEGY["slow"])
    slow = config.STRATEGY["slow"]
    buy_idx = None
    for i in range(len(nav) - 1, slow - 1, -1):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        if mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]:
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
    if held < config.STRATEGY["hold_days"]:
        return "HOLDING", detail                  # 持有中
    if held == config.STRATEGY["hold_days"]:
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
    L += ["", f"> 策略：MA{config.STRATEGY['fast']}/MA{config.STRATEGY['slow']} 金叉买入，持有 {config.STRATEGY['hold_days']} 天卖出；历史综合胜率 63.1%。"]
    return "\n".join(L)


def send_mail(subject, body):
    import smtplib
    from email.mime.text import MIMEText
    host = os.environ.get("MAIL_SERVER")
    if not host:
        return False
    port = int(os.environ.get("MAIL_PORT", 465))
    user = os.environ.get("MAIL_USERNAME", "")
    pwd = os.environ.get("MAIL_PASSWORD", "")
    to = os.environ.get("MAIL_TO", user)
    msg = MIMEText(body, "plain", "utf-8")
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


if __name__ == "__main__":
    rows = check_all()
    out_json = os.path.join(os.path.dirname(__file__), "signals.json")
    json.dump(rows, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    buys = [r for r in rows if r["state"] == "BUY"]
    if buys and config.EMAIL_ENABLED:
        body = render_markdown(rows)
        ok = send_mail(f"ETF买入信号 {NOW}：" + "、".join(r["name"] for r in buys), body)
        print("\n[邮件通知]" + ("已发送" if ok else "未配置 SMTP，跳过"))
