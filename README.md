# 证券市场分析报告（交互式网页）

一个本地运行的 Python 网页工具：自动抓取免费公开数据，从**宏观经济、供给与需求、机构行为**三个角度生成证券市场分析报告，你可以随时刷新数据、更新报告。

## 功能

- 📊 **市场全景**：主要指数涨跌、风格（大盘/小盘、成长/价值）、行业轮动、估值分位、股债性价比、两市成交额
- 🏛 **宏观经济**：GDP、CPI/PPI、PMI、M1/M2、社融、LPR、财政收支、固投、社零、工业、出口、中美国债收益率
- ⚖️ **供需与资金**：IPO/回购（供给）vs 两融/北向/ETF/新发基金/新增开户（需求）
- 🏦 **机构行为**：杠杆资金、外资、被动资金、公募供给、产业资本分门别类
- 🧭 **总结与展望**：自动信号打分 + 自动摘要 + 你自己写"本期观点"（保存在本地）
- 📤 **导出**：一键生成 Markdown 报告快照

## 快速开始

```bash
cd market_report
python -m pip install -r requirements.txt
```

更新全部数据（首次约 2-3 分钟，之后很快）：

```bash
python scripts/update_data.py
```

启动网页：

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。之后每次打开网页，程序会按数据新鲜度自动增量更新；也可以在左侧点"立即更新全部数据"。

只生成 Markdown 报告（不打开网页）：

```bash
python scripts/gen_report.py --start 2026-01-01
```

## 数据源

全部为免费公开接口（AKShare 封装）：新浪财经、腾讯财经、同花顺、乐咕乐股、巨潮资讯、东方财富数据中心、国家统计局、央行、中国结算等。

已知限制（网页中也有标注）：
- 北向资金净买入自 2024 年 8 月起官方停止披露，此后只能看历史或手动补充；
- 公募/险资/社保的季度持仓没有免费全量接口，需要手动填 `data/manual/manual_institutions.csv`；
- 某些免费接口偶尔会失效，程序会自动使用本地缓存并提示，不影响的指标照常展示；
- 两市成交额是从启用本工具开始逐日快照累积的，历史越长越有参考意义。

## 手动补充数据

见 `data/manual/README.md`。把官方口径的数字填进去，刷新网页即可展示。

## 定时更新（可选）

Windows 可以用"任务计划程序"定时运行：

```bat
cd /d D:\codex\market_report && python scripts\update_data.py
```

然后定时生成报告：

```bat
cd /d D:\codex\market_report && python scripts\gen_report.py
```

## 目录结构

```text
market_report/
├─ app.py                  # Streamlit 网页入口
├─ config.yaml             # 指数/ETF观察池/缓存策略配置
├─ requirements.txt
├─ src/
│  ├─ fetcher.py           # AKShare 取数 + 缓存 + 手动数据
│  ├─ indicators.py        # 指标计算
│  ├─ charts.py            # Plotly 图表
│  ├─ narrative.py         # 自动摘要
│  ├─ report_builder.py    # Markdown 报告
│  └─ ui.py                # 页面渲染
├─ scripts/
│  ├─ update_data.py       # 命令行更新数据
│  └─ gen_report.py        # 命令行生成报告
├─ data/
│  ├─ cache/               # 自动生成的数据缓存
│  ├─ manual/              # 手动 CSV 模板
│  └─ notes.md             # 你的本期观点
└─ reports/                # 生成的报告
```

## 免责声明

本工具基于免费公开数据自动生成，仅供研究参考，不构成投资建议。数据可能存在延迟、缺失或口径差异。
