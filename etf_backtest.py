# -*- coding: utf-8 -*-
"""ETF 量化策略回测引擎
标的：支付宝可买、C类、7天免赎回费的 ETF 联接基金
数据源：天天基金 pingzhongdata（累计净值）
"""
import urllib.request, re, json, datetime, os, sys

POOL = {
    "004348": "南方中证500ETF联接C",
    "001593": "天弘创业板ETF联接C",
    "005733": "华夏上证50ETF联接C",
    "006479": "广发纳斯达克100ETF联接C",
    "006075": "博时标普500ETF联接C",
    "007801": "大成中证红利指数C",
    "007301": "国联安半导体ETF联接C",
}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "nav_cache")


def fetch(code):
    cache = os.path.join(CACHE_DIR, code + ".json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                               "Referer": "http://fund.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "ignore")
    # 优先累计净值，缺失则用单位净值
    m = re.search(r"var Data_ACWorthTrend = (\[.*?\]);", txt, re.S)
    if m:
        raw = json.loads(m.group(1))  # [[ms, nav], ...]
        arr = [{"date": datetime.datetime.utcfromtimestamp(x[0] / 1000).date().isoformat(),
                "nav": x[1]} for x in raw]
    else:
        m = re.search(r"var Data_netWorthTrend = (\[.*?\]);", txt, re.S)
        raw = json.loads(m.group(1))
        arr = [{"date": datetime.datetime.utcfromtimestamp(x["x"] / 1000).date().isoformat(),
                "nav": x["y"]} for x in raw]
    os.makedirs(CACHE_DIR, exist_ok=True)
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


def backtest(arr, fast=60, slow=120, min_hold=7, take_profit=None, stop_loss=None):
    """金叉买入、死叉卖出；min_hold 自然日锁定"""
    dates = [a["date"] for a in arr]
    nav = [a["nav"] for a in arr]
    mf = ma(nav, fast)
    ms = ma(nav, slow)

    trades = []
    pos = None  # {buy_idx, buy_nav, buy_date}
    for i in range(slow, len(nav)):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        cross_up = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
        cross_dn = mf[i - 1] >= ms[i - 1] and mf[i] < ms[i]

        if pos is None and cross_up:
            pos = {"buy_idx": i, "buy_nav": nav[i], "buy_date": dates[i]}
        elif pos is not None:
            d0 = datetime.date.fromisoformat(pos["buy_date"])
            d1 = datetime.date.fromisoformat(dates[i])
            held = (d1 - d0).days
            sell = False
            reason = ""
            ret = nav[i] / pos["buy_nav"] - 1
            if held >= min_hold and cross_dn:
                sell, reason = True, "死叉"
            if take_profit is not None and held >= min_hold and ret >= take_profit:
                sell, reason = True, f"止盈{ret*100:.0f}%"
            if stop_loss is not None and held >= min_hold and ret <= stop_loss:
                sell, reason = True, f"止损{ret*100:.0f}%"
            if sell:
                trades.append({"buy_date": pos["buy_date"], "sell_date": dates[i],
                               "ret": ret, "hold_days": held, "reason": reason})
                pos = None
    # 期末仍在持仓则按最后净值平仓
    if pos is not None:
        ret = nav[-1] / pos["buy_nav"] - 1
        d0 = datetime.date.fromisoformat(pos["buy_date"])
        held = (datetime.date.fromisoformat(dates[-1]) - d0).days
        trades.append({"buy_date": pos["buy_date"], "sell_date": dates[-1],
                       "ret": ret, "hold_days": held, "reason": "期末平仓"})
    return trades


def stats(trades):
    n = len(trades)
    if n == 0:
        return None
    win = sum(1 for t in trades if t["ret"] > 0)
    win_rate = win / n
    avg_ret = sum(t["ret"] for t in trades) / n
    avg_hold = sum(t["hold_days"] for t in trades) / n
    min_hold_ok = all(t["hold_days"] >= 7 for t in trades)
    total_ret = 1.0
    for t in trades:
        total_ret *= (1 + t["ret"])
    return {"n": n, "win": win, "win_rate": win_rate, "avg_ret": avg_ret,
            "avg_hold": avg_hold, "min_hold_ok": min_hold_ok, "total_ret": total_ret - 1}


if __name__ == "__main__":
    fast, slow, min_hold = 60, 120, 7
    tp, sl = None, None
    if len(sys.argv) > 1:
        fast, slow = int(sys.argv[1]), int(sys.argv[2])
    if len(sys.argv) > 3:
        min_hold = int(sys.argv[3])
    if len(sys.argv) > 5:
        tp = float(sys.argv[4]) if sys.argv[4] != "none" else None
        sl = float(sys.argv[5]) if sys.argv[5] != "none" else None

    print(f"策略: MA{fast}/{slow} 金叉买入, 死叉卖出 | 锁定期={min_hold}天 | 止盈={tp} 止损={sl}")
    print("=" * 100)
    total_win = total_n = 0
    rows = []
    for code, name in POOL.items():
        try:
            arr = fetch(code)
        except Exception as e:
            print(f"{code} {name}: 数据失败 {e}")
            continue
        arr = [a for a in arr if a["date"] >= "2020-01-01"]
        tr = backtest(arr, fast, slow, min_hold, tp, sl)
        s = stats(tr)
        if not s:
            print(f"{code} {name}: 无交易")
            continue
        rows.append((code, name, s))
        total_win += s["win"]; total_n += s["n"]
        print(f"{code} {name}\t交易{s['n']}笔\t胜率{s['win_rate']*100:.1f}%\t平均收益{s['avg_ret']*100:+.2f}%\t平均持有{s['avg_hold']:.0f}天\t累计{s['total_ret']*100:+.1f}%")
    if total_n:
        print("=" * 100)
        print(f"合计: {total_n} 笔交易, 综合胜率 {total_win/total_n*100:.1f}%")
