"""
数据层 — 缓存 + 列名标准化 + 基本面批量
⚠️ 本文件被覆盖过，完整重建
"""
import os, json, hashlib, logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path
import pandas as pd
import numpy as np
import akshare as ak

# ═══ Monkey-patch akshare 1.18.64 pandas 3.x bug ═══
_orig_info = ak.stock_individual_info_em
def _patched_info(symbol: str):
    """Monkey-patched stock_individual_info_em — works around pandas 3.x column bug.
    Falls back to stock_financial_abstract when the original fails."""
    try:
        return _orig_info(symbol)
    except (ValueError, KeyError):
        pass
    # Fallback: use stock_financial_abstract
    df = ak.stock_financial_abstract(symbol=symbol)
    if df.empty:
        raise ValueError(f"无法获取 {symbol} 基本面")
    latest_col = df.columns[2]  # first data column (after 选项, 指标)
    rows = {}
    for _, row in df.iterrows():
        rows[row['指标']] = row[latest_col]
    # 获取股票名称
    name = str(symbol)
    try:
        name_df = pd.DataFrame([item for item in rows.items()], columns=['指标','value'])
    except: pass
    eps = rows.get('基本每股收益', 0)
    bvps = rows.get('每股净资产', 0)
    net_profit = rows.get('净利润', 0)
    # PE/PB placeholder — 实际由 _get_one_fundamental 从 spot 补
    items = [
        {'item': '股票简称', 'value': name},
        {'item': '净资产收益率', 'value': str(rows.get('净资产收益率(ROE)', 0))},
        {'item': '毛利率', 'value': str(rows.get('毛利率', 0))},
        {'item': '净利率', 'value': str(rows.get('销售净利率', 0))},
        {'item': '资产负债率', 'value': str(rows.get('资产负债率', 0))},
        {'item': '流动比率', 'value': str(rows.get('流动比率', 0))},
        {'item': '基本每股收益', 'value': str(eps)},
        {'item': '每股净资产', 'value': str(bvps)},
        {'item': '营业收入', 'value': str(rows.get('营业总收入', 0))},
        {'item': '净利润', 'value': str(net_profit)},
        {'item': '股东权益', 'value': str(rows.get('股东权益合计(净资产)', 0))},
    ]
    return pd.DataFrame(items)
ak.stock_individual_info_em = _patched_info
# ═══ end monkey-patch ═══

logger = logging.getLogger(__name__)
CACHE_DIR = Path.home() / ".qstock_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COLUMN_MAP = {
    '开盘':'open','最高':'high','最低':'low','收盘':'close',
    '成交量':'volume','成交额':'amount','日期':'date','涨跌幅':'pct_change',
}

