import pandas as pd
import numpy as np
import pytest
from custom_strategy_interpreter import CustomStrategyInterpreter

def test_safe_sandboxing():
    # Attempt to inject dangerous imports or commands
    strategy_config = {
        "indicators": [
            {
                "name": "malicious",
                "type": "custom",
                "expression": "__import__('os').system('echo Hacked')"
            }
        ],
        "conditions": {
            "long": ["malicious > 0"],
            "short": [],
            "close_long": [],
            "close_short": []
        }
    }
    
    interpreter = CustomStrategyInterpreter(strategy_config)
    
    # Create dummy dataframe
    df = pd.DataFrame({
        "close": [10, 20, 30],
        "high": [12, 22, 32],
        "low": [8, 18, 28],
        "volume": [100, 200, 300]
    })
    
    # Evaluating should raise an error due to safe_eval restrictions
    with pytest.raises(Exception):
        interpreter.build_indicators(df)

def test_valid_expression():
    strategy_config = {
        "indicators": [
            {
                "name": "my_ma",
                "type": "sma",
                "period": 2,
                "source": "close"
            },
            {
                "name": "custom_cond",
                "type": "custom",
                "expression": "close > my_ma"
            }
        ],
        "conditions": {
            "long": ["custom_cond == True"],
            "short": [],
            "close_long": [],
            "close_short": []
        }
    }
    
    interpreter = CustomStrategyInterpreter(strategy_config)
    
    df = pd.DataFrame({
        "close": [10, 20, 30],
        "high": [12, 22, 32],
        "low": [8, 18, 28],
        "volume": [100, 200, 300]
    })
    
    processed_df = interpreter.build_indicators(df)
    
    assert 'my_ma' in processed_df.columns
    assert 'custom_cond' in processed_df.columns
    
    # Check signal
    signal = interpreter.check_signal(processed_df, 2)
    assert signal == "LONG"
