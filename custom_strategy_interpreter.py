import numpy as np
import pandas as pd
from simpleeval import SimpleEval
import time

def get_simpleeval_engine(df: pd.DataFrame):
    """Instantiates a sandboxed SimpleEval instance pre-loaded with pandas indicators."""
    evaluator = SimpleEval()
    
    # 1. Inject whitelisted operations
    evaluator.functions = {
        # Moving Averages
        'sma': lambda col, p: df[col].rolling(window=int(p)).mean(),
        'ema': lambda col, p: df[col].ewm(span=int(p), adjust=False).mean(),
        'wma': lambda col, p: df[col].rolling(window=int(p)).apply(
            lambda x: np.dot(x, np.arange(1, int(p) + 1)) / np.arange(1, int(p) + 1).sum(), raw=True
        ),
        'vwma': lambda p: (df['close'] * df['volume']).rolling(window=int(p)).sum() / df['volume'].rolling(window=int(p)).sum(),
        
        # Volatility & Range
        'std': lambda col, p: df[col].rolling(window=int(p)).std(),
        'atr': lambda p: pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1).rolling(window=int(p)).mean(),
        'highest': lambda col, p: df[col].rolling(window=int(p)).max(),
        'lowest': lambda col, p: df[col].rolling(window=int(p)).min(),
        
        # Math basics
        'abs': lambda x: np.abs(x),
        'log': lambda x: np.log(x),
        'sqrt': lambda x: np.sqrt(x),
        'max': lambda a, b: np.maximum(a, b),
        'min': lambda a, b: np.minimum(a, b),
    }
    
    # 2. Inject raw data column values
    evaluator.names = {col: df[col] for col in df.columns}
    return evaluator


