import React, { useEffect, useState, useMemo } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../lib/api';

interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
}

interface TradeSetupChartProps {
  symbol: string;
  entry: number;
  tp: number;
  sl: number;
  currentPrice?: number;
  side?: string;
  openTs?: number;
}

// In-memory client cache (5 minutes) so toggling cards is instant
const ohlcvCache = new Map<string, { ts: number; candles: Candle[] }>();
const CACHE_TTL_MS = 5 * 60 * 1000;

const fmtPrice = (v: number) => {
  if (!Number.isFinite(v)) return '0.00';
  return v >= 100 ? v.toFixed(2) : v >= 1 ? v.toFixed(2) : v.toFixed(4);
};

const fmtDate = (ms: number) => {
  const d = new Date(ms);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const TradeSetupChart: React.FC<TradeSetupChartProps> = ({
  symbol,
  entry,
  tp,
  sl,
  currentPrice = 0,
  side = 'LONG',
  openTs = 0,
}) => {
  const cleanSym = (symbol || '').split('/')[0].split(':')[0].trim().toUpperCase();
  const [candles, setCandles] = useState<Candle[] | null>(() => {
    const cached = ohlcvCache.get(cleanSym);
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) return cached.candles;
    return null;
  });
  const [loading, setLoading] = useState(!candles);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const fetchCandles = async (force = false) => {
    if (!cleanSym) return;
    if (!force) {
      const cached = ohlcvCache.get(cleanSym);
      if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
        setCandles(cached.candles);
        setLoading(false);
        return;
      }
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/trades/ohlcv?symbol=${encodeURIComponent(cleanSym)}&limit=45`);
      const list: Candle[] = res.data?.candles || [];
      ohlcvCache.set(cleanSym, { ts: Date.now(), candles: list });
      setCandles(list);
    } catch {
      setError('Failed to load chart data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandles(false);
  }, [cleanSym]);

  const effectiveCandles = useMemo(() => {
    const base = candles && candles.length > 0 ? [...candles] : [];
    if (base.length === 0 && entry > 0) {
      // Fallback flat series if market data unavailable
      const now = Date.now();
      for (let i = 20; i >= 0; i--) {
        const p = i === 0 && currentPrice > 0 ? currentPrice : entry;
        base.push({ t: now - i * 86400000, o: p, h: p * 1.005, l: p * 0.995, c: p });
      }
      return base;
    }
    if (base.length > 0 && currentPrice > 0) {
      const last = { ...base[base.length - 1] };
      last.c = currentPrice;
      last.h = Math.max(last.h, currentPrice);
      last.l = Math.min(last.l, currentPrice);
      base[base.length - 1] = last;
    }
    return base;
  }, [candles, entry, currentPrice]);

  if (loading) {
    return (
      <div className="w-full h-[240px] bg-[#0b0f19]/70 rounded-xl border border-white/5 flex flex-col items-center justify-center gap-2 text-gray-400 text-xs">
        <RefreshCw size={18} className="animate-spin text-cyan-400" />
        <span>Loading {cleanSym} chart...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full h-[200px] bg-[#0b0f19]/70 rounded-xl border border-rose-500/20 flex flex-col items-center justify-center gap-2 text-gray-400 text-xs">
        <span>{error}</span>
        <button
          type="button"
          onClick={() => fetchCandles(true)}
          className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/15 text-white font-bold uppercase tracking-wider text-[10px]"
        >
          Retry
        </button>
      </div>
    );
  }

  // SVG Layout
  const W = 760;
  const H = 260;
  const padL = 12;
  const padR = 72;
  const padT = 18;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const livePrice = currentPrice > 0 ? currentPrice : (effectiveCandles[effectiveCandles.length - 1]?.c || entry);

  // Y-axis bounds including Entry, TP, SL, and all candles
  const lows = effectiveCandles.map((c) => c.l);
  const highs = effectiveCandles.map((c) => c.h);
  let yMin = Math.min(...lows, entry > 0 ? entry : Infinity, livePrice > 0 ? livePrice : Infinity);
  let yMax = Math.max(...highs, entry > 0 ? entry : -Infinity, livePrice > 0 ? livePrice : -Infinity);
  if (sl > 0) yMin = Math.min(yMin, sl);
  if (tp > 0) yMax = Math.max(yMax, tp);
  const rawSpan = Math.max(yMax - yMin, yMax * 0.02 || 1);
  yMin -= rawSpan * 0.08;
  yMax += rawSpan * 0.08;
  const ySpan = yMax - yMin || 1;

  const toY = (price: number) => padT + ((yMax - price) / ySpan) * plotH;
  const n = effectiveCandles.length;
  const stepX = plotW / Math.max(1, n);
  const candleW = Math.max(3, Math.min(11, stepX * 0.62));
  const toX = (idx: number) => padL + idx * stepX + stepX / 2;

  // Determine where Entry/TP/SL zone starts
  const openMs = openTs > 0 ? (openTs < 1e11 ? openTs * 1000 : openTs) : 0;
  let zoneStartIdx = 0;
  if (openMs > 0) {
    const found = effectiveCandles.findIndex((c) => c.t >= openMs);
    if (found >= 0 && n - found >= 4) {
      zoneStartIdx = found;
    }
  }
  const zoneX = padL + zoneStartIdx * stepX;
  const zoneW = padL + plotW - zoneX;

  const gridPrices = [0, 0.25, 0.5, 0.75, 1].map((f) => yMin + f * ySpan);
  const hovered = hoverIdx !== null ? effectiveCandles[hoverIdx] : null;
  const isShort = side.toUpperCase() === 'SHORT' || side.toUpperCase() === 'SELL';
  const pnlPct = entry > 0 ? ((isShort ? entry - livePrice : livePrice - entry) / entry) * 100 : 0;

  return (
    <div className="w-full bg-[#0b0f19] rounded-xl border border-white/10 overflow-hidden select-none">
      {/* Top Info Bar / Hover Readout */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-white/5 text-[11px] bg-black/30">
        <div className="flex items-center gap-3 font-mono">
          {hovered ? (
            <>
              <span className="text-gray-400 font-bold">{fmtDate(hovered.t)}</span>
              <span className="text-gray-300">O <strong className="text-white">${fmtPrice(hovered.o)}</strong></span>
              <span className="text-gray-300">H <strong className="text-emerald-400">${fmtPrice(hovered.h)}</strong></span>
              <span className="text-gray-300">L <strong className="text-rose-400">${fmtPrice(hovered.l)}</strong></span>
              <span className="text-gray-300">C <strong className="text-cyan-300">${fmtPrice(hovered.c)}</strong></span>
            </>
          ) : (
            <>
              <span className="text-white font-bold">{cleanSym} • 1D</span>
              {entry > 0 && <span className="text-gray-400">Entry <strong className="text-white">${fmtPrice(entry)}</strong></span>}
              {livePrice > 0 && (
                <span className={pnlPct >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                  Now ${fmtPrice(livePrice)} ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                </span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-3 text-[10px] font-bold uppercase tracking-wider">
          {tp > 0 && <span className="text-emerald-400">TP ${fmtPrice(tp)}</span>}
          {sl > 0 && <span className="text-rose-400">SL ${fmtPrice(sl)}</span>}
        </div>
      </div>

      {/* Responsive SVG Candlestick Chart */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto block"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {/* Horizontal Gridlines & Right Price Labels */}
        {gridPrices.map((gp, i) => {
          const y = toY(gp);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
              <text x={W - padR + 6} y={y + 3.5} fill="#6b7280" fontSize="10" fontFamily="monospace">
                ${fmtPrice(gp)}
              </text>
            </g>
          );
        })}

        {/* Shaded TP Profit Zone */}
        {entry > 0 && tp > 0 && (
          <rect
            x={zoneX}
            y={Math.min(toY(entry), toY(tp))}
            width={zoneW}
            height={Math.abs(toY(entry) - toY(tp))}
            fill="rgba(16, 185, 129, 0.10)"
          />
        )}

        {/* Shaded SL Risk Zone */}
        {entry > 0 && sl > 0 && (
          <rect
            x={zoneX}
            y={Math.min(toY(entry), toY(sl))}
            width={zoneW}
            height={Math.abs(toY(entry) - toY(sl))}
            fill="rgba(244, 63, 94, 0.10)"
          />
        )}

        {/* TP / Entry / SL Reference Lines */}
        {tp > 0 && (
          <g>
            <line x1={zoneX} y1={toY(tp)} x2={W - padR} y2={toY(tp)} stroke="#10b981" strokeWidth="1.5" />
            <rect x={W - padR + 2} y={toY(tp) - 8} width={66} height={16} rx={4} fill="#065f46" />
            <text x={W - padR + 6} y={toY(tp) + 3.5} fill="#6ee7b7" fontSize="9.5" fontWeight="bold" fontFamily="monospace">
              TP {fmtPrice(tp)}
            </text>
          </g>
        )}
        {entry > 0 && (
          <g>
            <line x1={zoneX} y1={toY(entry)} x2={W - padR} y2={toY(entry)} stroke="#e5e7eb" strokeWidth="1.2" strokeDasharray="4 4" />
            <rect x={W - padR + 2} y={toY(entry) - 8} width={66} height={16} rx={4} fill="#374151" />
            <text x={W - padR + 6} y={toY(entry) + 3.5} fill="#ffffff" fontSize="9.5" fontWeight="bold" fontFamily="monospace">
              IN {fmtPrice(entry)}
            </text>
          </g>
        )}
        {sl > 0 && (
          <g>
            <line x1={zoneX} y1={toY(sl)} x2={W - padR} y2={toY(sl)} stroke="#f43f5e" strokeWidth="1.5" />
            <rect x={W - padR + 2} y={toY(sl) - 8} width={66} height={16} rx={4} fill="#881337" />
            <text x={W - padR + 6} y={toY(sl) + 3.5} fill="#fda4af" fontSize="9.5" fontWeight="bold" fontFamily="monospace">
              SL {fmtPrice(sl)}
            </text>
          </g>
        )}

        {/* Candlesticks */}
        {effectiveCandles.map((c, idx) => {
          const x = toX(idx);
          const isUp = c.c >= c.o;
          const color = isUp ? '#10b981' : '#f43f5e';
          const bodyTop = toY(Math.max(c.o, c.c));
          const bodyBot = toY(Math.min(c.o, c.c));
          const bodyH = Math.max(1.5, bodyBot - bodyTop);
          const isHov = hoverIdx === idx;
          return (
            <g key={idx}>
              {isHov && (
                <line x1={x} y1={padT} x2={x} y2={H - padB} stroke="rgba(56, 189, 248, 0.35)" strokeWidth="1" strokeDasharray="3 3" />
              )}
              <line x1={x} y1={toY(c.h)} x2={x} y2={toY(c.l)} stroke={color} strokeWidth="1.2" />
              <rect
                x={x - candleW / 2}
                y={bodyTop}
                width={candleW}
                height={bodyH}
                fill={color}
                rx={1}
                opacity={isHov ? 1 : 0.9}
              />
              {/* Invisible hover hitbox */}
              <rect
                x={padL + idx * stepX}
                y={padT}
                width={stepX}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHoverIdx(idx)}
              />
            </g>
          );
        })}

        {/* Current Live Price Marker */}
        {livePrice > 0 && (
          <g>
            <line x1={padL} y1={toY(livePrice)} x2={W - padR} y2={toY(livePrice)} stroke="#38bdf8" strokeWidth="1" strokeDasharray="2 3" opacity="0.7" />
            <rect x={W - padR + 2} y={toY(livePrice) - 8} width={66} height={16} rx={4} fill="#0369a1" />
            <text x={W - padR + 6} y={toY(livePrice) + 3.5} fill="#e0f2fe" fontSize="9.5" fontWeight="bold" fontFamily="monospace">
              ${fmtPrice(livePrice)}
            </text>
          </g>
        )}

        {/* X-Axis Date Labels (4 evenly spaced) */}
        {[0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1]
          .filter((v, i, arr) => v >= 0 && v < n && arr.indexOf(v) === i)
          .map((idx) => (
            <text
              key={idx}
              x={toX(idx)}
              y={H - 8}
              textAnchor="middle"
              fill="#6b7280"
              fontSize="9.5"
              fontFamily="monospace"
            >
              {fmtDate(effectiveCandles[idx].t)}
            </text>
          ))}
      </svg>
    </div>
  );
};

export default TradeSetupChart;
