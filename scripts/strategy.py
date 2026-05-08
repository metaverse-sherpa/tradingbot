import backtrader as bt
import numpy as np


class RRStrategy(bt.Strategy):
    params = (
        ('ema_trend', 200),
        ('use_ema_filter', True),    # If False, trades both directions regardless of trend
        ('bb_period', 20),
        ('bb_devfactor', 2.0),
        ('rsi_period', 14),
        ('rsi_lower', 30),           # RSI oversold threshold for longs
        ('rsi_upper', 70),           # RSI overbought threshold for shorts
        ('atr_period', 14),
        ('atr_multiplier', 1.5),
        ('risk_per_trade', 0.02),
        ('leverage', 20.0),
        ('rr_ratio', 1.0),
        ('slippage_pct', 0.0005),    # 0.05% market order slippage
        ('adx_period', 14),
        ('adx_threshold', 0),        # 0 = disabled
        ('use_trailing', False),
        ('trail_atr_mult', 3.0),
    )

    def __init__(self):
        self.ema_t = bt.indicators.EMA(self.data.close, period=self.p.ema_trend)
        self.bb = bt.indicators.BollingerBands(
            self.data.close, period=self.p.bb_period, devfactor=self.p.bb_devfactor)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            self.data, period=self.p.adx_period)

        self.order = None
        self.stop_price = None
        self.take_profit_price = None
        self.trailing_stop = None

        self.sim_equity = 10000.0
        self.max_equity = 10000.0
        self.max_drawdown = 0.0

    def next(self):
        if self.order:
            return

        if not self.position:
            # ADX filter (skip if threshold == 0)
            if self.p.adx_threshold > 0 and self.adx[0] < self.p.adx_threshold:
                return

            price = self.data.close[0]

            # LONG condition
            long_bb_rsi = price < self.bb.bot[0] and self.rsi[0] < self.p.rsi_lower
            long_trend = (price > self.ema_t[0]) if self.p.use_ema_filter else True

            if long_bb_rsi and long_trend:
                fill = price * (1 + self.p.slippage_pct)
                sl_dist = self.atr[0] * self.p.atr_multiplier
                self.stop_price = fill - sl_dist
                self.take_profit_price = fill + sl_dist * self.p.rr_ratio
                self.trailing_stop = self.stop_price

                risk_amt = self.sim_equity * self.p.risk_per_trade
                size = min(risk_amt / sl_dist, (self.sim_equity * self.p.leverage) / fill)
                self.order = self.buy(size=size)
                return

            # SHORT condition
            short_bb_rsi = price > self.bb.top[0] and self.rsi[0] > self.p.rsi_upper
            short_trend = (price < self.ema_t[0]) if self.p.use_ema_filter else True

            if short_bb_rsi and short_trend:
                fill = price * (1 - self.p.slippage_pct)
                sl_dist = self.atr[0] * self.p.atr_multiplier
                self.stop_price = fill + sl_dist
                self.take_profit_price = fill - sl_dist * self.p.rr_ratio
                self.trailing_stop = self.stop_price

                risk_amt = self.sim_equity * self.p.risk_per_trade
                size = min(risk_amt / sl_dist, (self.sim_equity * self.p.leverage) / fill)
                self.order = self.sell(size=size)

        else:
            if self.position.size > 0:  # LONG
                if self.p.use_trailing:
                    new_trail = self.data.close[0] - self.atr[0] * self.p.trail_atr_mult
                    if new_trail > self.trailing_stop:
                        self.trailing_stop = new_trail
                    if self.data.low[0] <= self.trailing_stop:
                        self.order = self.close()
                else:
                    if self.data.low[0] <= self.stop_price:
                        self.order = self.close()
                    elif self.data.high[0] >= self.take_profit_price:
                        self.order = self.close()

            elif self.position.size < 0:  # SHORT
                if self.p.use_trailing:
                    new_trail = self.data.close[0] + self.atr[0] * self.p.trail_atr_mult
                    if new_trail < self.trailing_stop:
                        self.trailing_stop = new_trail
                    if self.data.high[0] >= self.trailing_stop:
                        self.order = self.close()
                else:
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
