# ETF 量化信号策略（支付宝 C 类 ETF 联接）

> MA10/30 金叉买入 + 持有 20 天卖出，历史综合胜率 59.8%（逐年 52%~72%）。
> 每日定时检测信号，出买入信号时邮件通知。

## 文件结构

```
etf-quant/
├── config.py               # 标的池 + 策略参数
├── etf_backtest.py         # 回测引擎（可独立跑回测）
├── signal_monitor.py       # 信号监控（每日检测金叉，发邮件）
├── 回测报告.md             # 完整回测结果
├── .github/workflows/
│   └── signal-check.yml    # GitHub Actions 定时任务
└── nav_cache/              # 净值缓存（自动生成）
```

## 本地运行

```bash
# 查看今日信号报告
python signal_monitor.py

# 输出 JSON（供 CI / 二次开发）
python signal_monitor.py --json

# 跑回测（默认 MA10/30 + 持有20天）
python etf_backtest.py 10 30 20
```

邮件需要环境变量（可选，不配则仅打印报告）：
`SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASS` `MAIL_TO`

## 部署到 GitHub Actions（每天自动跑 + 邮件）

1. 新建仓库并推送本目录（`etf-quant/` 作为仓库根目录）。
2. 在仓库 **Settings → Secrets and variables → Actions** 添加以下 Secrets：

| Secret | 值示例（QQ 邮箱） |
|--------|------------------|
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `你的QQ号@qq.com` |
| `SMTP_PASS` | QQ邮箱「设置→账户→生成授权码」得到的授权码 |
| `MAIL_TO` | 收件邮箱（可等于 SMTP_USER） |

3. 启用 workflow（`.github/workflows/signal-check.yml`），默认每天 UTC 12:00（北京时间 20:00）自动运行。
4. 手动测试：仓库 **Actions** 页 → 选中 `ETF Signal Check` → **Run workflow**。

> 163 邮箱：`SMTP_HOST=smtp.163.com`，授权码在「设置→POP3/SMTP→开启并生成授权码」。

## 策略规则

- **买入**：MA10 上穿 MA30（金叉）。
- **持有**：20 个自然日（≥7 天，规避 C 类惩罚赎回费）。
- **卖出**：满 20 天机械卖出（不盯死叉）。
- **通知**：仅「今日金叉」触发邮件，持有中/已了结不打扰。

## 风险提示

历史回测不代表未来收益；胜率 59.8% 是统计值，单笔仍可能亏损。建议小额试水、分散标的。
