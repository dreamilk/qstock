from typing import List, Optional
from dataclasses import dataclass, field, asdict
import pandas as pd


@dataclass
class Stock:
    """Represents a filtered stock with strategy analysis results."""
    code: str = ""
    name: str = ""
    current_price: float = 0.0
    buy_price: float = 0.0
    sell_price: float = 0.0
    stop_loss: float = 0.0
    suggest_reason: str = ""
    score: float = 0.0

    def __str__(self):
        return f"{self.code} {self.name} {self.current_price} {self.buy_price} {self.sell_price} {self.suggest_reason}"
    
    def to_dict(self):
        return asdict(self)

class Strategy:
    """Base strategy class that all strategies should inherit from"""
    
    def __init__(self, name):
        self.name = name
    
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10, filter_stocks: bool = True) -> List[Stock]:
        """
        Filter stocks based on strategy criteria

        Args:
            buy_date: the date to buy the stock
            limit_stock_count: the maximum number of stocks to return
        Returns:
            List of filtered stocks
        """
        raise NotImplementedError("Subclasses must implement filter_stocks method") 
    


def toDataFrame(stocks: List[Stock]) -> pd.DataFrame:
    return pd.DataFrame([stock.to_dict() for stock in stocks])