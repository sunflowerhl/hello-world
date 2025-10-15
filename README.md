# 港股K线与交易点绘图工具

该仓库提供一个命令行程序，可以从雪球抓取最新的港股股票K线数据，并在同一时间轴上叠加手动整理的买卖交易记录（例如根据交易截图整理成CSV/JSON），最终生成带有买卖标记的K线图。

## 环境准备

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell（例如在 VS/VS Code 终端内）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果使用经典命令提示符 (cmd)，激活命令改为 `\.venv\Scripts\activate.bat`。

> Windows 11 默认缺少 IANA 时区数据库，`requirements.txt` 中包含的 `tzdata` 会在安装依赖时一并补齐，保证 `zoneinfo` 可以正常工作。

如果在运行脚本时看到 `ModuleNotFoundError: No module named 'mplfinance'` 或类似提示，请确认已经在激活虚拟环境后执行过 `pip install -r requirements.txt`，或单独安装缺失的依赖：

```powershell
pip install mplfinance
```

## 准备交易数据

将交易截图中的信息（时间、成交价格、买入或卖出方向，可选备注与数量）整理成CSV或JSON文件。

CSV示例：

```csv
time,price,side,quantity,note
2024-06-03 09:35,328.6,buy,100,开盘买入
2024-06-03 10:15,335.2,sell,100,止盈
```

JSON示例：

```json
[
  {"time": "2024-06-03T09:35:00", "price": 328.6, "side": "buy", "quantity": 100, "note": "开盘买入"},
  {"time": "2024-06-03T10:15:00", "price": 335.2, "side": "sell", "quantity": 100, "note": "止盈"}
]
```

时间字段会自动转换为香港时区（Asia/Hong_Kong）。如果文件中已经带有时区，会被统一转换。

## 运行示例

```bash
python src/plot_xueqiu_trades.py HK00700 \
  --period day \
  --count -120 \
  --trades trades.csv \
  --output tencent_trades.png
```

- `symbol`：雪球的股票代码（如腾讯控股为 `HK00700`）。
- `--period`：K线周期（支持 `day`, `week`, `month`, `60m`, `30m`, `15m`, `5m`, `1m`）。
- `--count`：拉取的K线数量，负数表示向历史回溯。
- `--trades`：交易数据文件路径，可选。
- `--output`：输出图像路径，默认 `kline_with_trades.png`。

程序会先访问雪球主页以获得必要的Cookie，然后调用K线接口获取数据，再利用 `mplfinance` 绘制K线图：

- 绿色上箭头标记买点，红色下箭头标记卖点；
- 右侧纵轴叠加以持仓和成交生成的收益变化曲线；
- 同时在图中注释备注信息。

若交易数据未提供 `quantity` 字段，则默认按 1 股（或 1 手）计算收益曲线。

## 注意事项

- 雪球接口需要在短时间内多次访问时设置合理的请求间隔，避免触发风控。
- 如果运行环境无法访问互联网，可以提前下载所需数据并缓存，或使用其他数据源替换 `XueqiuClient` 中的实现。
- 交易截图的识别（OCR）需要额外工具，建议人工整理交易数据后使用本程序绘图。