class DataFetcher:
    """数据获取器 — 缓存 + 重试 + 列名标准化"""

    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._trade_calendar = None
        self._spot_df = None

    # ═══ 行情 ═══

    def get_spot(self) -> pd.DataFrame:
        """全市场快照（自动缓存1小时）"""
        cache_key = f"spot_{datetime.now().strftime('%Y%m%d_%H')}"
        cached = self._load_cache(cache_key, ttl_hours=1)
        if cached is not None:
            self._spot_df = cached
            return cached
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            return df
        rename = {'代码':'code','名称':'name','最新价':'price',
                  '涨跌幅':'pct_change','总市值':'market_cap',
                  '市盈率-动态':'pe_ttm','市净率':'pb',
                  '成交量':'volume','成交额':'amount','换手率':'turnover'}
        df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
        self._save_cache(cache_key, df)
        self._spot_df = df
        return df

    def get_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        """个股日K线（前复权）"""
        cache_key = f"daily_{symbol}_{start}_{end}_{adjust}"
        cached = self._load_cache(cache_key, ttl_hours=24)
        if cached is not None:
            return cached
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end, adjust=adjust)
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns=COLUMN_MAP)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            for col in ['open','high','low','close','volume','amount']:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            self._save_cache(cache_key, df)
            return df
        except Exception as e:
            logger.warning(f"获取 {symbol} 日线失败: {e}")
            return pd.DataFrame()

    def get_index_daily(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        """指数日K"""
        cache_key = f"idx_{index_code}_{start}_{end}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached
        try:
            df = ak.stock_zh_index_daily_em(symbol=f"sh{index_code}")
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns={'date':'date','open':'open','high':'high','low':'low','close':'close','volume':'volume','amount':'amount'})
            df['date'] = pd.to_datetime(df['date'])
            mask = (df['date'] >= pd.Timestamp(start)) & (df['date'] <= pd.Timestamp(end))
            df = df[mask].sort_values('date').reset_index(drop=True)
            self._save_cache(cache_key, df)
            return df
        except Exception as e:
            logger.warning(f"指数 {index_code} 失败: {e}")
            return pd.DataFrame()

    # ═══ 基本面 ═══

    def get_fundamentals(self, symbols: List[str]) -> pd.DataFrame:
        """批量基本面（并发8线程）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        # 预加载 spot，避免并发线程各自拉取
        self._get_spot_cached()
        rows = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(self._get_one_fundamental, s): s for s in symbols}
            for f in as_completed(futures):
                r = f.result()
                if r:
                    rows.append(r)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _get_one_fundamental(self, symbol: str) -> Optional[Dict]:
        cache_key = f"fund_{symbol}"
        cached = self._load_cache(cache_key, ttl_hours=24)
        if cached is not None and not cached.empty:
            return cached.iloc[0].to_dict()
        try:
            info = ak.stock_individual_info_em(symbol=symbol)
            if info.empty:
                return None
            d = dict(zip(info['item'], info['value']))
            sf = self._safe_float
            # 兼容两个字段名（原始 API 用 '每股收益'，fallback 用 '基本每股收益'）
            _eps = sf(d.get('每股收益', 0)) or sf(d.get('基本每股收益', 0))
            _bvps = sf(d.get('每股净资产', 0))
            result = {
                'code': symbol,
                'name': d.get('股票简称', ''),
                'sector': d.get('所属行业', d.get('行业', '')),
                'market_cap': sf(d.get('总市值', 0)) / 1e8,
                'pe_ttm': sf(d.get('市盈率-动态', 0)),
                'pe_lyr': sf(d.get('市盈率-静态', 0)),
                'pb': sf(d.get('市净率', 0)),
                'roe': sf(d.get('净资产收益率', 0)),
                'gross_margin': sf(d.get('毛利率', 0)),
                'net_margin': sf(d.get('净利率', 0)),
                'debt_ratio': sf(d.get('资产负债率', 0)),
                'current_ratio': sf(d.get('流动比率', 0)),
                'dividend_yield': sf(d.get('股息率', 0)),
                'eps': _eps,
                'bvps': _bvps,
                'revenue': sf(d.get('营业收入', 0)) / 1e8,
                'net_profit': sf(d.get('净利润', 0)) / 1e8,
                'total_assets': sf(d.get('总资产', 0)) / 1e8,
            }

            # PE/PB fallback: monkey-patch API 不含这两个字段
            # 优先从 spot 缓存取，其次从 eps/bvps + 价格推算
            spot = self._get_spot_cached()
            if result['pe_ttm'] <= 0 or result['pb'] <= 0 or result['market_cap'] <= 0:
                if not spot.empty:
                    match = spot[spot['code'] == symbol]
                    if not match.empty:
                        price = match.iloc[0].get('price', 0)
                        if result['pe_ttm'] <= 0:
                            spot_pe = float(match.iloc[0].get('pe_ttm', 0))
                            if spot_pe > 0:
                                result['pe_ttm'] = spot_pe
                            elif _eps > 0 and price > 0:
                                result['pe_ttm'] = price / _eps
                        if result['pb'] <= 0:
                            spot_pb = float(match.iloc[0].get('pb', 0))
                            if spot_pb > 0:
                                result['pb'] = spot_pb
                            elif _bvps > 0 and price > 0:
                                result['pb'] = price / _bvps
                        if result['market_cap'] <= 0:
                            spot_mc = float(match.iloc[0].get('market_cap', 0))
                            if spot_mc > 0:
                                result['market_cap'] = spot_mc / 1e8
            # PE/PB fallback 已在上方内联处理
            df = pd.DataFrame([result])
            self._save_cache(cache_key, df)
            return result
        except Exception as e:
            logger.debug(f"fund {symbol} 失败: {e}")
            return None

    def _ensure_fund_pe_pb(self, symbol: str, result: Dict):
        """当 PE/PB 缺失时，从 spot 价格 + eps/bvps 计算"""
        eps = result.get('eps', 0)
        bvps = result.get('bvps', 0)
        pe = result.get('pe_ttm', 0)
        pb = result.get('pb', 0)
        market_cap = result.get('market_cap', 0)

        # 如果 PE/PB 都有值且 market_cap 合理，跳过
        if pe > 0 and pb > 0 and market_cap > 0:
            return

        # 获取 spot 数据
        spot = self._get_spot_cached()
        if spot.empty:
            return
        match = spot[spot['code'] == symbol]
        if match.empty:
            return

        price = match.iloc[0].get('price', 0)
        if price <= 0:
            return

        # 从 spot 直接取 PE/PB（优先于自己算）
        if pe == 0:
            spot_pe = match.iloc[0].get('pe_ttm', 0)
            if spot_pe > 0 and spot_pe < 1000:
                pe = float(spot_pe)
            elif eps > 0:
                pe = price / eps
            result['pe_ttm'] = pe

        if pb == 0:
            spot_pb = match.iloc[0].get('pb', 0)
            if spot_pb > 0 and spot_pb < 100:
                pb = float(spot_pb)
            elif bvps > 0:
                pb = price / bvps
            result['pb'] = pb

        if market_cap == 0:
            spot_mc = match.iloc[0].get('market_cap', 0)
            if spot_mc > 0:
                result['market_cap'] = float(spot_mc) / 1e8

    def _get_spot_cached(self) -> 'pd.DataFrame':
        """懒加载 spot 数据（避免重复拉取）"""
        # 先检查 _spot_df（可能在外部注入）
        if self._spot_df is not None:
            return self._spot_df
        try:
            df = self.get_spot()
            if not df.empty:
                self._spot_df = df
            return df
        except Exception:
            return pd.DataFrame()

    # ═══ 交易日历 ═══

    def get_trade_calendar(self) -> List:
        if self._trade_calendar is not None:
            return self._trade_calendar
        cache_key = "trade_calendar"
        cached = self._load_cache(cache_key, ttl_hours=6)
        if cached is not None:
            self._trade_calendar = cached['date'].tolist()
            return self._trade_calendar
        cal = ak.tool_trade_date_hist_sina()
        dates = sorted(cal['trade_date'].tolist())
        self._trade_calendar = dates
        self._save_cache(cache_key, pd.DataFrame({'date':dates}))
        return dates

    def get_trade_dates(self, start: str, end: str) -> List[str]:
        cal = self.get_trade_calendar()
        sd = pd.Timestamp(start).date()
        ed = pd.Timestamp(end).date()
        return [d.strftime("%Y-%m-%d") for d in cal if sd <= d <= ed]

    # ═══ 工具 ═══

    @staticmethod
    def _safe_float(val) -> float:
        try:
            if val is None or val=='' or val=='-' or (isinstance(val,float) and np.isnan(val)):
                return 0.0
            return float(str(val).replace(',','').replace('%',''))
        except: return 0.0

    def _cache_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode()).hexdigest()[:16]
        return CACHE_DIR / f"{h}.parquet"

    def _load_cache(self, key: str, ttl_hours: int = 0) -> Optional[pd.DataFrame]:
        if not self.cache_enabled:
            return None
        p = self._cache_path(key)
        p_pkl = Path(str(p).replace('.parquet', '.pkl'))
        for path in [p, p_pkl]:
            if not path.exists():
                continue
            if ttl_hours > 0:
                age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
                if age.total_seconds() > ttl_hours * 3600:
                    continue
            try:
                if path.suffix == '.parquet':
                    return pd.read_parquet(path)
                else:
                    return pd.read_pickle(path)
            except Exception:
                continue
        return None

    def _save_cache(self, key: str, df: pd.DataFrame):
        if not self.cache_enabled or df.empty:
            return
        path = self._cache_path(key)
        try:
            df.to_parquet(path, index=False)
        except Exception:
            try:
                df.to_pickle(str(path).replace('.parquet','.pkl'))
            except Exception as e:
                logger.debug(f"cache save fail: {e}")

    def clear_cache(self):
        for f in list(CACHE_DIR.glob("*.parquet")) + list(CACHE_DIR.glob("*.pkl")):
            f.unlink()
        self._trade_calendar = None
