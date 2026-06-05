import re

with open('app.js', 'r') as f:
    content = f.read()

# We want to replace the block from `let tradesMode = STATE.trades_mode;` to `return \`` (inclusive up to the main return)
# Actually, it's easier to just match from `let tradesMode = STATE.trades_mode;` to `</main>\n    \`;\n}`

start_pattern = "    let tradesMode = STATE.trades_mode;"
end_pattern = "    `;\n}"

start_idx = content.find(start_pattern)
end_idx = content.find(end_pattern, start_idx) + len(end_pattern)

old_block = content[start_idx:end_idx]

# Inside old block, there is generation for `listHtml`.
# We can create a JS function string that generates the HTML for a given type.

new_block = """    let tradesMode = STATE.trades_mode;
    if (!tradesMode) {
        tradesMode = (STATE.open_trades && STATE.open_trades.length === 0) ? 'closed' : 'active';
    }
    
    const generateTradeHtml = (type) => {
        const isCryptoType = type === 'crypto';
        let listHtml = '';
        
        if (tradesMode === 'active') {
            const filteredTrades = STATE.open_trades.filter(t => t.type === type);
            if (filteredTrades.length === 0) {
                listHtml = `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">hourglass_empty</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No open positions</p>
                        <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">The Sherpa engine is scanning the markets...</p>
                    </div>
                `;
            } else {
                listHtml = filteredTrades.map(trade => {
                    const timeAgo = (ts) => {
                        const diff = Math.floor(Date.now() / 1000) - ts;
                        if (diff < 60) return "Just now";
                        if (diff < 3600) return Math.floor(diff / 60) + "m ago";
                        if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
                        return Math.floor(diff / 86400) + "d ago";
                    };
                    const dateStr = trade.open_time ? timeAgo(trade.open_time) : 'Recent';
                    let displaySymbol = trade.symbol;
                    if (trade.type === 'crypto') {
                        displaySymbol = displaySymbol.replace(/\\/USDT.*$/, '');
                    }
                    
                    const pnlColor = (trade.unrealized_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const roeColor = (trade.roe || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const icon = trade.side === 'LONG' ? 'trending_up' : 'trending_down';
                    const assetIcon = trade.type === 'stock' ? '🦙' : '🪙';
                    const isExpanded = STATE.expanded_trade_id === trade.id;
                    
                    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                    const inlineBlur = isPrivacyOn ? 'style="filter: blur(5px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\\'none\\'" onmouseleave="this.style.filter=\\'blur(5px)\\'"' : '';
                    
                    let progressBarHtml = '';
                    if (isExpanded && trade.tp_price > 0 && trade.sl_price > 0) {
                        const entry = trade.entry_price || 0;
                        const mark = trade.mark_price || 0;
                        const tp = trade.tp_price || 0;
                        const sl = trade.sl_price || 0;
                        const isLong = trade.side === 'LONG';
                        
                        let pct = 50;
                        if (isLong) {
                            if (mark <= sl) pct = 0;
                            else if (mark >= tp) pct = 100;
                            else pct = ((mark - sl) / (tp - sl)) * 100;
                        } else {
                            if (mark >= sl) pct = 0;
                            else if (mark <= tp) pct = 100;
                            else pct = ((sl - mark) / (sl - tp)) * 100;
                        }
                        
                        const sl_pct = ((sl - entry) / entry) * 100;
                        const tp_pct = ((tp - entry) / entry) * 100;
                        
                        progressBarHtml = `
                            <div class="mt-4 pt-4 border-t border-white/5 space-y-4" onclick="event.stopPropagation()">
                                <h4 class="text-xs font-bold text-on-surface-variant/80 uppercase tracking-wider">Market Analysis & Setup</h4>
                                <div class="relative w-full aspect-[16/10] bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center">
                                    <img src="/api/trades/chart?symbol=${encodeURIComponent(trade.symbol)}&entry=${entry}&tp=${tp}&sl=${sl}&side=${trade.side}&open_ts=${trade.open_time}&type=${trade.type}" class="w-full h-full object-cover" alt="Trade Chart" />
                                </div>
                                
                                <button onclick="confirmClosePosition('${trade.id}', '${trade.type}', '${trade.symbol}')" class="w-full h-10 bg-error/15 hover:bg-error/25 border border-error/30 text-error font-bold text-xs uppercase tracking-wider rounded-lg flex items-center justify-center gap-2 mt-2 cursor-pointer transition-all active:scale-[0.98]">
                                    <span class="material-symbols-outlined text-[16px]">close</span>
                                    Market Close ${displaySymbol}
                                </button>
                            </div>
                        `;
                    } else if (isExpanded) {
                        progressBarHtml = `
                            <div class="mt-4 pt-4 border-t border-white/5 space-y-4" onclick="event.stopPropagation()">
                                <div class="text-center py-4 text-xs text-on-surface-variant">
                                    Live R:R levels are not configured for this manual or untracked position.
                                </div>
                                <button onclick="confirmClosePosition('${trade.id}', '${trade.type}', '${trade.symbol}')" class="w-full h-10 bg-error/15 hover:bg-error/25 border border-error/30 text-error font-bold text-xs uppercase tracking-wider rounded-lg flex items-center justify-center gap-2 cursor-pointer transition-all active:scale-[0.98]">
                                    <span class="material-symbols-outlined text-[16px]">close</span>
                                    Market Close ${displaySymbol}
                                </button>
                            </div>
                        `;
                    }
    
                    return `
                        <div onclick="toggleTradeExpand('${trade.id}')" class="glass-card rounded-lg p-4 border border-white/5 flex flex-col gap-3 cursor-pointer hover:border-white/20 transition-all">
                            <div class="flex justify-between items-center">
                                <div class="flex items-center gap-2">
                                    <div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-sm">
                                        ${assetIcon}
                                    </div>
                                    <div>
                                        <p class="font-label-md text-label-md font-bold text-on-surface truncate min-w-0">${displaySymbol}</p>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1">
                                            <span class="material-symbols-outlined text-[16px] ${trade.side === 'LONG' ? 'text-primary' : 'text-error'} shrink-0">${trade.side === 'LONG' ? 'trending_up' : 'trending_down'}</span>
                                            ${dateStr}
                                        </p>
                                    </div>
                                </div>
                                <div class="flex items-center gap-2">
                                    <button onclick="event.stopPropagation(); window.shareTradeCard('${trade.type}', '${trade.symbol}', '${trade.side}', ${trade.roe}, ${trade.entry_price}, ${trade.mark_price}, ${trade.unrealized_pnl})" class="p-1.5 text-on-surface-variant hover:text-primary rounded-full hover:bg-white/5 transition-colors cursor-pointer flex items-center justify-center" title="Share Trade Card">
                                        <span class="material-symbols-outlined text-[18px]">share</span>
                                    </button>
                                    <div class="text-right">
                                        <p class="font-numeric-data text-numeric-data font-bold ${pnlColor}">
                                            <span ${inlineBlur}>${(trade.unrealized_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(trade.unrealized_pnl || 0).toFixed(2)}</span>
                                            ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> / <span ${inlineBlur}>+$${(Math.abs(trade.tp_price - trade.entry_price) * (trade.qty || 0)).toFixed(2)}</span></span>` : ''}
                                        </p>
                                        <p class="font-numeric-data text-numeric-data text-sm ${roeColor}">
                                            ${(trade.roe || 0) >= 0 ? '+' : ''}${(trade.roe || 0).toFixed(2)}%
                                            ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> of ${Math.abs(((trade.tp_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0)}%</span>` : ''}
                                        </p>
                                    </div>
                                    <span class="material-symbols-outlined text-on-surface-variant/60 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}">expand_more</span>
                                </div>
                            </div>
                            <div class="flex justify-between items-center pt-3 border-t border-white/10">
                                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                    SL: <span class="text-on-surface">$${(trade.sl_price || 0).toFixed(4)} (${trade.entry_price > 0 && trade.sl_price > 0 ? (((trade.sl_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0) : '0'}%)</span>
                                </div>
                                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                    TP: <span class="text-on-surface">$${(trade.tp_price || 0).toFixed(4)} (${trade.entry_price > 0 && trade.tp_price > 0 ? (((trade.tp_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0) : '0'}%)</span>
                                </div>
                            </div>
                            ${progressBarHtml}
                        </div>
                    `;
                }).join('');
            }
        } else {
            const filteredHistory = STATE.history.filter(t => t.type === type);
            if (filteredHistory.length === 0) {
                listHtml = `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No trade history</p>
                    </div>
                `;
            } else {
                const timeAgo = (ts) => {
                    const diff = Math.floor(Date.now() / 1000) - ts;
                    if (diff < 60) return "Just now";
                    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
                    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
                    return Math.floor(diff / 86400) + "d ago";
                };
                
                listHtml = filteredHistory.map(t => {
                    const dateStr = t.close_time ? timeAgo(t.close_time) : 'Recent';
                    let displaySymbol = t.symbol;
                    if (t.type === 'crypto') {
                        displaySymbol = displaySymbol.replace(/\\/USDT.*$/, '');
                    }
                    
                    const pnlColor = (t.net_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const roePct = t.pnl_pct !== undefined ? t.pnl_pct : (t.roe_val !== undefined ? t.roe_val : (t.roe !== undefined ? t.roe : 0));
                    const roeColor = roePct >= 0 ? 'text-tertiary' : 'text-error';
                    const assetIcon = t.type === 'stock' ? '🦙' : '🪙';
                    const isLong = t.side === 'LONG' || t.side === 'l' || t.side === 'long';
                    
                    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                    const inlineBlur = isPrivacyOn ? 'style="filter: blur(5px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\\'none\\'" onmouseleave="this.style.filter=\\'blur(5px)\\'"' : '';
                    
                    return `
                        <div class="glass-card p-4 rounded-lg flex justify-between items-center border border-white/5">
                            <div class="flex items-center gap-3">
                                <div class="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-lg shrink-0">
                                    ${assetIcon}
                                </div>
                                <div class="min-w-0">
                                    <p class="font-label-md text-label-md font-bold text-on-surface flex items-center gap-1 truncate">
                                        ${displaySymbol}
                                        <span class="material-symbols-outlined text-[16px] ${isLong ? 'text-primary' : 'text-error'} shrink-0">${isLong ? 'trending_up' : 'trending_down'}</span>
                                    </p>
                                    <p class="font-label-sm text-label-sm text-on-surface-variant">${dateStr}</p>
                                </div>
                            </div>
                            <div class="flex items-center gap-2">
                                <button onclick="event.stopPropagation(); window.shareTradeCard('${t.type}', '${t.symbol}', '${t.side}', ${roePct}, ${t.entry_price || 0}, ${t.close_price || t.price || 0}, ${t.net_pnl || 0})" class="px-2.5 h-8 bg-surface-container border border-white/10 text-on-surface font-bold text-xs uppercase rounded-lg hover:bg-white/5 hover:border-primary/30 transition-all cursor-pointer flex items-center justify-center gap-1.5 mr-2" title="Share Trade Card">
                                    Share & Earn
                                </button>
                                <div class="text-right flex flex-col items-end">
                                    <p class="font-numeric-data text-numeric-data font-bold text-lg ${roeColor}">
                                        ${roePct >= 0 ? '+' : ''}${roePct.toFixed(2)}%
                                    </p>
                                    <p class="font-numeric-data text-numeric-data text-xs ${pnlColor} mt-0.5">
                                        <span ${inlineBlur}>${(t.net_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(t.net_pnl || 0).toFixed(2)}</span>
                                    </p>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }
        return listHtml;
    };
    
    const cryptoHtml = generateTradeHtml('crypto');
    const stockHtml = generateTradeHtml('stock');
    
    const cryptoCount = tradesMode === 'active' ? STATE.open_trades.filter(t => t.type === 'crypto').length : STATE.history.filter(t => t.type === 'crypto').length;
    const stockCount = tradesMode === 'active' ? STATE.open_trades.filter(t => t.type === 'stock').length : STATE.history.filter(t => t.type === 'stock').length;

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] md:max-w-5xl mx-auto">
            <div class="glass-card rounded-full flex border border-white/10 p-1 w-full max-w-[500px] mx-auto relative overflow-hidden z-10">
                <button onclick="setTradesMode('active')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${tradesMode === 'active' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Active Positions (${STATE.open_trades ? STATE.open_trades.length : 0})
                </button>
                <button onclick="setTradesMode('closed')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${tradesMode === 'closed' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Closed History (${STATE.history ? STATE.history.length : 0})
                </button>
            </div>

            <!-- Crypto vs Stocks Segmented Controller (Mobile Only) -->
            <div class="glass-card rounded-full flex border border-white/10 p-1 w-full relative overflow-hidden z-10 md:hidden">
                <button onclick="setDashboardTab('crypto')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Crypto (${cryptoCount})
                </button>
                <button onclick="setDashboardTab('stock')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Stocks (${stockCount})
                </button>
            </div>
            
            <!-- Mobile View (Single List) -->
            <div class="space-y-stack-gap md:hidden">
                ${isCrypto ? cryptoHtml : stockHtml}
            </div>
            
            <!-- Desktop View (Two Columns) -->
            <div class="hidden md:grid md:grid-cols-2 md:gap-6">
                <!-- Crypto Column -->
                <div>
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center gap-2">
                        <span>🪙</span> Crypto (${cryptoCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${cryptoHtml}
                    </div>
                </div>
                <!-- Stocks Column -->
                <div>
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center gap-2">
                        <span>🦙</span> Stocks (${stockCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${stockHtml}
                    </div>
                </div>
            </div>
            
            ${tradesMode === 'active' && STATE.open_trades.length > 0 ? `
                <div class="max-w-[500px] mx-auto mt-6">
                    <button onclick="panicCloseAll()" class="w-full h-12 bg-red-900/40 text-error font-label-md text-label-md font-bold rounded-lg border border-error/50 hover:bg-error/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                        <span class="material-symbols-outlined">warning</span>
                        🚨 PANIC - Close All Positions
                    </button>
                </div>
            ` : ''}
        </main>
    `;
}"""

content = content[:start_idx] + new_block + content[end_idx:]

with open('app.js', 'w') as f:
    f.write(content)

print("Updated app.js")

