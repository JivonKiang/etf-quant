# -*- coding: utf-8 -*-
"""持仓买卖信号提醒：检测 positions.json 里每只持仓的卖出/加仓信号
卖出：止盈+15% / 止损-8% / 收盘跌破MA20
加仓：收盘突破MA30 / 回踩MA20不破且MACD红柱
"""
import json, os, datetime, sys
import config
import signal_monitor as SM


def load_positions():
    path = os.path.join(os.path.dirname(__file__), "positions.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return []
    return []


def check_position_signals():
    alerts = []
    for p in load_positions():
        code = p["code"]
        try:
            arr = SM.fetch(code)
        except Exception as e:
            alerts.append({"code": code, "name": p["name"], "type": "ERROR", "reason": str(e)})
            continue
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        m20 = SM.ma(nav, 20)
        m30 = SM.ma(nav, 30)
        hist = SM.macd_hist(nav)
        i = len(nav) - 1
        cur = nav[i]
        prev = nav[i - 1] if i > 0 else cur
        ret = cur / p["buy_nav"] - 1
        held = (datetime.date.today() - datetime.date.fromisoformat(p["buy_date"])).days
        base = {"code": code, "name": p["name"], "ret": round(ret, 4), "held_days": held,
                "nav": round(cur, 4), "ma20": round(m20[i], 4) if m20[i] else None,
                "ma30": round(m30[i], 4) if m30[i] else None, "date": dates[i]}

        # ---- 卖出信号 ----
        if ret >= config.STRATEGY["take_profit"]:
            alerts.append({**base, "type": "SELL", "reason": "止盈 +15%"})
        elif ret <= -0.08:
            alerts.append({**base, "type": "SELL", "reason": "止损 -8%"})
        elif held >= 7 and m20[i] and m20[i - 1] and prev > m20[i - 1] and cur < m20[i]:
            alerts.append({**base, "type": "SELL", "reason": "收盘跌破 MA20"})

        # ---- 加仓信号 ----
        if m30[i] and m30[i - 1] and prev <= m30[i - 1] and cur > m30[i]:
            alerts.append({**base, "type": "ADD", "reason": "突破 MA30 压力位"})
        elif m20[i] and hist[i] > 0 and 0.98 * m20[i] <= cur <= 1.02 * m20[i]:
            alerts.append({**base, "type": "ADD", "reason": "回踩 MA20 获支撑"})

    return alerts


def render_report(alerts):
    if not alerts:
        return "今日无买卖信号。"
    L = ["# 持仓买卖提醒 — %s" % datetime.date.today(), ""]
    sells = [a for a in alerts if a["type"] == "SELL"]
    adds = [a for a in alerts if a["type"] == "ADD"]
    if sells:
        L.append("## 🔴 卖出信号")
        for a in sells:
            L.append("- **%s**（%s）：%s，当前收益 %+.2f%%（净值 %.4f，持有 %d 天）" % (
                a["name"], a["code"], a["reason"], a["ret"] * 100, a["nav"], a["held_days"]))
        L.append("")
    if adds:
        L.append("## 🟢 加仓信号")
        for a in adds:
            L.append("- **%s**（%s）：%s，当前收益 %+.2f%%（净值 %.4f）" % (
                a["name"], a["code"], a["reason"], a["ret"] * 100, a["nav"]))
        L.append("")
    return "\n".join(L)


def send_alerts(alerts):
    if not alerts:
        return False
    body = render_report(alerts)
    sells = [a for a in alerts if a["type"] == "SELL"]
    adds = [a for a in alerts if a["type"] == "ADD"]
    tag = []
    if sells:
        tag.append("卖")
    if adds:
        tag.append("加仓")
    subject = "📢 ETF持仓提醒 " + "/".join(tag) + " " + str(datetime.date.today())
    return SM.send_mail(subject, body, html=False)


if __name__ == "__main__":
    alerts = check_position_signals()
    print(render_report(alerts))
    if alerts and "--no-mail" not in sys.argv:
        ok = send_alerts(alerts)
        print("\n[邮件]" + ("已发送" if ok else "未配置 SMTP，跳过"))
