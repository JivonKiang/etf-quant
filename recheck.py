# -*- coding: utf-8 -*-
"""当前配置回测复核 + 参数/标的探索（临时脚本，可复用）
用法: python recheck.py
"""
import datetime, statistics
import signal_monitor as SM
import config

def fetch_all(pool):
    return {c: [a for a in SM.fetch(c) if a["date"] >= "2020-01-01"] for c in pool}

def gen(pool, fast, slow, hold, stop, tp, macd=True):
    fund_ret = {}
    all_dates = set()
    all_trades = []
    for code in pool:
        arr = fetch_all(pool)[code]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        mf = SM.ma(nav, fast)
        ms = SM.ma(nav, slow)
        hist = SM.macd_hist(nav)
        holding = [False] * len(nav)
        pos = None
        for i in range(max(slow, 26), len(nav)):
            if mf[i] is None or ms[i] is None or mf[i-1] is None or ms[i-1] is None:
                continue
            cross = mf[i-1] <= ms[i-1] and mf[i] > ms[i]
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
                    all_trades.append({"code": code, "ret": ret, "bd": pos["bd"],
                                       "sd": dates[i], "hold": held, "year": pos["bd"][:4]})
                    pos = None
        ret = {}
        for i in range(1, len(nav)):
            ret[dates[i]] = (nav[i]/nav[i-1] - 1) if holding[i] else 0.0
        fund_ret[code] = ret
        all_dates.update(dates)
    ds = sorted(all_dates)
    navv = 1.0
    equity = []
    daily = []
    for d in ds:
        rs = [fund_ret[c].get(d, 0.0) for c in pool]
        r = sum(rs)/len(rs)
        daily.append(r)
        navv *= (1 + r)
        equity.append([d, round(navv, 4)])
    return equity, all_trades, daily

def metrics(equity, trades, daily):
    days = (datetime.date.fromisoformat(equity[-1][0]) - datetime.date.fromisoformat(equity[0][0])).days
    cagr = (equity[-1][1]/equity[0][1]) ** (365/days) - 1
    peak = 0; mdd = 0
    for d, nav in equity:
        peak = max(peak, nav); mdd = min(mdd, nav/peak - 1)
    mdd = abs(mdd)
    sd = statistics.stdev(daily) if len(daily) > 1 else 0
    vol = sd * (252 ** 0.5)
    sharpe = (cagr - 0.02)/vol if vol > 0 else 0
    calmar = cagr/mdd if mdd > 0 else 0
    wins = [t["ret"] for t in trades if t["ret"] > 0]
    losses = [t["ret"] for t in trades if t["ret"] <= 0]
    pf = sum(wins)/abs(sum(losses)) if losses else 0
    plr = (sum(wins)/len(wins)) / (abs(sum(losses))/len(losses)) if wins and losses else 0
    win_rate = sum(1 for t in trades if t["ret"] > 0)/len(trades) if trades else 0
    avg = sum(t["ret"] for t in trades)/len(trades) if trades else 0
    return {"total": equity[-1][1]-1, "cagr": cagr, "mdd": mdd, "sharpe": sharpe,
            "calmar": calmar, "pf": pf, "plr": plr, "win_rate": win_rate,
            "avg": avg, "trades": len(trades)}

def report(tag, pool, fast, slow, hold, stop, tp, macd=True):
    eq, tr, daily = gen(pool, fast, slow, hold, stop, tp, macd)
    m = metrics(eq, tr, daily)
    print("[%s] MA%d/%d 持有%d 止损%s 止盈%s macd=%s" % (tag, fast, slow, hold, stop, tp, macd))
    print("  累计%+.1f%% 年化%.1f%% 回撤%.1f%% 夏普%.2f 卡玛%.2f 盈亏比%.2f 盈利因子%.2f 胜率%.1f%% 均笔%+.2f%% 交易%d笔" % (
        m["total"]*100, m["cagr"]*100, m["mdd"]*100, m["sharpe"], m["calmar"], m["plr"], m["pf"],
        m["win_rate"]*100, m["avg"]*100, m["trades"]))
    by_year = {}
    for t in tr:
        by_year.setdefault(t["year"], []).append(t["ret"])
    ys = sorted(by_year)
    seg = "  ".join("%s:%d/%d(%.0f%%)" % (y, sum(1 for r in by_year[y] if r>0), len(by_year[y]),
                    sum(1 for r in by_year[y] if r>0)/len(by_year[y])*100) for y in ys)
    print("  分段胜率 -> " + seg)
    return m, tr

if __name__ == "__main__":
    P = config.POOL
    print("=== 当前定稿配置 ===")
    report("当前", P, config.STRATEGY["fast"], config.STRATEGY["slow"],
           config.STRATEGY["hold_days"], None, config.STRATEGY["take_profit"], config.STRATEGY["macd_filter"])
