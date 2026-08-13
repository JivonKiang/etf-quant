# ETF 量化信号策略（支付宝 C 类 ETF 联接）

> MA10/30 金叉 + MACD 柱>0 买入 + 持有 20 天（或 +15% 止盈）卖出，历史综合胜率 **66.0%**（逐年 56%~80%）。
> 每个交易日 14:00 更新数据、14:45 发建议邮件；GitHub Pages 可视化展示每日信号与回测结果。

## 在线页面

**https://jivonkiang.github.io/etf-quant/** （电脑 / 手机均可访问，每日自动更新）

## 文件结构

```
etf-quant/
├── config.py               # 标的池(8只) + 策略参数 + ETF_MAP(场外→场内映射)
├── etf_backtest.py         # 回测引擎
├── optimize.py             # 参数扫描引擎
├── signal_monitor.py       # 信号监控（每日检测金叉 + 发建议邮件）
├── position_alert.py       # 持仓买卖提醒（止盈/止损/破位/加仓）
├── build_site.py           # 生成 Pages 前端 index.html
├── index.html              # 前端页面（build_site 自动生成）
├── positions.json          # 用户实际持仓（手动回报录入）
├── signals.json            # 每日信号（自动生成）
├── 回测报告.md             # 完整回测结果
└── .github/workflows/
    └── signal-check.yml    # 定时任务 + Pages 部署
```

## 策略规则

- **标的池**：8 只支付宝可买、C 类、持有≥7 天免赎回费的 ETF 联接基金（宽基 + 跨境 + 红利 + 半导体 + 科创50）。
- **买入**：MA10 上穿 MA30（金叉）**且 MACD 柱状图 > 0**。
- **持有**：20 个自然日（≥7 天，规避 C 类惩罚赎回费）。
- **卖出**：满 20 天机械卖出，或持有期内涨幅达 +15% 提前止盈。
- **胜率**：综合 66.0%，平均每笔 +1.64%，逐年 56%~80%。

## 定时任务

GitHub Actions 每个交易日（周一~周五，北京时间）自动运行两次：

| 时间 | 动作 |
|------|------|
| 14:00 | 拉最新净值 + 更新 Pages（不发邮件） |
| 14:45 | 发当日建议邮件（信号 + 持仓实时涨跌）+ 更新 Pages |

另有 WorkBuddy 自动化在 14:45 用 agent-mail 兜底发送买入信号邮件。

## 本地运行

```bash
python signal_monitor.py           # 打印今日信号报告
python signal_monitor.py --json    # 输出 JSON
python signal_monitor.py --no-mail # 不发邮件（CI 14:00 档用）
python position_alert.py           # 持仓买卖提醒
python build_site.py               # 生成前端 index.html
python etf_backtest.py 10 30 20    # 跑回测
```

## 风险提示

历史回测不代表未来收益；胜率 66.0% 是统计值，单笔仍可能亏损。建议小额试水、分散标的。
