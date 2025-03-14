from strategy.dragonhead import DragonHeadStrategy
from strategy.hit_board import HitBoardStrategy
from strategy.custom import CustomStrategy
from strategy.low_stock import LowStockStrategy

def get_strategy(strategy_name):
    """
    Factory function to get the appropriate strategy
    
    Args:
        strategy_name: Name of the strategy to use
        chart_generator: Function to generate charts (optional)
    
    Returns:
        Strategy object
    """
    if strategy_name.lower() == 'dragonhead':
        return DragonHeadStrategy()
    elif strategy_name.lower() == 'hit_board':
        return HitBoardStrategy()
    elif strategy_name.lower() == 'custom':
        return CustomStrategy()
    elif strategy_name.lower() == 'low_stock':
        return LowStockStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}") 