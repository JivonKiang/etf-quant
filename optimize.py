# -*- coding: utf-8 -*-
"""策略参数优化：目标夏普/卡玛最优，约束最大回撤<=10%"""
import datetime, statistics, itertools
import signal_monitor as SM
import config


def fetch_all():
    return {c: [a for a in SM.fetch(c) if a["date"] >= "2020-01-01"] for c in config.POOL}


def gen_trades_and_equity(fast, slow, hold, stop, tp, macd=True):
    """返回 (完整资金曲线, 交易列表, 日收益序列)"""
    fund_ret = {}
    all_dates = set()
    all_trades = []
    for code in config.POOL:
        arr = fetch_all()[code]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        mf = SM.ma(nav, fast)
        ms = SM.ma(nav, slow)
        hist = SM.macd_hist(nav)
        holding = [False] * len(nav)
        pos = None  # {bi, bn, bd}
        for i in range(max(slow, 26), len(nav)):
            if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
                continue
            cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
            if macd:
                cross = cross and hist[i] > 0
            if pos is None:
                if cross:
                    pos = {"bi": i, "bn": nav[i], "bd": dates[i]}
                    holding[i] = True
            else:
                holding[i] = True
                d0 = datetime.date.fromisoformat(pos["bd"])
                d1 = datetime.date.fromisoformat(dates[i])
                held = (d1 - d0).days
                ret = nav[i] / pos["bn"] - 1
                sell = False
                if stop is not None and ret <= stop:
                    sell = True
                elif tp is not None and ret >= tp:
                    sell = True
                elif held >= hold:
                    sell = True
                if sell:
                    all_trades.append({"ret": ret, "bd": pos["bd"], "sd": dates[i], "hold": held})
                    pos = None
        ret = {}
        for i in range(1, len(nav)):
            ret[dates[i]] = (nav[i] / nav[i - 1] - 1) if holding[i] else 0.0
        fund_ret[code] = ret
        all_dates.update(dates)
    ds = sorted(all_dates)
    navv = 1.0
    equity = []
    daily = []
    for d in ds:
        rs = [fund_ret[c].get(d, 0.0) for c in config.POOL]
        r = sum(rs) / len(rs)
        daily.append(r)
        navv *= (1 + r)
        equity.append([d, round(navv, 4)])
    return equity, all_trades, daily


def metrics(equity, trades, daily):
    days = (datetime.date.fromisoformat(equity[-1][0]) - datetime.date.fromisoformat(equity[0][0])).days
    cagr = (equity[-1][1] / equity[0][1]) ** (365 / days) - 1
    peak = 0
    mdd = 0
    for d, nav in equity:
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
    mdd = abs(mdd)
    sd = statistics.stdev(daily) if len(daily) > 1 else 0
    vol = sd * (252 ** 0.5)
    sharpe = (cagr - 0.02) / vol if vol > 0 else 0
    calmar = cagr / mdd if mdd > 0 else 0
    wins = [t["ret"] for t in trades if t["ret"] > 0]
    losses = [t["ret"] for t in trades if t["ret"] <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 0
    win_rate = sum(1 for t in trades if t["ret"] > 0) / len(trades) if trades else 0
    return {"cagr": cagr, "mdd": mdd, "vol": vol, "sharpe": sharpe, "calmar": calmar,
            "pf": pf, "win_rate": win_rate, "trades": len(trades)}


if __name__ == "__main__":
    data = fetch_all()
    # 第一轮：扫 均线 x 持有期（无止损止盈）
    print("=== 第一轮：均线 x 持有期（无止损止盈）===")
    results = []
    for (f, s) in [(5, 20), (10, 20), (10, 30), (20, 60), (30, 90), (60, 120)]:
        for hold in [10, 15, 20, 30, 45]:
            eq, tr, daily = gen_trades_and_equity(f, s, hold, None, None)
            m = metrics(eq, tr, daily)
            m.update({"fast": f, "slow": s, "hold": hold, "stop": None, "tp": None})
            results.append(m)
    # 筛选回撤<=10%，按夏普排序
    ok = [r for r in results if r["mdd"] <= 0.10]
    ok.sort(key=lambda x: -x["sharpe"])
    print("回撤<=10% 的配置，按夏普排序 Top10：")
    for r in ok[:10]:
        print("  MA%d/%d 持有%d天: 年化%.1f%% 回撤%.1f%% 夏普%.2f 卡玛%.2f 胜率%.0f%% 交易%d" % (
            r["fast"], r["slow"], r["hold"], r["cagr"]*100, r["mdd"]*100, r["sharpe"], r["calmar"], r["win_rate"]*100, r["trades"]))
    print()
    # 按卡玛排序
    ok2 = sorted(ok, key=lambda x: -x["calmar"])
    print("回撤<=10% 的配置，按卡玛排序 Top5：")
    for r in ok2[:5]:
        print("  MA%d/%d 持有%d天: 年化%.1f%% 回撤%.1f%% 夏普%.2f 卡玛%.2f" % (
            r["fast"], r["slow"], r["hold"], r["cagr"]*100, r["mdd"]*100, r["sharpe"], r["calmar"]))