class CustomStrategyInterpreter:
    def __init__(self, config_dict):
        self.config = config_dict
        self.name = config_dict.get("name", "Custom AI Strategy")
        self.indicators = config_dict.get("indicators", [])
        self.custom_columns = config_dict.get("custom_columns", [])
        self.long_entry = config_dict.get("long_entry_conditions", [])
        self.short_entry = config_dict.get("short_entry_conditions", [])
        self.exit_conditions = config_dict.get("exit_conditions", [])

    def build_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates standard indicators and custom math expressions on the DataFrame."""
        df = df.copy()
        
        # 1. Compute standard technical indicators configured in JSON
        for ind in self.indicators:
            name = ind["name"]
            itype = ind.get("type", ind.get("name", "")).upper()
            params = ind.get("params", {})
            src = ind.get("source", "close")
            
            if itype == "EMA":
                period = int(params.get("period", params.get("span", 14)))
                df[name] = df[src].ewm(span=period, adjust=False).mean()
            elif itype == "SMA":
                period = int(params.get("period", params.get("span", 14)))
                df[name] = df[src].rolling(window=period).mean()
            elif itype == "RSI":
                p = int(params.get("period", 14))
                delta = df[src].diff()
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                avg_gain = gain.rolling(window=p).mean()
                avg_loss = loss.rolling(window=p).mean()
                rs = avg_gain / (avg_loss + 1e-10)
                df[name] = 100 - (100 / (1 + rs))
            elif itype == "ATR":
                p = int(params.get("period", 14))
                tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
                df[name] = tr.rolling(window=p).mean()
            elif itype == "MACD":
                fast = int(params.get("fast", params.get("fast_period", 12)))
                slow = int(params.get("slow", params.get("slow_period", 26)))
                signal_p = int(params.get("signal", params.get("signal_period", 9)))
                exp1 = df[src].ewm(span=fast, adjust=False).mean()
                exp2 = df[src].ewm(span=slow, adjust=False).mean()
                df[name] = exp1 - exp2
                df[name + "_signal"] = df[name].ewm(span=signal_p, adjust=False).mean()
                df[name + "_hist"] = df[name] - df[name + "_signal"]
            elif itype == "BOLLINGER":
                window = int(params.get("window", params.get("period", 20)))
                std_dev = float(params.get("std_dev", params.get("std", 2.0)))
                sma = df[src].rolling(window=window).mean()
                std = df[src].rolling(window=window).std()
                df[name + "_upper"] = sma + (std * std_dev)
                df[name + "_lower"] = sma - (std * std_dev)
                df[name + "_mid"] = sma

        # 2. Compute custom columns via simpleeval
        evaluator = get_simpleeval_engine(df)
        for col in self.custom_columns:
            col_name = col["name"]
            expression = col["expression"]
            try:
                df[col_name] = evaluator.eval(expression)
                # Re-inject new computed column into simpleeval namespace for chaining
                evaluator.names[col_name] = df[col_name]
            except Exception as e:
                raise ValueError(f"Custom column expression error for '{col_name}': {e}")
        
        # 3. Auto-create any missing indicators referenced in entry conditions
        #    This handles cases where the AI references columns not in the indicators list
        all_conditions = self.long_entry + self.short_entry
        referenced_cols = set()
        for cond in all_conditions:
            referenced_cols.add(cond["left"])
            if isinstance(cond["right"], str):
                referenced_cols.add(cond["right"])
        
        import re
        for col_name in referenced_cols:
            if col_name in df.columns or col_name in ('open', 'high', 'low', 'close', 'volume'):
                continue
            # Try to auto-create from naming convention like EMA_9, SMA_50, RSI_14
            match = re.match(r'^(EMA|SMA|RSI|ATR)_(\d+)$', col_name, re.IGNORECASE)
            if match:
                ind_type = match.group(1).upper()
                period = int(match.group(2))
                src = 'close'
                if ind_type == 'EMA':
                    df[col_name] = df[src].ewm(span=period, adjust=False).mean()
                elif ind_type == 'SMA':
                    df[col_name] = df[src].rolling(window=period).mean()
                elif ind_type == 'RSI':
                    delta = df[src].diff()
                    gain = delta.clip(lower=0)
                    loss = -delta.clip(upper=0)
                    avg_gain = gain.rolling(window=period).mean()
                    avg_loss = loss.rolling(window=period).mean()
                    rs = avg_gain / (avg_loss + 1e-10)
                    df[col_name] = 100 - (100 / (1 + rs))
                elif ind_type == 'ATR':
                    tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
                    df[col_name] = tr.rolling(window=period).mean()
                print(f"[CustomStrategy] Auto-created missing indicator: {col_name} ({ind_type}, period={period})")
            else:
                # Try MACD/BOLLINGER sub-columns
                for suffix in ('_signal', '_hist', '_upper', '_lower', '_mid'):
                    if col_name.endswith(suffix):
                        base = col_name[:-len(suffix)]
                        if base in df.columns:
                            break  # The sub-column should already exist
                else:
                    print(f"[CustomStrategy] WARNING: Referenced column '{col_name}' not found and cannot be auto-created.")
                
        return df

    def evaluate_conditions(self, df: pd.DataFrame, idx: int, conditions: list) -> bool:
        """Evaluates entry/exit condition blocks at a specific candle index."""
        if not conditions:
            return False
            
        for cond in conditions:
            left_col = cond["left"]
            right = cond["right"]
            
            # Gracefully skip if referenced column doesn't exist
            if left_col not in df.columns:
                return False
            if isinstance(right, str) and right not in df.columns:
                # Try to parse as a number
                try:
                    right = float(right)
                except ValueError:
                    return False
            
            left_val = df[left_col].values[idx]
            right_val = df[right].values[idx] if isinstance(right, str) and right in df.columns else float(right)
            op = cond["operator"]
            
            # Check for NaN values which break comparisons
            if np.isnan(left_val) or np.isnan(right_val):
                return False
            
            # Left/Right previous index values for crossover analysis
            left_prev = df[left_col].values[idx - 1]
            right_prev = df[right].values[idx - 1] if isinstance(right, str) and right in df.columns else float(right)
            
            if np.isnan(left_prev) or np.isnan(right_prev):
                return False
            
            if op == ">" and not (left_val > right_val): return False
            elif op == "<" and not (left_val < right_val): return False
            elif op == ">=" and not (left_val >= right_val): return False
            elif op == "<=" and not (left_val <= right_val): return False
            elif op == "==" and not (left_val == right_val): return False
            elif op == "crosses_above" and not (left_prev <= right_prev and left_val > right_val): return False
            elif op == "crosses_below" and not (left_prev >= right_prev and left_val < right_val): return False
            
        return True

    def check_signal(self, df: pd.DataFrame, idx: int) -> str:
        """Returns 'LONG', 'SHORT', or None based on conditions at index."""
        if self.evaluate_conditions(df, idx, self.long_entry):
            return "LONG"
        if self.evaluate_conditions(df, idx, self.short_entry):
            return "SHORT"
        return None

def calculate_statistics(trade_history, initial_cash, equity_history):
    if not trade_history:
        return {
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "win_rate": 0.0,
            "max_dd_pct": 0.0,
            "total_trades": 0,
            "sharpe": 0.0,
            "profit_factor": 0.0
        }
    
    total_trades = len(trade_history)
    wins = [t for t in trade_history if t['pnl'] > 0]
    losses = [t for t in trade_history if t['pnl'] <= 0]
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    
    gross_profit = sum(t['pnl'] for t in wins)
    gross_loss = abs(sum(t['pnl'] for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0
    
    total_pnl = sum(t['pnl'] for t in trade_history)
    pnl_pct = (total_pnl / initial_cash) * 100
    
    # Calculate Max Drawdown
    if equity_history:
        equity_values = [e['equity'] for e in equity_history]
        peak = equity_values[0]
        max_dd = 0
        for eq in equity_values:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = max_dd * 100
    else:
        max_dd_pct = 0.0

    return {
        "pnl": total_pnl,
        "pnl_pct": pnl_pct,
        "win_rate": win_rate,
        "max_dd_pct": max_dd_pct,
        "total_trades": total_trades,
        "sharpe": 0.0,  # Simplify for now
        "profit_factor": profit_factor
    }

def run_combined_backtest(data_dict, interpreter: CustomStrategyInterpreter, risk_pct=0.02, initial_cash=10000.0, leverage=1.0, fee_rate=0.0005):
    """
    Simulates trading all whitelisted symbols simultaneously with a shared capital pool.
    
    Parameters:
    - data_dict: {symbol: df}
    - interpreter: CustomStrategyInterpreter
    - risk_pct: Percentage of total equity risked per trade (e.g. 0.02)
    - initial_cash: Starting USD portfolio size
    """
    # 1. Compute indicators for all symbols
    processed_dfs = {}
    warmup_periods = [int(ind.get("params", {}).get("span", 0)) for ind in interpreter.indicators] + \
                     [int(ind.get("params", {}).get("period", 0)) for ind in interpreter.indicators]
    min_warmup = max(warmup_periods) + 20 if warmup_periods else 20
    
    for sym, df in data_dict.items():
        processed_dfs[sym] = interpreter.build_indicators(df)
        
    # Get all unique dates in ascending order
    all_dates = sorted(list(set().union(*(df.index for df in processed_dfs.values()))))
    
    # Pre-cache row indexing to prevent slow DataFrame slicing
    sym_indices = {sym: {date: i for i, date in enumerate(df.index)} for sym, df in processed_dfs.items()}
    numpy_data = {sym: {col: df[col].values for col in df.columns} for sym, df in processed_dfs.items()}
    
    # Portfolio State variables
    cash = initial_cash
    active_trades = {}  # {symbol: trade_dict}
    trade_history = []
    equity_history = []
    
    # Use percentage-based SL/TP from exit_conditions if provided (AI sends these)
    exit_cfg = interpreter.config.get("exit_conditions", {})
    sl_pct = float(exit_cfg.get("sl_pct", 0)) / 100.0 if exit_cfg.get("sl_pct") else 0
    tp_pct = float(exit_cfg.get("tp_pct", 0)) / 100.0 if exit_cfg.get("tp_pct") else 0
    use_pct_exits = sl_pct > 0 and tp_pct > 0
    
    # Fallback to ATR-based exits if no percentage exits
    sl_atr_mult = interpreter.config.get("risk", {}).get("sl_atr_mult", 3.0)
    rr_ratio = interpreter.config.get("risk", {}).get("rr_ratio", 1.5)
    
    for t_idx, date in enumerate(all_dates):
        if t_idx < min_warmup:
            continue
            
        # A. PROCESS EXIT CHECKING (at the start of candle t open)
        symbols_to_close = []
        for sym, t in active_trades.items():
            idx = sym_indices[sym].get(date)
            if idx is None: continue
            
            o = numpy_data[sym]['open'][idx]
            h = numpy_data[sym]['high'][idx]
            l = numpy_data[sym]['low'][idx]
            
            exited = False
            exit_price = o
            exit_reason = ""
            
            # 1. Dynamic Exits (for stocks only)
            if interpreter.config.get("asset_type") == "stocks":
                # Evaluate exit conditions on closed bar (index t-1)
                if interpreter.evaluate_conditions(processed_dfs[sym], idx - 1, interpreter.exit_conditions):
                    exited = True
                    exit_price = o
                    exit_reason = "DYNAMIC_EXIT"
            
            # 2. Stop Loss & Take Profit (monitored intraday via high/low)
            if not exited:
                if t['side'] == "LONG":
                    if o <= t['sl']:
                        exited = True; exit_price = o; exit_reason = "STOP_LOSS (GAP)"
                    elif o >= t['tp']:
                        exited = True; exit_price = o; exit_reason = "TAKE_PROFIT (GAP)"
                    elif l <= t['sl'] and h >= t['tp']:
                        exited = True; exit_price = t['sl']; exit_reason = "STOP_LOSS (CONSERVATIVE)"
                    elif l <= t['sl']:
                        exited = True; exit_price = t['sl']; exit_reason = "STOP_LOSS"
                    elif h >= t['tp']:
                        exited = True; exit_price = t['tp']; exit_reason = "TAKE_PROFIT"
                else: # SHORT
                    if o >= t['sl']:
                        exited = True; exit_price = o; exit_reason = "STOP_LOSS (GAP)"
                    elif o <= t['tp']:
                        exited = True; exit_price = o; exit_reason = "TAKE_PROFIT (GAP)"
                    elif h >= t['sl'] and l <= t['tp']:
                        exited = True; exit_price = t['sl']; exit_reason = "STOP_LOSS (CONSERVATIVE)"
                    elif h >= t['sl']:
                        exited = True; exit_price = t['sl']; exit_reason = "STOP_LOSS"
                    elif l <= t['tp']:
                        exited = True; exit_price = t['tp']; exit_reason = "TAKE_PROFIT"
                        
            if exited:
                gross_pnl = (exit_price - t['entry_price']) * t['qty'] if t['side'] == "LONG" else (t['entry_price'] - exit_price) * t['qty']
                exit_value = exit_price * t['qty']
                fee = exit_value * fee_rate
                net_pnl = gross_pnl - fee - t['entry_fee']
                
                if t['side'] == "LONG":
                    cash += exit_value - fee
                else:
                    cash -= (exit_value + fee)
                    
                trade_history.append({
                    "symbol": sym, "side": t['side'], "entry_date": str(t['entry_date']), "exit_date": str(date),
                    "entry_price": t['entry_price'], "exit_price": exit_price, "qty": t['qty'],
                    "pnl": net_pnl, "pnl_pct": (net_pnl / t['notional']) * 100, "reason": exit_reason
                })
                symbols_to_close.append(sym)
                
        for sym in symbols_to_close:
            active_trades.pop(sym)
            
        # B. CALCULATE TOTAL PORTFOLIO EQUITY
        current_equity = cash
        for sym, t in active_trades.items():
            idx = sym_indices[sym].get(date)
            c = numpy_data[sym]['close'][idx] if idx is not None else t['entry_price']
            if t['side'] == "LONG":
                current_equity += t['qty'] * c
            else:
                current_equity -= t['qty'] * c
                
        equity_history.append({"date": str(date), "equity": current_equity, "cash": cash})
        
        # C. SCAN FOR NEW SIGNALS
        pending_signals = []
        for sym in numpy_data.keys():
            if sym in active_trades: continue
            
            idx = sym_indices[sym].get(date)
            if idx is None or idx < 1: continue
            
            # Signals fire on the close of candle t-1
            sig = interpreter.check_signal(processed_dfs[sym], idx - 1)
            if sig:
                # Validate direction settings
                if interpreter.config.get("direction") == "long_only" and sig != "LONG":
                    continue
                pending_signals.append((sym, sig))
                
        if not pending_signals:
            continue
            
        # Sort alphabetically to keep backtest execution deterministic
        pending_signals.sort(key=lambda x: x[0])
        
        # D. EQUAL-SPLIT ALLOCATION LOGIC
        # 1. Calculate free buying power
        buying_power = current_equity * leverage
        allocated_notional = sum(t['qty'] * t['entry_price'] for t in active_trades.values())
        free_buying_power = max(0.0, buying_power - allocated_notional)
        
        if free_buying_power <= 0:
            continue
            
        # 2. Divide available capital equally among all valid incoming signals
        split_power = free_buying_power / len(pending_signals)
        
        for sym, sig in pending_signals:
            idx = sym_indices[sym].get(date)
            entry_price = numpy_data[sym]['open'][idx] # Fill at open of bar t
            if use_pct_exits:
                # Use percentage-based SL/TP from AI config
                D = entry_price * sl_pct
                sl = entry_price * (1 - sl_pct) if sig == "LONG" else entry_price * (1 + sl_pct)
                tp = entry_price * (1 + tp_pct) if sig == "LONG" else entry_price * (1 - tp_pct)
            else:
                # ATR-based exits
                atr = numpy_data[sym].get('atr', numpy_data[sym]['close'])[idx - 1]
                D = sl_atr_mult * atr
                if D < entry_price * 0.005:
                    D = entry_price * 0.005
                sl = entry_price - D if sig == "LONG" else entry_price + D
                tp = entry_price + (rr_ratio * D) if sig == "LONG" else entry_price - (rr_ratio * D)
            
            # Sizing based on risk percentage allocation
            risk_dollars = current_equity * risk_pct
            ideal_qty = risk_dollars / D
            ideal_notional = ideal_qty * entry_price
            
            # Cap position size by split allocation limits
            final_notional = min(ideal_notional, split_power)
            final_qty = final_notional / entry_price
            
            entry_fee = final_notional * fee_rate
            
            if final_qty > 0.01 and final_notional > 10.0:
                if sig == "LONG":
                    cash -= (final_notional + entry_fee)
                else:
                    cash += (final_notional - entry_fee)
                    
                active_trades[sym] = {
                    "side": sig, "entry_date": date, "entry_price": entry_price, "sl": sl, "tp": tp,
                    "qty": final_qty, "notional": final_notional, "entry_fee": entry_fee
                }
                
    return {
        "metrics": calculate_statistics(trade_history, initial_cash, equity_history),
        "equity_curve": equity_history,
        "trades": trade_history
    }
