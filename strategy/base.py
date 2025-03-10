from typing import List
import pandas as pd


class Stock:
    code: str  
    name: str 
    current_price: float 
    buy_price: float 
    sell_price: float
    suggest_reason: str

    def __str__(self):
        return f"{self.code} {self.name} {self.current_price} {self.buy_price} {self.sell_price} {self.suggest_reason}"
    
    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "current_price": self.current_price,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "suggest_reason": self.suggest_reason
        }

class Strategy:
    """Base strategy class that all strategies should inherit from"""
    
    def __init__(self, name):
        self.name = name
    
    def filter_stocks(self, buy_date: str, limit_stock_count: int = 10) -> List[Stock]:
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