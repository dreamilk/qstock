# qstock 量化策略重构方案

**目标：** 从4个同质化"涨停回调"策略，重构为规范的多因子量化系统。

**架构：**
```
qstock/
├── config.py          # 集中配置
├── main.py            # 多策略编排入口
├── market_state.py    # 市场牛熊判断 + 自动仓位
├── risk/
│   ├── stops.py       # ATR动态止损
│   └── sizing.py      # 仓位管理
├── strategy/
│   ├── base.py        # 增强基类（含market_state集成）
│   ├── value.py       # 多因子价值策略（Piotroski + ROE + PE + 股息）
│   ├── momentum.py    # 截面动量策略
│   ├── sector.py      # 板块动量轮动
│   └── limitup.py     # 合并原4个涨停策略（加market filter）
├── backtest/
│   ├── engine.py      # 简单回测引擎
│   └── metrics.py     # 夏普/回撤/胜率/IC
└── pick.py → 保留兼容
```

**实施步骤（4个阶段）：**
1. 新建 market_state + risk层
2. 重写 value 策略 + 新增 momentum/sector
3. 整合原涨停策略
4. 回测框架 + main.py
