# ETF 量化信号策略（支付宝 C 类 ETF 联接）

> MA10/30 金叉买入 + 持有 20 天卖出，历史综合胜率 **63.1%**（逐年 54%~74%）。
> 每日凌晨定时检测信号，出买入信号邮件通知；GitHub Pages 可视化展示每日信号与回测结果。

## 在线页面

**https://jivonkiang.github.io/etf-quant/** （电脑 / 手机均可访问，每日自动更新）

## 文件结构

```
etf-quant/
├── config.py               # 标的池(7只) + 策略参数
├── etf_backtest.py         # 回测引擎
├── signal_monitor.py       # 信号监控（每日检测金叉）
├── build_site.py           # 生成 Pages 前端 index.html
├── index.html              # 前端页面（build_site 自动生成）
├── 回测报告.md             # 完整回测结果
└── .github/workflows/
    └── signal-check.yml    # 定时任务 + Pages 部署
```

## 策略规则

- **标的池**：7 只支付宝可买、C 类、持有≥7 天免赎回费的 ETF 联接基金（宽基+跨境+红利+半导体）。
- **买入**：MA10 上穿 MA30（金叉）。
- **持有**：20 个自然日（≥7 天，规避 C 类惩罚赎回费）。
- **卖出**：满 20 天机械卖出。
- **胜率**：综合 63.1%，平均每笔 +1.26%，逐年 54%~74%。

## 定时任务

GitHub Actions 每天自动运行两次（北京时间）：

| 时间 | 动作 |
|------|------|
| 2:00 | 完整跑信号检测 + 更新 Pages |
| 2:30 | 用最新数据再验证 + 再次更新 Pages |

出买入信号时，由 WorkBuddy 定时任务通过 agent-mail 发邮件通知。

## 本地运行

```bash
python signal_monitor.py           # 打印今日信号报告
python signal_monitor.py --json    # 输出 JSON
python build_site.py               # 生成前端 index.html
python etf_backtest.py 10 30 20    # 跑回测
```

## 风险提示

历史回测不代表未来收益；胜率 63.1% 是统计值，单笔仍可能亏损。建议小额试水、分散标的。
