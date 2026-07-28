#!/usr/bin/env python3
"""
🏔️ Standalone Crypto Portfolio Backtester Engine
--------------------------------------------------
Simulates chronological crypto portfolio execution across whitelisted symbols
with strict cash constraints, compounding risk management, dynamic liquidation-based
leverage calculations, and exact live trading engine alignment.
"""

import os
import sys
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database
from strategies import STRATEGIES, get_strategy

# ---------------------------------------------------------------------------
# Default Backtest Parameters
# ---------------------------------------------------------------------------
INITIAL_CASH = 10000.0
RISK_PER_TRADE = 0.015         # 1.5% compounding risk (Valkyrie Sweet Spot)
LEVERAGE = 20.0                # Max allowed leverage
FEE_RATE = 0.0005              # 0.05% fee per transaction (0.1% round-trip)
SAFETY_MARGIN = 0.04           # 4% safety margin buffer between SL and Liquidation price

PRECALCULATED_PATH = os.path.join(BASE_DIR, "data", "precalculated_trades.json")

def load_precalculated_trades(strategy_name):
    """Loads historical trade signals from precalculated cache if available."""
    if not os.path.exists(PRECALCULATED_PATH):
        return []
    try:
        with open(PRECALCULATED_PATH, "r") as f:
            all_trades = json.load(f)
        return [t for t in all_trades if t.get("strategy") == strategy_name or t.get("strategy_name") == strategy_name]
    except Exception as e:
        print(f"Error reading {PRECALCULATED_PATH}: {e}")
        return []

