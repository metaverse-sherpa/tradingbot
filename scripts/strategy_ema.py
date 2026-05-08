"""
EMA Crossover Scalper Strategy
-------------------------------
Entry:  Fast EMA crosses above Slow EMA → LONG  (RSI > rsi_threshold confirms momentum)
        Fast EMA crosses below Slow EMA → SHORT (RSI < 100-rsi_threshold)
        Optional ADX filter to avoid choppy markets
Exit:   Fixed ATR-based Stop Loss and Take Profit
"""
import backtrader as bt


class EMACrossStrategy(bt.Strategy):
    params = (
        ('ema_fast', 8),
        ('ema_slow', 21),
        ('rsi_period', 14),
        ('rsi_threshold', 50),   # RSI must be ABOVE this for longs, BELOW (100-this) for shorts
        ('atr_period', 14),
        ('atr_multiplier', 1.5),
        ('rr_ratio', 1.0),
        ('risk_per_trade', 0.02),
        ('leverage', 20.0),
        ('slippage_pct', 0.0005),  # 0.05% market order slippage
        ('adx_period', 14),
        ('adx_threshold', 0),     # 0 = disabled
    )

    def __init__(self):
        self.ema_fast = bt.indicators.EMA(self.data.close, period=self.p.ema_fast)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=self.p.ema_slow)
        self.crossover = bt.indicators.CrossOver(self.ema_fast, self.ema_slow)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            self.data, period=self.p.adx_period)

        self.order = None
        self.stop_price = None
        self.take_profit_price = None

        self.sim_equity = 10000.0
        self.max_equity = 10000.0
        self.max_drawdown = 0.0

    def next(self):
        if self.order:
            return

        if not self.position:
            # ADX filter
            if self.p.adx_threshold > 0 and self.adx[0] < self.p.adx_threshold:
                return

            # LONG: fast crosses above slow + RSI confirms bullish momentum
            if self.crossover[0] == 1 and self.rsi[0] > self.p.rsi_threshold:
                fill = self.data.close[0] * (1 + self.p.slippage_pct)
                sl_dist = self.atr[0] * self.p.atr_multiplier
                self.stop_price = fill - sl_dist
                self.take_profit_price = fill + sl_dist * self.p.rr_ratio

                risk_amt = self.sim_equity * self.p.risk_per_trade
                size = min(risk_amt / sl_dist,
                           (self.sim_equity * self.p.leverage) / fill)
                self.order = self.buy(size=size)

            # SHORT: fast crosses below slow + RSI confirms bearish momentum
            elif self.crossover[0] == -1 and self.rsi[0] < (100 - self.p.rsi_threshold):
                fill = self.data.close[0] * (1 - self.p.slippage_pct)
                sl_dist = self.atr[0] * self.p.atr_multiplier
                self.stop_price = fill + sl_dist
                self.take_profit_price = fill - sl_dist * self.p.rr_ratio

                risk_amt = self.sim_equity * self.p.risk_per_trade
                size = min(risk_amt / sl_dist,
                           (self.sim_equity * self.p.leverage) / fill)
                self.order = self.sell(size=size)

        else:
            # Exit management
            if self.position.size > 0:  # LONG in trade
                if self.data.low[0] <= self.stop_price:
                    self.order = self.close()
                elif self.data.high[0] >= self.take_profit_price:
                    self.order = self.close()

            elif self.position.size < 0:  # SHORT in trade
                if self.data.high[0] >= self.stop_price:
                    self.order = self.close()
                elif self.data.low[0] <= self.take_profit_price:
                    self.order = self.close()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.sim_equity += trade.pnlcomm
            if self.sim_equity > self.max_equity:
                self.max_equity = self.sim_equity
            else:
                dd = (self.max_equity - self.sim_equity) / self.max_equity * 100
                if dd > self.max_drawdown:
                    self.max_drawdown = dd