def run_crypto_backtest(strategy_name="Valkyrie Elite Scalper", initial_cash=INITIAL_CASH, risk_pct=RISK_PER_TRADE, leverage=LEVERAGE, verbose=True):
    """
    Chronological Crypto Portfolio Backtester Engine.
    Executes trades chronologically with strict equity-based position sizing and fee deduction.
    """
    print(f"\n{'═'*80}")
    print(f"🚀 RUNNING CRYPTO PORTFOLIO BACKTEST: {strategy_name.upper()}")
    print(f"   Starting Capital: ${initial_cash:,.2f} | Risk per Trade: {risk_pct*100:.1f}% | Max Leverage: {leverage:.0f}x")
    print(f"{'═'*80}\n")
    
    trades = load_precalculated_trades(strategy_name)
    if not trades:
        print(f"⚠️ No precalculated historical trade data found for strategy '{strategy_name}'.")
        print("Checking for custom user strategy in database...")
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT strategy_config FROM UserStrategies WHERE name = ?", (strategy_name,))
            row = c.fetchone()
        if row and row[0]:
            custom_cfg = json.loads(row[0])
            from custom_strategy_interpreter import CustomStrategyInterpreter, run_combined_backtest
            from web_api.routes_custom_strategies import load_historical_data
            data_dict = load_historical_data(asset_type="crypto", timeframe="15m")
            interpreter = CustomStrategyInterpreter(custom_cfg)
            res = run_combined_backtest(data_dict, interpreter, risk_pct=risk_pct, initial_cash=initial_cash, leverage=leverage)
            return res.get("metrics", {})
        else:
            print(f"❌ Strategy '{strategy_name}' not found.")
            return None
            
    # Parse trade dates
    for t in trades:
        t["entry_dt"] = datetime.fromisoformat(t["entry_date"]) if isinstance(t["entry_date"], str) else t["entry_date"]
        t["exit_dt"] = datetime.fromisoformat(t["exit_date"]) if isinstance(t["exit_date"], str) else t["exit_date"]
        
    trades.sort(key=lambda x: x["entry_dt"])
    
    # Chronological Event Timeline
    events = []
    for idx, t in enumerate(trades):
        events.append({"type": "entry", "date": t["entry_dt"], "trade_idx": idx})
        events.append({"type": "exit", "date": t["exit_dt"], "trade_idx": idx})
        
    # Process exits before entries on the same timestamp
    events.sort(key=lambda x: (x["date"], 0 if x["type"] == "exit" else 1))
    
    cash = initial_cash
    equity = initial_cash
    active_positions = {}
    trade_history = []
    equity_history = []
    
    max_equity = initial_cash
    max_dd = 0.0
    wins = 0
    losses = 0
    
    for ev in events:
        t_idx = ev["trade_idx"]
        t = trades[t_idx]
        sym = t.get("symbol", "CRYPTO")
        
        if ev["type"] == "entry":
            # Risk Management & Position Sizing
            sl_dist = float(t.get("sl_dist", 0.0))
            entry_price = float(t.get("entry_price", 0.0))
            if sl_dist <= 0 or entry_price <= 0:
                continue
                
            risk_dollars = equity * risk_pct
            raw_qty = risk_dollars / sl_dist
            
            # Dynamic Liquidation-Based Leverage Check
            side = t.get("side", "LONG").upper()
            sl = entry_price - sl_dist if side == "LONG" else entry_price + sl_dist
            
            if side == "LONG":
                denom = (1.0 + SAFETY_MARGIN) - (sl / entry_price)
                effective_lev = min(leverage, int(1.0 / denom)) if denom > 0 else leverage
            else:
                denom = (sl / entry_price) - (1.0 - SAFETY_MARGIN)
                effective_lev = min(leverage, int(1.0 / denom)) if denom > 0 else leverage
            effective_lev = max(1.0, float(effective_lev))
            
            max_notional = equity * effective_lev
            position_notional = min(raw_qty * entry_price, max_notional)
            qty = position_notional / entry_price
            
            entry_fee = position_notional * FEE_RATE
            
            active_positions[t_idx] = {
                "symbol": sym,
                "side": side,
                "entry_price": entry_price,
                "sl": sl,
                "qty": qty,
                "notional": position_notional,
                "risk_dollars": risk_dollars,
                "entry_fee": entry_fee,
                "effective_lev": effective_lev
            }
            
            cash -= entry_fee
            
            if verbose:
                print(f"🚀 [{ev['date'].strftime('%Y-%m-%d %H:%M')}] ENTERED {side} {sym}: Price ${entry_price:.4f} | Size: {qty:.4f} (${position_notional:.2f}) | Lev: {effective_lev:.0f}x")
                
        elif ev["type"] == "exit":
            pos = active_positions.pop(t_idx, None)
            if not pos:
                continue
                
            exit_price = float(t.get("exit_price", pos["entry_price"]))
            is_win = bool(t.get("win", exit_price > pos["entry_price"] if pos["side"] == "LONG" else exit_price < pos["entry_price"]))
            rr_ratio = float(t.get("rr_ratio", 1.5))
            
            # PnL Calculation
            if is_win:
                gross_pnl = pos["risk_dollars"] * rr_ratio
                wins += 1
                reason = "TAKE_PROFIT"
            else:
                gross_pnl = -pos["risk_dollars"]
                losses += 1
                reason = "STOP_LOSS"
                
            exit_value = pos["qty"] * exit_price
            exit_fee = exit_value * FEE_RATE
            net_pnl = gross_pnl - exit_fee - pos["entry_fee"]
            
            equity += net_pnl
            cash += net_pnl
            
            max_equity = max(max_equity, equity)
            dd = (max_equity - equity) / max_equity * 100.0
            max_dd = max(max_dd, dd)
            
            equity_history.append({"date": ev["date"], "equity": equity, "cash": cash})
            
            trade_history.append({
                "symbol": sym,
                "side": pos["side"],
                "entry_date": t["entry_dt"],
                "exit_date": ev["date"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "net_pnl": net_pnl,
                "pnl_pct": (net_pnl / pos["notional"]) * 100.0 if pos["notional"] > 0 else 0,
                "reason": reason
            })
            
            if verbose:
                print(f"📉 [{ev['date'].strftime('%Y-%m-%d %H:%M')}] CLOSED {pos['side']} {sym}: Entry ${pos['entry_price']:.4f}, Exit ${exit_price:.4f} ({reason}) | PnL: ${net_pnl:+.2f} ({(net_pnl/pos['notional']):+.2%})")

    total_trades = len(trade_history)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pnl_total = equity - initial_cash
    pnl_pct_total = (net_pnl_total / initial_cash) * 100.0
    
    winning_trades = [t for t in trade_history if t["net_pnl"] > 0]
    losing_trades = [t for t in trade_history if t["net_pnl"] <= 0]
    
    avg_win = (sum(t["net_pnl"] for t in winning_trades) / len(winning_trades)) if winning_trades else 0.0
    avg_loss = (sum(t["net_pnl"] for t in losing_trades) / len(losing_trades)) if losing_trades else 0.0
    gross_profit = sum(t["net_pnl"] for t in winning_trades)
    gross_loss = abs(sum(t["net_pnl"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

    print(f"\n{'═'*80}")
    print(f"🌍 CRYPTO PORTFOLIO SUMMARY: {strategy_name.upper()}")
    print(f"{'═'*80}")
    print(f"Initial Balance   : ${initial_cash:,.2f}")
    print(f"Final Balance     : ${equity:,.2f}")
    print(f"Cumulative PnL %  : {pnl_pct_total:+.2f}%")
    print(f"Win Rate          : {win_rate:.2f}% ({wins} W / {losses} L)")
    print(f"Max Drawdown      : {max_dd:.2f}%")
    print(f"Profit Factor     : {profit_factor:.2f}")
    print(f"Total Trades      : {total_trades}")
    print(f"Avg Win Amount    : ${avg_win:+.2f}")
    print(f"Avg Loss Amount   : ${avg_loss:+.2f}")
    print(f"{'═'*80}\n")
    
    return {
        "final_equity": equity,
        "pnl_pct": pnl_pct_total,
        "win_rate": win_rate,
        "max_dd_pct": max_dd,
        "profit_factor": profit_factor,
        "total_trades": total_trades
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Standalone Crypto Portfolio Backtester")
    parser.add_argument("--strategy", type=str, default="Valkyrie Elite Scalper", help="Active strategy to backtest")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial cash balance")
    parser.add_argument("--risk", type=float, default=1.5, help="Risk percentage per trade (e.g. 1.5 for 1.5%%)")
    args = parser.parse_args()
    
    run_crypto_backtest(
        strategy_name=args.strategy,
        initial_cash=args.capital,
        risk_pct=args.risk / 100.0,
        leverage=20.0,
        verbose=True
    )
