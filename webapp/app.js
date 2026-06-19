const API_BASE = '/api';

function getQueryParam(name) {
    let match = RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
    if (match) return match[1];
    match = RegExp('[?&]' + name + '=([^&]*)').exec(window.location.hash);
    return match ? match[1] : null;
}

function clearQueryParamFromUrl(paramName) {
    const url = new URL(window.location);
    if (url.searchParams.has(paramName)) {
        url.searchParams.delete(paramName);
        window.history.replaceState({}, '', url);
    }
    if (window.location.hash.includes(paramName + '=')) {
        let hash = window.location.hash;
        hash = hash.replace(new RegExp(`[?&]${paramName}=[^&]*`), '');
        window.history.replaceState({}, '', window.location.pathname + window.location.search + hash);
    }
}

const ZKCrypto = {
    async deriveMasterKey(password, email) {
        const encoder = new TextEncoder();
        const baseKey = await window.crypto.subtle.importKey(
            "raw",
            encoder.encode(password),
            "PBKDF2",
            false,
            ["deriveKey"]
        );
        const salt = encoder.encode(email + "_sherpa_salt");
        return window.crypto.subtle.deriveKey(
            {
                name: "PBKDF2",
                salt: salt,
                iterations: 100000,
                hash: "SHA-256"
            },
            baseKey,
            { name: "AES-GCM", length: 256 },
            false,
            ["encrypt", "decrypt"]
        );
    },

    async encryptPrivateKey(privateKeyJwk, aesKey) {
        const encoder = new TextEncoder();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const encrypted = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            aesKey,
            encoder.encode(JSON.stringify(privateKeyJwk))
        );
        const ivBase64 = btoa(String.fromCharCode(...iv));
        const ciphertextBase64 = btoa(String.fromCharCode(...new Uint8Array(encrypted)));
        return ivBase64 + ":" + ciphertextBase64;
    },

    async decryptPrivateKey(encryptedStr, aesKey) {
        const parts = encryptedStr.split(":");
        if (parts.length !== 2) throw new Error("Invalid encrypted key format");
        const iv = new Uint8Array(atob(parts[0]).split("").map(c => c.charCodeAt(0)));
        const ciphertext = new Uint8Array(atob(parts[1]).split("").map(c => c.charCodeAt(0)));
        
        const decrypted = await window.crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            aesKey,
            ciphertext
        );
        const decoder = new TextDecoder();
        return JSON.parse(decoder.decode(decrypted));
    },

    async generateRSAKeyPair() {
        return window.crypto.subtle.generateKey(
            {
                name: "RSA-OAEP",
                modulusLength: 2048,
                publicExponent: new Uint8Array([1, 0, 1]),
                hash: "SHA-256"
            },
            true,
            ["encrypt", "decrypt"]
        );
    },

    async exportPublicKeyPEM(publicKey) {
        const exported = await window.crypto.subtle.exportKey("spki", publicKey);
        const b64 = btoa(String.fromCharCode(...new Uint8Array(exported)));
        let pem = "-----BEGIN PUBLIC KEY-----\n";
        for (let i = 0; i < b64.length; i += 64) {
            pem += b64.substring(i, i + 64) + "\n";
        }
        pem += "-----END PUBLIC KEY-----";
        return pem;
    },

    async importPrivateKey(privateKeyJwk) {
        return window.crypto.subtle.importKey(
            "jwk",
            privateKeyJwk,
            { name: "RSA-OAEP", hash: "SHA-256" },
            false,
            ["decrypt"]
        );
    },

    async decryptRSA(encryptedBase64, rsaPrivateKey) {
        const binary = atob(encryptedBase64);
        const array = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            array[i] = binary.charCodeAt(i);
        }
        const decrypted = await window.crypto.subtle.decrypt(
            { name: "RSA-OAEP" },
            rsaPrivateKey,
            array
        );
        const decoder = new TextDecoder();
        return decoder.decode(decrypted);
    }
};
// Pre-generate a keypair immediately to avoid registration CPU bottlenecks
window.sharedPregeneratedKeypair = ZKCrypto.generateRSAKeyPair();

async function setupZKKeys(email, password) {
    try {
        const keys = await apiRequest('/settings/zk-keys', 'GET');
        
        let passphrase = password;
        let aesKey = null;
        
        if (!passphrase && auth.currentUser) {
            // Persistent Firebase UID is stable across devices
            passphrase = auth.currentUser.uid;
            aesKey = await ZKCrypto.deriveMasterKey(passphrase, email);
            
            if (keys && keys.public_key && keys.encrypted_private_key) {
                try {
                    // Test if we can decrypt with the UID-derived key
                    const pKeyJwk = await ZKCrypto.decryptPrivateKey(keys.encrypted_private_key, aesKey);
                    sessionStorage.setItem('zk_private_key_jwk', JSON.stringify(pKeyJwk));
                    STATE.rsa_private_key = await ZKCrypto.importPrivateKey(pKeyJwk);
                    console.log("🔒 Decrypted and loaded ZK keys using Firebase UID.");
                    return;
                } catch (uidDecErr) {
                    console.log("⚠️ Decryption with UID failed. Trying legacy localStorage passphrase...");
                    const legacyPass = localStorage.getItem('zk_passphrase');
                    if (legacyPass) {
                        try {
                            const legacyKey = await ZKCrypto.deriveMasterKey(legacyPass, email);
                            const pKeyJwk = await ZKCrypto.decryptPrivateKey(keys.encrypted_private_key, legacyKey);
                            
                            // Re-encrypt the private key using the stable UID-derived key to migrate the user
                            const newEncrypted = await ZKCrypto.encryptPrivateKey(pKeyJwk, aesKey);
                            await apiRequest('/settings/zk-keys', 'POST', {
                                public_key: keys.public_key,
                                encrypted_private_key: newEncrypted
                            });
                            
                            sessionStorage.setItem('zk_private_key_jwk', JSON.stringify(pKeyJwk));
                            STATE.rsa_private_key = await ZKCrypto.importPrivateKey(pKeyJwk);
                            console.log("🔒 Decrypted legacy keys and migrated encryption to stable Firebase UID.");
                            return;
                        } catch (legacyDecErr) {
                            console.error("Legacy decryption also failed:", legacyDecErr);
                        }
                    }
                }
            }
        } else {
            // Default password-based derivation (or random fallback if no user is signed in)
            if (!passphrase) {
                passphrase = localStorage.getItem('zk_passphrase');
                if (!passphrase) {
                    passphrase = btoa(String.fromCharCode(...window.crypto.getRandomValues(new Uint8Array(24))));
                    localStorage.setItem('zk_passphrase', passphrase);
                }
            }
            aesKey = await ZKCrypto.deriveMasterKey(passphrase, email);
            
            if (keys && keys.public_key && keys.encrypted_private_key) {
                try {
                    const pKeyJwk = await ZKCrypto.decryptPrivateKey(keys.encrypted_private_key, aesKey);
                    sessionStorage.setItem('zk_private_key_jwk', JSON.stringify(pKeyJwk));
                    STATE.rsa_private_key = await ZKCrypto.importPrivateKey(pKeyJwk);
                    console.log("🔒 Decrypted and loaded pre-existing ZK keys.");
                    return;
                } catch (decErr) {
                    console.error("Could not decrypt pre-existing private key:", decErr);
                }
            }
        }
        
        // If we didn't return (decryption failed or no key exists), generate new keypair
        console.log("🔒 Generating new ZK Keypair...");
        const keypair = await (window.sharedPregeneratedKeypair || ZKCrypto.generateRSAKeyPair());
        // Pre-generate another one for future use/rotation
        window.sharedPregeneratedKeypair = ZKCrypto.generateRSAKeyPair();
        
        const pubKeyPem = await ZKCrypto.exportPublicKeyPEM(keypair.publicKey);
        const pKeyJwk = await window.crypto.subtle.exportKey("jwk", keypair.privateKey);
        sessionStorage.setItem('zk_private_key_jwk', JSON.stringify(pKeyJwk));
        
        // Ensure we have an AES key derived (fallback to random if all else failed)
        if (!aesKey) {
            passphrase = passphrase || localStorage.getItem('zk_passphrase') || btoa(String.fromCharCode(...window.crypto.getRandomValues(new Uint8Array(24))));
            localStorage.setItem('zk_passphrase', passphrase);
            aesKey = await ZKCrypto.deriveMasterKey(passphrase, email);
        }
        
        const encryptedPrivKey = await ZKCrypto.encryptPrivateKey(pKeyJwk, aesKey);
        
        await apiRequest('/settings/zk-keys', 'POST', {
            public_key: pubKeyPem,
            encrypted_private_key: encryptedPrivKey
        });
        
        STATE.rsa_private_key = keypair.privateKey;
        console.log("🔒 Generated and registered new ZK keypair.");
    } catch (err) {
        console.error("ZK Cryptography setup failed:", err);
    }
}

async function decryptAndProcessBalanceHistory() {
    if (!STATE.raw_balance_history || !STATE.raw_balance_history.length) {
        STATE.balance_history = [];
        return;
    }
    if (!STATE.rsa_private_key) {
        if (STATE.user && STATE.user.email) {
            await setupZKKeys(STATE.user.email, null);
        }
    }
    if (!STATE.rsa_private_key) {
        console.warn("🔐 Decryption key not available for balance history.");
        STATE.balance_history = null;
        return;
    }
    
    const decrypted = [];
    for (const item of STATE.raw_balance_history) {
        let cryptoBal = 0;
        let stockBal = 0;
        
        try {
            if (item.encrypted_crypto_balance) {
                const dec = await ZKCrypto.decryptRSA(item.encrypted_crypto_balance, STATE.rsa_private_key);
                cryptoBal = parseFloat(dec) || 0;
            }
        } catch (err) {
            console.error("Failed to decrypt crypto balance:", err);
        }
        
        try {
            if (item.encrypted_stock_balance) {
                const dec = await ZKCrypto.decryptRSA(item.encrypted_stock_balance, STATE.rsa_private_key);
                stockBal = parseFloat(dec) || 0;
            }
        } catch (err) {
            console.error("Failed to decrypt stock balance:", err);
        }
        
        decrypted.push({
            timestamp: item.timestamp,
            crypto: cryptoBal,
            stock: stockBal,
            total: cryptoBal + stockBal
        });
    }
    STATE.balance_history = decrypted;
}

window.handleChartHover = function(e, type, pointsJson) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const svgWidth = 500;
    const scale = svgWidth / rect.width;
    const svgX = x * scale;
    
    const points = JSON.parse(decodeURIComponent(pointsJson));
    if (!points || !points.length) return;
    
    let closest = null;
    let minDist = Infinity;
    
    const paddingLeft = 55;
    const paddingRight = 20;
    const minX = Math.min(...points.map(p => p.x));
    const maxX = Math.max(...points.map(p => p.x));
    
    points.forEach((p, idx) => {
        let px = paddingLeft + (points.length <= 1 ? (svgWidth - paddingLeft - paddingRight) / 2 : ((p.x - minX) / (maxX - minX)) * (svgWidth - paddingLeft - paddingRight));
        let dist = Math.abs(px - svgX);
        if (dist < minDist) {
            minDist = dist;
            closest = { ...p, index: idx, px: px };
        }
    });
    
    if (closest) {
        const markerLine = document.getElementById(`chart-marker-line-${type}`);
        const markerDot = document.getElementById(`chart-marker-dot-${type}`);
        const tooltip = document.getElementById(`chart-tooltip-${type}`);
        
        if (markerLine && markerDot && tooltip) {
            markerLine.setAttribute('x1', closest.px);
            markerLine.setAttribute('x2', closest.px);
            markerLine.classList.remove('hidden');
            
            const minYVal = Math.min(...points.map(p => p.y));
            let maxYVal = Math.max(...points.map(p => p.y));
            if (minYVal === maxYVal) {
                maxYVal = maxYVal * 1.1;
            } else {
                const pad = (maxYVal - minYVal) * 0.15;
                maxYVal = maxYVal + pad;
            }
            
            const yMinBound = Math.max(0, minYVal - (maxYVal - minYVal) * 0.15);
            const py = 180 - 25 - ((closest.y - yMinBound) / (maxYVal - yMinBound || 1)) * (180 - 20 - 25);
            
            markerDot.setAttribute('cx', closest.px);
            markerDot.setAttribute('cy', py);
            markerDot.classList.remove('hidden');
            
            const dateStr = new Date(closest.x * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
            const valStr = isPrivacyOn ? '••••••' : '$' + closest.y.toFixed(2);
            
            tooltip.innerHTML = `
                <div class="font-bold text-xs text-on-surface">${valStr}</div>
                <div class="text-[10px] text-on-surface-variant">${dateStr}</div>
            `;
            
            const tooltipWidth = tooltip.offsetWidth || 80;
            let tooltipX = (closest.px / svgWidth) * rect.width - tooltipWidth / 2;
            if (tooltipX < 0) tooltipX = 0;
            if (tooltipX + tooltipWidth > rect.width) tooltipX = rect.width - tooltipWidth;
            
            tooltip.style.left = `${tooltipX}px`;
            tooltip.style.top = `10px`;
            tooltip.style.opacity = '1';
        }
    }
};

window.handleChartLeave = function(type) {
    const markerLine = document.getElementById(`chart-marker-line-${type}`);
    const markerDot = document.getElementById(`chart-marker-dot-${type}`);
    const tooltip = document.getElementById(`chart-tooltip-${type}`);
    
    if (markerLine) markerLine.classList.add('hidden');
    if (markerDot) markerDot.classList.add('hidden');
    if (tooltip) tooltip.style.opacity = '0';
};

window.forceRefreshSegment = function(segment) {
    if (segment === 'crypto') {
        STATE.is_loading_crypto_balance = true;
    } else {
        STATE.is_loading_stock_balance = true;
    }
    
    const updateViewIfOnDashboard = () => {
        if (STATE.current_view === 'dashboard') {
            renderView();
        }
    };
    
    updateViewIfOnDashboard();
    
    const balancePromise = apiRequest(`/user/balance?segment=${segment}&bypass_cache=true`)
        .then(bal => {
            if (bal) {
                if (segment === 'crypto') {
                    STATE.crypto_balance = bal.crypto_balance;
                } else {
                    STATE.stock_balance = bal.stock_balance;
                }
                STATE.total_balance = STATE.crypto_balance + STATE.stock_balance;
            }
        }).catch(err => {
            console.error(`Failed to refresh balance for ${segment}:`, err);
        });
        
    const statsPromise = apiRequest(`/user/stats?segment=${segment}&bypass_cache=true`)
        .then(stats => {
            if (stats && stats[segment]) {
                if (!STATE.stats) STATE.stats = {};
                STATE.stats[segment] = stats[segment];
                if (segment === 'crypto') {
                    STATE.stats.active_crypto_strategy = stats.active_crypto_strategy;
                } else {
                    STATE.stats.active_stock_strategy = stats.active_stock_strategy;
                }
            }
        }).catch(err => {
            console.error(`Failed to refresh stats for ${segment}:`, err);
        });
        
    const openTradesPromise = apiRequest(`/trades/open?segment=${segment}&bypass_cache=true`)
        .then(open => {
            if (open) {
                STATE.open_trades = STATE.open_trades.filter(t => t.type !== segment).concat(open);
            }
        }).catch(err => {
            console.error(`Failed to refresh open trades for ${segment}:`, err);
        });
        
    Promise.all([balancePromise, statsPromise, openTradesPromise])
        .finally(() => {
            if (segment === 'crypto') {
                STATE.is_loading_crypto_balance = false;
            } else {
                STATE.is_loading_stock_balance = false;
            }
            updateViewIfOnDashboard();
        });
};


let STATE = {
    user: null,
    crypto_balance: 0.0,
    stock_balance: 0.0,
    total_balance: 0.0,
    open_trades: [],
    history: [],
    free_history: [],
    active_signals: [],
    active_signals_sort_by: 'pnl',
    open_trades_sort_by: 'pnl',
    closed_signals: [],
    stats: null,
    free_stats: null,
    landing_auth_mode: 'login',
    current_view: 'login',
    dashboard_tab: 'crypto',
    trades_mode: null,
    signals_tab: 'active',
    expanded_trade_id: null,
    expanded_signal_id: null,
    is_loading_signals: false,
    is_loading_active_signals: true,
    is_loading_dashboard: false,
    is_loading_crypto_balance: false,
    is_loading_stock_balance: false,
    history_expanded_id: null,
    free_history_expanded_id: null,
    profile_menu_open: false,
    google_verifying: false,
    backtest: { running: false, result: null, period: '3 Years', capital: 1000, strategy: 'Valkyrie Elite Scalper' }
};

const STRATEGY_ICONS = {
    "Mean Reversion Scalper": "📈",
    "Valkyrie Elite Scalper": "🛡️",
    "Sherpa Velocity Pullback": "🦙"
};

const STRATEGY_GUIDES = {
    "Mean Reversion Scalper": {
        philosophy: "Mean Reversion. Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.",
        indicators: "Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.",
        pace: "Highly active. Averages ~0.84 trades/day.",
        drawdown: "Optimized for recommended <strong class='text-primary'>1.0% risk</strong>, maintaining a safe drawdown of <strong class='text-primary'>~21.9%</strong> (well below the 25% safety ceiling) while delivering <strong class='text-[#ffdb3c]'>+384.1%</strong> PnL.",
        img: "/api/charts/mean_reversion_infographic.png",
        backtest_stats: null
    },
    "Valkyrie Elite Scalper": {
        philosophy: "Wick Rejection. Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.",
        indicators: "Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.",
        pace: "Patient and calculated. Averages ~0.68 trades/day.",
        drawdown: "Highly protected; ultra-low peak drawdown ceiling (<strong class='text-primary'>~16.2% to 19.5%</strong> on expanded basket).",
        img: "/api/charts/valkyrie_elite_infographic_ai.png",
        backtest_stats: {
            win_rate: "58%", trades: "747", sharpe: "3.86", max_dd: "-19.5%", net_pnl: "+240.1%", final_bal: "$34,010.00",
            img: "/api/charts/valkyrie_equity.png"
        }
    },
    "Sherpa Velocity Pullback": {
        philosophy: "Momentum Pullback. Targets short-term oversold pullback cycles on megacap US equities (NASDAQ/NYSE top 40) during robust, verified uptrends using SuperTrend filtering.",
        indicators: "Daily Close > EMA(200), SuperTrend(10, 3) is UP, 4-period RSI (< 26).",
        pace: "Daily swing. Scans daily at market open (9:31 AM EST). Averages ~0.42 trades/day.",
        drawdown: "Highly optimized equity curve, maintaining a tight <strong class='text-primary'>22.7%</strong> maximum drawdown with a verified <strong class='text-[#ffdb3c]'>+252.5%</strong> return and high <strong class='text-tertiary'>68.4%</strong> win rate over a 5-year period.",
        img: "/api/charts/stock_strategy_infographic.png",
        backtest_stats: {
            win_rate: "68.4%", trades: "785", sharpe: "1.22", max_dd: "-22.7%", net_pnl: "+252.5%", final_bal: "$35,253.71",
            img: "/api/charts/stock_master_audit.png"
        }
    }
};

function renderStrategyGuideContent(name, includeBacktest = true) {
    const guide = STRATEGY_GUIDES[name] || STRATEGY_GUIDES["Valkyrie Elite Scalper"];
    const isStock = (name === 'Sherpa Velocity Pullback');
    let html = '';
    
    if (includeBacktest && guide.backtest_stats) {
        html += `
        <div class="mb-4">
            <div class="flex items-center gap-2 mb-2">
                <span class="material-symbols-outlined text-primary text-sm">history</span>
                <h5 class="text-xs font-bold text-primary uppercase tracking-wider">${isStock ? '5-Year' : '3-Year'} Historical Backtest</h5>
            </div>
            <p class="text-[10px] text-on-surface-variant mb-4 leading-relaxed">
                These performance metrics and equity curves are based on <strong>${isStock ? '5' : '3'} years of rigorous historical data</strong>. (Simulated with $10k starting capital and a strict 2% risk management per trade for stocks, 1.5% for crypto).
            </p>
            
            ${guide.backtest_stats.img ? `
            <div class="relative overflow-y-auto rounded-xl border border-white/10 bg-black/40 max-h-[400px] mb-4 flex items-start justify-center cursor-zoom-in group shadow-lg custom-scrollbar" onclick="window.open('${guide.backtest_stats.img}', '_blank')">
                <img src="${guide.backtest_stats.img}" alt="Backtest Equity Curve" class="w-full h-auto object-contain" onerror="this.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='"/>
                <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 pointer-events-none">
                    <span class="material-symbols-outlined text-white text-2xl">zoom_in</span>
                    <span class="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
                </div>
            </div>
            ` : ''}
            
            <div class="grid grid-cols-2 gap-2">
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Win Rate</div>
                    <div class="text-tertiary font-bold text-sm">${guide.backtest_stats.win_rate}</div>
                </div>
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Total Trades</div>
                    <div class="text-on-surface font-bold text-sm">${guide.backtest_stats.trades}</div>
                </div>
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Sharpe Ratio</div>
                    <div class="text-[#ffdb3c] font-bold text-sm">${guide.backtest_stats.sharpe}</div>
                </div>
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Max Drawdown</div>
                    <div class="text-error font-bold text-sm">${guide.backtest_stats.max_dd}</div>
                </div>
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Net PnL</div>
                    <div class="text-tertiary font-bold text-sm">${guide.backtest_stats.net_pnl}</div>
                </div>
                <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                    <div class="text-[9px] text-on-surface-variant uppercase">Final Balance</div>
                    <div class="text-on-surface font-bold text-sm">${guide.backtest_stats.final_bal}</div>
                </div>
            </div>
        </div>
        <div class="my-4 border-t border-white/5 w-full"></div>
        `;
    }

    html += `
        <div class="relative overflow-y-auto rounded-xl border border-white/10 bg-black/40 max-h-[400px] flex items-start justify-center cursor-zoom-in group shadow-lg custom-scrollbar" onclick="window.open('${guide.img}', '_blank')">
            <img src="${guide.img}" alt="${name} Infographic" class="w-full h-auto object-contain" onerror="this.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='"/>
            <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 pointer-events-none">
                <span class="material-symbols-outlined text-white text-2xl">zoom_in</span>
                <span class="text-xs text-white font-bold uppercase tracking-wider">Expand Infographic</span>
            </div>
        </div>
        <div class="space-y-2 bg-surface-container/30 rounded-xl p-4 mt-4 text-left" style="font-size: 11px;">
            <div>
                <span class="text-on-surface-variant font-bold uppercase tracking-wider block mb-1" style="font-size: 9px;">Philosophy</span>
                <p class="text-on-surface leading-relaxed mt-0.5">${guide.philosophy}</p>
            </div>
            <div class="pt-2">
                <span class="text-on-surface-variant font-bold uppercase tracking-wider block mb-1" style="font-size: 9px;">Indicators</span>
                <p class="text-on-surface leading-relaxed mt-0.5">${guide.indicators}</p>
            </div>
            <div class="pt-2">
                <span class="text-on-surface-variant font-bold uppercase tracking-wider block mb-1" style="font-size: 9px;">Execution Pace</span>
                <p class="text-on-surface leading-relaxed mt-0.5">${guide.pace}</p>
            </div>
            <div class="pt-2">
                <span class="text-on-surface-variant font-bold uppercase tracking-wider block mb-1" style="font-size: 9px;">Drawdown Profile</span>
                <p class="text-on-surface leading-relaxed mt-0.5">${guide.drawdown}</p>
            </div>
        </div>
    `;
    
    return html;
}


// ----------------- Toast Utility -----------------
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `glass-card p-4 rounded-lg shadow-lg flex items-center gap-2 pointer-events-auto transform translate-y-2 opacity-0 transition-all duration-300 border-l-4 ${
        type === 'error' ? 'border-l-error' : type === 'warning' ? 'border-l-secondary-container' : 'border-l-tertiary'
    }`;
    
    const icon = type === 'error' ? 'error' : type === 'warning' ? 'warning' : 'check_circle';
    const color = type === 'error' ? 'text-error' : type === 'warning' ? 'text-secondary-container' : 'text-tertiary';
    
    toast.innerHTML = `
        <span class="material-symbols-outlined ${color}">${icon}</span>
        <span class="text-on-surface font-body-md text-body-md font-medium">${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Trigger animations
    setTimeout(() => {
        toast.classList.remove('opacity-0', 'translate-y-2');
    }, 10);
    
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

window.setLandingAuthMode = function(mode) {
    STATE.landing_auth_mode = mode;
    renderView();
    if (mode === 'login' && STATE.current_view === 'landing') {
        initGoogleSignIn();
    }
}

// ----------------- API Requests -----------------
async function apiRequest(endpoint, method = 'GET', data = null) {
    const url = `${API_BASE}${endpoint}`;
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'omit' // We are using Bearer tokens now
    };
    
    // Inject Bearer Token
    let token = localStorage.getItem('session_token');
    if (window.auth && auth.currentUser) {
        try {
            token = await auth.currentUser.getIdToken();
            localStorage.setItem('session_token', token);
        } catch (e) {
            console.error("Failed to refresh Firebase token in apiRequest:", e);
        }
    }
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(url, options);
        if (response.status === 401) {
            localStorage.removeItem('session_token');
            if (window.location.hash !== '#/login' && window.location.hash !== '#/register' && window.location.hash !== '#/landing' && window.location.hash !== '#/' && window.location.hash !== '#/help') {
                // Unauthorized → redirect to landing
                STATE.user = null;
                navigate('#/landing');
            }
            if (endpoint === '/auth/login') {
                try {
                    const errorData = await response.json();
                    throw new Error(errorData.error || "Invalid password. If you can't remember it, click 'Forgot password?' to reset it.");
                } catch (e) {
                    if (e.message.includes("Invalid password")) throw e;
                    throw new Error("Invalid password. If you can't remember it, click 'Forgot password?' to reset it.");
                }
            }
            return null;
        }
        
        if (response.status === 502 || response.status === 503) {
            throw new Error("The MetaverseSherpa is pushing a new release up the mountain.");
        }
        
        let resData;
        try {
            resData = await response.json();
        } catch (e) {
            if (!response.ok) {
                throw new Error("The MetaverseSherpa is pushing a new release up the mountain.");
            }
            throw new Error("Invalid response from server");
        }
        
        if (!response.ok) {
            throw new Error(resData.error || resData.message || "Something went wrong");
        }
        return resData;
    } catch (err) {
        showToast(err.message, "error");
        return null;
    }
}

// ----------------- Google Sign In Loading & Helpers -----------------
let googleAuthOverlayTimer = null;
let googleAuthActive = false;

window.showGoogleLoading = function(title = "Connecting to Google", subtitle = "Please select your Google account in the popup window.") {
    const overlay = document.getElementById('loading-overlay');
    const titleEl = document.getElementById('loading-title');
    const subtitleEl = document.getElementById('loading-subtitle');
    if (overlay) {
        if (titleEl) titleEl.innerText = title;
        if (subtitleEl) subtitleEl.innerText = subtitle;
        overlay.classList.add('active');
        googleAuthActive = true;
    }
};

window.hideGoogleLoading = function() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.remove('active');
        googleAuthActive = false;
        if (googleAuthOverlayTimer) {
            clearTimeout(googleAuthOverlayTimer);
            googleAuthOverlayTimer = null;
        }
    }
};

// Detect when user clicks Google Sign-In (losing window focus to the iframe)
window.addEventListener('blur', () => {
    // Small delay to ensure document.activeElement is updated
    setTimeout(() => {
        const activeEl = document.activeElement;
        if (activeEl && (
            activeEl.id === 'google-signin-btn-login' || 
            activeEl.id === 'google-signin-btn-landing' || 
            (activeEl.tagName === 'IFRAME' && activeEl.src && activeEl.src.includes('accounts.google.com'))
        )) {
            window.showGoogleLoading("Connecting to Google", "Please select your Google account in the popup window.");
        }
    }, 100);
});

// Detect when user closes the popup or returns to window
window.addEventListener('focus', () => {
    if (googleAuthActive) {
        if (googleAuthOverlayTimer) clearTimeout(googleAuthOverlayTimer);
        googleAuthOverlayTimer = setTimeout(() => {
            // Only hide if we aren't currently verifying/authenticating the token
            if (googleAuthActive && !STATE.google_verifying) {
                window.hideGoogleLoading();
            }
        }, 1500); // 1.5s window to allow handleGoogleCredentialResponse to trigger
    }
});

// ----------------- Google Sign In Initialization -----------------
let cachedGoogleClientId = null;
let googleInitialized = false;

window.renderGoogleButtons = function() {
    if (!window.google || !cachedGoogleClientId) return;
    
    if (!googleInitialized) {
        window.google.accounts.id.initialize({
            client_id: cachedGoogleClientId,
            callback: handleGoogleCredentialResponse,
            use_fedcm_for_prompt: false
        });
        googleInitialized = true;
    }

    // Render button on Login Page container if present
    const btnLogin = document.getElementById('google-signin-btn-login');
    if (btnLogin) {
        window.google.accounts.id.renderButton(btnLogin, {
            theme: 'outline',
            size: 'large',
            width: btnLogin.clientWidth || 368,
            text: 'continue_with',
            shape: 'pill'
        });
    }

    // Render button on Landing Page container if present
    const btnLanding = document.getElementById('google-signin-btn-landing');
    if (btnLanding) {
        window.google.accounts.id.renderButton(btnLanding, {
            theme: 'outline',
            size: 'large',
            width: btnLanding.clientWidth || 340,
            text: 'continue_with',
            shape: 'pill'
        });
    }
};

async function initGoogleSignIn() {
    if (!cachedGoogleClientId) {
        // Fetch the client ID from the backend securely so it's not hardcoded in the frontend repository
        const config = await apiRequest('/config', 'GET');
        cachedGoogleClientId = config ? config.google_client_id : null;
    }
    
    if (!cachedGoogleClientId) {
        console.error("Google Client ID not found from backend config.");
        return;
    }

    // Inject official Google script dynamically
    if (!document.getElementById('google-gsi-script')) {
        const script = document.createElement('script');
        script.id = 'google-gsi-script';
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => {
            window.renderGoogleButtons();
        };
        document.head.appendChild(script);
    } else {
        // If script is already injected (e.g. view transitions), just render button
        setTimeout(window.renderGoogleButtons, 50);
    }
}

async function handleGoogleCredentialResponse(response) {
    STATE.google_verifying = true;
    window.showGoogleLoading("Verifying Account", "Loading your premium dashboard...");
    
    try {
        const credential = firebase.auth.GoogleAuthProvider.credential(response.credential);
        const userCredential = await auth.signInWithCredential(credential);
        const idToken = await userCredential.user.getIdToken();
        
        localStorage.setItem('session_token', idToken);
        
        const referrer = localStorage.getItem('referred_by');
        const payload = {};
        if (referrer) {
            payload.referred_by = parseInt(referrer);
        }
        
        const res = await apiRequest('/auth/sync', 'POST', payload);
        STATE.google_verifying = false;
        
        if (res) {
            STATE.user = res.user;
            await setupZKKeys(res.user.email, null);
            const profile = await apiRequest('/user/profile');
            if (profile) {
                STATE.user = profile;
            }
            if (referrer) {
                showToast("Referral successfully applied! Welcome to Metaverse Sherpa.");
                localStorage.removeItem('referred_by');
            }
            navigate('#/dashboard');
        }
    } catch (error) {
        STATE.google_verifying = false;
        showToast(error.message, 'error');
    }
    window.hideGoogleLoading();
}

// ----------------- Routing & View Management -----------------
function navigate(hash) {
    window.location.hash = hash;
}

async function handleRoute() {
    window.scrollTo(0, 0);

    const savedPrivKey = sessionStorage.getItem('zk_private_key_jwk');
    if (savedPrivKey && !STATE.rsa_private_key) {
        try {
            STATE.rsa_private_key = await ZKCrypto.importPrivateKey(JSON.parse(savedPrivKey));
            console.log("🔒 Restored ZK private key from sessionStorage.");
        } catch (err) {
            console.error("Failed to restore ZK key:", err);
        }
    }

    const token = localStorage.getItem('session_token');
    const isFirstLoad = token && !STATE.user;
    let hash = window.location.hash || '#/landing';
    if (hash.includes('?')) {
        hash = hash.split('?')[0];
    }
    if (isFirstLoad && hash !== '#/landing' && hash !== '#/' && hash !== '#/login' && hash !== '#/register' && hash !== '#/help') {
        window.showGoogleLoading("Climbing up the Metaverse...", "Loading your secure trading session...");
    }

    const refCode = getQueryParam('ref');
    if (refCode) {
        localStorage.setItem('referred_by', refCode);
        clearQueryParamFromUrl('ref');
        if (hash !== '#/login') {
            navigate('#/login');
            return;
        }
    }

    const giftCode = getQueryParam('gift');
    if (giftCode) {
        localStorage.setItem('pending_gift_code', giftCode);
        clearQueryParamFromUrl('gift');
        if (hash !== '#/landing') {
            navigate('#/landing');
            return;
        }
    }

    const tgSync = getQueryParam('tg_sync');
    if (tgSync) {
        localStorage.setItem('pending_tg_sync', tgSync);
        clearQueryParamFromUrl('tg_sync');
    }

    // Auto-login redirect logic
    if (token && (hash === '#/login' || hash === '#/register' || hash === '#/landing' || hash === '#/' || window.location.hash.startsWith('#/reset-password'))) {
        try {
            const profile = await apiRequest('/user/profile');
            if (profile) {
                STATE.user = profile;
                navigate('#/dashboard');
                return;
            }
        } catch (e) {
            // Proceed to Auth Guard if validation fails
        }
    }
    
    // Auth Guard
    if (hash === '#/login' || hash === '#/register' || hash === '#/landing' || hash === '#/' || window.location.hash.startsWith('#/reset-password')) {
        let view = (hash === '#/' || hash === '#/landing') ? 'landing' : hash.substring(2);
        
        if (window.location.hash.startsWith('#/reset-password')) {
            const urlParams = new URLSearchParams(window.location.hash.split('?')[1]);
            STATE.reset_token = urlParams.get('token');
            STATE.landing_auth_mode = 'reset_password';
            view = 'landing';
        }
        STATE.current_view = view;
        
        if (view === 'landing') {
            if ((!STATE.signals || STATE.signals.length === 0) && !STATE.free_stats) {
                STATE.is_loading_signals = true;
                renderView(); // Render loading skeleton
            } else {
                STATE.is_loading_signals = false;
                renderView(); // Instantly load cached signals
            }
            
            // Revalidate in background
            Promise.all([
                apiRequest('/signals/active'),
                apiRequest('/stats/free')
            ]).then(([signals, freeStats]) => {
                STATE.signals = signals || [];
                if (freeStats) {
                    STATE.free_stats = freeStats;
                }
                STATE.is_loading_signals = false;
                renderView();
            }).catch(err => {
                console.error("Error loading landing data in background:", err);
                STATE.is_loading_signals = false;
                renderView();
            });
        } else {
            renderView();
        }

        if (STATE.current_view === 'login' || STATE.current_view === 'landing') {
            initGoogleSignIn();
        }
        return;
    }
    
    // Fetch profile status to keep session sync
    if (STATE.user) {
        // Background sync: update profile asynchronously without blocking the route transition
        apiRequest('/user/profile').then(profile => {
            if (profile) {
                const oldPremium = STATE.user.is_premium;
                STATE.user = profile;
                if (oldPremium !== profile.is_premium && STATE.current_view === 'dashboard') {
                    renderView();
                }
            }
        }).catch(err => console.error("Error updating profile in background:", err));
    } else {
        // Blocking: first load only requires profile to render
        try {
            const profile = await apiRequest('/user/profile');
            if (!profile && hash !== '#/help') {
                window.hideGoogleLoading();
                return;
            }
            STATE.user = profile;
        } catch (e) {
            window.hideGoogleLoading();
            if (hash !== '#/help') return;
        }
    }
    window.hideGoogleLoading();
    
    // Check and redeem pending gift code if any
    await checkAndRedeemPendingGift();
    
    // Check and sync pending telegram chat ID if any
    await checkAndSyncPendingTelegram();
    
    // Check for deployment success message if admin
    if (STATE.user) {
        const isSuperAdmin = STATE.user.telegram_chat_id === 1567788633;
        const isAdmin = STATE.user.is_admin || isSuperAdmin;
        if (isAdmin) {
            checkDeploymentAlert();
        }
    }
    
    // Determine view route
    if (hash === '#/dashboard') {
        STATE.current_view = 'dashboard';
        STATE.is_loading_crypto_balance = true;
        STATE.is_loading_stock_balance = true;
        
        // 1. Render immediately using cached/default state for a lightning fast load
        renderView();
        
        // 2. Fetch ALL data (including live balance) in the background asynchronously
        const cryptoStatsPromise = (STATE.user && STATE.user.is_premium) ? apiRequest('/user/stats?segment=crypto') : Promise.resolve(null);
        const stockStatsPromise = (STATE.user && STATE.user.is_premium) ? apiRequest('/user/stats?segment=stock') : Promise.resolve(null);
        const freeStatsPromise = apiRequest('/stats/free');
        const balHistoryPromise = (STATE.user && STATE.user.is_premium) ? apiRequest('/user/balance-history') : Promise.resolve(null);

        const updateViewIfOnDashboard = () => {
            if (STATE.current_view === 'dashboard') {
                renderView();
            }
        };

        // Fetch Crypto balance
        apiRequest('/user/balance?segment=crypto').then(bal => {
            if (bal) {
                STATE.crypto_balance = bal.crypto_balance;
                STATE.crypto_auth_success = bal.crypto_auth_success;
                STATE.total_balance = STATE.crypto_balance + STATE.stock_balance;
            }
            STATE.is_loading_crypto_balance = false;
            updateViewIfOnDashboard();
            if (window.location.hash.includes('#/settings')) renderView();
        }).catch(err => {
            STATE.is_loading_crypto_balance = false;
            updateViewIfOnDashboard();
        });

        // Fetch Stock balance
        apiRequest('/user/balance?segment=stock').then(bal => {
            if (bal) {
                STATE.stock_balance = bal.stock_balance;
                STATE.stock_auth_success = bal.stock_auth_success;
                STATE.total_balance = STATE.crypto_balance + STATE.stock_balance;
            }
            STATE.is_loading_stock_balance = false;
            updateViewIfOnDashboard();
            if (window.location.hash.includes('#/settings')) renderView();
        }).catch(err => {
            STATE.is_loading_stock_balance = false;
            updateViewIfOnDashboard();
        });

        apiRequest('/signals/active').then(sigs => {
            if (sigs) {
                STATE.active_signals = sigs;
                
                if (window.location.hash.includes('debug_signals=true') || window.location.href.includes('debug_signals=true')) {
                    const now = Math.floor(Date.now() / 1000);
                    STATE.active_signals = [
                        {
                            id: "debug-crypto-1",
                            symbol: "BTC/USDT",
                            strategy: "Valkyrie Elite Scalper",
                            side: "LONG",
                            entry_price: 65400.0,
                            tp_price: 66000.0,
                            sl_price: 65000.0,
                            pnl_pct: 0.45,
                            pnl_usdt: 15.00,
                            open_time: now - 3600
                        },
                        {
                            id: "debug-stock-1",
                            symbol: "AAPL",
                            strategy: "Sherpa Velocity Pullback",
                            side: "LONG",
                            entry_price: 185.50,
                            tp_price: 195.00,
                            sl_price: 180.00,
                            pnl_pct: -1.25,
                            pnl_usdt: -5.50,
                            open_time: now - 86400
                        }
                    ];
                }
                
                const isAnyCalculating = sigs.some(s => s.pnl_pct === null || s.pnl_pct === undefined);
                if (isAnyCalculating && STATE.current_view === 'dashboard') {
                    setTimeout(window.pollActiveSignalsForHydration, 2000);
                }
            }
            STATE.is_loading_active_signals = false;
            updateViewIfOnDashboard();
        }).catch(err => {
            STATE.is_loading_active_signals = false;
            updateViewIfOnDashboard();
        });

        // Fetch Crypto open trades
        apiRequest('/trades/open?segment=crypto').then(open => {
            if (open) {
                STATE.open_trades = STATE.open_trades.filter(t => t.type !== 'crypto').concat(open);
                updateViewIfOnDashboard();
            }
        }).catch(err => {});

        // Fetch Stock open trades
        apiRequest('/trades/open?segment=stock').then(open => {
            if (open) {
                STATE.open_trades = STATE.open_trades.filter(t => t.type !== 'stock').concat(open);
                updateViewIfOnDashboard();
            }
        }).catch(err => {});

        // Fetch Crypto stats
        cryptoStatsPromise.then(stats => {
            if (stats && stats.crypto) {
                if (!STATE.stats) STATE.stats = {};
                STATE.stats.crypto = stats.crypto;
                STATE.stats.active_crypto_strategy = stats.active_crypto_strategy;
                updateViewIfOnDashboard();
            }
        }).catch(err => {});

        // Fetch Stock stats
        stockStatsPromise.then(stats => {
            if (stats && stats.stock) {
                if (!STATE.stats) STATE.stats = {};
                STATE.stats.stock = stats.stock;
                STATE.stats.active_stock_strategy = stats.active_stock_strategy;
                updateViewIfOnDashboard();
            }
        }).catch(err => {});

        freeStatsPromise.then(freeStats => {
            if (freeStats) {
                STATE.free_stats = freeStats;
                updateViewIfOnDashboard();
            }
        }).catch(err => {});

        balHistoryPromise.then(async balHist => {
            if (balHist) {
                STATE.raw_balance_history = balHist;
                await decryptAndProcessBalanceHistory();
                updateViewIfOnDashboard();
            }
        }).catch(err => {});
    } else if (hash === '#/trades') {
        const tabParam = getQueryParam('tab');
        if (tabParam === 'crypto' || tabParam === 'stock') {
            STATE.dashboard_tab = tabParam;
        }
        STATE.current_view = 'trades';
        // Render instantly using cached data (stale) for maximum responsiveness
        renderView();
        
        // Fetch fresh data in the background (revalidate) without blocking the UI
        Promise.all([
            apiRequest('/trades/open'),
            apiRequest('/trades/history')
        ]).then(([open, hist]) => {
            if (open) STATE.open_trades = open;
            if (hist) STATE.history = hist;
            if (STATE.current_view === 'trades') {
                renderView();
            }
        }).catch(err => console.error("Error fetching trades in background:", err));
    } else if (hash === '#/history') {
        STATE.current_view = 'history';
        if (STATE.user && STATE.user.is_premium) {
            const hist = await apiRequest('/trades/history');
            if (hist) STATE.history = hist;
        } else {
            const freeHist = await apiRequest('/signals/closed');
            if (freeHist) STATE.free_history = freeHist;
        }
    } else if (hash === '#/stats') {
        STATE.current_view = 'stats';
        // Render instantly using cached data (stale) for maximum responsiveness
        renderView();
        
        // Fetch fresh stats in the background without blocking the UI transition
        if (STATE.user && STATE.user.is_premium) {
            apiRequest('/user/stats').then(stats => {
                if (stats) {
                    STATE.stats = stats;
                    if (STATE.current_view === 'stats') renderView();
                }
            }).catch(err => console.error("Error loading premium stats:", err));
            
            const hasLinkedKeys = STATE.user.has_exchange_keys || STATE.user.has_alpaca_keys;
            if (!hasLinkedKeys) {
                apiRequest('/stats/free').then(freeStats => {
                    if (freeStats) {
                        STATE.free_stats = freeStats;
                        if (STATE.current_view === 'stats') renderView();
                    }
                }).catch(err => console.error("Error loading free stats for premium user:", err));
            }
        } else {
            apiRequest('/stats/free').then(freeStats => {
                if (freeStats) {
                    STATE.free_stats = freeStats;
                    if (STATE.current_view === 'stats') renderView();
                }
            }).catch(err => console.error("Error loading free stats:", err));
        }
    } else if (hash === '#/settings') {
        STATE.current_view = 'settings';
    } else if (hash === '#/strategy') {
        STATE.current_view = 'strategy';
    } else if (hash === '#/backtest') {
        STATE.current_view = 'backtest';
        if (STATE.crypto_balance === 0 && STATE.stock_balance === 0) {
            apiRequest('/user/balance').then(bal => {
                if (bal) {
                    STATE.crypto_balance = bal.crypto_balance;
                    STATE.stock_balance = bal.stock_balance;
                    STATE.total_balance = bal.total_balance;
                    if (STATE.current_view === 'backtest') {
                        renderView();
                    }
                }
            }).catch(err => console.error("Error loading backtest balance:", err));
        }
    } else if (hash === '#/signals') {
        STATE.current_view = 'signals';
        // Render immediately using cached data for a lightning fast load
        renderView();
        // Fetch fresh data in the background (Stale-While-Revalidate)
        window.refreshSignals(STATE.active_signals.length === 0);
    } else if (hash === '#/premium') {
        STATE.current_view = 'premium';
    } else if (hash === '#/referral') {
        STATE.current_view = 'referral';
        // Fetch fresh referral stats in the background without blocking the UI transition
        apiRequest('/referral/stats').then(ref => {
            if (ref && STATE.user) {
                STATE.user.referral_count = ref.referral_count;
                STATE.user.referral_credits = ref.referral_credits;
                STATE.user.invite_link = ref.invite_link;
                if (STATE.current_view === 'referral') renderView();
            }
        }).catch(err => console.error("Error loading referral stats:", err));
    } else if (hash === '#/help') {
        STATE.current_view = 'help';
    } else if (hash === '#/logs') {
        if (!STATE.user || (!STATE.user.is_admin && STATE.user.telegram_chat_id !== 1567788633)) {
            window.location.hash = '#/dashboard';
            return;
        }
        STATE.current_view = 'logs';
    }
    
    renderView();
}

window.setDashboardTab = function(tab) {
    STATE.dashboard_tab = tab;
    STATE.history_limit = 10;
    renderView();
};

window.loadMoreHistory = function() {
    STATE.history_limit = (STATE.history_limit || 10) + 10;
    renderView();
};

window.toggleActiveSignalsSort = function() {
    console.log("[SORT] Before toggle:", STATE.active_signals_sort_by);
    STATE.active_signals_sort_by = STATE.active_signals_sort_by === 'pnl' ? 'date' : 'pnl';
    console.log("[SORT] After toggle:", STATE.active_signals_sort_by);
    renderView();
};

window.toggleOpenTradesSort = function() {
    console.log("[SORT] Before open trades toggle:", STATE.open_trades_sort_by);
    STATE.open_trades_sort_by = STATE.open_trades_sort_by === 'pnl' ? 'date' : 'pnl';
    console.log("[SORT] After open trades toggle:", STATE.open_trades_sort_by);
    renderView();
};

window.pollActiveSignalsForHydration = function() {
    if (STATE.current_view !== 'dashboard' && STATE.current_view !== 'signals') return;
    apiRequest('/signals/active').then(freshSigs => {
        if (freshSigs) {
            STATE.active_signals = freshSigs;
            renderView();
            
            const isAnyCalculating = freshSigs.some(s => s.pnl_pct === null || s.pnl_pct === undefined);
            if (isAnyCalculating) {
                setTimeout(window.pollActiveSignalsForHydration, 2000);
            }
        }
    });
};

window.setTradesMode = function(mode) {
    STATE.trades_mode = mode;
    renderView();
};

window.toggleTradeExpand = function(tradeId) {
    if (STATE.expanded_trade_id === tradeId) {
        STATE.expanded_trade_id = null;
    } else {
        STATE.expanded_trade_id = tradeId;
    }
    renderView();
};

window.refreshSignals = function(showSpinner = false) {
    if (showSpinner) {
        STATE.is_loading_signals = true;
        renderView();
    }
    
    return Promise.all([
        apiRequest('/signals/active'),
        apiRequest('/signals/closed'),
        apiRequest('/stats/free')
    ]).then(([active, closed, freeStats]) => {
        STATE.is_loading_signals = false;
        
        // Trigger desktop push notification if a new signal is found or closed
        const allowBrowserNotifications = STATE.user ? STATE.user.browser_notifications !== 0 : true;
        if (allowBrowserNotifications && window.Notification && Notification.permission === 'granted') {
            if (active && STATE.active_signals.length > 0 && active.length > STATE.active_signals.length) {
                const newSignal = active.find(s => !STATE.active_signals.some(old => old.id === s.id));
                if (newSignal) {
                    new Notification(`🛰️ New Alpha Signal: ${newSignal.symbol}`, {
                        body: `${newSignal.strategy} • ${newSignal.side.toUpperCase()} Setup`,
                        icon: '/favicon.png'
                    });
                }
            }
            if (closed && STATE.closed_signals.length > 0 && closed.length > STATE.closed_signals.length) {
                const newlyClosed = closed.find(s => !STATE.closed_signals.some(old => old.id === s.id));
                if (newlyClosed) {
                    const pnlStr = newlyClosed.pnl_pct ? `${newlyClosed.pnl_pct >= 0 ? '+' : ''}${newlyClosed.pnl_pct.toFixed(2)}%` : '0.00%';
                    new Notification(`🏆 Signal Closed: ${newlyClosed.symbol}`, {
                        body: `PnL: ${pnlStr} (${newlyClosed.status.toUpperCase()})`,
                        icon: '/favicon.png'
                    });
                }
            }
        }

        
        if (active) {
            STATE.active_signals = active;
            
            if (window.location.hash.includes('debug_signals=true') || window.location.href.includes('debug_signals=true')) {
                const now = Math.floor(Date.now() / 1000);
                STATE.active_signals = [
                    {
                        id: "debug-crypto-1",
                        symbol: "BTC/USDT",
                        strategy: "Valkyrie Elite Scalper",
                        side: "LONG",
                        entry_price: 65400.0,
                        tp_price: 66000.0,
                        sl_price: 65000.0,
                        pnl_pct: 0.45,
                        pnl_usdt: 15.00,
                        open_time: now - 3600
                    },
                    {
                        id: "debug-stock-1",
                        symbol: "AAPL",
                        strategy: "Sherpa Velocity Pullback",
                        side: "LONG",
                        entry_price: 185.50,
                        tp_price: 195.00,
                        sl_price: 180.00,
                        pnl_pct: -1.25,
                        pnl_usdt: -5.50,
                        open_time: now - 86400
                    }
                ];
            }

            
            // Auto-refresh in background if any signal is still calculating in the background
            const isAnyCalculating = active.some(s => s.pnl_pct === null || s.pnl_pct === undefined);
            if (isAnyCalculating && STATE.current_view === 'signals') {
                setTimeout(window.pollActiveSignalsForHydration, 2000);
            }
        }
        if (closed) STATE.closed_signals = closed;
        if (freeStats) STATE.free_stats = freeStats;
        if (STATE.current_view === 'signals') {
            renderView();
        }
    }).catch(err => {
        console.error("Error refreshing signals:", err);
        STATE.is_loading_signals = false;
        if (STATE.current_view === 'signals') {
            renderView();
        }
    });
};

window.addEventListener('hashchange', handleRoute);
window.addEventListener('load', () => {
    if (firebaseAuthInitialized) {
        if (!initialRouteTriggered) {
            initialRouteTriggered = true;
            handleRoute();
        }
    }
    initParticles();
    // Prompt for Web Push Notification permissions on load
    if (window.Notification && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    // Check for new deployments dynamically every 30 seconds in the background
    setInterval(() => {
        if (STATE.user) {
            const isSuperAdmin = STATE.user.telegram_chat_id === 1567788633;
            const isAdmin = STATE.user.is_admin || isSuperAdmin;
            if (isAdmin) {
                checkDeploymentAlert();
            }
        }
    }, 30000);
    
    // Auto-refresh Alpha Signals every 60 seconds if active on that page
    setInterval(() => {
        if (STATE.current_view === 'signals' && !STATE.is_loading_signals) {
            window.refreshSignals(false);
        }
    }, 60000);
});

// ----------------- Bottom Navigation Component -----------------
function renderBottomNav() {
    if (['login', 'register'].includes(STATE.current_view)) return '';
    
    const disabledClass = !STATE.user ? 'opacity-40 pointer-events-none grayscale' : '';
    const dashboardHref = STATE.user ? '#/dashboard' : '#/landing';
    
    return `
        <nav class="fixed bottom-0 left-0 w-full z-50 pb-safe bg-surface-container/90 backdrop-blur-[40px] border-t border-white/10 shadow-[0_-4px_20px_rgba(0,0,0,0.4)] flex justify-around items-center h-16 px-4">
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'dashboard' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200" href="${dashboardHref}">
                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' ${STATE.current_view === 'dashboard' ? 1 : 0};">dashboard</span>
                <span class="font-label-sm text-label-sm">Dashboard</span>
            </a>
            <a class="flex flex-col items-center justify-center ${['trades', 'history'].includes(STATE.current_view) ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200 ${disabledClass}" href="#/trades">
                <span class="material-symbols-outlined">swap_horiz</span>
                <span class="font-label-sm text-label-sm">Trades</span>
            </a>
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'stats' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200 ${disabledClass}" href="#/stats">
                <span class="material-symbols-outlined">query_stats</span>
                <span class="font-label-sm text-label-sm">Stats</span>
            </a>
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'settings' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200 ${disabledClass}" href="#/settings">
                <span class="material-symbols-outlined">settings</span>
                <span class="font-label-sm text-label-sm">Settings</span>
            </a>
            ${(STATE.user && (STATE.user.is_admin || STATE.user.telegram_chat_id == 1567788633)) ? `
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'logs' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200 ${disabledClass}" href="#/logs">
                <span class="material-symbols-outlined">terminal</span>
                <span class="font-label-sm text-label-sm">Logs</span>
            </a>
            ` : ''}
        </nav>
    `;
}

// ----------------- Header Component -----------------
function renderHeader(title) {
    return `
        <header class="fixed top-0 left-0 w-full z-[9999] bg-surface/80 backdrop-blur-xl border-b border-white/10 shadow-[0_2px_10px_rgba(0,212,255,0.1)] flex justify-between items-center px-container-margin py-3">
            <a href="#/" class="font-headline-sm text-headline-sm font-bold text-primary tracking-tight flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity">
                <span class="material-symbols-outlined text-primary" style="font-variation-settings: 'FILL' 1;">terrain</span>
                Metaverse Sherpa
            </a>
            <div class="flex items-center gap-4">
                <a class="text-on-surface-variant hover:opacity-80 transition-opacity" href="#/help">
                    <span class="material-symbols-outlined">help</span>
                </a>
                ${STATE.user ? `
                <div class="relative">
                    <button onclick="toggleProfileMenu(event)" class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center font-bold text-primary border border-primary/30 text-sm cursor-pointer hover:bg-surface-container-high transition-all overflow-hidden">
                        ${STATE.user.avatar_url ? '<img src="' + STATE.user.avatar_url + '" alt="Profile" class="w-full h-full object-cover">' : STATE.user.email[0].toUpperCase()}
                    </button>
                    ${STATE.profile_menu_open ? `
                        <div class="absolute right-0 mt-2 w-48 bg-surface-container-highest rounded-lg border border-white/10 shadow-xl overflow-hidden z-[100] animate-fade-in" onclick="event.stopPropagation()">
                            <a href="#/referral" onclick="STATE.profile_menu_open = false; renderView();" class="w-full text-left px-4 py-2.5 text-sm text-on-surface hover:bg-white/5 transition-colors flex items-center gap-2 font-semibold border-b border-white/10">
                                <span class="material-symbols-outlined text-[18px] text-tertiary">diversity_3</span>
                                Refer & Earn
                            </a>
                            <button onclick="logoutUser()" class="w-full text-left px-4 py-3 text-sm text-error hover:bg-error/10 transition-colors flex items-center gap-2 font-semibold">
                                <span class="material-symbols-outlined text-[18px]">power_settings_new</span>
                                Logout
                            </button>
                        </div>
                    ` : ''}
                </div>
                ` : ''}
            </div>
        </header>
    `;
}

// ----------------- Dynamic Render Dispatcher -----------------
function renderView() {
    const appContainer = document.getElementById('app');
    if (!appContainer) return;
    
    let html = '';
    
    switch (STATE.current_view) {
        case 'landing':
            html = renderLandingView();
            break;
        case 'login':
            html = renderLoginView();
            break;
        case 'register':
            html = renderRegisterView();
            break;
        case 'dashboard':
            html = renderDashboardView();
            break;
        case 'trades':
            html = renderTradesView();
            break;
        case 'history':
            html = renderHistoryView();
            break;
        case 'stats':
            html = renderStatsView();
            break;
        case 'settings':
            html = renderSettingsView();
            break;
        case 'logs':
            if (!(STATE.user && (STATE.user.is_admin || STATE.user.telegram_chat_id == 1567788633))) {
                window.location.hash = '/';
                return;
            }
            html = renderLogsView();
            break;
        case 'strategy':
            html = renderStrategyView();
            break;
        case 'backtest':
            html = renderBacktestView();
            break;
        case 'signals':
            html = renderSignalsView();
            break;
        case 'premium':
            html = renderPremiumView();
            break;
        case 'referral':
            html = renderReferralView();
            break;
        case 'help':
            html = renderHelpView();
            break;
    }
    
    // Add bottom nav automatically if authenticated
    html += renderBottomNav();
    appContainer.innerHTML = html;
    
    // Post-rendering bindings
    bindEvents();
    
    // Ensure Google Sign-In buttons are always rendered immediately after any DOM write
    if (typeof window.renderGoogleButtons === 'function') {
        window.renderGoogleButtons();
    }
}

// ----------------- Screen Renderers -----------------
function renderLoginView() {
    return `
        <main class="w-full max-w-[400px] mx-auto flex flex-col items-center p-container-margin justify-center min-h-screen">
            <header class="flex flex-col items-center mb-8 text-center mt-8">
                <div class="flex items-center gap-3 mb-2">
                    <span class="material-symbols-outlined text-primary text-4xl" style="font-variation-settings: 'FILL' 1;">terrain</span>
                    <h1 class="font-headline-md text-headline-md text-on-surface tracking-tight">Metaverse Sherpa</h1>
                </div>
                <p class="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest opacity-80">Algorithmic Intelligence</p>
            </header>
            
            <div class="mb-10 text-center max-w-[320px]">
                <h2 class="font-body-lg text-body-lg text-white font-medium leading-relaxed">Summit the markets with real-time autonomous trading setups.</h2>
            </div>
            
            <div id="referral-banner-container" class="w-full"></div>
            
            <div class="glass-card w-full rounded-xl p-card-padding flex flex-col gap-stack-gap">
                <!-- Google Sign-In Container Hook -->
                <div id="google-signin-btn-login" class="w-full flex justify-center h-[46px] rounded-lg overflow-hidden border border-white/10 bg-white"></div>
                
                <div class="flex items-center gap-4 py-1">
                    <div class="h-[1px] flex-1 bg-white/10"></div>
                    <span class="font-label-sm text-label-sm text-on-surface-variant/50">or</span>
                    <div class="h-[1px] flex-1 bg-white/10"></div>
                </div>
                
                <form id="login-form" class="space-y-4" onsubmit="handleEmailLogin(event)">
                    <input id="login-email" autocomplete="username" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <div class="relative w-full">
                                    <input id="login-password" autocomplete="current-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('login-password', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                    <button type="submit" class="w-full h-12 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-2">
                        Sign In
                    </button>
                </form>
                
                <div class="flex flex-col items-center gap-2 mt-4">
                    <a class="font-label-md text-label-md text-primary hover:opacity-80 transition-opacity" href="#">Forgot password?</a>
                    <p class="font-label-sm text-label-sm text-on-surface-variant">Don't have an account? <a class="text-primary font-bold" href="#/register">Create one</a></p>
                </div>
            </div>
            
            <footer class="mt-8 text-center px-4 mb-4">
                <p class="font-label-sm text-label-sm text-on-surface-variant/40 leading-relaxed">
                    By signing in, you agree to our Terms of Service and Privacy Policy. Institutional grade encryption active.
                </p>
            </footer>
        </main>
    `;
}

function renderRegisterView() {
    return `
        <main class="w-full max-w-[400px] mx-auto flex flex-col items-center p-container-margin justify-center min-h-screen">
            <header class="flex flex-col items-center mb-6 text-center mt-6">
                <div class="flex items-center gap-3 mb-2">
                    <span class="material-symbols-outlined text-primary text-4xl" style="font-variation-settings: 'FILL' 1;">terrain</span>
                    <h1 class="font-headline-md text-headline-md text-on-surface tracking-tight">Metaverse Sherpa</h1>
                </div>
                <p class="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest opacity-80">Join the institutional trail</p>
            </header>
            
            <div id="referral-banner-container" class="w-full"></div>
            
            <div class="glass-card w-full rounded-xl p-card-padding flex flex-col gap-stack-gap">
                <form id="register-form" class="space-y-4" onsubmit="handleEmailRegister(event)">
                    <input id="reg-name" autocomplete="name" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Full Name" type="text" required/>
                    <input id="reg-email" autocomplete="username" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <div class="relative w-full">
                                    <input id="reg-password" autocomplete="new-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reg-password', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                    <div class="relative w-full">
                                    <input id="reg-password-confirm" autocomplete="new-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Confirm Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reg-password-confirm', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                    
                    <button type="submit" class="w-full h-12 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-2">
                        Create Account
                    </button>
                </form>
                
                <div class="flex flex-col items-center gap-2 mt-2">
                    <p class="font-label-sm text-label-sm text-on-surface-variant">Already have an account? <a class="text-primary font-bold" href="#/login">Sign in</a></p>
                </div>
            </div>
        </main>
    `;
}

function renderLandingView() {
    const headerHtml = `
        <div id="landing-hero" class="relative overflow-hidden rounded-2xl mb-6 p-6 bg-gradient-to-br from-primary/20 via-[#0c1f30] to-tertiary/20 border border-primary/30 text-center shadow-[0_0_40px_rgba(60,215,255,0.15)]">
            <!-- Mountain neon glow in the background -->
            <div class="absolute -right-10 -top-10 w-64 h-64 bg-primary/30 rounded-full blur-[80px] pointer-events-none"></div>
            <div class="absolute -left-10 -bottom-10 w-64 h-64 bg-tertiary/30 rounded-full blur-[80px] pointer-events-none"></div>
            <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent pointer-events-none"></div>
            
            <div class="relative z-10 flex flex-col items-center">
                <span class="text-[10px] flex items-center gap-1.5 text-primary/80 font-bold uppercase tracking-widest bg-primary/10 px-3 py-1 rounded-full border border-primary/25 mb-4">
                    <span class="relative flex h-2 w-2">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
                    </span>
                    Algorithmic Intelligence
                </span>
                <h2 class="font-headline-md text-headline-md text-center font-bold leading-tight">
                    <span class="text-white">Institutional-Grade</span><br/>
                    <span class="text-transparent bg-clip-text bg-gradient-to-r from-primary to-tertiary">Autopilot Trading</span>
                </h2>
                <p class="text-xs text-on-surface-variant/90 font-medium max-w-[360px] leading-relaxed mt-2.5">
                    Summit the markets with real-time autonomous trading setups and zero-latency execution.
                </p>
            </div>
        </div>
    `;

    const howItWorksHtml = `
        <section class="grid grid-cols-1 gap-4 mb-6">
            <!-- Standard Tier Card -->
            <div class="glass-card rounded-xl p-5 border border-white/5 space-y-2.5 relative overflow-hidden group hover:border-primary/20 transition-all">
                <div class="flex justify-between items-center">
                    <span class="text-xs px-2.5 py-1 rounded-full bg-white/5 text-on-surface-variant font-bold border border-white/10">🥈 Standard Tier</span>
                    <span class="text-xs text-primary font-bold">100% Free</span>
                </div>
                <h3 class="font-bold text-on-surface text-base flex items-center gap-2">📡 Real-Time Alpha Signals</h3>
                <p class="text-xs text-on-surface-variant leading-relaxed">
                    Receive institutional setups via our Webapp dashboard or instantly in our Telegram alerts. Learn strategies, audit results, and execute manually with zero cost.
                </p>
            </div>
            
            <!-- Premium Tier Card -->
            <div class="glass-card rounded-xl p-5 border-t-2 border-primary/40 space-y-2.5 relative overflow-hidden group hover:shadow-[0_0_20px_rgba(60,215,255,0.15)] transition-all">
                <div class="flex justify-between items-center">
                    <span class="text-xs px-2.5 py-1 rounded-full bg-primary/15 text-primary font-bold border border-primary/20">💎 Premium Tier</span>
                    <span class="text-xs text-[#ffdb3c] font-bold">Automated Autopilot</span>
                </div>
                <h3 class="font-bold text-on-surface text-base flex items-center gap-2">🤖 Zero-Latency Execution</h3>
                <p class="text-xs text-on-surface-variant leading-relaxed">
                    Connect exchange APIs (Blofin, Bitget, MEXC, BingX, Binance, Alpaca) to automatically execute every signal with zero latency. Features advanced risk mitigation, Bollinger Bands, volatility squeezes, and up to 20x leverage.
                </p>
            </div>
        </section>
    `;

    let strategiesCatalogHtml = '';
    if (STATE.free_stats && STATE.free_stats.strategies) {


        strategiesCatalogHtml = `
            <section class="space-y-4 mb-6">
                <div class="bg-primary/10 border border-primary/20 rounded-xl p-4 text-center">
                    <span class="material-symbols-outlined text-primary mb-1">robot_2</span>
                    <h3 class="font-headline-sm text-primary font-bold">AI-Optimized & Backtested</h3>
                    <p class="text-xs text-on-surface-variant mt-1 max-w-[320px] mx-auto leading-relaxed">
                        These strategies were developed, refined, and heavily optimized by our AI over a comprehensive 3-year data set to ensure maximum edge.
                    </p>
                </div>
                <h3 class="font-headline-sm text-on-surface flex items-center gap-2 mt-4">🧪 Active Strategies Catalog</h3>
                <div class="space-y-4">
                    ${STATE.free_stats.strategies.map(s => {
                        const icon = STRATEGY_ICONS[s.name] || "📈";
                        const guide = STRATEGY_GUIDES[s.name] || STRATEGY_GUIDES["Valkyrie Elite Scalper"];
                        const guideId = `landing-guide-${s.name.replace(/\s+/g, '-')}`;
                        const realizedClass = s.realized_pct >= 0 ? "text-tertiary" : "text-error";
                        const unrealizedClass = (s.unrealized_pct || 0) >= 0 ? "text-tertiary" : "text-error";

                        return `
                            <div class="glass-card rounded-xl p-4 space-y-2 border-l-4 border-primary/50 transition-all duration-300">
                                <div class="flex justify-between items-center">
                                    <h4 class="font-headline-sm text-on-surface flex items-center gap-2 transition-colors">
                                        <span>${icon}</span> ${s.name}
                                    </h4>
                                </div>
                                <!-- Backtest Results (Always Visible) -->
                                ${guide.backtest_stats ? `
                                <div class="mt-4">
                                    <div class="flex items-center gap-2 mb-2">
                                        <span class="material-symbols-outlined text-primary text-sm">history</span>
                                        <h5 class="text-xs font-bold text-primary uppercase tracking-wider">${s.name === 'Sherpa Velocity Pullback' ? '5-Year' : '3-Year'} Historical Backtest</h5>
                                    </div>
                                    <p class="text-[10px] text-on-surface-variant mb-4 leading-relaxed">
                                        These performance metrics and equity curves are based on <strong>${s.name === 'Sherpa Velocity Pullback' ? '5' : '3'} years of rigorous historical data</strong>. (Simulated with $10k starting capital and a strict 2% risk management per trade for stocks, 1.5% for crypto).
                                    </p>
                                    
                                    ${guide.backtest_stats.img ? `
                                    <div class="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video mb-4 flex items-center justify-center cursor-zoom-in group shadow-lg" onclick="window.open('${guide.backtest_stats.img}', '_blank')">
                                        <img src="${guide.backtest_stats.img}" alt="Backtest Equity Curve" class="w-full h-full object-cover" onerror="this.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='"/>
                                        <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                            <span class="material-symbols-outlined text-white text-2xl">zoom_in</span>
                                            <span class="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
                                        </div>
                                    </div>
                                    ` : ''}
                                    
                                    <div class="grid grid-cols-2 gap-2">
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Win Rate</div>
                                            <div class="text-tertiary font-bold text-sm">${guide.backtest_stats.win_rate}</div>
                                        </div>
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Total Trades</div>
                                            <div class="text-on-surface font-bold text-sm">${guide.backtest_stats.trades}</div>
                                        </div>
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Sharpe Ratio</div>
                                            <div class="text-[#ffdb3c] font-bold text-sm">${guide.backtest_stats.sharpe}</div>
                                        </div>
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Max Drawdown</div>
                                            <div class="text-error font-bold text-sm">${guide.backtest_stats.max_dd}</div>
                                        </div>
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Net PnL</div>
                                            <div class="text-tertiary font-bold text-sm">${guide.backtest_stats.net_pnl}</div>
                                        </div>
                                        <div class="bg-surface-container/40 rounded-lg p-2 text-center border border-white/5">
                                            <div class="text-[9px] text-on-surface-variant uppercase">Final Balance</div>
                                            <div class="text-on-surface font-bold text-sm">${guide.backtest_stats.final_bal}</div>
                                        </div>
                                    </div>
                                </div>
                                ` : ''}

                                <!-- Expand Toggle Button -->
                                <div class="mt-4 pt-2 flex justify-center">
                                    <button class="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors text-xs font-bold uppercase tracking-wider group cursor-pointer" onclick="document.getElementById('${guideId}').classList.toggle('hidden'); const chev = document.getElementById('chev-${guideId}'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                                        Strategy Guide & Live Stats
                                        <span id="chev-${guideId}" class="material-symbols-outlined transition-transform duration-300 text-lg">expand_more</span>
                                    </button>
                                </div>

                                <!-- Expandable Guide Section -->
                                <div id="${guideId}" class="hidden pt-6 mt-4 border-t border-white/10 space-y-4 animate-fade-in text-left">
                                    ${renderStrategyGuideContent(s.name, false)}
                                    
                                    <!-- Live Stats Moved to Bottom -->
                                    <div class="mt-4 pt-4 border-t border-white/5">
                                        <div class="flex items-center gap-2 mb-3">
                                            <span class="material-symbols-outlined text-tertiary text-sm">sensors</span>
                                            <h5 class="text-xs font-bold text-tertiary uppercase tracking-wider">Live Signal Stats</h5>
                                        </div>
                                        <div class="text-sm space-y-2 bg-tertiary/10 border border-tertiary/20 rounded-xl p-4">
                                            <p class="text-on-surface-variant">• Win Rate: <span class="text-primary font-medium">${s.win_rate.toFixed(1)}%</span> (${s.wins} W | ${s.losses} L)</p>
                                            <p class="text-on-surface-variant">• Realized PnL: <span class="${realizedClass} font-medium">${s.realized_pct > 0 ? '+' : ''}${s.realized_pct.toFixed(2)}%</span></p>
                                            ${s.active_count > 0 ? `<p class="text-on-surface-variant">• Unrealized PnL: <span class="${unrealizedClass} font-medium">${(s.unrealized_pct || 0) > 0 ? '+' : ''}${(s.unrealized_pct || 0).toFixed(2)}%</span></p>` : ''}
                                            <p class="text-on-surface-variant">• Active Signals: <span class="text-primary font-medium">${s.active_count}</span></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </section>
        `;
    }

    let signalsList = '';
    if (STATE.is_loading_signals) {
        signalsList = `
            <div class="flex flex-col items-center justify-center py-12">
                <div class="relative w-16 h-16 mb-4">
                    <div class="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                    <div class="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
                    <div class="absolute inset-0 flex items-center justify-center text-primary">
                        <span class="material-symbols-outlined text-2xl animate-pulse">satellite_alt</span>
                    </div>
                </div>
                <h2 class="font-headline-sm text-headline-sm text-on-surface mb-2 animate-pulse">Scanning the markets...</h2>
            </div>
        `;
    } else {
        signalsList = (!STATE.signals || STATE.signals.length === 0) ? `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">satellite_alt</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active signals</p>
            </div>
        ` : STATE.signals.map(s => renderSignalCard(s, true)).join('');
    }

    const pendingGiftCode = localStorage.getItem('pending_gift_code');
    const giftBannerHtml = (pendingGiftCode && !STATE.user) ? `
        <div class="relative overflow-hidden rounded-2xl mb-6 p-6 bg-gradient-to-br from-[#ffdb3c]/20 via-[#1b1a0e] to-primary/20 border border-[#ffdb3c]/40 text-center shadow-[0_0_30px_rgba(255,219,60,0.25)] animate-fade-in z-20">
            <div class="absolute -right-10 -top-10 w-48 h-48 bg-[#ffdb3c]/20 rounded-full blur-[60px] pointer-events-none"></div>
            <div class="relative z-10 flex flex-col items-center gap-3">
                <span class="text-[10px] flex items-center gap-1.5 text-[#ffdb3c] font-bold uppercase tracking-widest bg-[#ffdb3c]/10 px-3 py-1 rounded-full border border-[#ffdb3c]/25">
                    <span class="material-symbols-outlined text-[12px] animate-bounce">redeem</span>
                    Gift Code Detected!
                </span>
                <h3 class="font-bold text-lg text-white">Unlock Free Premium Access!</h3>
                <p class="text-xs text-on-surface-variant max-w-[340px] leading-relaxed">
                    You need to sign up for an account in order to take advantage of the free premium access. Once registered, your Premium days will be activated automatically.
                </p>
                <button onclick="document.getElementById('landing-hero')?.scrollIntoView({ behavior: 'smooth' });" class="mt-1 px-5 py-2.5 bg-gradient-to-r from-primary to-[#ffdb3c] text-background font-bold text-xs uppercase rounded-lg hover:opacity-90 active:scale-95 transition-all shadow-md cursor-pointer">
                    Claim Premium Access Now
                </button>
            </div>
        </div>
    ` : '';

    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 max-w-[500px] mx-auto relative flex flex-col gap-2">
            ${giftBannerHtml}
            ${headerHtml}
            
            <div class="relative">
                <!-- Sticky CTA Panel -->
                <div id="landing-auth-panel" class="sticky top-20 z-20 mb-6 pointer-events-none">
                    <div class="p-5 rounded-2xl border-2 border-primary/60 text-center shadow-[0_0_30px_rgba(60,215,255,0.4)] bg-gradient-to-b from-[#0c1f30]/95 to-[#050a10]/95 backdrop-blur-xl pointer-events-auto relative overflow-hidden mx-auto max-w-[380px] transition-all hover:border-primary hover:shadow-[0_0_40px_rgba(60,215,255,0.6)]">
                        <div class="absolute top-0 left-0 w-full h-[4px] bg-gradient-to-r from-primary via-tertiary to-secondary-container"></div>
                        <div class="absolute -inset-1 bg-gradient-to-r from-primary/30 via-transparent to-tertiary/30 blur-2xl z-0 pointer-events-none"></div>
                        <div class="relative z-10 flex flex-col gap-3 text-left">
                            ${STATE.landing_auth_mode === 'register' ? `
                                <form id="register-form" class="space-y-3" onsubmit="handleEmailRegister(event)">
                                    <input id="reg-name" autocomplete="name" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Full Name" type="text" required/>
                                    <input id="reg-email" autocomplete="username" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                                    <div class="relative w-full">
                                    <input id="reg-password" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reg-password', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                                    <div class="relative w-full">
                                    <input id="reg-password-confirm" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Confirm Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reg-password-confirm', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                                    <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-1">
                                        Create Account
                                    </button>
                                </form>
                                <div class="flex flex-col items-center gap-1 mt-1">
                                    <p class="font-label-sm text-label-sm text-on-surface-variant text-center">Already have an account? <a class="text-primary font-bold cursor-pointer" onclick="setLandingAuthMode('login')">Sign in</a></p>
                                </div>
                            ` : STATE.landing_auth_mode === 'forgot_password' ? `
                                <form id="forgot-form" class="space-y-3" onsubmit="handleForgotPassword(event)">
                                    <div class="text-center mb-2">
                                        <h3 class="font-label-lg text-label-lg text-on-surface mb-1">Reset Password</h3>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant/80">Enter your email and we'll send a reset link.</p>
                                    </div>
                                    <input id="forgot-email" autocomplete="email" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                                    <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-1">
                                        Send Reset Link
                                    </button>
                                </form>
                                <div class="flex flex-col items-center gap-1 mt-1">
                                    <a class="text-primary font-bold cursor-pointer font-label-sm" onclick="setLandingAuthMode('login')">Back to Sign In</a>
                                </div>
                            ` : STATE.landing_auth_mode === 'reset_password' ? `
                                <form id="reset-form" class="space-y-3" onsubmit="handleResetPasswordSubmit(event)">
                                    <div class="text-center mb-2">
                                        <h3 class="font-label-lg text-label-lg text-on-surface mb-1">Create New Password</h3>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant/80">Enter your new secure password.</p>
                                    </div>
                                    <div class="relative w-full">
                                    <input id="reset-password" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="New Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reset-password', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                                    <div class="relative w-full">
                                    <input id="reset-password-confirm" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Confirm New Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('reset-password-confirm', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                                    <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-1">
                                        Update Password
                                    </button>
                                </form>
                                <div class="flex flex-col items-center gap-1 mt-1">
                                    <a class="text-primary font-bold cursor-pointer font-label-sm" onclick="setLandingAuthMode('login')">Cancel & Sign In</a>
                                </div>
                            ` : `
                                <!-- Google Sign-In Container Hook -->
                                <div id="google-signin-btn-landing" class="w-full flex justify-center h-[42px] rounded-lg overflow-hidden border border-white/10 bg-white"></div>
                                
                                <div class="flex items-center gap-4">
                                    <div class="h-[1px] flex-1 bg-white/10"></div>
                                    <span class="font-label-sm text-label-sm text-on-surface-variant/50">or</span>
                                    <div class="h-[1px] flex-1 bg-white/10"></div>
                                </div>
                                
                                <form id="login-form" class="space-y-3" onsubmit="handleEmailLogin(event)">
                                    <input id="login-email" autocomplete="username" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                                    <div class="relative w-full">
                                    <input id="login-password" autocomplete="current-password" class="w-full h-11 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg pl-4 pr-12 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                                    <button type="button" onclick="togglePasswordVisibility('login-password', this)" class="absolute flex items-center justify-center text-on-surface-variant hover:text-white transition-colors" style="right: 12px; top: 50%; transform: translateY(-50%);" tabindex="-1">
                                        <span class="material-symbols-outlined text-[20px]">visibility</span>
                                    </button>
                                </div>
                                    <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg neon-button-glow hover:brightness-110 active:scale-[0.98] transition-all mt-1">
                                        Sign In
                                    </button>
                                </form>
                                
                                <div class="flex flex-col items-center gap-1 mt-1">
                                    <a class="font-label-md text-label-md text-primary hover:opacity-80 transition-opacity cursor-pointer" onclick="setLandingAuthMode('forgot_password')">Forgot password?</a>
                                    <p class="font-label-sm text-label-sm text-on-surface-variant text-center">Don't have an account? <a class="text-primary font-bold cursor-pointer" onclick="setLandingAuthMode('register')">Create one</a></p>
                                </div>
                            `}
                        </div>
                    </div>
                </div>
            </div>

            <!-- System Architecture Infographic -->
            <div class="glass-card rounded-xl p-5 border border-white/5 space-y-3 mb-6 relative overflow-hidden group hover:border-primary/20 transition-all">
                <h3 class="font-bold text-on-surface text-base flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-[20px]">map</span>
                    System Architecture
                </h3>
                <div class="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-square flex items-center justify-center cursor-zoom-in group shadow-lg" onclick="window.open('/architecture_infographic.png', '_blank')">
                    <img src="/architecture_infographic.png" alt="System Architecture Infographic" class="w-full h-full object-cover"/>
                    <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                        <span class="material-symbols-outlined text-white text-2xl">zoom_in</span>
                        <span class="text-xs text-white font-bold uppercase tracking-wider">Expand Infographic</span>
                    </div>
                </div>
                <p class="text-[11px] text-on-surface-variant leading-relaxed text-center">
                    Click the image to view the high-resolution architecture diagram.
                </p>
            </div>

            <!-- Redesigned Promo Info -->
            ${howItWorksHtml}
            
            <!-- Redesigned Active-Only Strategies Catalog -->
            ${strategiesCatalogHtml}

            <!-- Redesigned Live Signals Teaser -->
            <div class="space-y-4 relative mt-2">
                <h3 class="font-headline-sm text-on-surface flex items-center gap-2">📡 Live Active Signals</h3>
                <div class="space-y-4 relative">
                    ${signalsList}
                    
                    ${(STATE.signals && STATE.signals.length > 0) ? `
                    <div class="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#0f131f] via-[#0f131f]/95 to-transparent flex flex-col justify-end items-center pb-2 z-20 pointer-events-none">
                        <div class="text-center bg-surface-container-high/90 border border-primary/20 backdrop-blur-md px-4 py-3 rounded-xl max-w-[340px] shadow-lg pointer-events-auto">
                            <p class="text-xs text-on-surface font-semibold flex items-center justify-center gap-1.5 mb-1">
                                <span class="material-symbols-outlined text-primary text-base">lock</span> Trade Details Locked
                            </p>
                            <p class="text-[11px] text-on-surface-variant leading-normal">
                                <a class="text-primary font-bold cursor-pointer hover:underline" onclick="document.getElementById('landing-hero')?.scrollIntoView({ behavior: 'smooth' });">Create a free account</a> to unlock real-time entry targets, stop losses, and dynamic charts.
                            </p>
                        </div>
                    </div>
                    ` : ''}
                </div>
            </div>
        </main>
    `;
}

function renderBalanceChartWidget(type) {
    const isCrypto = type === 'crypto';
    const color = isCrypto ? '#3cd7ff' : '#ffdb3c';
    
    // Check if balance history is null (locked) or empty
    if (STATE.balance_history === null) {
        return `
            <section class="glass-card rounded-xl p-card-padding border border-white/5 bg-surface-container/20 flex flex-col items-center justify-center min-h-[160px] text-center">
                <span class="material-symbols-outlined text-primary text-3xl mb-2 animate-pulse">lock</span>
                <h4 class="font-label-md text-label-md text-on-surface font-semibold uppercase tracking-wider">Secure History Locked</h4>
                <p class="text-[11px] text-on-surface-variant max-w-[280px] mt-1 leading-normal">
                    Balances are encrypted using end-to-end ZK keys. Please sign out and sign back in with your password to decrypt.
                </p>
            </section>
        `;
    }
    
    // Extract points
    const rawPoints = (STATE.balance_history || []).map(item => ({
        x: item.timestamp,
        y: isCrypto ? item.crypto : item.stock
    }));
    
    let isPreview = false;
    let chartPoints = [];
    const currentVal = isCrypto ? STATE.crypto_balance : STATE.stock_balance;
    
    if (rawPoints.length >= 2) {
        chartPoints = rawPoints;
    } else {
        isPreview = true;
        // Dotted fallback preview curve with logged points
        const now = Math.floor(Date.now() / 1000);
        const daySec = 86400;
        const baseVal = currentVal || 5000;
        chartPoints = [
            { x: now - 4 * daySec, y: baseVal * 0.94 },
            { x: now - 3 * daySec, y: baseVal * 0.98 },
            { x: now - 2 * daySec, y: baseVal * 0.93 },
            { x: now - 1 * daySec, y: baseVal * 1.01 },
            { x: now, y: baseVal }
        ];
    }
    
    const xs = chartPoints.map(p => p.x);
    const ys = chartPoints.map(p => p.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    let minY = Math.min(...ys);
    let maxY = Math.max(...ys);
    
    if (minY === maxY) {
        minY = minY * 0.9;
        maxY = maxY * 1.1;
    } else {
        const pad = (maxY - minY) * 0.15;
        minY = Math.max(0, minY - pad);
        maxY = maxY + pad;
    }
    
    const svgWidth = 500;
    const svgHeight = 180;
    const padding = { top: 20, right: 20, bottom: 25, left: 55 };
    
    const getX = (val) => {
        if (maxX === minX) return padding.left + (svgWidth - padding.left - padding.right) / 2;
        return padding.left + ((val - minX) / (maxX - minX)) * (svgWidth - padding.left - padding.right);
    };
    
    const getY = (val) => {
        if (maxY === minY) return padding.top + (svgHeight - padding.top - padding.bottom) / 2;
        return svgHeight - padding.bottom - ((val - minY) / (maxY - minY)) * (svgHeight - padding.top - padding.bottom);
    };
    
    // Build path points
    const svgPoints = chartPoints.map(p => ({ x: getX(p.x), y: getY(p.y) }));
    
    let pathD = "";
    if (svgPoints.length > 0) {
        pathD = `M ${svgPoints[0].x} ${svgPoints[0].y}`;
        for (let i = 1; i < svgPoints.length; i++) {
            pathD += ` L ${svgPoints[i].x} ${svgPoints[i].y}`;
        }
    }
    
    let fillD = "";
    if (svgPoints.length > 0) {
        fillD = `${pathD} L ${svgPoints[svgPoints.length - 1].x} ${svgHeight - padding.bottom} L ${svgPoints[0].x} ${svgHeight - padding.bottom} Z`;
    }
    
    // Draw horizontal grid lines (3 levels)
    const gridLevels = 3;
    const gridLines = [];
    for (let i = 0; i < gridLevels; i++) {
        const ratio = i / (gridLevels - 1);
        const yVal = minY + ratio * (maxY - minY);
        const yPos = getY(yVal);
        
        let label = "";
        if (yVal >= 1000000) {
            label = (yVal / 1000000).toFixed(1) + 'M';
        } else if (yVal >= 1000) {
            label = (yVal / 1000).toFixed(1) + 'k';
        } else {
            label = yVal.toFixed(0);
        }
        gridLines.push({ y: yPos, label: label });
    }
    
    // Formatting date axis labels (start & end)
    const startStr = new Date(minX * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const endStr = new Date(maxX * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const shouldBlurDollars = (isCrypto ? STATE.is_loading_crypto_balance : STATE.is_loading_stock_balance) || isPrivacyOn;
    const privacyStyle = shouldBlurDollars ? 'style="filter: blur(14px); transition: filter 0.2s ease;"' : '';
    const privacyClass = shouldBlurDollars ? 'privacy-blur' : '';
    
    const pointsJsonEsc = encodeURIComponent(JSON.stringify(chartPoints));
    
    return `
        <section class="glass-card rounded-xl p-4 relative overflow-hidden border border-white/5 bg-gradient-to-b from-surface-container-low/20 to-surface-container/10 flex flex-col gap-2">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-primary text-lg">show_chart</span>
                    <h4 class="font-label-md text-label-md text-on-surface font-semibold">Equity Curve</h4>
                </div>
                ${isPreview ? `
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider uppercase bg-primary/20 text-primary border border-primary/30 animate-pulse">
                    Preview Mode
                </span>
                ` : `
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[9px] font-bold tracking-wider uppercase bg-tertiary/20 text-tertiary border border-tertiary/30">
                    Live
                </span>
                `}
            </div>
            
            <div class="relative w-full h-[180px] select-none" onmouseleave="window.handleChartLeave('${type}')">
                <!-- Tooltip box -->
                <div id="chart-tooltip-${type}" class="absolute bg-surface-container/90 border border-white/15 rounded-md px-2.5 py-1 text-center pointer-events-none opacity-0 shadow-lg transition-opacity duration-150 z-20 min-w-[70px]"></div>
                
                <!-- SVG Canvas -->
                <svg viewBox="0 0 500 180" class="w-full h-full overflow-visible">
                    <defs>
                        <linearGradient id="gradient-${type}" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>
                            <stop offset="100%" stop-color="${color}" stop-opacity="0.0"/>
                        </linearGradient>
                    </defs>
                    
                    <!-- Horizontal Grid Lines & Labels -->
                    ${gridLines.map(line => `
                        <line x1="${padding.left}" y1="${line.y}" x2="${svgWidth - padding.right}" y2="${line.y}" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
                        <text x="${padding.left - 8}" y="${line.y + 4}" fill="rgba(255,255,255,0.4)" font-size="9" text-anchor="end" class="${privacyClass}" ${privacyStyle}>$${line.label}</text>
                    `).join('')}
                    
                    <!-- Fill under curve -->
                    ${fillD ? `<path d="${fillD}" fill="url(#gradient-${type})" />` : ''}
                    
                    <!-- Line curve -->
                    ${pathD ? `<path d="${pathD}" fill="none" stroke="${color}" stroke-width="2.5" ${isPreview ? 'stroke-dasharray="4,4"' : ''} stroke-linecap="round" stroke-linejoin="round" />` : ''}
                    
                    <!-- Hover elements -->
                    <line id="chart-marker-line-${type}" x1="0" y1="${padding.top}" x2="0" y2="${svgHeight - padding.bottom}" stroke="rgba(255,255,255,0.2)" stroke-dasharray="3,3" class="hidden" />
                    <circle id="chart-marker-dot-${type}" r="5" fill="${color}" stroke="#0c0e12" stroke-width="1.5" class="hidden shadow-[0_0_8px_rgba(255,255,255,0.4)]" />
                    
                    <!-- X-Axis Labels -->
                    <text x="${padding.left}" y="${svgHeight - 6}" fill="rgba(255,255,255,0.4)" font-size="9" text-anchor="start">${startStr}</text>
                    <text x="${svgWidth - padding.right}" y="${svgHeight - 6}" fill="rgba(255,255,255,0.4)" font-size="9" text-anchor="end">${endStr}</text>
                    
                    <!-- Interactive Hover Overlay Rect -->
                    <rect x="${padding.left}" y="${padding.top}" width="${svgWidth - padding.left - padding.right}" height="${svgHeight - padding.top - padding.bottom}" fill="transparent" class="cursor-crosshair" onmousemove="window.handleChartHover(event, '${type}', '${pointsJsonEsc}')" />
                </svg>
            </div>
        </section>
    `;
}

function renderDashboardView() {
    if (STATE.is_loading_dashboard) {
        return `
            ${renderHeader()}
            <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] md:max-w-5xl mx-auto flex flex-col items-center justify-center min-h-[60vh]">
                <div class="relative w-24 h-24 mb-6">
                    <div class="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                    <div class="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
                    <div class="absolute inset-0 flex items-center justify-center text-primary">
                        <span class="material-symbols-outlined text-3xl animate-pulse">dashboard</span>
                    </div>
                </div>
                <h2 class="font-headline-sm text-headline-sm text-on-surface mb-2 animate-pulse">Loading Dashboard...</h2>
                <p class="font-body-md text-body-md text-on-surface-variant text-center max-w-[280px]">
                    Gathering your portfolio metrics.
                </p>
            </main>
        `;
    }

    const isPremium = STATE.user && STATE.user.is_premium;
    const hasLinkedCrypto = !!(STATE.user && STATE.user.has_exchange_keys);
    const hasLinkedStock = !!(STATE.user && STATE.user.has_alpaca_keys);
    const hasLinkedKeys = hasLinkedCrypto || hasLinkedStock;
    let isCrypto = STATE.dashboard_tab === 'crypto';
    if (hasLinkedCrypto && !hasLinkedStock) {
        isCrypto = true;
    } else if (!hasLinkedCrypto && hasLinkedStock) {
        isCrypto = false;
    }
    
    const tierBadge = `
        <div class="inline-flex items-center gap-1.5 px-3 py-1 glass-card ${isPremium ? 'gold-glow' : 'cyan-glow'} rounded-full">
            <span class="text-[10px]">${isPremium ? '💎' : '🥈'}</span>
            <span class="font-label-sm text-label-sm ${isPremium ? 'text-secondary-container' : 'text-primary'}">${isPremium ? 'Premium' : 'Standard'}</span>
        </div>
    `;

    if (!isPremium) {
        const active_signals = STATE.active_signals || [];
        const cryptoSignals = active_signals.filter(s => s.symbol && s.symbol.includes('/'));
        const stockSignals = active_signals.filter(s => s.symbol && !s.symbol.includes('/'));
        const cryptoCount = cryptoSignals.length;
        const stockCount = stockSignals.length;

        // Tabs visibility logic: if no crypto, only show stocks, and vice-versa
        let showCryptoTab = cryptoCount > 0;
        let showStockTab = stockCount > 0;
        if (cryptoCount === 0 && stockCount === 0) {
            showCryptoTab = true;
            showStockTab = true;
        }

        let isCrypto = STATE.dashboard_tab === 'crypto';
        if (isCrypto && !showCryptoTab && showStockTab) {
            isCrypto = false;
        } else if (!isCrypto && !showStockTab && showCryptoTab) {
            isCrypto = true;
        }

        const sortedCrypto = [...cryptoSignals].sort((a, b) => {
            if (STATE.active_signals_sort_by === 'date') {
                return (b.open_time || 0) - (a.open_time || 0);
            } else {
                return (b.pnl_pct || 0) - (a.pnl_pct || 0);
            }
        });

        const sortedStock = [...stockSignals].sort((a, b) => {
            if (STATE.active_signals_sort_by === 'date') {
                return (b.open_time || 0) - (a.open_time || 0);
            } else {
                return (b.pnl_pct || 0) - (a.pnl_pct || 0);
            }
        });

        const cryptoHtml = sortedCrypto.length === 0 ? `
            <div class="text-center py-8">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-5xl mb-3">hourglass_empty</span>
                <p class="font-body-md text-on-surface font-semibold">No active crypto signals</p>
            </div>
        ` : sortedCrypto.map(s => renderSignalCard(s)).join('');

        const stockHtml = sortedStock.length === 0 ? `
            <div class="text-center py-8">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-5xl mb-3">hourglass_empty</span>
                <p class="font-body-md text-on-surface font-semibold">No active stock signals</p>
            </div>
        ` : sortedStock.map(s => renderSignalCard(s)).join('');

        const shimmerHtml = `
            <div class="flex flex-col gap-4 animate-fade-in">
                <!-- Shimmer Card 1 -->
                <div class="glass-card rounded-xl p-card-padding relative overflow-hidden border border-white/5 bg-gradient-to-r from-surface-container-low/20 to-surface-container/20">
                    <div class="flex justify-between items-center mb-3">
                        <div class="h-6 w-32 bg-white/10 rounded-full animate-pulse"></div>
                        <div class="h-6 w-20 bg-primary/20 rounded-full animate-pulse"></div>
                    </div>
                    <div class="h-4 w-40 bg-white/5 rounded-full mb-6 animate-pulse"></div>
                    <div class="flex justify-between items-center pt-4 border-t border-white/5">
                        <div class="h-8 w-24 bg-white/5 rounded-lg animate-pulse"></div>
                        <div class="h-8 w-24 bg-white/5 rounded-lg animate-pulse"></div>
                    </div>
                    <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.05),transparent)] -translate-x-full animate-shimmer" style="animation: shimmer 1.5s infinite;"></div>
                </div>
            </div>
        `;

        let contentHtml = '';
        if (STATE.is_loading_active_signals && active_signals.length === 0) {
            contentHtml = shimmerHtml;
        } else if (active_signals.length === 0) {
            contentHtml = `
                <div class="text-center py-2 flex flex-col items-center justify-center animate-fade-in w-full">
                    ${getFreeStatsHtml()}
                </div>
            `;
        } else {
            if (showCryptoTab && showStockTab) {
                contentHtml = `
                    <!-- Mobile Tab Bar -->
                    <div class="glass-card rounded-full flex border border-white/10 p-1 w-full max-w-[500px] mx-auto relative overflow-hidden z-10 md:hidden mb-4">
                        <button onclick="setDashboardTab('crypto')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                            Crypto (${cryptoCount})
                        </button>
                        <button onclick="setDashboardTab('stock')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                            Stocks (${stockCount})
                        </button>
                    </div>

                    <!-- Mobile List (Single Column) -->
                    <div class="space-y-stack-gap md:hidden animate-fade-in">
                        ${isCrypto ? cryptoHtml : stockHtml}
                    </div>

                    <!-- Desktop View (Two Columns) -->
                    <div class="hidden md:grid md:grid-cols-2 md:gap-6 animate-fade-in">
                        <!-- Crypto Column -->
                        <div>
                            <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                                <span>🪙</span> Crypto (${cryptoCount})
                            </h3>
                            <div class="space-y-stack-gap">
                                ${cryptoHtml}
                            </div>
                        </div>
                        <!-- Stocks Column -->
                        <div>
                            <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                                <span>🦙</span> Stocks (${stockCount})
                            </h3>
                            <div class="space-y-stack-gap">
                                ${stockHtml}
                            </div>
                        </div>
                    </div>
                `;
            } else {
                const singleHtml = showCryptoTab ? cryptoHtml : stockHtml;
                const singleCount = showCryptoTab ? cryptoCount : stockCount;
                const singleLabel = showCryptoTab ? 'Crypto' : 'Stocks';
                const singleIcon = showCryptoTab ? '🪙' : '🦙';
                
                contentHtml = `
                    <div class="w-full max-w-[600px] mx-auto space-y-4 animate-fade-in">
                        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                            <span>${singleIcon}</span> ${singleLabel} (${singleCount})
                        </h3>
                        <div class="space-y-stack-gap">
                            ${singleHtml}
                        </div>
                    </div>
                `;
            }
        }

        return `
            ${renderHeader()}
            <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] md:max-w-5xl mx-auto">
                <div class="flex justify-between items-center">
                    ${tierBadge}
                </div>
                
                ${(STATE.is_loading_active_signals || (STATE.active_signals && STATE.active_signals.length > 0)) ? `
                <div class="flex items-center justify-between mt-6">
                    <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Active Signals</h2>
                    <button onclick="window.toggleActiveSignalsSort()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 hover:border-primary/30 transition-all text-xs font-semibold text-on-surface-variant hover:text-primary active:scale-95" title="Toggle sorting order">
                        <span class="material-symbols-outlined text-[16px]">${STATE.active_signals_sort_by === 'pnl' ? 'calendar_month' : 'trending_up'}</span>
                        <span>${STATE.active_signals_sort_by === 'pnl' ? 'Newest First' : 'Most Profitable First'}</span>
                    </button>
                </div>
                ` : ''}
                
                ${contentHtml}
            </main>
        `;
    }
    
    const activeStats = (STATE.stats && (isCrypto ? STATE.stats.crypto : STATE.stats.stock)) || { cumulative_pnl: 0, win_rate: 0, overall_pnl: 0, overall_pnl_pct: 0 };
    const activeStrategy = STATE.user ? (isCrypto ? (STATE.user.active_crypto_strategy || 'Valkyrie Elite Scalper') : (STATE.user.active_stock_strategy || 'None')) : (isCrypto ? 'Valkyrie Elite Scalper' : 'None');
    const balance = isCrypto ? STATE.crypto_balance : STATE.stock_balance;
    const activeTradesCount = STATE.open_trades.filter(t => t.type === (isCrypto ? 'crypto' : 'stock')).length;
    
    const backtestOnclick = isCrypto 
        ? `resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('${activeStrategy === 'None' ? 'Valkyrie Elite Scalper' : activeStrategy}'); triggerBacktest(); }, 150);`
        : `resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('Sherpa Velocity Pullback'); triggerBacktest(); }, 150);`;

    // Gated actions for premium
    const actionCards = `
        <a href="#/trades" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
            <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">data_exploration</span>
            <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Live Trades</span>
        </a>
        <a href="#/history" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
            <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">history</span>
            <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Trade History</span>
        </a>
        <a href="#/stats" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
            <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">insights</span>
            <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">My Stats</span>
        </a>
        <button onclick="${backtestOnclick}" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group cursor-pointer w-full">
            <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">science</span>
            <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Backtest</span>
        </button>
        <a href="#/signals" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group col-span-2">
            <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">satellite_alt</span>
            <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Alpha Signals (${(STATE.active_signals || []).filter(s => isCrypto ? s.symbol.includes('/') : !s.symbol.includes('/')).length})</span>
        </a>
    `;
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const shouldBlurDollars = STATE.is_loading_crypto_balance || STATE.is_loading_stock_balance || isPrivacyOn;
    
    const privacyStyle = shouldBlurDollars ? 'style="filter: blur(14px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
    const privacyClass = shouldBlurDollars ? 'privacy-blur' : '';
    const privacyHoverHandlers = shouldBlurDollars ? `onmouseenter="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='none')" onmouseleave="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='blur(14px)')"` : '';

    function renderDashboardColumn(type) {
        const isCryptoType = type === 'crypto';
        const isPremium = STATE.user && STATE.user.is_premium;
        const hasLinkedCrypto = !!(STATE.user && STATE.user.has_exchange_keys);
        const hasLinkedStock = !!(STATE.user && STATE.user.has_alpaca_keys);

        const showLoadingBalance = isCryptoType ? STATE.is_loading_crypto_balance : STATE.is_loading_stock_balance;

        const colIsPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
        const colShouldBlurDollars = showLoadingBalance || colIsPrivacyOn;
        const colPrivacyStyle = colShouldBlurDollars ? 'style="filter: blur(14px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
        const colPrivacyClass = colShouldBlurDollars ? 'privacy-blur' : '';
        const colPrivacyHoverHandlers = colShouldBlurDollars ? `onmouseenter="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='none')" onmouseleave="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='blur(14px)')"` : '';

        const typeStats = (STATE.stats && (isCryptoType ? STATE.stats.crypto : STATE.stats.stock)) || { cumulative_pnl: 0, win_rate: 0, overall_pnl: 0, overall_pnl_pct: 0 };
        const typeStrategy = STATE.user ? (isCryptoType ? (STATE.user.active_crypto_strategy || 'Valkyrie Elite Scalper') : (STATE.user.active_stock_strategy || 'None')) : (isCryptoType ? 'Valkyrie Elite Scalper' : 'None');
        const typeBalance = isCryptoType ? STATE.crypto_balance : STATE.stock_balance;
        const typeActiveTradesCount = STATE.open_trades.filter(t => t.type === type).length;
        
        const typeBacktestOnclick = isCryptoType 
            ? `STATE.dashboard_tab = 'crypto'; resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('${typeStrategy === 'None' ? 'Valkyrie Elite Scalper' : typeStrategy}'); triggerBacktest(); }, 150);`
            : `STATE.dashboard_tab = 'stock'; resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('Sherpa Velocity Pullback'); triggerBacktest(); }, 150);`;

        const typeActionCards = `
            <a href="#/trades" onclick="STATE.dashboard_tab = '${type}';" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
                <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">data_exploration</span>
                <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Live Trades</span>
            </a>
            <a href="#/history" onclick="STATE.dashboard_tab = '${type}';" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
                <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">history</span>
                <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Trade History</span>
            </a>
            <a href="#/stats" onclick="STATE.dashboard_tab = '${type}';" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group">
                <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">insights</span>
                <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">My Stats</span>
            </a>
            <button onclick="${typeBacktestOnclick}" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group cursor-pointer w-full">
                <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">science</span>
                <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Backtest</span>
            </button>
            <a href="#/signals" onclick="STATE.dashboard_tab = '${type}';" class="glass-card rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group col-span-2">
                <span class="material-symbols-outlined text-primary text-xl group-hover:scale-110 transition-transform">satellite_alt</span>
                <span class="font-label-md text-label-md text-on-surface font-semibold whitespace-nowrap">Alpha Signals (${(STATE.active_signals || []).filter(s => isCryptoType ? s.symbol.includes('/') : !s.symbol.includes('/')).length})</span>
            </a>
        `;

        const typePnlVal = typeStats.overall_pnl !== undefined ? typeStats.overall_pnl : (typeStats.cumulative_pnl || 0);
        const typeStartingCapital = typeBalance - typePnlVal;
        const typePnlPct = typeStats.overall_pnl_pct !== undefined ? typeStats.overall_pnl_pct : (typeStartingCapital > 0 ? (typePnlVal / typeStartingCapital) * 100 : 0);

        return `
            <div class="space-y-4">
                <h2 class="font-headline-sm text-headline-sm text-on-surface flex items-center gap-2">
                    <span>${isCryptoType ? '🪙' : '📈'}</span> ${isCryptoType ? 'Crypto Portfolio' : 'Stock Portfolio'}
                </h2>
                
                <!-- Balance Card -->
                <section class="glass-card cyan-glow rounded-xl p-card-padding relative overflow-hidden cursor-pointer" ${colPrivacyHoverHandlers}>
                    <div class="absolute -right-10 -top-10 w-32 h-32 bg-primary/10 blur-3xl rounded-full pointer-events-none"></div>
                    <div class="relative z-10 pointer-events-none">
                        <p class="font-label-md text-label-md text-on-surface-variant mb-1 flex items-center gap-1.5">
                            <span>${isCryptoType ? 'Crypto Equity' : 'Stock Equity'}</span>
                            <button onclick="event.stopPropagation(); window.forceRefreshSegment('${type}')" class="p-1 -m-1 hover:bg-white/10 rounded-full transition-colors flex items-center justify-center text-primary cursor-pointer pointer-events-auto" title="Force Refresh">
                                <span class="material-symbols-outlined text-sm">sync</span>
                            </button>
                        </p>
                        ${showLoadingBalance ? `
                        <div class="flex items-center gap-3 py-1.5 animate-pulse">
                            <span class="material-symbols-outlined text-primary text-xl animate-spin">sync</span>
                            <span class="text-xs text-on-surface-variant font-medium">Loading encrypted account balance details...</span>
                        </div>
                        ` : `
                        <div class="flex items-baseline gap-3">
                            <h1 class="font-display-lg text-display-lg text-on-surface drop-shadow-[0_0_12px_rgba(168,232,255,0.15)] ${colPrivacyClass}" ${colPrivacyStyle}>$${(typeBalance || 0).toFixed(2)}</h1>
                            <div class="${typePnlVal >= 0 ? 'text-tertiary' : 'text-error'} flex items-baseline gap-1">
                                <span class="font-headline-sm text-headline-sm">${typePnlVal >= 0 ? '+' : ''}${typePnlPct.toFixed(2)}%</span>
                                <span class="font-label-md text-label-md text-on-surface-variant font-normal">(<span class="${colPrivacyClass}" ${colPrivacyStyle}>${typePnlVal >= 0 ? '+' : '-'}$${Math.abs(typePnlVal).toFixed(2)}</span>)</span>
                            </div>
                        </div>
                        `}
                    </div>
                </section>
                
                ${renderBalanceChartWidget(type)}
                
                <!-- Quick Stats -->
                <section class="grid grid-cols-2 gap-stack-gap">
                    <a href="#/trades" onclick="STATE.dashboard_tab = '${type}';" class="glass-card rounded-lg p-3 text-center border-t-2 border-primary/40 hover:bg-white/5 transition-colors group block">
                        <p class="font-label-sm text-label-sm text-on-surface-variant mb-1 group-hover:text-primary transition-colors">Open Trades</p>
                        ${showLoadingBalance ? `
                        <div class="flex items-center justify-center py-1 animate-pulse">
                            <span class="material-symbols-outlined text-primary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="font-numeric-data text-numeric-data text-primary">${typeActiveTradesCount}</p>
                        `}
                    </a>
                    <div class="glass-card rounded-lg p-3 text-center border-t-2 border-tertiary/40">
                        <p class="font-label-sm text-label-sm text-on-surface-variant mb-1">Win Rate</p>
                        ${showLoadingBalance ? `
                        <div class="flex items-center justify-center py-1 animate-pulse">
                            <span class="material-symbols-outlined text-tertiary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="font-numeric-data text-numeric-data text-tertiary flex items-baseline gap-2 justify-center">
                            ${typeStats.win_rate || 0}% 
                            <span class="text-xs text-on-surface-variant font-normal">(${typeStats.wins || 0}W / ${typeStats.losses || 0}L)</span>
                        </p>
                        `}
                    </div>
                </section>
                
                <button onclick="window.shareStatsCard('${type}')" class="w-full h-11 bg-surface-container text-on-surface font-label-md text-label-md border border-white/10 rounded-lg hover:bg-white/5 hover:border-primary/30 transition-all flex items-center justify-center gap-2 cursor-pointer">
                    <span class="material-symbols-outlined text-[18px]">share</span> Share & Earn
                </button>
                
                <!-- Action Grid -->
                <section class="grid grid-cols-2 gap-stack-gap">
                    ${typeActionCards}
                </section>
            </div>
        `;
    }

    const isTabLinked = isCrypto ? hasLinkedCrypto : hasLinkedStock;
    
    let dashboardContent = '';
    
    if (!hasLinkedKeys) {
        // Neither connected
        dashboardContent = `
            <!-- No Exchange Linked / Active Signals -->
            <div class="space-y-6 mt-6 animate-fade-in w-full max-w-[500px] lg:max-w-full mx-auto">
                ${!STATE.hide_exchange_warning ? `
                <div class="glass-card rounded-xl p-card-padding border border-white/10 bg-surface-container/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div class="space-y-1">
                        <h3 class="font-body-lg text-body-lg font-bold text-on-surface flex items-center gap-2">
                            <span class="material-symbols-outlined text-on-surface-variant">link_off</span> Exchange Not Connected
                        </h3>      
                        <p class="text-xs text-on-surface-variant leading-relaxed max-w-[800px] pt-1">
                            Until you connect your crypto and/or stock exchange, you'll only see the free Alpha Signals.
                        </p>
                    </div>
                    <div class="flex items-center gap-2">
                        <a href="#/settings" class="shrink-0 h-10 px-5 inline-flex items-center justify-center bg-white/5 border border-white/10 text-on-surface font-bold text-xs tracking-wider rounded-lg hover:bg-white/10 transition-colors">
                            CONNECT EXCHANGE
                        </a>
                        <button onclick="STATE.hide_exchange_warning = true; renderView();" class="text-on-surface-variant hover:text-white transition-colors w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 shrink-0" title="Hide">
                            <span class="material-symbols-outlined text-[20px]">close</span>
                        </button>
                    </div>
                </div>
                ` : ''}
                
                ${(STATE.is_loading_active_signals || (STATE.active_signals && STATE.active_signals.length > 0)) ? `
                <div class="flex items-center justify-between pt-4">
                    <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Active Signals</h2>
                    <button onclick="console.log('Sorting signals...'); window.toggleActiveSignalsSort()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 hover:border-primary/30 transition-all text-xs font-semibold text-on-surface-variant hover:text-primary active:scale-95" title="Toggle sorting order">
                        <span class="material-symbols-outlined text-[16px]">${STATE.active_signals_sort_by === 'pnl' ? 'calendar_month' : 'trending_up'}</span>
                        <span>${STATE.active_signals_sort_by === 'pnl' ? 'Newest First' : 'Most Profitable First'}</span>
                    </button>
                </div>
                ` : ''}
                
                <div class="space-y-stack-gap">
                    ${STATE.is_loading_active_signals && STATE.active_signals.length === 0 ? `
                        <div class="flex flex-col gap-4 animate-fade-in">
                            <!-- Shimmer Card 1 -->
                            <div class="glass-card rounded-xl p-card-padding relative overflow-hidden border border-white/5 bg-gradient-to-r from-surface-container-low/20 to-surface-container/20">
                                <div class="flex justify-between items-center mb-3">
                                    <div class="h-6 w-32 bg-white/10 rounded-full animate-pulse"></div>
                                    <div class="h-6 w-20 bg-primary/20 rounded-full animate-pulse"></div>
                                </div>
                                <div class="h-4 w-40 bg-white/5 rounded-full mb-6 animate-pulse"></div>
                                <div class="flex justify-between items-center pt-4 border-t border-white/5">
                                    <div class="h-8 w-24 bg-white/5 rounded-lg animate-pulse"></div>
                                    <div class="h-8 w-24 bg-white/5 rounded-lg animate-pulse"></div>
                                </div>
                                <div class="absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.05),transparent)] -translate-x-full animate-shimmer" style="animation: shimmer 1.5s infinite;"></div>
                            </div>
                        </div>
                    ` : (() => {
                        const sorted = [...STATE.active_signals].sort((a, b) => {
                            if (STATE.active_signals_sort_by === 'date') {
                                return (b.open_time || 0) - (a.open_time || 0);
                            } else {
                                return (b.pnl_pct || 0) - (a.pnl_pct || 0);
                            }
                        });
                        return sorted.length === 0 ? `
                            <div class="text-center py-2 flex flex-col items-center justify-center animate-fade-in w-full">
                                ${getFreeStatsHtml()}
                            </div>
                        ` : `
                            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 w-full">
                                ${sorted.map(s => renderSignalCard(s)).join('')}
                            </div>
                        `;
                    })()}
                </div>
            </div>
        `;
    } else if (hasLinkedCrypto && hasLinkedStock) {
        // Both connected: responsive layout
        dashboardContent = `
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 animate-fade-in">
                <!-- Crypto Column (Visible on Crypto tab or on Desktop) -->
                <div class="${isCrypto ? 'block' : 'hidden md:block'}">
                    ${renderDashboardColumn('crypto')}
                </div>
                <!-- Stock Column (Visible on Stock tab or on Desktop) -->
                <div class="${!isCrypto ? 'block' : 'hidden md:block'}">
                    ${renderDashboardColumn('stock')}
                </div>
            </div>
        `;
    } else {
        // Only one connected
        const activeType = hasLinkedCrypto ? 'crypto' : 'stock';
        dashboardContent = `
            <div class="max-w-[500px] mx-auto animate-fade-in">
                ${renderDashboardColumn(activeType)}
            </div>
        `;
    }

    let mainMaxWidthClass = 'max-w-[500px]';
    if (hasLinkedCrypto && hasLinkedStock) {
        mainMaxWidthClass = 'max-w-[500px] md:max-w-[1000px]';
    } else if (!hasLinkedKeys) {
        mainMaxWidthClass = 'max-w-[500px] lg:max-w-full';
    }

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap ${mainMaxWidthClass} mx-auto">
            <!-- Tier Badge & Tabs -->
            <div class="flex justify-between items-center">
                <div class="inline-flex items-center gap-1.5 px-3 py-1 glass-card ${isPremium ? 'gold-glow' : 'cyan-glow'} rounded-full">
                    <span class="text-[10px]">${isPremium ? '💎' : '🥈'}</span>
                    <span class="font-label-sm text-label-sm ${isPremium ? 'text-secondary-container' : 'text-primary'}">${isPremium ? 'Premium' : 'Standard'}</span>
                </div>
                ${(hasLinkedCrypto && hasLinkedStock) ? `
                <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1 md:hidden">
                    <button onclick="setDashboardTab('crypto')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Crypto</button>
                    <button onclick="setDashboardTab('stock')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Stocks</button>
                </div>
                ` : ''}
            </div>
            
            ${dashboardContent}
        </main>
    `;
}


window.setHistoryPage = function(type, delta) {
    if (type === 'crypto') {
        STATE.history_page_crypto = (STATE.history_page_crypto || 1) + delta;
    } else {
        STATE.history_page_stock = (STATE.history_page_stock || 1) + delta;
    }
    renderView();
};

function renderTradesView() {
    const isPremium = STATE.user && STATE.user.is_premium;
    
    if (!isPremium) {
        return `
            ${renderHeader()}
            <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
                <h2 class="font-headline-sm text-headline-sm text-on-surface">💎 Go Premium</h2>
                
                <div class="glass-card rounded-xl overflow-hidden border-t-2 border-secondary-container/40">
                    <div class="p-6 bg-surface-container-low text-center border-b border-white/5 relative overflow-hidden">
                        <div class="absolute inset-0 bg-gradient-to-br from-secondary-container/10 to-transparent pointer-events-none"></div>
                        <span class="material-symbols-outlined text-secondary-container text-5xl mb-2 relative z-10">diamond</span>
                        <h2 class="text-2xl font-bold text-on-surface relative z-10">Unlock the 23x Wealth Gap</h2>
                        <p class="text-sm text-on-surface-variant mt-2 relative z-10">Unlock professional-grade tools used by elite traders.</p>
                    </div>
                    <div class="p-6 space-y-5">
                        <div class="flex items-start gap-3">
                            <span class="material-symbols-outlined text-primary text-2xl mt-0.5">smart_toy</span>
                            <div>
                                <p class="font-bold text-on-surface">Full Autopilot</p>
                                <p class="text-sm text-on-surface-variant mt-0.5">Live auto-trading directly on your exchange.</p>
                            </div>
                        </div>
                        <div class="flex items-start gap-3">
                            <span class="material-symbols-outlined text-primary text-2xl mt-0.5">query_stats</span>
                            <div>
                                <p class="font-bold text-on-surface">Full Sherpa Basket</p>
                                <p class="text-sm text-on-surface-variant mt-0.5">Trade all 19+ premium symbols.</p>
                            </div>
                        </div>
                        <div class="flex items-start gap-3">
                            <span class="material-symbols-outlined text-primary text-2xl mt-0.5">tune</span>
                            <div>
                                <p class="font-bold text-on-surface">Advanced Risk</p>
                                <p class="text-sm text-on-surface-variant mt-0.5">Set custom risk-per-trade percentages.</p>
                            </div>
                        </div>
                        <div class="flex items-start gap-3">
                            <span class="material-symbols-outlined text-primary text-2xl mt-0.5">bolt</span>
                            <div>
                                <p class="font-bold text-on-surface">Priority Execution</p>
                                <p class="text-sm text-on-surface-variant mt-0.5">Priority in the engine's background loop.</p>
                            </div>
                        </div>
                    </div>
                    <div class="p-6 bg-surface-container-low border-t border-white/5">
                        <a href="#/premium" class="block w-full text-center h-12 leading-[48px] bg-secondary-container text-on-secondary-container font-bold rounded-lg hover:brightness-110 transition-all shadow-[0_0_15px_rgba(212,175,55,0.3)]">
                            Upgrade Now - $20 / mo
                        </a>
                        <p class="text-center text-xs text-tertiary mt-4">
                            🎁 Or invite 3 friends to unlock 1 Month Free! <a href="#/referral" class="underline font-bold">Tap to refer!</a>
                        </p>
                    </div>
                </div>
            </main>
        `;
    }

    const isCrypto = STATE.dashboard_tab === 'crypto';
    const hasLinkedCrypto = !!(STATE.user && STATE.user.has_exchange_keys);
    const hasLinkedStock = !!(STATE.user && STATE.user.has_alpaca_keys);
    const isTabLinked = isCrypto ? hasLinkedCrypto : hasLinkedStock;
    
    if (isPremium && !isTabLinked) {
        return `
            ${renderHeader()}
            <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="font-headline-sm text-headline-sm text-on-surface">📈 Live Trades</h2>
                    ${(hasLinkedCrypto || hasLinkedStock) ? `
                    <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1">
                        <button onclick="setDashboardTab('crypto')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Crypto</button>
                        <button onclick="setDashboardTab('stock')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Stocks</button>
                    </div>
                    ` : ''}
                </div>
                
                <div class="glass-card rounded-xl p-card-padding border border-white/10 bg-surface-container/30 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div class="space-y-1">
                        <h3 class="font-body-lg text-body-lg font-bold text-on-surface flex items-center gap-2">
                            <span class="material-symbols-outlined text-on-surface-variant">smart_toy</span> Automate Trades
                        </h3>
                        <p class="text-xs text-on-surface-variant leading-relaxed max-w-[420px]">
                            Stop trading manually and let our AI do the heavy lifting! Connect your ${(!hasLinkedCrypto && !hasLinkedStock) ? 'Crypto Exchange or Alpaca Stocks' : (isCrypto ? 'Crypto Exchange' : 'Alpaca Stocks')} API credentials securely to unlock full autonomous copy-trading and monitor your live portfolio performance in real-time.
                        </p>
                    </div>
                    <a href="#/settings" class="shrink-0 h-10 px-5 inline-flex items-center justify-center bg-white/5 border border-white/10 text-on-surface font-bold text-xs tracking-wider rounded-lg hover:bg-white/10 transition-colors">
                        GO TO SETTINGS
                    </a>
                </div>
            </main>
        `;
    }
    let tradesMode = STATE.trades_mode;
    if (!tradesMode) {
        tradesMode = (STATE.open_trades && STATE.open_trades.length === 0) ? 'closed' : 'active';
    }
    
    const generateTradeHtml = (type) => {
        const isCryptoType = type === 'crypto';
        let listHtml = '';
        
        if (tradesMode === 'active') {
            const filteredTrades = (STATE.open_trades || []).filter(t => t.type === type);
            const sortedTrades = [...filteredTrades].sort((a, b) => {
                if (STATE.open_trades_sort_by === 'date') {
                    const timeA = a.open_time ? (a.open_time > 1000000000000 ? a.open_time : a.open_time * 1000) : Date.now();
                    const timeB = b.open_time ? (b.open_time > 1000000000000 ? b.open_time : b.open_time * 1000) : Date.now();
                    return timeB - timeA;
                } else {
                    return (b.roe || 0) - (a.roe || 0);
                }
            });
            if (sortedTrades.length === 0) {
                listHtml = `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">hourglass_empty</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No open positions</p>
                        <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">The Sherpa engine is scanning the markets...</p>
                    </div>
                `;
            } else {
                listHtml = sortedTrades.map(trade => {
                    const dateStr = trade.open_time ? timeAgo(trade.open_time) : 'Recent';
                    let displaySymbol = trade.symbol;
                    if (trade.type === 'crypto') {
                        displaySymbol = displaySymbol.replace(/\/USDT.*$/, '');
                    }
                    
                    const pnlColor = (trade.unrealized_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const roeColor = (trade.roe || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const icon = trade.side === 'LONG' ? 'trending_up' : 'trending_down';
                    const assetIcon = trade.type === 'stock' ? '🦙' : '🪙';
                    const isExpanded = STATE.expanded_trade_id === trade.id;
                    
                    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                    const inlineBlur = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(14px)\'"' : '';
                    
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
                                <div class="flex items-center justify-between">
                                    <h4 class="text-xs font-bold text-on-surface-variant/80 uppercase tracking-wider">Market Analysis & Setup</h4>
                                    <span id="chart-status-trade-${trade.id}" class="text-[10px] text-primary font-mono flex items-center gap-1.5">
                                        <span class="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
                                        AI Agent plotting chart...
                                    </span>
                                </div>
                                <div class="relative w-full bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
                                    <div id="chart-loading-trade-${trade.id}" class="absolute inset-0 p-4 font-mono text-[10px] text-primary/80 bg-[#0b0f19]/90 flex flex-col justify-start gap-1 text-left overflow-y-auto scrollbar-thin select-none">
                                        <div class="flex items-center justify-between border-b border-white/10 pb-1.5 mb-1.5">
                                            <div class="flex items-center gap-1.5">
                                                <span class="w-2 h-2 rounded-full bg-error/80"></span>
                                                <span class="w-2 h-2 rounded-full bg-warning/80"></span>
                                                <span class="w-2 h-2 rounded-full bg-success/80"></span>
                                            </div>
                                            <span class="text-[9px] text-on-surface-variant/40">sherpa_analyst_agent.py</span>
                                        </div>
                                        <div class="space-y-1">
                                            <div class="text-on-surface/90 font-semibold">&gt; python3 sherpa_analyst_agent.py --symbol ${trade.symbol} --side ${trade.side}</div>
                                            <div class="text-primary/70 animate-pulse">[0.5s] Sourcing exchange order books and historical candles...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 1.5s; opacity: 0;">[1.8s] Candlestick series downloaded (150 periods). Analyzing patterns...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 3.5s; opacity: 0;">[3.2s] Slicing indicator overlays: 20/50/200 EMA + Bollinger Bands...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 5.5s; opacity: 0;">[5.0s] Mapping trade plan: entry ($${entry.toFixed(4)}), tp ($${tp.toFixed(4)}), sl ($${sl.toFixed(4)})...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 7.2s; opacity: 0;">[7.2s] Calculating Risk/Reward ratio and trade trajectory progress...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 9.5s; opacity: 0;">[9.5s] Constructing Matplotlib dynamic layout canvas with dark theme...</div>
                                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 12.0s; opacity: 0;">[12.0s] Compiling chart canvas assets & rendering price action lines...</div>
                                            <div class="text-primary/50 animate-pulse" style="animation: reveal-log 0.2s forwards, pulse 1.5s infinite; animation-delay: 15.0s; opacity: 0;">[15.0s] Completing high-resolution plot generation on backend...</div>
                                        </div>
                                    </div>
                                    <img src="/api/trades/chart?symbol=${encodeURIComponent(trade.symbol)}&entry=${entry}&tp=${tp}&sl=${sl}&side=${trade.side}&open_ts=${trade.open_time}&type=${trade.type}&current_price=${trade.mark_price || 0}" 
                                         onload="const l = document.getElementById('chart-loading-trade-${trade.id}'); if(l)l.remove(); const s = document.getElementById('chart-status-trade-${trade.id}'); if(s)s.remove(); this.classList.remove('hidden');" 
                                         class="w-full h-auto block hidden" alt="Trade Chart" />
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
                                    <div class="text-right flex flex-col items-end">
                                        <p class="font-numeric-data text-numeric-data font-bold text-lg ${roeColor}">
                                            ${(trade.roe || 0) >= 0 ? '+' : ''}${(trade.roe || 0).toFixed(2)}%
                                            ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> of ${Math.abs(((trade.tp_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0)}%</span>` : ''}
                                        </p>
                                        <p class="font-numeric-data text-numeric-data text-xs ${pnlColor} mt-0.5">
                                            <span ${inlineBlur}>${(trade.unrealized_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(trade.unrealized_pnl || 0).toFixed(2)}</span>
                                            ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-[10px] font-normal"> / <span ${inlineBlur}>+$${(Math.abs(trade.tp_price - trade.entry_price) * (trade.qty || 0)).toFixed(2)}</span></span>` : ''}
                                        </p>
                                    </div>
                                    <span class="material-symbols-outlined text-on-surface-variant/60 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}">expand_more</span>
                                </div>
                            </div>
                            <div class="flex justify-between items-center pt-3 border-t border-white/10">
                                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                    SL: <span class="text-on-surface">$${(trade.sl_price || 0).toFixed(trade.type === 'crypto' ? 4 : 2)} (${trade.entry_price > 0 && trade.sl_price > 0 ? (((trade.sl_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0) : '0'}%)</span>
                                </div>
                                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                    TP: <span class="text-on-surface">$${(trade.tp_price || 0).toFixed(trade.type === 'crypto' ? 4 : 2)} (${trade.entry_price > 0 && trade.tp_price > 0 ? (((trade.tp_price - trade.entry_price) / trade.entry_price) * 100 * (trade.type === 'crypto' ? 20.0 : 1.0)).toFixed(0) : '0'}%)</span>
                                </div>
                            </div>
                            ${progressBarHtml}
                        </div>
                    `;
                }).join('');
            }
        } else {
            const filteredHistory = (STATE.history || []).filter(t => t.type === type);
            if (filteredHistory.length === 0) {
                listHtml = `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No trade history</p>
                    </div>
                `;
            } else {
                const page = type === 'crypto' ? (STATE.history_page_crypto || 1) : (STATE.history_page_stock || 1);
                const itemsPerPage = 10;
                const totalPages = Math.ceil(filteredHistory.length / itemsPerPage);
                const safePage = Math.min(Math.max(1, page), totalPages);
                
                const startIndex = (safePage - 1) * itemsPerPage;
                const pagedHistory = filteredHistory.slice(startIndex, startIndex + itemsPerPage);
            
                const itemsHtml = pagedHistory.map(t => {
                    const dateStr = t.timestamp ? timeAgo(t.timestamp) : 'Recent';
                    let displaySymbol = t.symbol;
                    if (t.type === 'crypto') {
                        displaySymbol = displaySymbol.replace(/\/USDT.*$/, '');
                    }
                    
                    const pnlColor = (t.net_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                    const roePct = t.pnl_pct !== undefined ? t.pnl_pct : (t.roe_val !== undefined ? t.roe_val : (t.roe !== undefined ? t.roe : 0));
                    const roeColor = roePct >= 0 ? 'text-tertiary' : 'text-error';
                    const assetIcon = t.type === 'stock' ? '🦙' : '🪙';
                    const isLong = t.side === 'LONG' || t.side === 'l' || t.side === 'long';
                    
                    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                    const inlineBlur = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(14px)\'"' : '';
                    
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
                
                let paginationHtml = '';
                if (totalPages > 1) {
                    paginationHtml = `
                        <div class="flex items-center justify-between mt-6 px-2">
                            <button onclick="setHistoryPage('${type}', -1)" ${safePage === 1 ? 'disabled' : ''} class="w-10 h-10 rounded-full flex items-center justify-center border border-white/10 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                                <span class="material-symbols-outlined text-on-surface-variant">chevron_left</span>
                            </button>
                            <span class="text-xs font-bold text-on-surface-variant/80">Page ${safePage} of ${totalPages}</span>
                            <button onclick="setHistoryPage('${type}', 1)" ${safePage === totalPages ? 'disabled' : ''} class="w-10 h-10 rounded-full flex items-center justify-center border border-white/10 hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-all">
                                <span class="material-symbols-outlined text-on-surface-variant">chevron_right</span>
                            </button>
                        </div>
                    `;
                }
                
                listHtml = itemsHtml + paginationHtml;
            }
        }
        return listHtml;
    };
    
    const cryptoHtml = generateTradeHtml('crypto');
    const stockHtml = generateTradeHtml('stock');
    
    const cryptoCount = tradesMode === 'active' ? (STATE.open_trades || []).filter(t => t.type === 'crypto').length : (STATE.history || []).filter(t => t.type === 'crypto').length;
    const stockCount = tradesMode === 'active' ? (STATE.open_trades || []).filter(t => t.type === 'stock').length : (STATE.history || []).filter(t => t.type === 'stock').length;

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

            <!-- Sort Controls -->
            ${tradesMode === 'active' && STATE.open_trades && STATE.open_trades.length > 0 ? `
            <div class="flex justify-end items-center w-full z-10 relative">
                <button onclick="window.toggleOpenTradesSort()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 hover:border-primary/30 transition-all text-xs font-semibold text-on-surface-variant hover:text-primary active:scale-95" title="Toggle sorting order">
                    <span class="material-symbols-outlined text-[16px]">${STATE.open_trades_sort_by === 'pnl' ? 'calendar_month' : 'trending_up'}</span>
                    <span>${STATE.open_trades_sort_by === 'pnl' ? 'Newest First' : 'Most Profitable First'}</span>
                </button>
            </div>
            ` : ''}

            ${(cryptoCount > 0 && stockCount > 0) || (cryptoCount === 0 && stockCount === 0) ? `
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
            ` : `
            <!-- Mobile View (Single List - One Category Only) -->
            <div class="space-y-stack-gap md:hidden">
                <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                    ${cryptoCount > 0 ? `<span>🪙</span> Crypto (${cryptoCount})` : `<span>🦙</span> Stocks (${stockCount})`}
                </h3>
                ${cryptoCount > 0 ? cryptoHtml : stockHtml}
            </div>
            `}
            
            <!-- Desktop View -->
            <div class="hidden md:grid ${(cryptoCount > 0 && stockCount > 0) || (cryptoCount === 0 && stockCount === 0) ? 'md:grid-cols-2' : 'md:grid-cols-1'} md:gap-6">
                <!-- Crypto Column -->
                ${cryptoCount > 0 || (cryptoCount === 0 && stockCount === 0) ? `
                <div>
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                        <span>🪙</span> Crypto (${cryptoCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${cryptoHtml}
                    </div>
                </div>
                ` : ''}
                <!-- Stocks Column -->
                ${stockCount > 0 || (cryptoCount === 0 && stockCount === 0) ? `
                <div>
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                        <span>🦙</span> Stocks (${stockCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${stockHtml}
                    </div>
                </div>
                ` : ''}
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
}

function renderFreeHistoryView() {
    if (!STATE.free_history) return `${renderHeader()}<main class="pt-20 px-container-margin"><div class="text-center p-8 text-on-surface-variant">Loading history...</div></main>`;

    let listHtml = STATE.free_history.map((t, i) => {
        const isStock = t.symbol && !t.symbol.includes('/');
        const assetIcon = isStock ? '🦙' : '🪙';
        const sideIcon = String(t.side).toLowerCase() === 'long' ? '📈' : '📉';
        
        let dateStr = "Unknown";
        if (t.close_time) {
            const dt = new Date(t.close_time * 1000);
            const m = String(dt.getMonth() + 1).padStart(2, '0');
            const d = String(dt.getDate()).padStart(2, '0');
            const hh = String(dt.getHours()).padStart(2, '0');
            const mm = String(dt.getMinutes()).padStart(2, '0');
            dateStr = `${m}-${d} ${hh}:${mm}`;
        }
        
        const pnlPct = t.pnl_pct || 0;
        const winIcon = pnlPct > 0 ? '🏆' : '❌';
        
        const dollarVal = (1000 * (pnlPct/100)).toFixed(2);
        const pnlDollar = pnlPct >= 0 ? `+$${dollarVal}` : `-$${Math.abs(dollarVal)}`;
        const pnlColor = pnlPct > 0 ? 'text-tertiary' : 'text-error';

        return `
            <div class="glass-card rounded-lg p-4 border border-white/5 space-y-2 relative overflow-hidden group">
                <div class="flex items-center gap-2 text-sm">
                    <span class="font-bold text-base text-on-surface-variant">${i + 1}.</span>
                    <div class="w-6 h-6 rounded-full bg-surface-container flex items-center justify-center text-xs border border-white/10">
                        ${assetIcon}
                    </div>
                    <span class="font-bold text-primary text-base">${t.symbol.split('/')[0]}</span>
                    <span class="text-base">${sideIcon}</span>
                    <span class="text-on-surface-variant text-xs ml-auto">| ${dateStr}</span>
                </div>
                
                <div class="flex items-center gap-2 text-sm">
                    <span>🧠</span>
                    <span class="italic text-on-surface-variant">${t.strategy || 'Metaverse Sherpa'}</span>
                </div>
                
                <div class="flex items-center gap-2 text-sm">
                    <span>${winIcon}</span>
                    <span class="text-on-surface-variant">PnL:</span>
                    <span class="font-mono bg-surface-container-low px-2 py-0.5 rounded blur-[4px] group-active:blur-none transition-all cursor-pointer font-bold ${pnlColor}">${pnlDollar}</span>
                    <span class="font-bold ${pnlColor}">(${pnlPct > 0 ? '+' : ''}${pnlPct.toFixed(1)}%)</span>
                </div>
            </div>
        `;
    }).join('');

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface flex items-center gap-2 mb-6">
                📜 Metaverse Sherpa History
            </h2>
            
            <div class="space-y-3">
                ${listHtml}
            </div>
            
            <p class="text-center text-xs text-on-surface-variant mt-4 opacity-70">
                *Tap blurred PnL amounts to reveal
            </p>
        </main>
    `;
}

function timeAgo(ts) {
    if (!ts) return 'Just now';
    const now = Date.now();
    const tsMs = ts > 1000000000000 ? ts : ts * 1000;
    const diff = Math.max(0, now - tsMs);
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

function renderHistoryView() {
    if (!STATE.user || !STATE.user.is_premium) {
        return renderFreeHistoryView();
    }
    
    const isCrypto = STATE.dashboard_tab === 'crypto';
    const filteredHistory = STATE.history.filter(t => t.type === (isCrypto ? 'crypto' : 'stock'));
    
    STATE.history_limit = STATE.history_limit || 10;
    const historyToRender = filteredHistory.slice(0, STATE.history_limit);
    const hasMoreHistory = filteredHistory.length > STATE.history_limit;
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="flex items-center gap-6 justify-between">
                <h2 class="font-headline-sm text-headline-sm text-on-surface whitespace-nowrap">📜 History</h2>
                ${(STATE.user.has_exchange_keys || STATE.user.has_alpaca_keys) ? `
                <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1">
                    <button onclick="setDashboardTab('crypto')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Crypto</button>
                    <button onclick="setDashboardTab('stock')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Stocks</button>
                </div>
                ` : ''}
            </div>
            
            <div class="space-y-stack-gap">
                ${filteredHistory.length === 0 ? `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No trade history</p>
                    </div>
                ` : historyToRender.map(t => {
                        const cleanSymbol = t.symbol ? t.symbol.split('/')[0].split(':')[0] : 'Unknown';
                        const sideEmoji = (t.side === 'l' || t.side === 'buy') ? '📈' : '📉';
                        const dateStr = timeAgo(t.timestamp);
                        
                        const pnlVal = t.roe_val || t.roe_pct || t.pnl_pct || 0;
                        const pnlColor = pnlVal >= 0 ? 'text-tertiary' : 'text-error';
                        const pnlPctStr = pnlVal > 0 ? `+${pnlVal.toFixed(2)}%` : `${pnlVal.toFixed(2)}%`;
                        
                        const dollarStr = (t.net_pnl || 0) >= 0 ? `+$${Math.abs(t.net_pnl || 0).toFixed(2)}` : `-$${Math.abs(t.net_pnl || 0).toFixed(2)}`;
                        
                        const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                        const inlineBlur = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(14px)\'"' : '';
                        
                        const assetIcon = t.type === 'stock' ? '🦙' : '🪙';
                        
                        // We do not have open time for crypto cache currently, so only display closed time
                        // If open_time was added in the future, we could subtract it.
                        let openDurationStr = "";
                        if (t.open_time && t.timestamp) {
                            const openTsMs = t.open_time > 1000000000000 ? t.open_time : t.open_time * 1000;
                            const closeTsMs = t.timestamp > 1000000000000 ? t.timestamp : t.timestamp * 1000;
                            const durSec = Math.floor((closeTsMs - openTsMs) / 1000);
                            if (durSec > 0) {
                                const dh = Math.floor(durSec / 3600);
                                const dm = Math.floor((durSec % 3600) / 60);
                                openDurationStr = ` • Open ${dh > 0 ? dh + 'h ' : ''}${dm}m`;
                            }
                        }

                        return `
                            <div class="glass-card p-4 rounded-lg flex justify-between items-center border border-white/5">
                                <div class="flex items-center gap-3">
                                    <div class="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-xl">
                                        ${sideEmoji}
                                    </div>
                                    <div>
                                        <p class="font-label-md text-label-md font-bold text-on-surface">${cleanSymbol}</p>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant">${dateStr}${openDurationStr}</p>
                                    </div>
                                </div>
                                <div class="flex items-center gap-2">
                                    <button onclick="event.stopPropagation(); window.shareTradeCard('${t.type}', '${t.symbol}', '${t.side}', ${pnlVal}, ${t.entry_price || 0}, ${t.close_price || t.price || 0}, ${t.net_pnl || 0})" class="px-2.5 h-8 bg-surface-container border border-white/10 text-on-surface font-bold text-xs uppercase rounded-lg hover:bg-white/5 hover:border-primary/30 transition-all cursor-pointer flex items-center justify-center gap-1.5 mr-2" title="Share Trade Card">
                                        Share & Earn
                                    </button>
                                    <div class="text-right flex flex-col items-end">
                                        <p class="font-numeric-data text-numeric-data font-bold ${pnlColor}">
                                            ${pnlPctStr}
                                        </p>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant" ${inlineBlur}>
                                            ${dollarStr}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                    
                    ${hasMoreHistory ? `
                        <button onclick="loadMoreHistory()" class="w-full py-3 mt-4 glass-card rounded-lg font-label-md text-on-surface-variant hover:text-on-surface hover:bg-white/5 transition-colors text-center border border-white/5">
                            Load More
                        </button>
                    ` : ''}
            </div>
        </main>
    `;
}

function getFreeStatsHtml(showHeader = false) {
    if (!STATE.free_stats || !STATE.free_stats.strategies) {
        return `<div class="text-center p-8 text-on-surface-variant">Loading stats...</div>`;
    }

    const isDesktop = window.innerWidth >= 1024; // lg breakpoint

    let strategiesHtml = STATE.free_stats.strategies.map(s => {
        const icon = STRATEGY_ICONS[s.name] || "📈";
        const guideId = `guide-${s.name.replace(/\s+/g, '-')}`;
        
        const realizedClass = s.realized_pct >= 0 ? "text-tertiary" : "text-error";
        const unrealizedClass = (s.unrealized_pct || 0) >= 0 ? "text-tertiary" : "text-error";

        const hiddenClass = isDesktop ? '' : 'hidden';
        const initialRotation = isDesktop ? 'rotate(180deg)' : 'rotate(0deg)';

        return `
            <div class="glass-card rounded-xl p-4 space-y-2 border-l-4 border-primary/50 transition-all duration-300 text-left h-full flex flex-col">
                <div class="flex justify-between items-center cursor-pointer group" onclick="document.getElementById('${guideId}').classList.toggle('hidden'); const chev = document.getElementById('chev-${guideId}'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                    <h3 class="font-headline-sm text-on-surface flex items-center gap-2 group-hover:text-primary transition-colors">
                        <span>${icon}</span> ${s.name}
                    </h3>
                    <span id="chev-${guideId}" class="material-symbols-outlined text-on-surface-variant transition-transform duration-300" style="transform: ${initialRotation}">expand_more</span>
                </div>
                <div class="text-sm space-y-1">
                    <p class="text-on-surface-variant">• Win Rate: <span class="text-primary font-medium">${s.win_rate.toFixed(1)}%</span> (${s.wins} W | ${s.losses} L)</p>
                    <p class="text-on-surface-variant">• Realized PnL: <span class="${realizedClass} font-medium">${s.realized_pct > 0 ? '+' : ''}${s.realized_pct.toFixed(2)}%</span></p>
                    ${s.active_count > 0 ? `<p class="text-on-surface-variant">• Unrealized PnL: <span class="${unrealizedClass} font-medium">${(s.unrealized_pct || 0) > 0 ? '+' : ''}${(s.unrealized_pct || 0).toFixed(2)}%</span></p>` : ''}
                    <p class="text-on-surface-variant">• Active Signals: <span class="text-primary font-medium">${s.active_count}</span></p>
                </div>
                <div class="pt-2 space-y-2">
                    <button onclick="window.shareStatsCard('free', '${s.name}')" class="w-full h-9 bg-surface-container border border-white/10 text-on-surface font-bold text-xs uppercase rounded-lg hover:bg-white/5 hover:border-primary/30 transition-all flex items-center justify-center gap-1.5 cursor-pointer">
                        <span class="material-symbols-outlined text-[14px]">share</span>
                        Share & Earn
                    </button>
                    <button onclick="resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('${s.name}'); triggerBacktest(); }, 150);" class="w-full h-9 bg-surface-container border border-white/10 text-on-surface font-bold text-xs uppercase rounded-lg hover:bg-white/5 transition-all flex items-center justify-center gap-1.5 cursor-pointer">
                        <span class="material-symbols-outlined text-[14px]">science</span>
                        Backtest
                    </button>
                </div>
                
                <div id="${guideId}" class="${hiddenClass} pt-4 mt-auto border-t border-white/5 space-y-4 animate-fade-in flex-grow">
                    ${renderStrategyGuideContent(s.name, false)}
                </div>
            </div>
        `;
    }).join('');

    return `
        ${showHeader ? `
        <div class="flex items-center gap-3 mt-4 mb-4 text-left">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🧪 Forward Testing Stats</h2>
        </div>
        ` : ''}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 w-full">
            ${strategiesHtml}
        </div>
    `;
}

function renderFreeStatsView(showPremiumBanner = false) {
    if (!STATE.free_stats) return `${renderHeader()}<main class="pt-20 px-container-margin"><div class="text-center p-8 text-on-surface-variant">Loading stats...</div></main>`;

    const premiumBanner = (showPremiumBanner && !STATE.hide_stats_warning) ? `
        <div class="glass-card rounded-xl p-card-padding border border-primary/20 bg-primary/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-2">
            <div class="space-y-1">
                <h3 class="font-body-lg text-body-lg font-bold text-primary flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary">info</span> Live Stats Pending
                </h3>
                <p class="text-xs text-on-surface-variant leading-relaxed max-w-[400px]">
                    Your live portfolio performance will appear here once you connect your exchange API keys. Until then, you can view the forward-tested strategy performance below.
                </p>
            </div>
            <div class="flex items-center gap-2">
                <a href="#/settings" class="shrink-0 h-10 px-5 inline-flex items-center justify-center bg-primary/20 border border-primary/50 text-primary font-bold text-xs tracking-wider rounded-lg hover:bg-primary hover:text-on-primary transition-colors">
                    CONNECT
                </a>
                <button onclick="STATE.hide_stats_warning = true; renderView();" class="text-primary/70 hover:text-primary transition-colors w-8 h-8 flex items-center justify-center rounded-full hover:bg-primary/10 shrink-0" title="Hide">
                    <span class="material-symbols-outlined text-[20px]">close</span>
                </button>
            </div>
        </div>
    ` : '';

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] md:max-w-5xl mx-auto">
            ${premiumBanner}
            ${getFreeStatsHtml(true)}
        </main>
    `;
}

function renderStatsView() {
    if (!STATE.user || !STATE.user.is_premium) {
        return renderFreeStatsView();
    }
    
    const hasLinkedKeys = STATE.user.has_exchange_keys || STATE.user.has_alpaca_keys;
    if (!hasLinkedKeys) {
        return renderFreeStatsView(true);
    }
    
    const showLoadingStats = !STATE.stats;
    
    const s = STATE.stats || {
        crypto: { portfolio_value: 0.0, overall_pnl: 0.0, overall_pnl_pct: 0.0, wins: 0, losses: 0, total_trades: 0, win_rate: 0.0, open_positions: 0, unrealized_pnl: 0.0 },
        stock: { portfolio_value: 0.0, overall_pnl: 0.0, overall_pnl_pct: 0.0, wins: 0, losses: 0, total_trades: 0, win_rate: 0.0, open_positions: 0, unrealized_pnl: 0.0, closed_trades: 0 }
    };
    
    const crypto = s.crypto || { portfolio_value: 0.0, overall_pnl: 0.0, overall_pnl_pct: 0.0, wins: 0, losses: 0, total_trades: 0, win_rate: 0.0, open_positions: 0, unrealized_pnl: 0.0 };
    const stock = s.stock || { portfolio_value: 0.0, overall_pnl: 0.0, overall_pnl_pct: 0.0, wins: 0, losses: 0, total_trades: 0, win_rate: 0.0, open_positions: 0, unrealized_pnl: 0.0, closed_trades: 0 };
    
    if (crypto.unrealized_pnl_pct === undefined) {
        crypto.unrealized_pnl_pct = crypto.portfolio_value > 0 ? (crypto.unrealized_pnl / crypto.portfolio_value) * 100 : 0;
    }
    if (stock.unrealized_pnl_pct === undefined) {
        stock.unrealized_pnl_pct = stock.portfolio_value > 0 ? (stock.unrealized_pnl / stock.portfolio_value) * 100 : 0;
    }
    
    const cryptoNetPnl = crypto.overall_pnl + crypto.unrealized_pnl;
    const stockNetPnl = stock.overall_pnl + stock.unrealized_pnl;
    
    const cryptoNetPnlPct = crypto.overall_pnl_pct + crypto.unrealized_pnl_pct;
    const stockNetPnlPct = stock.overall_pnl_pct + stock.unrealized_pnl_pct;
    
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const inlineBlur = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(14px)\'"' : '';
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] md:max-w-5xl mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">📊 Institutional Performance</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Crypto Performance Section -->
                <section class="glass-card rounded-xl p-card-padding border-t-2 border-primary/40 space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="font-bold text-on-surface flex items-center gap-2">🪙 Crypto Performance</h3>
                    <span class="text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary font-bold capitalize">${(STATE.user && STATE.user.has_exchange_keys && STATE.user.exchange_id) ? STATE.user.exchange_id : 'Live API'}</span>
                </div>
                
                <div class="grid grid-cols-3 gap-2 text-center" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Portf Value</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-primary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1" ${inlineBlur}>$${crypto.portfolio_value.toFixed(2)}</p>
                        <p class="text-[10px] mt-0.5">&nbsp;</p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Win Rate</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-tertiary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-tertiary mt-1">${crypto.win_rate.toFixed(1)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5">(${crypto.wins}W / ${crypto.losses}L)</p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Cum PnL</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-primary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold ${crypto.overall_pnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${crypto.overall_pnl_pct >= 0 ? '+' : ''}${crypto.overall_pnl_pct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${crypto.overall_pnl >= 0 ? '+' : ''}$${crypto.overall_pnl.toFixed(2)})</p>
                        `}
                    </div>
                </div>
                
                ${(crypto.open_positions > 0 && !showLoadingStats) ? `
                <div class="grid grid-cols-3 gap-2 text-center mt-2" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider"># Open</p>
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='crypto'; STATE.trades_mode='active';" class="hover:text-primary transition-colors">${crypto.open_positions}</a>
                        </p>
                        <p class="text-[10px] mt-0.5">&nbsp;</p>
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Unrealized PnL</p>
                        <p class="text-sm font-bold ${crypto.unrealized_pnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${crypto.unrealized_pnl_pct >= 0 ? '+' : ''}${crypto.unrealized_pnl_pct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${crypto.unrealized_pnl >= 0 ? '+' : ''}$${crypto.unrealized_pnl.toFixed(2)})</p>
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Net PnL</p>
                        <p class="text-sm font-bold ${cryptoNetPnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${cryptoNetPnlPct >= 0 ? '+' : ''}${cryptoNetPnlPct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${cryptoNetPnl >= 0 ? '+' : ''}$${cryptoNetPnl.toFixed(2)})</p>
                    </div>
                </div>
                ` : `
                <div class="grid grid-cols-2 gap-2 text-center mt-2" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[58px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Open Trades</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1 animate-pulse mt-0.5">
                            <span class="material-symbols-outlined text-primary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='crypto'; STATE.trades_mode='active';" class="hover:text-primary transition-colors">0</a>
                        </p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[58px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Closed Trades</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1 animate-pulse mt-0.5">
                            <span class="material-symbols-outlined text-primary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='crypto'; STATE.trades_mode='closed';" class="hover:text-primary transition-colors">${crypto.wins + crypto.losses}</a>
                        </p>
                        `}
                    </div>
                </div>
                `}
            </section>
            
            <!-- Stocks Performance Section -->
            <section class="glass-card rounded-xl p-card-padding border-t-2 border-secondary-container/40 space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="font-bold text-on-surface flex items-center gap-2">🦙 Stocks Performance</h3>
                    <span class="text-xs px-2.5 py-1 rounded-full bg-secondary-container/10 text-secondary-container font-bold">Alpaca Live</span>
                </div>
                
                <div class="grid grid-cols-3 gap-2 text-center" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Portf Value</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-primary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1" ${inlineBlur}>$${stock.portfolio_value.toFixed(2)}</p>
                        <p class="text-[10px] mt-0.5">&nbsp;</p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Win Rate</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-tertiary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-tertiary mt-1">${stock.win_rate.toFixed(1)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5">(${stock.wins}W / ${stock.losses}L)</p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[72px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Cum PnL</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1.5 animate-pulse mt-1">
                            <span class="material-symbols-outlined text-primary text-lg animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold ${stock.overall_pnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${stock.overall_pnl_pct >= 0 ? '+' : ''}${stock.overall_pnl_pct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${stock.overall_pnl >= 0 ? '+' : ''}$${stock.overall_pnl.toFixed(2)})</p>
                        `}
                    </div>
                </div>
                
                ${(stock.open_positions > 0 && !showLoadingStats) ? `
                <div class="grid grid-cols-3 gap-2 text-center mt-2" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider"># Open</p>
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='stock'; STATE.trades_mode='active';" class="hover:text-primary transition-colors">${stock.open_positions}</a>
                        </p>
                        <p class="text-[10px] mt-0.5">&nbsp;</p>
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Unrealized PnL</p>
                        <p class="text-sm font-bold ${stock.unrealized_pnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${stock.unrealized_pnl_pct >= 0 ? '+' : ''}${stock.unrealized_pnl_pct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${stock.unrealized_pnl >= 0 ? '+' : ''}$${stock.unrealized_pnl.toFixed(2)})</p>
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Net PnL</p>
                        <p class="text-sm font-bold ${stockNetPnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">${stockNetPnlPct >= 0 ? '+' : ''}${stockNetPnlPct.toFixed(2)}%</p>
                        <p class="text-[10px] font-normal text-on-surface-variant mt-0.5" ${inlineBlur}>(${stockNetPnl >= 0 ? '+' : ''}$${stockNetPnl.toFixed(2)})</p>
                    </div>
                </div>
                ` : `
                <div class="grid grid-cols-2 gap-2 text-center mt-2" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[58px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Open Trades</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1 animate-pulse mt-0.5">
                            <span class="material-symbols-outlined text-primary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='stock'; STATE.trades_mode='active';" class="hover:text-primary transition-colors">0</a>
                        </p>
                        `}
                    </div>
                    <div class="bg-surface-container rounded-lg p-2 flex flex-col justify-center min-h-[58px]">
                        <p class="text-[10px] text-on-surface-variant uppercase tracking-wider">Closed Trades</p>
                        ${showLoadingStats ? `
                        <div class="flex items-center justify-center py-1 animate-pulse mt-0.5">
                            <span class="material-symbols-outlined text-primary text-sm animate-spin">sync</span>
                        </div>
                        ` : `
                        <p class="text-sm font-bold text-on-surface mt-1">
                            <a href="#/trades" onclick="STATE.dashboard_tab='stock'; STATE.trades_mode='closed';" class="hover:text-primary transition-colors">${stock.wins + stock.losses}</a>
                        </p>
                        `}
                    </div>
                </div>
                `}
            </section>
            </div>
        </main>
    `;
}
function renderSettingsView() {
    const user = STATE.user || {};
    const isActive = user.is_active;
    const isPremium = user.is_premium;
    // Check if the user is linked
    const isTelegramLinked = !!user.telegram_chat_id;
    const isSuperAdmin = user.telegram_chat_id === 1567788633;
    const isAdmin = !!(user.is_admin || isSuperAdmin);
    
    const hasLinkedCrypto = !!user.has_exchange_keys;
    const hasLinkedStock = !!user.has_alpaca_keys;
    
    // Parse expiration details
    let expiryText = 'Not Premium';
    if (isAdmin) {
        expiryText = 'Lifetime Active (Admin)';
    } else if (isPremium && user.premium_expiry) {
        expiryText = `Expires: ${new Date(user.premium_expiry * 1000).toLocaleDateString()}`;
    } else if (isPremium) {
        expiryText = 'Lifetime Active';
    }
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 max-w-[500px] lg:max-w-5xl mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface mb-6">⚙️ Settings</h2>
            
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-section-gap items-start">

                <!-- LEFT COLUMN -->
                <div class="space-y-section-gap flex flex-col">
                    <!-- Premium Status & Renew Option -->
            <section class="glass-card rounded-xl p-card-padding flex items-center justify-between border border-white/10">
                <div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface flex items-center gap-2">
                        <span class="material-symbols-outlined text-secondary-container">diamond</span> Premium Membership
                    </h3>
                    <p class="text-xs text-on-surface-variant mt-1">${expiryText}</p>
                </div>
                ${isPremium ? (isAdmin ? '' : `
                    <button onclick="showRenewModal()" class="px-4 py-2 bg-secondary-container text-on-secondary-container rounded-lg font-bold hover:brightness-110 transition-all text-xs flex items-center gap-1 shadow-[0_0_8px_rgba(212,175,55,0.3)]">
                        <span class="material-symbols-outlined text-[14px]">autorenew</span> Renew
                    </button>
                `) : `
                    <a href="#/premium" class="px-4 py-2 bg-secondary-container text-on-secondary-container rounded-lg font-bold hover:brightness-110 transition-all text-xs">
                        Upgrade
                    </a>
                `}
            </section>

            ${isPremium ? `
            <section class="glass-card rounded-xl p-card-padding border border-white/10 animate-fade-in">
                <details class="group" ${window.innerWidth >= 1024 ? 'open' : ''}>
                    <summary class="font-body-lg text-body-lg font-bold text-on-surface flex justify-between items-center cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none">
                        <div class="flex items-center gap-2">
                            🔌 Connected Exchanges
                        </div>
                        <span class="material-symbols-outlined transition-transform duration-300 group-open:rotate-180 text-on-surface-variant">expand_more</span>
                    </summary>
                    <div class="space-y-4 mt-4">
                        ${hasLinkedCrypto ? `
                        <form class="bg-surface-container-low p-4 rounded-xl border border-white/5 space-y-3" onsubmit="event.preventDefault()">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-sm text-on-surface flex items-center gap-1.5">
                                    🪙 Crypto: <span class="capitalize text-primary font-mono">${user.exchange_id || 'Blofin'}${user.exchange_id === 'bingx' ? ' (Perpetual Futures)' : ''} ${STATE.crypto_auth_success ? '<span title="Successfully Authenticated" class="cursor-help">✅</span>' : ''}</span>
                                </span>
                                <div class="flex items-center gap-2">
                                    <button onclick="testExchangeConnection('crypto', this)" class="text-xs text-primary font-bold hover:underline flex items-center gap-1 cursor-pointer">
                                        <span class="material-symbols-outlined text-[14px]">wifi_tethering</span>Test
                                    </button>
                                    <button onclick="deleteExchange('crypto')" class="text-xs text-[#ef4444] font-bold hover:underline flex items-center gap-1 cursor-pointer">
                                        <span class="material-symbols-outlined text-[14px]">delete</span>Delete
                                    </button>
                                </div>
                            </div>
                            <div class="space-y-2 text-xs">
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">API Key:</span>
                                    <div class="flex items-center gap-2">
                                        <input type="password" value="${user.api_key || (user.has_exchange_keys ? '••••••••••••' : '')}" readonly autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-right text-on-surface font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" id="crypto-key-display"/>
                                    </div>
                                </div>
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">API Secret:</span>
                                    <div class="flex items-center gap-2">
                                        <input type="password" value="${user.api_secret || (user.has_exchange_keys ? '••••••••••••' : '')}" readonly autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-right text-on-surface font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" id="crypto-secret-display"/>
                                    </div>
                                </div>
                                ${user.has_exchange_keys && !['coinbase'].includes(user.exchange_id) ? `
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">Passphrase:</span>
                                    <div class="flex items-center gap-2">
                                        <input type="password" value="${user.api_password || (user.has_exchange_keys ? '••••••••••••' : '')}" readonly autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-right text-on-surface font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" id="crypto-pass-display"/>
                                    </div>
                                </div>
                                ` : ''}
                            </div>
                        </form>
                        ` : ''}
                        
                        ${hasLinkedStock ? `
                        <form class="bg-surface-container-low p-4 rounded-xl border border-white/5 space-y-3" onsubmit="event.preventDefault()">
                            <div class="flex justify-between items-center">
                                <span class="font-bold text-sm text-on-surface flex items-center gap-1.5">
                                    🦙 Stocks: <span class="text-primary font-mono">Alpaca</span>
                                </span>
                                <button onclick="deleteExchange('stock')" class="text-xs text-[#ef4444] font-bold hover:underline flex items-center gap-1 cursor-pointer">
                                    <span class="material-symbols-outlined text-[14px]">delete</span>Delete
                                </button>
                            </div>
                            <div class="space-y-2 text-xs">
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">API Key:</span>
                                    <div class="flex items-center gap-2">
                                        <input type="password" value="${user.alpaca_api_key || (user.has_alpaca_keys ? '••••••••••••' : '')}" readonly autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-right text-on-surface font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" id="stock-key-display"/>
                                    </div>
                                </div>
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">API Secret:</span>
                                    <div class="flex items-center gap-2">
                                        <input type="password" value="${user.alpaca_api_secret || (user.has_alpaca_keys ? '••••••••••••' : '')}" readonly autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-right text-on-surface font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" id="stock-secret-display"/>
                                    </div>
                                </div>
                                <div class="flex justify-between items-center gap-2">
                                    <span class="text-on-surface-variant">Endpoint URL:</span>
                                    <span class="text-on-surface font-mono text-xs">${user.alpaca_endpoint || 'https://api.alpaca.markets'}</span>
                                </div>
                            </div>
                        </form>
                        ` : ''}

                        ${!hasLinkedCrypto && !hasLinkedStock ? `
                        <div class="bg-surface-container-low p-4 rounded-xl border border-white/5 text-xs text-on-surface-variant leading-relaxed">
                            No exchanges connected. Connect your Crypto Exchange or Alpaca Stocks API credentials below to unlock autonomous copy-trading.
                        </div>
                        ` : ''}

                        <!-- Connect Exchange Wizard Form (if both are not connected) -->
                        ${(!hasLinkedCrypto || !hasLinkedStock) ? `
                        <div id="exchange-wizard-container" class="pt-4 border-t border-white/10 space-y-4 animate-fade-in">
                            <h4 class="font-body-md text-body-md font-bold text-on-surface">
                                🔌 Connect ${(!hasLinkedCrypto && !hasLinkedStock) ? 'Exchange' : (hasLinkedCrypto ? 'Stocks Platform' : 'Crypto Exchange')}
                            </h4>
                            <div class="space-y-2">
                                <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Select Platform</label>
                                <details class="relative w-full group z-50" id="exchange-dropdown-details">
                                    <summary class="w-full h-11 bg-surface-container-low text-on-surface text-base border border-white/10 rounded-lg px-4 flex items-center justify-between cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                                        <span id="exchange-select-label">${!hasLinkedCrypto ? 'Blofin' : 'Alpaca Stocks'}</span>
                                        <span class="material-symbols-outlined text-on-surface-variant group-open:rotate-180 transition-transform">expand_more</span>
                                    </summary>
                                    <div class="absolute top-full left-0 right-0 mt-1 bg-surface-container-high border border-white/10 rounded-lg shadow-xl z-50 overflow-hidden">
                                        <div class="p-1 max-h-64 overflow-y-auto">
                                            ${!hasLinkedCrypto ? `
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('blofin', 'Blofin')">Blofin</div>
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('binance', 'Binance')">Binance</div>
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('mexc', 'MEXC')">MEXC</div>
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('bitget', 'Bitget')">Bitget</div>
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('bingx', 'BingX')">BingX</div>
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('coinbase', 'Coinbase Advanced (CDP keys)')">Coinbase Advanced (CDP keys)</div>
                                            ` : ''}
                                            ${!hasLinkedStock ? `
                                            <div class="px-4 py-3 hover:bg-white/10 cursor-pointer text-sm text-on-surface rounded transition-colors" onclick="window.selectExchange('alpaca', 'Alpaca Stocks')">Alpaca Stocks</div>
                                            ` : ''}
                                        </div>
                                    </div>
                                </details>
                                <input type="hidden" id="exchange-id" value="${!hasLinkedCrypto ? 'blofin' : 'alpaca'}">
                            </div>
                            <form onsubmit="handleExchangeSetup(event)" class="space-y-3" autocomplete="off">
                                <div class="space-y-1">
                                    <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">API Key</label>
                                    <input id="api-key" autocomplete="new-password" data-lpignore="true" data-1p-ignore data-bwignore class="w-full h-11 bg-surface-container-low text-on-surface text-base border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" placeholder="API Key" type="text" required/>
                                </div>
                                <div class="space-y-1">
                                    <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">API Secret</label>
                                    <input id="api-secret" autocomplete="new-password" data-lpignore="true" data-1p-ignore data-bwignore class="w-full h-11 bg-surface-container-low text-on-surface text-base border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" placeholder="API Secret" type="password" required/>
                                </div>
                                <div id="pwd-field-container" class="space-y-1">
                                    <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Passphrase</label>
                                    <input id="api-password" autocomplete="new-password" data-lpignore="true" data-1p-ignore data-bwignore class="w-full h-11 bg-surface-container-low text-on-surface text-base border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" placeholder="Passphrase" type="password"/>
                                </div>
                                <div id="bingx-futures-field-container" class="p-3 bg-primary/10 rounded-lg border border-primary/20 text-xs text-on-surface-variant space-y-1 hidden">
                                    <span class="font-bold text-primary flex items-center gap-1">
                                        <span class="material-symbols-outlined text-sm">info</span> BingX Requirement
                                    </span>
                                    <p>Metaverse Sherpa connects to BingX using <strong>Perpetual Futures</strong>. Please make sure your API key has <strong>Read</strong> and <strong>Perpetual Futures Trading</strong> permissions enabled, and your funds are in your Perpetual Futures account.</p>
                                </div>
                                <div id="coinbase-advanced-field-container" class="p-3 bg-primary/10 rounded-lg border border-primary/20 text-xs text-on-surface-variant space-y-1 hidden">
                                    <span class="font-bold text-primary flex items-center gap-1">
                                        <span class="material-symbols-outlined text-sm">info</span> Coinbase Advanced Key Format
                                    </span>
                                    <p>Your API Key must be the <strong>full resource name</strong> provided by Coinbase, formatted like: <code>organizations/{org_id}/apiKeys/{key_id}</code>. If you downloaded the JSON file, copy the full <code>name</code> property for the API Key.</p>
                                </div>
                                <div id="endpoint-field-container" class="space-y-1 hidden">
                                    <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Endpoint URL</label>
                                    <input id="alpaca-endpoint" autocomplete="off" data-lpignore="true" data-1p-ignore data-bwignore class="w-full h-11 bg-surface-container-low text-on-surface text-base border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" placeholder="https://api.alpaca.markets" type="text" value="https://api.alpaca.markets"/>
                                </div>
                                <div id="coinbase-sandbox-field-container" class="flex items-center gap-2 p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg hidden">
                                    <input id="coinbase-sandbox" type="checkbox" class="w-4 h-4 rounded border-white/10 accent-primary cursor-pointer"/>
                                    <label for="coinbase-sandbox" class="text-xs text-amber-300 cursor-pointer select-none">⚠️ Use Sandbox/Testnet Environment (disable for live trading)</label>
                                </div>
                                <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg hover:brightness-110 transition-all mt-2 cursor-pointer">
                                    Save Keys
                                </button>
                            </form>
                        </div>
                        ` : ''}
                    </div>
                </details>
            </section>
            ` : ''}
                    <!-- Bot Status Panel (Gated to Premium Users Only) -->
            ${isPremium && (hasLinkedCrypto || hasLinkedStock) ? `
            <section class="glass-card rounded-xl p-card-padding flex items-center justify-between border-t-2 ${isActive ? 'border-tertiary/40' : 'border-error/40'}">
                <div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Autopilot Status</h3>
                    <p class="text-xs text-on-surface-variant mt-1">${isActive ? 'Active and executing signals' : 'Paused'}</p>
                </div>
                <button onclick="toggleBotStatus(${isActive})" class="px-4 py-2 rounded-lg font-bold transition-all ${
                    isActive ? 'bg-error/20 text-error border border-error/55' : 'bg-tertiary/20 text-tertiary border border-tertiary/55'
                }">
                    ${isActive ? 'STOP BOT' : 'START BOT'}
                </button>
            </section>
            ` : ''}

                    <!-- Telegram Sync -->
            <section class="glass-card rounded-xl p-card-padding space-y-4">
                <div class="flex justify-between items-center">
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">📱 Telegram Sync</h3>
                    ${isTelegramLinked && !STATE.editing_telegram ? `
                        <button onclick="STATE.editing_telegram = true; renderView();" class="text-xs text-primary font-bold hover:underline flex items-center gap-1 cursor-pointer">
                            <span class="material-symbols-outlined text-[14px]">edit</span>Edit
                        </button>
                    ` : ''}
                </div>
                ${isTelegramLinked && !STATE.editing_telegram ? `
                    <div class="flex items-center gap-3 bg-tertiary/10 p-3 rounded-lg border border-tertiary/20">
                        <span class="material-symbols-outlined text-tertiary text-2xl">check_circle</span>
                        <div>
                            <p class="text-xs text-on-surface-variant uppercase tracking-wider">Status</p>
                            <p class="text-sm font-bold text-on-surface">Telegram Linked Successfully</p>
                            <p class="text-xs text-on-surface-variant mt-0.5">Chat ID: ${user.telegram_chat_id}</p>
                        </div>
                    </div>
                ` : `
                    <p class="text-xs text-on-surface-variant leading-relaxed">Sync your web account with the <a href="https://t.me/metaversesherpa_trading_bot" target="_blank" class="text-primary hover:underline">Telegram bot</a> to receive live signals and portfolio updates. Send /start to the bot to get your Chat ID.</p>
                    <form onsubmit="handleTelegramSetup(event)" class="space-y-3">
                        <input id="telegram-chat-id" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" placeholder="Telegram Chat ID (e.g. 123456789)" type="text" value="${user.telegram_chat_id || ''}" required/>
                        <button type="submit" class="w-full h-11 bg-secondary-container text-on-secondary-container font-label-md text-label-md font-bold rounded-lg hover:brightness-110 transition-all mt-2 cursor-pointer">
                            ${isTelegramLinked ? 'Update Telegram Link' : 'Link Telegram'}
                        </button>
                    </form>
                `}
            </section>

                    <!-- Premium Plan & Referral Buttons -->
            <section class="grid grid-cols-2 gap-stack-gap">
                ${!isPremium ? `
                <a href="#/premium" class="glass-card rounded-lg p-4 flex flex-col items-center gap-2 hover:bg-white/5 transition-colors text-center">
                    <span class="material-symbols-outlined text-secondary-container text-2xl">diamond</span>
                    <span class="text-xs font-semibold text-on-surface">Premium Plan</span>
                </a>
                ` : `
                <div class="glass-card rounded-lg p-4 flex flex-col items-center gap-2 text-center opacity-50">
                    <span class="material-symbols-outlined text-secondary-container text-2xl">check_circle</span>
                    <span class="text-xs font-semibold text-on-surface">Active Premium</span>
                </div>
                `}
                <a href="#/referral" class="glass-card rounded-lg p-4 flex flex-col items-center gap-2 hover:bg-white/5 transition-colors text-center">
                    <span class="material-symbols-outlined text-tertiary text-2xl">diversity_3</span>
                    <span class="text-xs font-semibold text-on-surface">Refer & Earn</span>
                </a>
            </section>

                    <!-- Email Notifications Setting -->
            <section class="glass-card rounded-xl p-card-padding space-y-4">
                <div class="flex justify-between items-center">
                    <div>
                        <h3 class="font-body-lg text-body-lg font-bold text-on-surface">📧 Email Alerts</h3>
                        <p class="text-xs text-on-surface-variant mt-1">Receive signals & trade alerts via email</p>
                    </div>
                    <button onclick="toggleEmailNotifications()" class="px-4 py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition-all cursor-pointer ${
                        (user.email_notifications !== 0) ? 'bg-primary/20 text-primary border border-primary/55' : 'bg-surface-container-high text-on-surface border border-white/10'
                    }">
                        ${(user.email_notifications !== 0) ? 'Enabled 🔔' : 'Disabled 🔕'}
                    </button>
                </div>
                
                ${(user.email_notifications !== 0) ? `
                <div class="space-y-2 pt-2 border-t border-white/5 animate-fade-in">
                    <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Email Alert Frequency</label>
                    <div class="grid grid-cols-2 gap-2">
                        <button onclick="setEmailFrequency('realtime')" class="h-10 rounded-lg text-xs font-bold transition-all border ${
                            (user.email_frequency !== 'daily') ? 'bg-primary/20 text-primary border-primary/55' : 'bg-surface-container-low text-on-surface-variant border-white/10 hover:bg-white/5'
                        }">
                            Real-time
                        </button>
                        <button onclick="setEmailFrequency('daily')" class="h-10 rounded-lg text-xs font-bold transition-all border ${
                            (user.email_frequency === 'daily') ? 'bg-primary/20 text-primary border-primary/55' : 'bg-surface-container-low text-on-surface-variant border-white/10 hover:bg-white/5'
                        }">
                            Daily Summary
                        </button>
                    </div>
                </div>
                ` : ''}
            </section>

                    <!-- Browser Notifications Setting -->
            <section class="glass-card rounded-xl p-card-padding flex items-center justify-between border-t-2 border-secondary-container/40">
                <div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">🖥️ Browser Notifications</h3>
                    <p class="text-xs text-on-surface-variant mt-1">Receive native desktop popups for signal alerts</p>
                </div>
                <button onclick="toggleBrowserNotifications()" class="px-4 py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition-all cursor-pointer ${
                    (user.browser_notifications !== 0) ? 'bg-primary/20 text-primary border border-primary/55' : 'bg-surface-container-high text-on-surface border border-white/10'
                }">
                    ${(user.browser_notifications !== 0) ? 'Notifications On 🔔' : 'Notifications Off 🔕'}
                </button>
            </section>

                </div>


                <!-- RIGHT COLUMN -->
                <div class="space-y-section-gap flex flex-col">


                    <!-- Privacy Mode Setting -->
            <section class="glass-card rounded-xl p-card-padding flex items-center justify-between border-t-2 border-primary/40">
                <div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Privacy Mode</h3>
                    <p class="text-xs text-on-surface-variant mt-1">🔒 Hide Dollar PnL amounts across the app</p>
                </div>
                <button onclick="togglePrivacySetting()" class="px-4 py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition-all cursor-pointer ${
                    (user.hide_dollars !== false) ? 'bg-primary/20 text-primary border border-primary/55' : 'bg-surface-container-high text-on-surface border border-white/10'
                }">
                    ${(user.hide_dollars !== false) ? 'Privacy On 🔒' : 'Privacy Off 👁️'}
                </button>
            </section>

                    <!-- Algorithmic Strategies Dropdowns -->
            <section class="glass-card rounded-xl p-card-padding space-y-4 relative z-50">
                <h3 class="font-body-lg text-body-lg font-bold text-on-surface">🤖 Algorithmic Strategies</h3>
                <div class="space-y-3">
                    <div class="space-y-1">
                        <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Crypto Strategy</label>
                        <div class="relative">
                            <select onchange="handleStrategyChange('crypto', this.value)" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg pl-4 pr-10 cyan-glow-focus transition-all appearance-none cursor-pointer">
                                ${!(user.disabled_strategies || []).includes('Mean Reversion Scalper') ? `
                                <option value="Mean Reversion Scalper" ${(user.active_crypto_strategy || 'Valkyrie Elite Scalper') === 'Mean Reversion Scalper' ? 'selected' : ''}>Mean Reversion Scalper</option>
                                ` : ''}
                                ${!(user.disabled_strategies || []).includes('Valkyrie Elite Scalper') ? `
                                <option value="Valkyrie Elite Scalper" ${(user.active_crypto_strategy || 'Valkyrie Elite Scalper') === 'Valkyrie Elite Scalper' ? 'selected' : ''}>Valkyrie Elite Scalper</option>
                                ` : ''}
                                <option value="None" ${(user.active_crypto_strategy || 'Valkyrie Elite Scalper') === 'None' ? 'selected' : ''}>None (Disabled)</option>
                            </select>
                            <div class="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant flex items-center justify-center">
                                <span class="material-symbols-outlined text-xl">expand_more</span>
                            </div>
                        </div>
                        ${(user.active_crypto_strategy && user.active_crypto_strategy !== 'None') || (!user.active_crypto_strategy) ? `
                        <div class="pt-1">
                            <div class="flex justify-between items-center cursor-pointer p-2 bg-surface-container/50 border border-white/5 hover:bg-white/5 rounded-lg transition-colors group" onclick="document.getElementById('crypto-guide').classList.toggle('hidden'); const chev = document.getElementById('crypto-chev'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                                <span class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant group-hover:text-primary transition-colors flex items-center gap-1"><span class="material-symbols-outlined text-sm">info</span> View Strategy Details</span>
                                <span id="crypto-chev" class="material-symbols-outlined text-on-surface-variant text-sm transition-transform duration-300">expand_more</span>
                            </div>
                            <div id="crypto-guide" class="hidden pt-3 animate-fade-in text-left">
                                ${renderStrategyGuideContent(user.active_crypto_strategy || 'Valkyrie Elite Scalper', true)}
                            </div>
                        </div>
                        ` : ''}
                    </div>
                    <div class="space-y-1">
                        <label class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider">Stock Strategy</label>
                        <div class="relative">
                            <select onchange="handleStrategyChange('stock', this.value)" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg pl-4 pr-10 cyan-glow-focus transition-all appearance-none cursor-pointer">
                                ${!(user.disabled_strategies || []).includes('Sherpa Velocity Pullback') ? `
                                <option value="Sherpa Velocity Pullback" ${(user.active_stock_strategy || 'Sherpa Velocity Pullback') === 'Sherpa Velocity Pullback' ? 'selected' : ''}>Sherpa Velocity Pullback</option>
                                ` : ''}
                                <option value="None" ${(user.active_stock_strategy || 'Sherpa Velocity Pullback') === 'None' ? 'selected' : ''}>None (Disabled)</option>
                            </select>
                            <div class="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant flex items-center justify-center">
                                <span class="material-symbols-outlined text-xl">expand_more</span>
                            </div>
                        </div>
                        ${(user.active_stock_strategy && user.active_stock_strategy !== 'None') || (!user.active_stock_strategy) ? `
                        <div class="pt-1">
                            <div class="flex justify-between items-center cursor-pointer p-2 bg-surface-container/50 border border-white/5 hover:bg-white/5 rounded-lg transition-colors group" onclick="document.getElementById('stock-guide').classList.toggle('hidden'); const chev = document.getElementById('stock-chev'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                                <span class="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant group-hover:text-primary transition-colors flex items-center gap-1"><span class="material-symbols-outlined text-sm">info</span> View Strategy Details</span>
                                <span id="stock-chev" class="material-symbols-outlined text-on-surface-variant text-sm transition-transform duration-300">expand_more</span>
                            </div>
                            <div id="stock-guide" class="hidden pt-3 animate-fade-in text-left">
                                ${renderStrategyGuideContent(user.active_stock_strategy || 'Sherpa Velocity Pullback', true)}
                            </div>
                        </div>
                        ` : ''}
                    </div>
                    
                    <!-- Risk Sizing Settings (Moved into Strategies) -->
                    <div class="space-y-4 pt-4 mt-2 border-t border-white/10">
                        <h4 class="font-bold text-sm text-on-surface">⚖️ Risk & Sizing</h4>
                        <div class="space-y-4">
                            <div class="space-y-2">
                                <div class="flex justify-between text-sm">
                                    <span class="text-on-surface-variant">Crypto Risk per Trade</span>
                                    <span id="risk-val" class="text-primary font-bold">${user.risk_pct || '1.5'}%</span>
                                </div>
                                <input id="risk-slider" class="w-full accent-primary bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" type="range" min="0.5" max="5" step="0.1" value="${user.risk_pct || '1.5'}" oninput="document.getElementById('risk-val').innerText = this.value + '%'; if(window.STATE && STATE.user) STATE.user.risk_pct = parseFloat(this.value);"/>
                            </div>
                            
                            <div class="space-y-2">
                                <div class="flex justify-between text-sm">
                                    <span class="text-on-surface-variant">Stock Risk per Trade</span>
                                    <span id="stock-risk-val" class="text-secondary-container font-bold">${user.stock_risk_pct || '1.0'}%</span>
                                </div>
                                <input id="stock-risk-slider" class="w-full accent-secondary bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" type="range" min="0.5" max="5" step="0.1" value="${user.stock_risk_pct || '1.0'}" oninput="document.getElementById('stock-risk-val').innerText = this.value + '%'; if(window.STATE && STATE.user) STATE.user.stock_risk_pct = parseFloat(this.value);"/>
                            </div>
                        </div>
                        <button onclick="savePreferences()" class="w-full h-11 bg-surface-container text-on-surface font-label-md text-label-md border border-white/10 rounded-lg hover:bg-white/5 transition-all mt-2 cursor-pointer">
                            Apply Sizing
                        </button>
                    </div>

                    ${(hasLinkedCrypto || hasLinkedStock) ? `
                    <div class="flex gap-3 pt-4">
                        ${hasLinkedCrypto ? `
                        <button onclick="resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('${user.active_crypto_strategy === 'None' ? 'Valkyrie Elite Scalper' : user.active_crypto_strategy}'); triggerBacktest(); }, 150);" class="flex-1 h-11 bg-gradient-to-r from-primary to-[#3cd7ff] text-background font-bold text-xs uppercase rounded-lg shadow-lg cyan-glow hover:opacity-90 active:scale-95 transition-all flex items-center justify-center gap-1.5 cursor-pointer">
                            <span class="material-symbols-outlined text-[16px]">science</span>
                            Backtest Crypto
                        </button>
                        ` : ''}
                        ${hasLinkedStock ? `
                        <button onclick="resetBacktester(); navigate('#/backtest'); setTimeout(() => { window.selectStrategy('Sherpa Velocity Pullback'); triggerBacktest(); }, 150);" class="flex-1 h-11 bg-gradient-to-r from-[#ffdb3c] to-[#f9a826] text-background font-bold text-xs uppercase rounded-lg shadow-lg gold-glow hover:opacity-90 active:scale-95 transition-all flex items-center justify-center gap-1.5 cursor-pointer">
                            <span class="material-symbols-outlined text-[16px]">science</span>
                            Backtest Stocks
                        </button>
                        ` : ''}
                    </div>
                    ` : ''}
                </div>
            </section>


            ${isAdmin ? `
            <section class="glass-card rounded-xl p-card-padding space-y-4 border border-[#ffdb3c]/30 gold-glow">
                <h3 class="font-body-lg text-body-lg font-bold text-[#ffdb3c] flex items-center gap-2">
                    <span class="material-symbols-outlined">workspace_premium</span> Admin Gifting Center
                </h3>
                <p class="text-xs text-on-surface-variant leading-relaxed">
                    Generate single-use premium gift links that can be shared with anyone. The recipient can redeem the code either on the Web App or the Telegram Bot.
                </p>
                <div id="gift-generation-container" class="space-y-3">
                    <div class="space-y-2">
                        <div class="flex justify-between text-xs">
                            <span class="text-on-surface-variant">Gift Duration</span>
                            <span id="gift-duration-val" class="text-[#ffdb3c] font-bold">1 Month</span>
                        </div>
                        <input id="gift-duration-slider" class="w-full accent-primary bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" type="range" min="1" max="12" step="1" value="1" oninput="document.getElementById('gift-duration-val').innerText = this.value + (this.value == 1 ? ' Month' : ' Months');"/>
                    </div>
                    <button onclick="generateAdminGiftCode()" class="w-full h-11 bg-gradient-to-r from-primary to-[#ffdb3c] text-background font-bold rounded-lg hover:opacity-90 active:scale-95 transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer">
                        <span class="material-symbols-outlined text-lg">redeem</span>
                        <span>Generate Universal Gift Link</span>
                    </button>
                </div>
            </section>
            ` : ''}
                </div>

            </div>

            <!-- Logout Link -->
            <button onclick="handleLogout()" class="w-full py-3 bg-red-950/20 text-error font-bold rounded-lg border border-error/30 hover:bg-red-950/40 text-center cursor-pointer mt-section-gap">
                Logout Session
            </button>
        </main>
    `;
}

function renderLogsView() {
    const webapiFilter = localStorage.getItem('webapi_log_filter') || '';
    const tradingbotFilter = localStorage.getItem('tradingbot_log_filter') || '';

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 max-w-[1200px] mx-auto min-h-screen flex flex-col">
            <div class="flex justify-between items-center mb-4 shrink-0 glass-card rounded-xl p-card-padding border border-[#ffdb3c]/30 gold-glow">
                <h2 class="font-headline-sm text-headline-sm text-[#ffdb3c] flex items-center gap-2">
                    <span class="material-symbols-outlined">terminal</span> Server Logs
                </h2>
            </div>
            
            <style>
                .logs-layout { display: flex; gap: 1rem; width: 100%; height: 100%; }
                .log-panel { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; }
                .mobile-logs-tabs { display: none; }
                
                @media (max-width: 768px) {
                    .mobile-logs-tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; width: 100%; }
                    .log-panel { display: none !important; }
                    .log-panel.active-tab { display: flex !important; }
                }
            </style>
            
            <div class="mobile-logs-tabs">
                <button onclick="window.setAdminLogsTab('webapi')" class="flex-1 py-2 text-sm font-bold rounded-lg border transition-colors ${window.adminLogsMobileTab !== 'tradingbot' ? 'bg-primary/20 text-primary border-primary' : 'bg-surface-container-high text-on-surface-variant border-white/10'}">Web API</button>
                <button onclick="window.setAdminLogsTab('tradingbot')" class="flex-1 py-2 text-sm font-bold rounded-lg border transition-colors ${window.adminLogsMobileTab === 'tradingbot' ? 'bg-primary/20 text-primary border-primary' : 'bg-surface-container-high text-on-surface-variant border-white/10'}">Trading Bot</button>
            </div>

            <div class="logs-layout">
                <!-- Web Server -->
                <div class="log-panel glass-card rounded-xl p-card-padding border border-[#ffdb3c]/30 gold-glow ${window.adminLogsMobileTab !== 'tradingbot' ? 'active-tab' : ''}">
                    <div class="flex justify-between items-center mb-3 shrink-0">
                        <h4 class="font-bold text-sm text-on-surface truncate">Web API</h4>
                        <div class="flex items-center gap-1.5 shrink-0">
                            <button onclick="copyLogs('webapi')" title="Copy Visible Logs" class="text-[10px] bg-surface-container-high text-on-surface-variant px-2 py-1.5 rounded hover:bg-white/10 transition-colors font-bold uppercase tracking-wider flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">content_copy</span></button>
                            <button onclick="promptLogFilter('webapi')" title="Filter Logs" class="text-[10px] bg-surface-container-high px-2 py-1.5 rounded hover:bg-white/10 transition-colors font-bold uppercase tracking-wider flex items-center gap-1 ${webapiFilter ? 'text-[#ffdb3c] border border-[#ffdb3c]/50' : 'text-on-surface-variant'}"><span class="material-symbols-outlined text-[12px]">filter_alt</span></button>
                            <button onclick="restartService('webapi')" class="text-[10px] bg-error/20 text-error px-3 py-1.5 rounded hover:bg-error/40 transition-colors font-bold uppercase tracking-wider">Reload</button>
                        </div>
                    </div>
                    <div style="color: #4ade80; white-space: pre; overflow-x: auto; height: 65vh;" class="bg-black border border-white/10 rounded-lg p-3 font-mono text-[10px] leading-tight" id="webapi-logs-container">
                        Loading Web API logs...
                    </div>
                </div>
                <!-- Trading Bot -->
                <div class="log-panel glass-card rounded-xl p-card-padding border border-[#ffdb3c]/30 gold-glow ${window.adminLogsMobileTab === 'tradingbot' ? 'active-tab' : ''}">
                    <div class="flex justify-between items-center mb-3 shrink-0">
                        <h4 class="font-bold text-sm text-on-surface truncate">Trading Bot</h4>
                        <div class="flex items-center gap-1.5 shrink-0">
                            <button onclick="copyLogs('tradingbot')" title="Copy Visible Logs" class="text-[10px] bg-surface-container-high text-on-surface-variant px-2 py-1.5 rounded hover:bg-white/10 transition-colors font-bold uppercase tracking-wider flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">content_copy</span></button>
                            <button onclick="promptLogFilter('tradingbot')" title="Filter Logs" class="text-[10px] bg-surface-container-high px-2 py-1.5 rounded hover:bg-white/10 transition-colors font-bold uppercase tracking-wider flex items-center gap-1 ${tradingbotFilter ? 'text-[#ffdb3c] border border-[#ffdb3c]/50' : 'text-on-surface-variant'}"><span class="material-symbols-outlined text-[12px]">filter_alt</span></button>
                            <button onclick="restartService('tradingbot')" class="text-[10px] bg-error/20 text-error px-3 py-1.5 rounded hover:bg-error/40 transition-colors font-bold uppercase tracking-wider">Restart</button>
                        </div>
                    </div>
                    <div style="color: #3cd7ff; white-space: pre; overflow-x: auto; height: 65vh;" class="bg-black border border-white/10 rounded-lg p-3 font-mono text-[10px] leading-tight" id="tradingbot-logs-container">
                        Loading Trading Bot logs...
                    </div>
                </div>
            </div>
        </main>
    `;
}

function renderStrategyView() {
    const user = STATE.user || {};
    const current = user.active_crypto_strategy || 'Valkyrie Elite Scalper';
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">⚖️ Strategy</h2>
            
            <div class="glass-card rounded-xl p-card-padding border-t-2 border-primary/40">
                <p class="text-xs text-on-surface-variant uppercase">Current Active</p>
                <h3 class="text-lg font-bold text-on-surface mt-1">🪙 ${current}</h3>
            </div>
            
            <div class="space-y-stack-gap">
                ${!(user.disabled_strategies || []).includes('Mean Reversion Scalper') ? `
                <button onclick="changeStrategy('Mean Reversion Scalper')" class="w-full glass-card rounded-xl p-4 flex justify-between items-center hover:bg-white/5 text-left border ${current === 'Mean Reversion Scalper' ? 'border-primary' : 'border-white/10'}">
                    <div>
                        <h4 class="font-semibold text-on-surface">Mean Reversion Scalper</h4>
                        <p class="text-xs text-on-surface-variant mt-1">Scalps volatile assets under extreme RSI overbought/oversold boundaries.</p>
                    </div>
                    ${current === 'Mean Reversion Scalper' ? '<span class="material-symbols-outlined text-primary">check_circle</span>' : ''}
                </button>
                ` : ''}

                ${!(user.disabled_strategies || []).includes('Valkyrie Elite Scalper') ? `
                <button onclick="changeStrategy('Valkyrie Elite Scalper')" class="w-full glass-card rounded-xl p-4 flex justify-between items-center hover:bg-white/5 text-left border ${current === 'Valkyrie Elite Scalper' ? 'border-primary' : 'border-white/10'}">
                    <div>
                        <h4 class="font-semibold text-on-surface">Valkyrie Elite Scalper</h4>
                        <p class="text-xs text-on-surface-variant mt-1">Advanced volatility and trend tracker optimized for active crypto markets.</p>
                    </div>
                    ${current === 'Valkyrie Elite Scalper' ? '<span class="material-symbols-outlined text-primary">check_circle</span>' : ''}
                </button>
                ` : ''}
                
                ${!(user.disabled_strategies || []).includes('Sherpa Velocity Pullback') ? `
                <button onclick="changeStrategy('Sherpa Velocity Pullback')" class="w-full glass-card rounded-xl p-4 flex justify-between items-center hover:bg-white/5 text-left border ${current === 'Sherpa Velocity Pullback' ? 'border-primary' : 'border-white/10'}">
                    <div>
                        <h4 class="font-semibold text-on-surface">Sherpa Velocity Pullback</h4>
                        <p class="text-xs text-on-surface-variant mt-1">Captures high-volume momentum trends with strict trailing stops.</p>
                    </div>
                    ${current === 'Sherpa Velocity Pullback' ? '<span class="material-symbols-outlined text-primary">check_circle</span>' : ''}
                </button>
                ` : ''}
            </div>
        </main>
    `;
}

function renderBacktestView() {
    const bt = STATE.backtest;
    const user = STATE.user || {};
    const selectedStrategy = bt.strategy || 'Valkyrie Elite Scalper';
    const isStock = (selectedStrategy === 'Sherpa Velocity Pullback');
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🔬 Backtest Engine</h2>
            
            ${bt.running ? `
                <div class="glass-card rounded-xl p-8 text-center space-y-4 min-h-[160px] flex flex-col justify-center items-center">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-primary border-t-transparent mb-4"></div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface transition-all duration-300">${bt.statusMessage || 'Sherpa Engine is Crunching Alpha...'}</h3>
                    <p class="text-[10px] text-on-surface-variant uppercase tracking-wider animate-pulse">Scanning ${isStock ? '5' : '3'} years of historical market data</p>
                </div>
            ` : bt.result ? `
                <div class="glass-card rounded-xl p-card-padding space-y-4">
                    <div class="flex flex-col gap-1 border-b border-white/5 pb-3">
                        <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Backtest Complete!</h3>
                    </div>
                    
                    ${bt.result.chart_url ? `
                        <div class="relative w-full aspect-[12/10] bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center mb-2">
                            <img src="${bt.result.chart_url}" class="w-full h-full object-contain" alt="Equity Curve" />
                        </div>
                    ` : ''}
                    
                    <div class="text-center mb-4">
                        <p class="text-[10px] text-primary font-bold uppercase tracking-wider">
                            Strategy: <span class="text-white">${bt.result.strategy}</span> | Capital: <span class="text-white">$${(bt.result.capital || 10000).toLocaleString()}</span> | Risk: <span class="text-white">${bt.result.risk_pct || 1.5}%</span>
                        </p>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-stack-gap">
                        <div class="bg-surface-container rounded-lg p-3 text-center">
                            <p class="text-xs text-on-surface-variant">Win Rate</p>
                            <p class="text-lg font-bold text-tertiary">${bt.result.win_rate}%</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center">
                            <p class="text-xs text-on-surface-variant">Total Trades</p>
                            <p class="text-lg font-bold text-primary">${bt.result.total_trades}</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center">
                            <p class="text-xs text-on-surface-variant">Sharpe Ratio</p>
                            <p class="text-lg font-bold text-secondary-container">${bt.result.profit_factor}</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center">
                            <p class="text-xs text-on-surface-variant">Max Drawdown</p>
                            <p class="text-lg font-bold text-error">-${bt.result.max_drawdown}%</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center flex flex-col justify-center">
                            <p class="text-xs text-on-surface-variant">Projected Balance</p>
                            <p class="text-lg font-bold text-on-surface mt-1">
                                $${((bt.result.capital || 10000) + bt.result.net_pnl).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                            </p>
                            <p class="text-[10px] mt-0.5">&nbsp;</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center flex flex-col justify-center">
                            <p class="text-xs text-on-surface-variant">Projected PnL</p>
                            <p class="text-lg font-bold ${bt.result.net_pnl >= 0 ? 'text-tertiary' : 'text-error'} mt-1">
                                ${bt.result.net_pnl >= 0 ? '+' : ''}${((bt.result.net_pnl / (bt.result.capital || 10000)) * 100).toFixed(2)}%
                            </p>
                            <p class="text-[10px] font-normal text-on-surface-variant mt-0.5">
                                (${bt.result.net_pnl >= 0 ? '+' : ''}$${Math.abs(bt.result.net_pnl).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})})
                            </p>
                        </div>
                    </div>
                    <button onclick="resetBacktester()" class="w-full h-11 bg-primary-container text-on-primary-container font-bold rounded-lg hover:brightness-110 transition-all cursor-pointer">
                        Run New Backtest
                    </button>
                </div>
            ` : `
                <div class="glass-card rounded-xl p-card-padding space-y-4">
                    <div class="space-y-2">
                        <label class="text-xs text-on-surface-variant font-semibold uppercase">Strategy</label>
                        <div class="relative">
                            <select id="bt-strategy" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg pl-4 pr-10 cyan-glow-focus transition-all appearance-none cursor-pointer" onchange="window.selectStrategy(this.value)">
                                ${!(user.disabled_strategies || []).includes('Mean Reversion Scalper') ? `
                                <option value="Mean Reversion Scalper">Mean Reversion Scalper</option>
                                ` : ''}
                                ${!(user.disabled_strategies || []).includes('Valkyrie Elite Scalper') ? `
                                <option value="Valkyrie Elite Scalper" ${((user.disabled_strategies || []).includes('Mean Reversion Scalper') || (user.active_crypto_strategy || 'Valkyrie Elite Scalper') === 'Valkyrie Elite Scalper') ? 'selected' : ''}>Valkyrie Elite Scalper</option>
                                ` : ''}
                                ${!(user.disabled_strategies || []).includes('Sherpa Velocity Pullback') ? `
                                <option value="Sherpa Velocity Pullback">Sherpa Velocity Pullback</option>
                                ` : ''}
                            </select>
                            <div class="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant flex items-center justify-center">
                                <span class="material-symbols-outlined text-xl">expand_more</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="space-y-1">
                        <label class="text-xs text-on-surface-variant font-semibold uppercase">Starting Capital ($)</label>
                        <input id="bt-capital" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all animate-none" type="number" min="100" max="10000000" value="${STATE.crypto_balance ? Number(STATE.crypto_balance).toFixed(2) : 10000}"/>
                    </div>
                    
                    <div class="space-y-2">
                        <div class="flex justify-between text-xs font-semibold uppercase text-on-surface-variant">
                            <span>Risk per Trade</span>
                            <span id="bt-risk-val" class="text-primary font-bold">${user.risk_pct || 1.0}%</span>
                        </div>
                        <input id="bt-risk" class="w-full accent-primary bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" type="range" min="0.5" max="5" step="0.1" value="${user.risk_pct || 1.0}" oninput="document.getElementById('bt-risk-val').innerText = this.value + '%'"/>
                    </div>
                    
                    <button id="bt-submit-btn" onclick="triggerBacktest()" class="w-full h-11 bg-primary-container text-on-primary-container font-bold rounded-lg hover:brightness-110 transition-all cursor-pointer">
                        ▶ Run ${isStock ? '5-Year' : '3-Year'} Backtest
                    </button>
                </div>
            `}
        </main>
    `;
}

window.toggleSignalExpand = function(id) {
    if (String(STATE.expanded_signal_id) === String(id)) {
        STATE.expanded_signal_id = null;
    } else {
        STATE.expanded_signal_id = String(id);
    }
    renderView();
}

window.openLiveTrade = async function(id) {
    const btn = document.getElementById(`manual-trade-btn-${id}`);
    if (btn) {
        btn.innerHTML = `<span class="material-symbols-outlined animate-spin mr-2 text-[18px]">autorenew</span> Executing...`;
        btn.disabled = true;
    }
    try {
        const res = await apiRequest('/user/manual-trade', 'POST', { signal_id: id });
        if (res && res.success) {
            showToast('Live Trade Opened Successfully!', 'success');
            handleRoute(); // Reloads active trades and signals
        } else {
            showToast('Error opening trade: ' + ((res && res.error) || 'Unknown error'), 'error');
        }
    } catch (e) {
        showToast('Error: ' + e, 'error');
    } finally {
        if (btn) {
            btn.innerHTML = `▶️ Open Live Trade`;
            btn.disabled = false;
        }
    }
}

function renderSignalCard(sig, isLanding = false) {
    const isPremium = STATE.user && STATE.user.is_premium;
    const isExpanded = !isLanding && isPremium && String(STATE.expanded_signal_id) === String(sig.id);
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const privacyStyle = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
    const privacyClass = isPrivacyOn ? 'privacy-blur' : '';
    const privacyHoverHandlers = isPrivacyOn ? `onmouseenter="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='none')" onmouseleave="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='blur(14px)')"` : '';
    
    const getSignalAge = (openTime) => {
        if (!openTime) return 'N/A';
        const now = Date.now();
        const ts = openTime * (openTime > 1000000000000 ? 1 : 1000);
        const diffMs = now - ts;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHrs = Math.floor(diffMins / 60);
        if (diffHrs < 24) return `${diffHrs}h ago`;
        const diffDays = Math.floor(diffHrs / 24);
        return `${diffDays}d ago`;
    };

    const entry = sig.entry_price || 0;
    const tp = sig.tp_price || 0;
    const sl = sig.sl_price || 0;
    const isLong = !sig.side || sig.side.toUpperCase() === 'LONG' || sig.side.toUpperCase() === 'BUY' || sig.side.toUpperCase() === 'L';
    const sideStr = isLong ? 'LONG' : 'SHORT';
    
    const isCryptoSignal = sig.symbol && sig.symbol.includes('/');
    const leverage = isCryptoSignal ? 20.0 : 1.0;
    const sl_pct = entry > 0 ? -Math.abs(((sl - entry) / entry) * 100) * leverage : 0;
    const tp_pct = entry > 0 ? Math.abs(((tp - entry) / entry) * 100) * leverage : 0;
    
    const isCalculating = sig.pnl_pct === null || sig.pnl_pct === undefined;
    const current_pnl_pct = isCalculating ? 0 : sig.pnl_pct;
    const current_pnl_val = isCalculating ? 0 : (sig.pnl_usdt || 0);
    const target_pnl_pct = Math.abs(tp_pct);
    const pos_size = sig.position_size || (current_pnl_pct !== 0 ? (current_pnl_val / (current_pnl_pct / 100)) : 1000);
    const simulated_target_val = (target_pnl_pct / 100) * pos_size;

    const mark = sig.current_price || (entry + (entry * ((current_pnl_pct / leverage) / 100) * (isLong ? 1 : -1)));
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
    
    const userHasKeys = isCryptoSignal ? (STATE.user && STATE.user.has_exchange_keys) : (STATE.user && STATE.user.has_alpaca_keys);
    
    const cleanSigSym = (sig.symbol || '').split(':')[0].replace(/\//g, '');
    const hasPosition = STATE.open_trades && STATE.open_trades.some(t => {
        if (!t.symbol) return false;
        const cleanTSym = t.symbol.split(':')[0].replace(/\//g, '');
        return cleanTSym === cleanSigSym;
    });
    
    const showManualTradeButton = STATE.user && STATE.user.is_premium && userHasKeys && !hasPosition;
    
    let progressBarHtml = '';
    if (isExpanded) {
        const manualTradeHtml = showManualTradeButton ? `
            <div class="mt-4 pt-4 border-t border-white/5 flex justify-center">
                <button id="manual-trade-btn-${sig.id}" onclick="event.stopPropagation(); window.openLiveTrade('${sig.id}')" class="w-full h-12 flex items-center justify-center gap-2 bg-primary text-on-primary font-bold rounded-lg hover:brightness-110 transition-all shadow-[0_0_12px_rgba(168,232,255,0.4)] uppercase tracking-wide">
                    <span class="material-symbols-outlined text-[20px]">bolt</span>
                    Execute Live Trade
                </button>
            </div>
        ` : '';
        
        progressBarHtml = `
            <div class="mt-4 pt-4 border-t border-white/5 space-y-4" onclick="event.stopPropagation()">
                <div class="flex items-center justify-between">
                    <h4 class="text-xs font-bold text-on-surface-variant/80 uppercase tracking-wider">Market Analysis & Setup</h4>
                    <span id="chart-status-sig-${sig.id}" class="text-[10px] text-primary font-mono flex items-center gap-1.5">
                        <span class="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
                        AI Agent plotting chart...
                    </span>
                </div>
                <div class="relative w-full bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
                    <div id="chart-loading-sig-${sig.id}" class="absolute inset-0 p-4 font-mono text-[10px] text-primary/80 bg-[#0b0f19]/90 flex flex-col justify-start gap-1 text-left overflow-y-auto scrollbar-thin select-none">
                        <div class="flex items-center justify-between border-b border-white/10 pb-1.5 mb-1.5">
                            <div class="flex items-center gap-1.5">
                                <span class="w-2 h-2 rounded-full bg-error/80"></span>
                                <span class="w-2 h-2 rounded-full bg-warning/80"></span>
                                <span class="w-2 h-2 rounded-full bg-success/80"></span>
                            </div>
                            <span class="text-[9px] text-on-surface-variant/40">sherpa_analyst_agent.py</span>
                        </div>
                        <div class="space-y-1">
                            <div class="text-on-surface/90 font-semibold">&gt; python3 sherpa_analyst_agent.py --symbol ${sig.symbol} --side ${sideStr}</div>
                            <div class="text-primary/70 animate-pulse">[0.5s] Sourcing exchange order books and historical candles...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 1.5s; opacity: 0;">[1.8s] Candlestick series downloaded (150 periods). Analyzing patterns...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 3.5s; opacity: 0;">[3.2s] Slicing indicator overlays: 20/50/200 EMA + Bollinger Bands...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 5.5s; opacity: 0;">[5.0s] Mapping trade plan: entry ($${entry.toFixed(4)}), tp ($${tp.toFixed(4)}), sl ($${sl.toFixed(4)})...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 7.2s; opacity: 0;">[7.2s] Calculating Risk/Reward ratio and trade trajectory progress...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 9.5s; opacity: 0;">[9.5s] Constructing Matplotlib dynamic layout canvas with dark theme...</div>
                            <div class="text-primary/60" style="animation: reveal-log 0.2s forwards; animation-delay: 12.0s; opacity: 0;">[12.0s] Compiling chart canvas assets & rendering price action lines...</div>
                            <div class="text-primary/50 animate-pulse" style="animation: reveal-log 0.2s forwards, pulse 1.5s infinite; animation-delay: 15.0s; opacity: 0;">[15.0s] Completing high-resolution plot generation on backend...</div>
                        </div>
                    </div>
                    <img src="/api/trades/chart?symbol=${encodeURIComponent(sig.symbol)}&entry=${entry}&tp=${tp}&sl=${sl}&side=${sideStr}&open_ts=${sig.open_time || 0}&type=${sig.symbol && sig.symbol.includes('/') ? 'crypto' : 'stock'}&current_price=${mark}" 
                         onload="const l = document.getElementById('chart-loading-sig-${sig.id}'); if(l)l.remove(); const s = document.getElementById('chart-status-sig-${sig.id}'); if(s)s.remove(); this.classList.remove('hidden');" 
                         class="w-full h-auto block hidden" alt="Signal Chart" />
                </div>
                ${manualTradeHtml}
            </div>
        `;
    }

    return `
        <div ${isLanding ? '' : (isPremium ? `onclick="toggleSignalExpand('${sig.id}')"` : `onclick="showToast('Upgrade to Premium to view charts and details!', 'warning')" tabindex="0"`)} class="glass-card rounded-lg p-4 border border-white/5 flex flex-col gap-3 ${isLanding ? '' : 'cursor-pointer hover:border-white/20'} transition-all group" ${privacyHoverHandlers}>
            <div class="flex justify-between items-center">
                <div class="pointer-events-none">
                    <h4 class="font-bold text-on-surface flex items-center gap-1">
                        ${sig.symbol} 
                        <span class="material-symbols-outlined text-[16px] ${isLong ? 'text-primary' : 'text-error'}">${isLong ? 'trending_up' : 'trending_down'}</span>
                    </h4>
                    <p class="text-[11px] text-on-surface-variant mt-1 flex items-center gap-1.5 flex-wrap">
                        <span>${sig.strategy}</span>
                        <span class="text-on-surface-variant/30">•</span>
                        <span class="text-primary/90 font-semibold flex items-center gap-0.5">
                            <span class="material-symbols-outlined text-[13px] translate-y-[-0.5px]">schedule</span>
                            ${getSignalAge(sig.open_time)}
                        </span>
                    </p>
                </div>
                <div class="flex items-center gap-3">
                    <div class="text-right flex flex-col justify-center pointer-events-none" ${isLanding ? 'style="filter: blur(8px); user-select: none;"' : ''}>
                        ${isCalculating ? `
                            <p class="font-numeric-data text-[10px] font-bold text-primary/80 animate-pulse flex items-center gap-1 justify-end uppercase tracking-wider">
                                <span class="inline-block w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
                                Calculating PnL...
                            </p>
                        ` : `
                            <p class="font-numeric-data text-numeric-data font-bold text-lg ${current_pnl_pct >= 0 ? 'text-tertiary' : 'text-error'}">
                                ${current_pnl_pct >= 0 ? '+' : ''}${current_pnl_pct.toFixed(2)}%
                            </p>
                            ${tp > 0 ? `<p class="text-on-surface-variant/50 text-[10px] font-normal uppercase tracking-widest mt-0.5">Target: ${Math.abs(target_pnl_pct).toFixed(0)}%</p>` : ''}
                        `}
                    </div>
                    ${!isLanding ? `
                    <button onclick="event.stopPropagation(); window.shareTradeCard('${isCryptoSignal ? 'crypto' : 'stock'}', '${sig.symbol}', '${sideStr}', ${current_pnl_pct}, ${entry}, ${mark}, ${current_pnl_val})" class="p-1.5 text-on-surface-variant hover:text-primary rounded-full hover:bg-white/5 transition-colors cursor-pointer flex items-center justify-center" title="Share Signal Card">
                        <span class="material-symbols-outlined text-[18px]">share</span>
                    </button>
                    ` : ''}
                    ${(!isLanding && isPremium) ? `
                    <div class="text-on-surface-variant/40 group-hover:text-primary transition-colors flex items-center justify-center pointer-events-none">
                        <span class="material-symbols-outlined text-xl transition-transform duration-300 ${isExpanded ? 'rotate-180 text-primary' : ''}">expand_more</span>
                    </div>
                    ` : ''}
                </div>
            </div>
            <div class="flex justify-between items-center pt-3 border-t border-white/10 pointer-events-none" ${(isLanding || !isPremium) ? 'style="filter: blur(8px); user-select: none;"' : ''}>
                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                    SL: <span class="text-on-surface">$${sl.toFixed(isCryptoSignal ? 4 : 2)} (${sl_pct.toFixed(0)}%)</span>
                </div>
                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                    TP: <span class="text-on-surface">$${tp.toFixed(isCryptoSignal ? 4 : 2)} (+${tp_pct.toFixed(0)}%)</span>
                </div>
            </div>
            ${progressBarHtml}
        </div>
    `;
}

function renderClosedSignalCard(sig) {
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const privacyStyle = isPrivacyOn ? 'style="filter: blur(14px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
    const privacyClass = isPrivacyOn ? 'privacy-blur' : '';
    
    const entry = sig.entry_price || 0;
    const isCrypto = sig.symbol && sig.symbol.includes('/');
    
    // Dynamically calculate actual exit price using entry and pnl_raw, falling back to tp/sl
    const isLong = !sig.side || sig.side.toUpperCase() === 'LONG' || sig.side.toUpperCase() === 'BUY' || sig.side.toUpperCase() === 'L';
    const exitPrice = sig.pnl_raw ? (isLong ? (entry + sig.pnl_raw) : (entry - sig.pnl_raw)) : (sig.status === 'tp' ? (sig.tp_price || 0) : (sig.sl_price || 0));
    
    const pnl_pct = sig.pnl_pct || 0;
    
    const leverage = isCrypto ? 20.0 : 1.0;
    const display_pnl_pct = pnl_pct * leverage;
    
    const isWin = display_pnl_pct >= 0;
    const statusText = sig.status === 'tp' ? '🏆 Take Profit' : (sig.status === 'sl' ? '❌ Stop Loss' : '🔒 Closed');
    const statusColor = sig.status === 'tp' ? 'text-tertiary' : (sig.status === 'sl' ? 'text-error' : 'text-[#ffdb3c]');
    const pnlColor = isWin ? 'text-tertiary' : 'text-error';
    const cardBorderColor = sig.status === 'tp' ? 'border-tertiary/20' : (sig.status === 'sl' ? 'border-error/20' : 'border-white/5');
    
    const openTimeStr = sig.open_time ? new Date(sig.open_time * (sig.open_time > 1000000000000 ? 1 : 1000)).toLocaleString() : 'N/A';
    const closeTimeStr = sig.close_time ? new Date(sig.close_time * (sig.close_time > 1000000000000 ? 1 : 1000)).toLocaleString() : 'N/A';

    return `
        <div class="glass-card rounded-lg p-4 border ${cardBorderColor} flex flex-col gap-3 transition-all hover:bg-white/5">
            <div class="flex justify-between items-center">
                <div>
                    <h4 class="font-bold text-on-surface flex items-center gap-1">
                        ${sig.symbol}
                        <span class="text-[10px] ${statusColor} font-bold px-2 py-0.5 rounded-full bg-white/5 ml-2">${statusText}</span>
                        <button onclick="window.shareTradeCard('${isCrypto ? 'crypto' : 'stock'}', '${sig.symbol}', '${sig.side || 'LONG'}', ${display_pnl_pct}, ${sig.entry_price || 0}, ${exitPrice || 0}, ${sig.pnl_usdt || 0})" class="p-1 text-on-surface-variant hover:text-primary rounded-full hover:bg-white/5 transition-colors cursor-pointer flex items-center justify-center ml-1" title="Share Trade Card">
                            <span class="material-symbols-outlined text-[16px]">share</span>
                        </button>
                    </h4>
                    <p class="text-xs text-on-surface-variant mt-1">${sig.strategy}</p>
                </div>
                <div class="text-right">
                    <p class="font-numeric-data text-numeric-data font-bold text-lg ${pnlColor}">
                        ${isWin ? '+' : ''}${display_pnl_pct.toFixed(2)}%
                    </p>
                    <p class="text-on-surface-variant/50 text-[10px] uppercase tracking-wider mt-0.5 ${privacyClass}" ${privacyStyle}>
                        ${isWin ? '+' : ''}$${(sig.pnl_usdt || 0).toFixed(2)} USDT
                    </p>
                </div>
            </div>
            <div class="flex justify-between items-center pt-3 border-t border-white/10 font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                <div>Entry: <span class="text-on-surface">$${entry.toFixed(4)}</span></div>
                <div>Exit: <span class="text-on-surface">$${exitPrice.toFixed(4)}</span></div>
            </div>
            <div class="flex justify-between items-center text-[10px] text-on-surface-variant/60 font-mono mt-1 pt-1">
                <div>Opened: <span>${openTimeStr}</span></div>
                <div>Closed: <span>${closeTimeStr}</span></div>
            </div>
        </div>
    `;
}

window.toggleSignalsStats = function() {
    STATE.show_signals_stats = !STATE.show_signals_stats;
    renderView();
};

window.setSignalsTab = function(tab) {
    STATE.signals_tab = tab;
    // Reset the stats accordion state when changing tabs
    STATE.show_signals_stats = false;
    renderView();
};

window.setSignalsCategoryTab = function(tab) {
    STATE.signals_category_tab = tab;
    renderView();
};

function renderSignalsView() {
    if (STATE.is_loading_signals) {
        const loadingMessages = [
            "Sherpa is consulting the algorithmic oracles...",
            "Analyzing quantum market fluctuations...",
            "Deploying the Alpha-Seeking Sherpas...",
            "Calibrating the velocity pullbacks...",
            "Parsing the cosmic charts...",
            "Calculating precise entry vectors..."
        ];
        const msg = loadingMessages[new Date().getSeconds() % loadingMessages.length];
        
        return `
            ${renderHeader()}
            <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto flex flex-col items-center justify-center min-h-[60vh]">
                <div class="relative w-24 h-24 mb-6">
                    <div class="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                    <div class="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
                    <div class="absolute inset-0 flex items-center justify-center text-primary">
                        <span class="material-symbols-outlined text-3xl animate-pulse">satellite_alt</span>
                    </div>
                </div>
                <h2 class="font-headline-sm text-headline-sm text-on-surface mb-2 animate-pulse">Scanning Markets...</h2>
                <p class="font-body-md text-body-md text-on-surface-variant text-center max-w-[280px]">
                    ${msg}
                </p>
            </main>
        `;
    }

    const currentTab = STATE.signals_tab || 'active';
    let listHtml = '';
    
    if (currentTab === 'active') {
        const active_signals = STATE.active_signals || [];
        const cryptoActive = active_signals.filter(s => s.symbol && s.symbol.includes('/'));
        const stockActive = active_signals.filter(s => s.symbol && !s.symbol.includes('/'));
        const cryptoCount = cryptoActive.length;
        const stockCount = stockActive.length;

        let showCryptoTab = cryptoCount > 0;
        let showStockTab = stockCount > 0;
        if (cryptoCount === 0 && stockCount === 0) {
            showCryptoTab = true;
            showStockTab = true;
        }

        let isCrypto = (STATE.signals_category_tab || 'crypto') === 'crypto';
        if (isCrypto && !showCryptoTab && showStockTab) {
            isCrypto = false;
        } else if (!isCrypto && !showStockTab && showCryptoTab) {
            isCrypto = true;
        }

        const sortedCrypto = [...cryptoActive].sort((a, b) => {
            if (STATE.active_signals_sort_by === 'date') {
                return (b.open_time || 0) - (a.open_time || 0);
            } else {
                return (b.pnl_pct || 0) - (a.pnl_pct || 0);
            }
        });

        const sortedStock = [...stockActive].sort((a, b) => {
            if (STATE.active_signals_sort_by === 'date') {
                return (b.open_time || 0) - (a.open_time || 0);
            } else {
                return (b.pnl_pct || 0) - (a.pnl_pct || 0);
            }
        });

        const cryptoHtml = sortedCrypto.length === 0 ? `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">hourglass_empty</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active crypto signals</p>
            </div>
        ` : sortedCrypto.map(s => renderSignalCard(s)).join('');

        const stockHtml = sortedStock.length === 0 ? `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">hourglass_empty</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active stock signals</p>
            </div>
        ` : sortedStock.map(s => renderSignalCard(s)).join('');

        if (active_signals.length === 0) {
            listHtml = `
                <div class="text-center py-12">
                    <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">satellite_alt</span>
                    <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active signals</p>
                    <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">Sherpa is analyzing markets...</p>
                </div>
            `;
        } else if (showCryptoTab && showStockTab) {
            listHtml = `
                <!-- Category Tab Bar (Mobile Only) -->
                <div class="glass-card rounded-full flex border border-white/10 p-1 w-full max-w-[500px] mx-auto relative overflow-hidden z-10 md:hidden mb-4 animate-fade-in">
                    <button onclick="setSignalsCategoryTab('crypto')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                        Crypto (${cryptoCount})
                    </button>
                    <button onclick="setSignalsCategoryTab('stock')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                        Stocks (${stockCount})
                    </button>
                </div>

                <!-- Mobile List (Single Column) -->
                <div class="space-y-stack-gap md:hidden animate-fade-in">
                    ${isCrypto ? cryptoHtml : stockHtml}
                </div>

                <!-- Desktop View (Two Columns) -->
                <div class="hidden md:grid md:grid-cols-2 md:gap-6 animate-fade-in">
                    <!-- Crypto Column -->
                    <div>
                        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                            <span>🪙</span> Crypto (${cryptoCount})
                        </h3>
                        <div class="space-y-stack-gap">
                            ${cryptoHtml}
                        </div>
                    </div>
                    <!-- Stocks Column -->
                    <div>
                        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                            <span>🦙</span> Stocks (${stockCount})
                        </h3>
                        <div class="space-y-stack-gap">
                            ${stockHtml}
                        </div>
                    </div>
                </div>
            `;
        } else {
            const singleHtml = showCryptoTab ? cryptoHtml : stockHtml;
            const singleCount = showCryptoTab ? cryptoCount : stockCount;
            const singleLabel = showCryptoTab ? 'Crypto' : 'Stocks';
            const singleIcon = showCryptoTab ? '🪙' : '🦙';
            
            listHtml = `
                <div class="w-full max-w-[600px] mx-auto space-y-4 animate-fade-in">
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                        <span>${singleIcon}</span> ${singleLabel} (${singleCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${singleHtml}
                    </div>
                </div>
            `;
        }
    } else {
        const closed_signals = STATE.closed_signals || [];
        const cryptoClosed = closed_signals.filter(s => s.symbol && s.symbol.includes('/'));
        const stockClosed = closed_signals.filter(s => s.symbol && !s.symbol.includes('/'));
        const cryptoCount = cryptoClosed.length;
        const stockCount = stockClosed.length;

        let showCryptoTab = cryptoCount > 0;
        let showStockTab = stockCount > 0;
        if (cryptoCount === 0 && stockCount === 0) {
            showCryptoTab = true;
            showStockTab = true;
        }

        let isCrypto = (STATE.signals_category_tab || 'crypto') === 'crypto';
        if (isCrypto && !showCryptoTab && showStockTab) {
            isCrypto = false;
        } else if (!isCrypto && !showStockTab && showCryptoTab) {
            isCrypto = true;
        }

        const cryptoHtml = cryptoClosed.length === 0 ? `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No closed crypto signals</p>
            </div>
        ` : cryptoClosed.map(s => renderClosedSignalCard(s)).join('');

        const stockHtml = stockClosed.length === 0 ? `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No closed stock signals</p>
            </div>
        ` : stockClosed.map(s => renderClosedSignalCard(s)).join('');

        if (closed_signals.length === 0) {
            listHtml = `
                <div class="text-center py-12">
                    <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">satellite_alt</span>
                    <p class="font-body-lg text-body-lg text-on-surface font-semibold">No closed signals</p>
                    <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">Closed signals will appear here once resolved.</p>
                </div>
            `;
        } else if (showCryptoTab && showStockTab) {
            listHtml = `
                <!-- Category Tab Bar (Mobile Only) -->
                <div class="glass-card rounded-full flex border border-white/10 p-1 w-full max-w-[500px] mx-auto relative overflow-hidden z-10 md:hidden mb-4 animate-fade-in">
                    <button onclick="setSignalsCategoryTab('crypto')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                        Crypto (${cryptoCount})
                    </button>
                    <button onclick="setSignalsCategoryTab('stock')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                        Stocks (${stockCount})
                    </button>
                </div>

                <!-- Mobile List (Single Column) -->
                <div class="space-y-stack-gap md:hidden animate-fade-in">
                    ${isCrypto ? cryptoHtml : stockHtml}
                </div>

                <!-- Desktop View (Two Columns) -->
                <div class="hidden md:grid md:grid-cols-2 md:gap-6 animate-fade-in">
                    <!-- Crypto Column -->
                    <div>
                        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                            <span>🪙</span> Crypto (${cryptoCount})
                        </h3>
                        <div class="space-y-stack-gap">
                            ${cryptoHtml}
                        </div>
                    </div>
                    <!-- Stocks Column -->
                    <div>
                        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                            <span>🦙</span> Stocks (${stockCount})
                        </h3>
                        <div class="space-y-stack-gap">
                            ${stockHtml}
                        </div>
                    </div>
                </div>
            `;
        } else {
            const singleHtml = showCryptoTab ? cryptoHtml : stockHtml;
            const singleCount = showCryptoTab ? cryptoCount : stockCount;
            const singleLabel = showCryptoTab ? 'Crypto' : 'Stocks';
            const singleIcon = showCryptoTab ? '🪙' : '🦙';
            
            listHtml = `
                <div class="w-full max-w-[600px] mx-auto space-y-4 animate-fade-in">
                    <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center justify-center gap-2">
                        <span>${singleIcon}</span> ${singleLabel} (${singleCount})
                    </h3>
                    <div class="space-y-stack-gap">
                        ${singleHtml}
                    </div>
                </div>
            `;
        }
    }

    let statsSection = '';
    if (currentTab === 'closed') {
        const isOpen = !!STATE.show_signals_stats;
        let statsContent = '';
        if (isOpen) {
            if (STATE.free_stats && STATE.free_stats.strategies) {
                const strategyIcons = {
                    "Mean Reversion Scalper": "📈",
                    "Valkyrie Elite Scalper": "🛡️",
                    "Sherpa Velocity Pullback": "🦙"
                };
                const guides = {
                    "Mean Reversion Scalper": {
                        philosophy: "Mean Reversion. Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.",
                        indicators: "Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.",
                        pace: "Highly active. Averages ~0.84 trades/day.",
                        drawdown: "Optimized for recommended <strong class='text-primary'>1.0% risk</strong>, maintaining a safe drawdown of <strong class='text-primary'>~21.9%</strong> (well below the 25% safety ceiling) while delivering <strong class='text-[#ffdb3c]'>+384.1%</strong> PnL.",
                        img: "/api/charts/mean_reversion_infographic.png"
                    },
                    "Valkyrie Elite Scalper": {
                        philosophy: "Wick Rejection. Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.",
                        indicators: "Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.",
                        pace: "Patient and calculated. Averages ~0.68 trades/day.",
                        drawdown: "Highly protected; ultra-low peak drawdown ceiling (<strong class='text-primary'>~16.2% to 19.5%</strong> on expanded basket).",
                        img: "/api/charts/valkyrie_elite_infographic.png"
                    },
                    "Sherpa Velocity Pullback": {
                        philosophy: "Momentum Pullback. Targets short-term oversold pullback cycles on megacap US equities (NASDAQ/NYSE top 40) during robust, verified uptrends using SuperTrend filtering.",
                        indicators: "Daily Close > EMA(200), SuperTrend(10, 3) is UP, 4-period RSI (< 26).",
                        pace: "Daily swing. Scans daily at market open (9:31 AM EST). Averages ~0.42 trades/day.",
                        drawdown: "Highly optimized equity curve, maintaining a tight <strong class='text-primary'>22.7%</strong> maximum drawdown with a verified <strong class='text-[#ffdb3c]'>+102.3%</strong> return and high <strong class='text-tertiary'>70.2%</strong> win rate over a 5-year period.",
                        img: "/api/charts/stock_strategy_infographic.png"
                    }
                };

                const strategyRows = STATE.free_stats.strategies.map(s => {
                    const icon = strategyIcons[s.name] || "📈";
                    const guide = guides[s.name] || guides["Valkyrie Elite Scalper"];
                    const guideId = `sig-guide-${s.name.replace(/\s+/g, '-')}`;
                    
                    const realizedPct = s.realized_pct || 0;
                    const unrealizedPct = s.unrealized_pct || 0;
                    const netPct = realizedPct + unrealizedPct;
                    
                    const netClass = netPct >= 0 ? "text-tertiary" : "text-error";
                    const realizedClass = realizedPct >= 0 ? "text-tertiary" : "text-error";
                    const unrealizedClass = unrealizedPct >= 0 ? "text-tertiary" : "text-error";
                    
                    return `
                        <div class="flex flex-col gap-1 p-2 bg-surface-container-low rounded-lg border border-white/5 hover:border-white/10 transition-colors">
                            <div class="flex justify-between items-center pb-1">
                                <div class="flex items-center gap-1.5 cursor-pointer group" onclick="document.getElementById('${guideId}').classList.toggle('hidden'); const chev = document.getElementById('sig-chev-${guideId}'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                                    <span class="text-sm">${icon}</span>
                                    <span class="font-bold text-xs text-on-surface truncate max-w-[150px] group-hover:text-primary transition-colors" title="${s.name}">${s.name}</span>
                                    <span id="sig-chev-${guideId}" class="material-symbols-outlined text-[14px] text-on-surface-variant transition-transform duration-300">expand_more</span>
                                </div>
                                <div class="flex items-center gap-1">
                                    <span class="uppercase text-on-surface-variant font-bold tracking-wider text-[10px]">Net:</span>
                                    <span class="font-numeric-data font-bold text-sm ${netClass}">${netPct >= 0 ? '+' : ''}${netPct.toFixed(2)}%</span>
                                </div>
                            </div>
                            
                            <div class="flex justify-between items-center pt-1.5 border-t border-white/5">
                                <div class="flex flex-col items-center justify-center">
                                    <button onclick="event.stopPropagation(); window.shareStatsCard('free', '${s.name}')" class="p-1 text-on-surface-variant hover:text-primary rounded-full hover:bg-white/5 transition-colors cursor-pointer flex items-center justify-center" title="Share Strategy Stats">
                                        <span class="material-symbols-outlined text-[16px]">share</span>
                                    </button>
                                </div>
                                <div class="flex flex-col items-center">
                                    <span class="uppercase text-on-surface-variant font-semibold tracking-wider text-[10px]">Win %</span>
                                    <span class="font-numeric-data text-primary font-bold leading-tight mt-0.5 text-lg" style="white-space: nowrap;">${s.win_rate.toFixed(1)}% <span class="text-on-surface-variant/70 font-medium text-xs">(${s.wins}W-${s.losses}L)</span></span>
                                </div>
                                <div class="flex flex-col items-center">
                                    <span class="uppercase text-on-surface-variant font-semibold tracking-wider text-[10px]">Real</span>
                                    <span class="font-numeric-data ${realizedClass} font-bold leading-tight mt-0.5 text-lg">${realizedPct >= 0 ? '+' : ''}${realizedPct.toFixed(2)}%</span>
                                </div>
                                <div class="flex flex-col items-center">
                                    <span class="uppercase text-on-surface-variant font-semibold tracking-wider text-[10px]">Unreal</span>
                                    <span class="font-numeric-data ${unrealizedClass} font-bold leading-tight mt-0.5 text-sm">${unrealizedPct >= 0 ? '+' : ''}${unrealizedPct.toFixed(2)}%</span>
                                </div>
                                <div class="flex flex-col items-center">
                                    <span class="uppercase text-on-surface-variant font-semibold tracking-wider text-[10px]">Open</span>
                                    <span class="font-numeric-data text-on-surface font-bold leading-tight mt-0.5 text-sm">${s.active_count || 0}</span>
                                </div>
                            </div>
                            
                            <!-- Expandable Guide Section -->
                            <div id="${guideId}" class="hidden pt-3 mt-1 border-t border-white/5 space-y-3 animate-fade-in">
                                <div class="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video flex items-center justify-center cursor-zoom-in group" onclick="window.open('${guide.img}', '_blank')">
                                    <img src="${guide.img}" alt="${s.name} Infographic" class="w-full h-full object-cover" onerror="this.src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='"/>
                                    <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                        <span class="material-symbols-outlined text-white text-2xl">zoom_in</span>
                                        <span class="text-xs text-white font-bold uppercase tracking-wider">Expand</span>
                                    </div>
                                </div>
                                <div class="space-y-1.5 bg-surface-container/30 rounded-lg p-2.5" style="font-size: 10px;">
                                    <div>
                                        <span class="text-on-surface-variant font-bold uppercase tracking-wider block" style="font-size: 8px;">Philosophy</span>
                                        <p class="text-on-surface leading-tight mt-0.5">${guide.philosophy}</p>
                                    </div>
                                    <div>
                                        <span class="text-on-surface-variant font-bold uppercase tracking-wider block" style="font-size: 8px;">Indicators</span>
                                        <p class="text-on-surface leading-tight mt-0.5">${guide.indicators}</p>
                                    </div>
                                    <div>
                                        <span class="text-on-surface-variant font-bold uppercase tracking-wider block" style="font-size: 8px;">Execution Pace</span>
                                        <p class="text-on-surface leading-tight mt-0.5">${guide.pace}</p>
                                    </div>
                                    <div>
                                        <span class="text-on-surface-variant font-bold uppercase tracking-wider block" style="font-size: 8px;">Drawdown Profile</span>
                                        <p class="text-on-surface leading-tight mt-0.5">${guide.drawdown}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
                
                statsContent = `
                    <div class="pt-2 border-t border-white/10 animate-fade-in flex flex-col gap-1.5">
                        ${strategyRows}
                    </div>
                `;
            } else {
                statsContent = `
                    <div class="pt-3 border-t border-white/10 text-center py-4 text-xs text-on-surface-variant animate-fade-in">
                        Loading strategy stats...
                    </div>
                `;
            }
        }
        
        statsSection = `
            <div class="glass-card rounded-xl p-3 border border-white/10 mb-4 transition-all duration-300 w-full max-w-[600px] mx-auto">
                <button onclick="window.toggleSignalsStats()" class="flex items-center justify-between w-full text-on-surface-variant hover:text-on-surface transition-colors active:scale-[0.99]">
                    <div class="flex items-center gap-2">
                        <span class="material-symbols-outlined text-[20px] text-primary">analytics</span>
                        <span class="font-semibold text-sm text-on-surface">Alpha Signals Stats</span>
                    </div>
                    <span class="material-symbols-outlined text-[20px] transition-transform duration-300 ${isOpen ? 'rotate-180 text-primary' : ''}">expand_more</span>
                </button>
                ${statsContent}
            </div>
        `;
    }

    return `
        ${renderHeader()}
        <main class="w-full pt-[60px] pb-24 max-w-[500px] md:max-w-5xl mx-auto animate-fade-in relative">
            <div class="sticky top-[58px] z-40 w-full bg-surface/95 backdrop-blur-xl pt-4 pb-4 px-container-margin mb-4">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Alpha Signals</h2>
                    <div class="flex items-center gap-2">
                        ${currentTab === 'active' && STATE.active_signals.length > 0 ? `
                        <button onclick="window.toggleActiveSignalsSort()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 hover:border-primary/30 transition-all text-xs font-semibold text-on-surface-variant hover:text-primary active:scale-95" title="Toggle sorting order">
                            <span class="material-symbols-outlined text-[16px]">${STATE.active_signals_sort_by === 'pnl' ? 'calendar_month' : 'trending_up'}</span>
                            <span>${STATE.active_signals_sort_by === 'pnl' ? 'Newest First' : 'Most Profitable First'}</span>
                        </button>
                        ` : ''}
                        <button onclick="window.refreshSignals(true)" class="flex items-center justify-center w-9 h-9 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 hover:border-primary/30 transition-all text-on-surface-variant hover:text-primary active:scale-95 group" title="Refresh Signals">
                            <span class="material-symbols-outlined text-[20px] ${STATE.is_loading_signals ? 'animate-spin text-primary' : 'group-hover:rotate-180 transition-transform duration-500'}">refresh</span>
                        </button>
                    </div>
                </div>
                
                <!-- Tabs -->
                <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1 w-full max-w-[500px] mx-auto z-10">
                    <button onclick="setSignalsTab('active')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${currentTab === 'active' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">Active Signals</button>
                    <button onclick="setSignalsTab('closed')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${currentTab === 'closed' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">Closed Signals</button>
                </div>
            </div>
            
            <div class="px-container-margin space-y-section-gap">
                ${statsSection}
                
                ${listHtml}
            </div>
        </main>
    `;
}

function renderPremiumView() {
    const user = STATE.user || {};
    const isPremium = user.is_premium;
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">💎 Premium Upgrade</h2>
            
            <div class="glass-card rounded-xl p-6 border-t-2 border-secondary-container/40 relative overflow-hidden">
                <h3 class="text-2xl font-bold text-secondary-container flex items-center gap-2">
                    <span>💎</span> Premium autopilot
                </h3>
                <p class="text-xs text-on-surface-variant mt-2 leading-relaxed">
                    Unlocks full autonomous execution directly linked to your exchange API. Active 24/7.
                </p>
                <div class="border-t border-white/10 mt-4 pt-4 text-center">
                    <p class="text-sm text-on-surface-variant">Membership Status</p>
                    <p class="text-xl font-bold ${isPremium ? 'text-secondary-container' : 'text-on-surface-variant'} mt-1">
                        ${isPremium ? 'ACTIVE MEMBERSHIP' : 'STANDARD TIER (READ ONLY)'}
                    </p>
                </div>
            </div>
            
            <div class="glass-card rounded-xl p-card-padding space-y-4">
                <h4 class="font-semibold text-on-surface">Upgrade / Renew via TRON USDT</h4>
                
                <div class="bg-primary/10 rounded-lg p-3 border border-primary/20 space-y-2">
                    <p class="text-sm text-on-surface"><span class="font-bold text-primary">1.</span> Send <span class="font-bold text-secondary-container">20 USDT</span> (TRC-20) to the Treasury wallet below.</p>
                    <p class="text-sm text-on-surface"><span class="font-bold text-primary">2.</span> Enter your sending wallet address and click <span class="font-semibold">Save Source Wallet</span>.</p>
                    <p class="text-sm text-on-surface"><span class="font-bold text-primary">3.</span> Click <span class="font-semibold">Verify Blockchain Payment</span>.</p>
                </div>

                <div class="flex justify-center py-2">
                    <img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=TY1V64xJc24abG9aq4UXGeMJtvPhSDCgoj" alt="TRON Wallet QR Code" class="rounded-lg p-2 bg-white" width="160" height="160" />
                </div>
                <div onclick="navigator.clipboard.writeText('TY1V64xJc24abG9aq4UXGeMJtvPhSDCgoj'); showToast('Wallet address copied!')" class="bg-surface-container rounded-lg p-3 border border-white/5 space-y-2 cursor-pointer hover:bg-white/5 transition-colors group">
                    <div class="flex justify-between items-center">
                        <p class="text-xs text-on-surface-variant uppercase">USDT TRC-20 Treasury</p>
                        <span class="material-symbols-outlined text-[16px] text-on-surface-variant group-hover:text-primary transition-colors">content_copy</span>
                    </div>
                    <p class="text-sm font-mono text-primary break-all">TY1V64xJc24abG9aq4UXGeMJtvPhSDCgoj</p>
                </div>
                <div class="space-y-3">
                    <input id="wallet-addr" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4" placeholder="Your source USDT TRC20 Wallet" type="text" value="${user.source_wallet || ''}"/>
                    <button onclick="saveWallet()" class="w-full h-11 bg-surface-container text-on-surface font-label-md text-label-md border border-white/10 rounded-lg hover:bg-white/5 transition-all">
                        👛 Save Source Wallet
                    </button>
                    <button onclick="auditPayment()" class="w-full h-11 bg-primary-container text-on-primary-container font-bold rounded-lg hover:brightness-110 transition-all">
                        🔎 Verify Blockchain Payment
                    </button>
                </div>
            </div>
        </main>
    `;
}

function renderReferralView() {
    const user = STATE.user || {};
    const refCount = user.referral_count || 0;
    const credits = user.referral_credits || 0.0;
    const refId = user.telegram_chat_id || user.id;
    const inviteLink = user.invite_link || `https://bot.metaversesherpa.io/#/register?ref=${refId}`;
    const telegramInviteLink = `https://t.me/metaversesherpa_trading_bot?start=ref_${refId}`;
    
    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🤝 Refer & Earn</h2>
            
            <div class="glass-card rounded-xl p-6 border-t-2 border-tertiary/40">
                <h3 class="text-xl font-bold text-tertiary">Recruit & Unlock</h3>
                <p class="text-xs text-on-surface-variant mt-2 leading-relaxed">
                    Earn 30 Days Free Premium for every 3 active members you refer to Metaverse Sherpa.
                </p>
            </div>
            
            <div class="grid grid-cols-2 gap-stack-gap">
                <div class="glass-card rounded-lg p-4 text-center">
                    <p class="text-xs text-on-surface-variant">Recruits</p>
                    <p class="text-2xl font-bold text-primary mt-1">${refCount}</p>
                </div>
                <div class="glass-card rounded-lg p-4 text-center">
                    <p class="text-xs text-on-surface-variant">Reward Credits</p>
                    <p class="text-2xl font-bold text-tertiary mt-1">$${credits.toFixed(2)}</p>
                </div>
            </div>
            
            <div class="glass-card rounded-xl p-card-padding space-y-4">
                <h4 class="font-semibold text-on-surface text-sm">Your Institutional Invite Link (Web)</h4>
                <div class="flex gap-2">
                    <input class="flex-1 h-11 bg-surface-container-low text-on-surface text-xs font-mono border border-white/10 rounded-lg px-4 select-all" type="text" readonly value="${inviteLink}"/>
                    <button onclick="navigator.clipboard.writeText('${inviteLink}').then(() => showToast('Invite link copied!'))" class="h-11 px-3 bg-surface-container border border-white/10 rounded-lg text-primary hover:bg-white/5">
                        Copy
                    </button>
                </div>
                
                <h4 class="font-semibold text-on-surface text-sm mt-4 pt-4 border-t border-white/10">Your Institutional Invite Link (Telegram)</h4>
                <div class="flex gap-2">
                    <input class="flex-1 h-11 bg-surface-container-low text-on-surface text-xs font-mono border border-white/10 rounded-lg px-4 select-all" type="text" readonly value="${telegramInviteLink}"/>
                    <button onclick="navigator.clipboard.writeText('${telegramInviteLink}').then(() => showToast('Invite link copied!'))" class="h-11 px-3 bg-surface-container border border-white/10 rounded-lg text-primary hover:bg-white/5">
                        Copy
                    </button>
                </div>
            </div>
        </main>
    `;
}

function renderHelpView() {
    const allStrategies = Object.keys(STRATEGY_GUIDES);

    let strategiesHtml = allStrategies.map(name => {
        const icon = STRATEGY_ICONS[name] || "📈";
        const guideId = `help-guide-${name.replace(/\\s+/g, '-')}`;
        
        return `
            <div class="glass-card rounded-xl p-4 space-y-2 border border-white/5 transition-all duration-300">
                <div class="flex justify-between items-center cursor-pointer group" onclick="document.getElementById('${guideId}').classList.toggle('hidden'); const chev = document.getElementById('help-chev-${guideId}'); chev.style.transform = chev.style.transform === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';">
                    <h3 class="font-headline-sm text-on-surface flex items-center gap-2 group-hover:text-primary transition-colors text-sm">
                        <span>${icon}</span> ${name}
                    </h3>
                    <span id="help-chev-${guideId}" class="material-symbols-outlined text-on-surface-variant transition-transform duration-300">expand_more</span>
                </div>
                
                <div id="${guideId}" class="hidden pt-4 mt-2 border-t border-white/5 space-y-4 animate-fade-in text-left">
                    ${renderStrategyGuideContent(name, true)}
                </div>
            </div>
        `;
    }).join('');

    if (allStrategies.length === 0) {
        strategiesHtml = `<p class="text-xs text-on-surface-variant mt-2 leading-relaxed font-normal">No strategies available.</p>`;
    }

    return `
        ${renderHeader()}
        <main class="w-full pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="flex items-center justify-between mb-6">
                <h2 class="font-headline-sm text-headline-sm text-on-surface">❓ User Manual</h2>
                <button onclick="history.back()" class="p-2 text-on-surface-variant hover:text-on-surface hover:bg-white/5 rounded-full transition-colors flex items-center justify-center cursor-pointer" title="Close">
                    <span class="material-symbols-outlined text-[24px]">close</span>
                </button>
            </div>
            
            <div class="space-y-stack-gap">
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface flex items-center gap-2">
                        <span class="material-symbols-outlined text-primary">account_balance_wallet</span> Portfolio Audits & Sync
                    </h3>
                    <p class="text-xs text-on-surface-variant mt-2 leading-relaxed font-normal">
                        Your dashboard queries live balances directly from your connected exchanges (CCXT for crypto, Alpaca API for stocks). Open positions and active trades are updated in real-time, mirroring the exact portfolio structure tracked by the Metaverse Sherpa Telegram bot.
                    </p>
                </div>
                
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface flex items-center gap-2">
                        <span class="material-symbols-outlined text-primary">percent</span> Sizing & Sizing Rules
                    </h3>
                    <p class="text-xs text-on-surface-variant mt-2 leading-relaxed font-normal">
                        Manage your risk sizing dynamically. High-volume momentum strategies default to strict sizing limits: <strong>1.5%</strong> per trade for Crypto, and <strong>1.0%</strong> for Stocks to guard capital. You can fully customize these limits in the Settings panel under Sizing.
                    </p>
                </div>
                
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface flex items-center gap-2">
                        <span class="material-symbols-outlined text-primary">vpn_key</span> Exchange Connection Security
                    </h3>
                    <p class="text-xs text-on-surface-variant mt-2 leading-relaxed font-normal">
                        All exchange credentials (API Keys, Secrets, and Passphrases) are encrypted on-disk using military-grade multi-layer Fernet keys. The engine only requires <strong>read</strong> and <strong>trade</strong> permissions; never enable withdrawal permissions.
                    </p>
                </div>
                
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface flex items-center gap-2 mb-4">
                        <span class="material-symbols-outlined text-primary">smart_toy</span> Active Algorithmic Strategies
                    </h3>
                    <div class="space-y-3">
                        ${strategiesHtml}
                    </div>
                </div>
            </div>

            <div class="mt-8">
                <button onclick="history.back()" class="w-full h-11 bg-surface-container text-on-surface font-label-md text-label-md border border-white/10 rounded-lg hover:bg-white/5 transition-all cursor-pointer flex items-center justify-center gap-2">
                    <span class="material-symbols-outlined text-[18px]">close</span>
                    Close Manual
                </button>
            </div>
        </main>
    `;
}

// ----------------- Event Handlers & Forms -----------------
const firebaseConfig = {
  apiKey: "AIzaSyC5_-c02iid6jrfyzwaMok4O63FP4885LY",
  authDomain: "tradingbot-bf028.firebaseapp.com",
  projectId: "tradingbot-bf028",
  storageBucket: "tradingbot-bf028.firebasestorage.app",
  messagingSenderId: "1030598184996",
  appId: "1:1030598184996:web:a6038b9ca7d80a19b348b1",
  measurementId: "G-VDWMF4K1KV"
};

// Initialize Firebase compat
if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
}
const auth = firebase.auth();

let firebaseAuthInitialized = false;
let initialRouteTriggered = false;

auth.onIdTokenChanged(async (user) => {
    if (user) {
        try {
            const idToken = await user.getIdToken();
            localStorage.setItem('session_token', idToken);
        } catch (e) {
            console.error("Failed to store refreshed token:", e);
        }
    } else {
        localStorage.removeItem('session_token');
    }
    
    if (!firebaseAuthInitialized) {
        firebaseAuthInitialized = true;
        if (!initialRouteTriggered) {
            initialRouteTriggered = true;
            handleRoute();
        }
    }
});

async function handleEmailLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    try {
        // Sign in via Firebase Auth
        const userCredential = await auth.signInWithEmailAndPassword(email, password);
        const idToken = await userCredential.user.getIdToken();
        
        // Save the Firebase ID token locally as our session token
        localStorage.setItem('session_token', idToken);
        
        // Sync profile with backend (passes token in require_auth implicitly next)
        const profile = await apiRequest('/user/profile');
        if (profile) {
            STATE.user = profile;
        }
        await setupZKKeys(email, password);
        showToast("Welcome back, Sherpa trader!");
        navigate('#/dashboard');
    } catch (error) {
        showToast(error.message, "error");
    }
}

async function handleForgotPassword(e) {
    e.preventDefault();
    const email = document.getElementById('forgot-email').value;
    
    try {
        await auth.sendPasswordResetEmail(email);
        showToast("Password reset link sent to your email.");
        setLandingAuthMode('login');
    } catch (error) {
        showToast("Error sending reset email: " + error.message, "error");
    }
}

window.handleResetPasswordSubmit = async function(e) {
    e.preventDefault();
    showToast("Please use the link sent to your email to reset your password.", "warning");
}

async function handleEmailRegister(e) {
    e.preventDefault();
    const name = document.getElementById('reg-name').value;
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    
    const refCode = getQueryParam('ref') || localStorage.getItem('referred_by');
    
    try {
        // Register in Firebase Auth
        const userCredential = await auth.createUserWithEmailAndPassword(email, password);
        await userCredential.user.updateProfile({ displayName: name });
        const idToken = await userCredential.user.getIdToken();
        
        // Store token
        localStorage.setItem('session_token', idToken);
        
        // Sync profile and referrals in Postgres
        const payload = { full_name: name };
        if (refCode) {
            payload.referred_by = parseInt(refCode);
        }
        
        // Create user placeholder in local database
        const res = await apiRequest('/auth/sync', 'POST', payload);
        if (res) {
            STATE.user = res.user;
            await setupZKKeys(email, password);
            const profile = await apiRequest('/user/profile');
            if (profile) {
                STATE.user = profile;
            }
            showToast("Account successfully registered!");
            if (refCode) {
                showToast("Referral successfully applied! Welcome to Metaverse Sherpa.");
                localStorage.removeItem('referred_by');
            }
            navigate('#/dashboard');
        }
    } catch (error) {
        showToast(error.message, "error");
    }
}

async function triggerGoogleLogin() {
    if (window.google) {
        document.cookie = "g_state=;path=/;expires=Thu, 01 Jan 1970 00:00:01 GMT";
        window.showGoogleLoading("Connecting to Google", "Please select your Google account in the popup window.");
        window.google.accounts.id.prompt();
    } else {
        showToast("Google Sign-In is blocked or initializing. If using Brave, try clicking the native button or lowering Shields temporarily.", "warning");
        initGoogleSignIn();
    }
}

async function handleLogout() {
    try {
        await auth.signOut();
        await apiRequest('/auth/logout', 'POST');
    } catch (e) {}
    localStorage.removeItem('session_token');
    sessionStorage.removeItem('zk_private_key_jwk');
    
    // Reset STATE to defaults
    STATE.user = null;
    STATE.rsa_private_key = null;
    STATE.crypto_balance = 0.0;
    STATE.stock_balance = 0.0;
    STATE.total_balance = 0.0;
    STATE.open_trades = [];
    STATE.history = [];
    STATE.free_history = [];
    STATE.active_signals = [];
    STATE.stats = null;
    STATE.free_stats = null;
    STATE.current_view = 'landing';
    
    showToast("Logged out successfully");
    window.location.href = '/';
}

async function handleExchangeSetup(e) {
    e.preventDefault();
    const exId = document.getElementById('exchange-id').value;
    const key = document.getElementById('api-key').value;
    const secret = document.getElementById('api-secret').value;
    
    let res;
    if (exId === 'alpaca') {
        const endpoint = document.getElementById('alpaca-endpoint').value;
        res = await apiRequest('/settings/alpaca', 'POST', {
            api_key: key,
            api_secret: secret,
            endpoint: endpoint
        });
    } else {
        const pwd = document.getElementById('api-password').value;
        const cbSandboxEl = document.getElementById('coinbase-sandbox');
        const cbSandbox = cbSandboxEl ? cbSandboxEl.checked : true;
        res = await apiRequest('/settings/exchange', 'POST', {
            exchange_id: exId,
            api_key: key,
            api_secret: secret,
            api_password: pwd,
            bingx_futures_type: 'perpetual',
            coinbase_sandbox: cbSandbox
        });
    }
    
    if (res) {
        if (STATE.user) {
            if (exId === 'alpaca') {
                STATE.user.has_alpaca_keys = true;
            } else {
                STATE.user.has_exchange_keys = true;
                STATE.user.exchange_id = exId;
            }
        }
        showToast("Exchange keys saved successfully!");
        STATE.editing_exchange = null;
        handleRoute();
    }
}

async function toggleBotStatus(currentStatus) {
    const res = await apiRequest('/settings/status', 'POST', { is_active: !currentStatus });
    if (res) {
        showToast(`Autopilot ${!currentStatus ? 'started' : 'stopped'} successfully`);
        handleRoute();
    }
}

async function handleTelegramSetup(e) {
    e.preventDefault();
    const telegram_chat_id = document.getElementById('telegram-chat-id').value;
    const res = await apiRequest('/settings/telegram', 'POST', { telegram_chat_id });
    if (res) {
        if (STATE.user) {
            STATE.user.telegram_chat_id = parseInt(telegram_chat_id);
        }
        STATE.editing_telegram = false;
        showToast(res.message);
        handleRoute();
    }
}

async function savePreferences() {
    const val = parseFloat(document.getElementById('risk-slider').value);
    const stockVal = parseFloat(document.getElementById('stock-risk-slider').value);
    const res = await apiRequest('/settings/preferences', 'POST', { 
        risk_pct: val,
        stock_risk_pct: stockVal
    });
    if (res) {
        if (STATE.user) {
            STATE.user.risk_pct = val;
            STATE.user.stock_risk_pct = stockVal;
        }
        showToast("Risk configuration updated");
        handleRoute();
    }
}

async function handleStrategyChange(type, strategyName) {
    const res = await apiRequest('/settings/strategy', 'POST', { type, strategy: strategyName });
    if (res) {
        showToast(res.message);
        
        if (STATE.user) {
            if (type === 'crypto') {
                STATE.user.active_crypto_strategy = strategyName;
            } else if (type === 'stock') {
                STATE.user.active_stock_strategy = strategyName;
            }
        }
        
        // Dynamically update UI risk sliders and state if strategy is turned on
        if (strategyName !== 'None') {
            if (type === 'crypto') {
                const cryptoSlider = document.getElementById('risk-slider');
                const cryptoVal = document.getElementById('risk-val');
                if (cryptoSlider && cryptoVal) {
                    cryptoSlider.value = '1.5';
                    cryptoVal.innerText = '1.5%';
                }
                if (STATE.user) STATE.user.risk_pct = 1.5;
            } else if (type === 'stock') {
                const stockSlider = document.getElementById('stock-risk-slider');
                const stockVal = document.getElementById('stock-risk-val');
                if (stockSlider && stockVal) {
                    stockSlider.value = '1.0';
                    stockVal.innerText = '1.0%';
                }
                if (STATE.user) STATE.user.stock_risk_pct = 1.0;
            }
            // Auto apply the new strategy sizing preference
            await savePreferences();
        } else {
            handleRoute();
        }
    }
}

window.selectExchange = function(val, label) {
    const input = document.getElementById('exchange-id');
    const labelEl = document.getElementById('exchange-select-label');
    const details = document.getElementById('exchange-dropdown-details');
    if (input && labelEl && details) {
        input.value = val;
        labelEl.innerText = label;
        details.removeAttribute('open');
        window.toggleExchangeFields();
    }
};

window.toggleExchangeFields = function() {
    const exId = document.getElementById('exchange-id').value;
    const pwdDiv = document.getElementById('pwd-field-container');
    const endpointDiv = document.getElementById('endpoint-field-container');
    const bingxDiv = document.getElementById('bingx-futures-field-container');
    
    if (pwdDiv) {
        if (['blofin', 'bitget'].includes(exId)) {
            pwdDiv.classList.remove('hidden');
        } else {
            pwdDiv.classList.add('hidden');
        }
    }
    
    if (endpointDiv) {
        if (exId === 'alpaca') {
            endpointDiv.classList.remove('hidden');
        } else {
            endpointDiv.classList.add('hidden');
        }
    }
    
    const cbAdvDiv = document.getElementById('coinbase-advanced-field-container');
    if (cbAdvDiv) {
        if (exId === 'coinbase') {
            cbAdvDiv.classList.remove('hidden');
        } else {
            cbAdvDiv.classList.add('hidden');
        }
    }
    
    if (bingxDiv) {
        if (exId === 'bingx') {
            bingxDiv.classList.remove('hidden');
        } else {
            bingxDiv.classList.add('hidden');
        }
    }
    
    const cbSandboxDiv = document.getElementById('coinbase-sandbox-field-container');
    if (cbSandboxDiv) {
        if (exId === 'coinbase') {
            cbSandboxDiv.classList.remove('hidden');
        } else {
            cbSandboxDiv.classList.add('hidden');
        }
    }
};

window.editExchange = function(type) {
    STATE.editing_exchange = type;
    renderView();
    
    // Select correct platform in custom select box and trigger toggle
    setTimeout(() => {
        const exchangeSelect = document.getElementById('exchange-id');
        if (exchangeSelect) {
            if (type === 'crypto') {
                exchangeSelect.value = STATE.user.exchange_id || 'blofin';
            } else {
                exchangeSelect.value = 'alpaca';
            }
            window.toggleExchangeFields();
            
            // Prefill credentials
            const keyInput = document.getElementById('api-key');
            const secretInput = document.getElementById('api-secret');
            const passInput = document.getElementById('api-password');
            const endpointInput = document.getElementById('alpaca-endpoint');
            
            if (type === 'crypto') {
                if (keyInput) keyInput.value = STATE.user.api_key || '';
                if (secretInput) secretInput.value = STATE.user.api_secret || '';
                if (passInput) passInput.value = STATE.user.api_password || '';
                const cbSandboxInput = document.getElementById('coinbase-sandbox');
                if (cbSandboxInput) {
                    cbSandboxInput.checked = (STATE.user.coinbase_sandbox !== undefined) ? STATE.user.coinbase_sandbox : true;
                }
            } else {
                if (keyInput) keyInput.value = STATE.user.alpaca_api_key || '';
                if (secretInput) secretInput.value = STATE.user.alpaca_api_secret || '';
                if (endpointInput) endpointInput.value = STATE.user.alpaca_endpoint || 'https://api.alpaca.markets';
            }
            
            // Scroll to the wizard
            const wizardSection = document.getElementById('exchange-wizard-section');
            if (wizardSection) {
                wizardSection.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }, 50);
};

window.deleteExchange = function(type) {
    const isCrypto = type === 'crypto';
    const message = isCrypto 
        ? "🚨 WARNING: This will permanently delete your Crypto API credentials and deactivate automated copy-trading for crypto. Are you sure?"
        : "🚨 WARNING: This will permanently delete your Alpaca Stock API credentials and deactivate automated copy-trading for stocks. Are you sure?";
        
    if (confirm(message)) {
        const endpoint = isCrypto ? '/settings/exchange' : '/settings/alpaca';
        apiRequest(endpoint, 'DELETE')
        .then(data => {
            showToast(data.message || "Credentials deleted successfully!");
            // Reload user profile and refresh view
            return apiRequest('/user/profile');
        })
        .then(profile => {
            if (profile) {
                STATE.user = profile;
                renderView();
            }
        })
        .catch(err => {
            console.error(err);
            alert(`Error: ${err.message || err}`);
        });
    }
};

window.testExchangeConnection = async function(segment, btn) {
    const origLabel = btn.innerHTML;
    btn.innerHTML = '<span class="material-symbols-outlined text-[14px] animate-spin">refresh</span>Testing...';
    btn.disabled = true;
    try {
        const result = await apiRequest(`/settings/test-connection?segment=${segment}`);
        if (result && result.success) {
            showToast(`✅ ${(segment === 'crypto' ? result.exchange : 'Alpaca')} connection successful!`);
            if (result.note) setTimeout(() => showToast(`ℹ️ ${result.note}`, 'info'), 1500);
            if (segment === 'crypto') STATE.crypto_auth_success = true;
            if (segment === 'stock') STATE.stock_auth_success = true;
            renderView();
        } else {
            const errMsg = (result && result.error) || 'Unknown error';
            const hint = result && result.hint;
            showToast(`❌ Connection failed: ${errMsg}`, 'error');
            if (hint) setTimeout(() => showToast(`💡 ${hint}`, 'info'), 1500);
            console.error('[Test Connection] Error:', errMsg);
            if (result && result.diag) console.error('[Test Connection] Diagnostics:', JSON.stringify(result.diag, null, 2));
        }
    } catch (e) {
        showToast(`❌ Connection test error: ${e.message || e}`, 'error');
    } finally {
        btn.innerHTML = origLabel;
        btn.disabled = false;
    }
};

window.toggleDisplayVisibility = function(inputId, iconEl) {
    const input = document.getElementById(inputId);
    if (input) {
        if (input.type === 'password') {
            input.type = 'text';
            iconEl.textContent = 'visibility_off';
        } else {
            input.type = 'password';
            iconEl.textContent = 'visibility';
        }
    }
};


window.showRenewModal = function() {
    alert("💎 RENEW MEMBERSHIP VIA TRON\n\nPlease send exactly 20 USDT (TRC-20) to the address below:\n\nTUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3\n\nAfter submitting, please save your USDT wallet under the Premium panel to allow instant block confirmation.");
};

async function triggerBacktest() {
    const strategyEl = document.getElementById('bt-strategy');
    const capitalEl = document.getElementById('bt-capital');
    const riskEl = document.getElementById('bt-risk');
    
    const strategy = strategyEl ? strategyEl.value : 'Valkyrie Elite Scalper';
    const capital = capitalEl ? parseFloat(capitalEl.value) : 10000.0;
    const risk = riskEl ? parseFloat(riskEl.value) : 1.0;

    const isStock = (strategy === 'Sherpa Velocity Pullback');
    const frames = isStock ? [
        "🦙 Sherpa is saddling up the Alpaca team...",
        "🧗‍♂️ Climbing the steep cliffs of Wall Street...",
        "🌲 Navigating the dense forest of Megacap Tech...",
        "🏔 Mapping the 5-year velocity trails...",
        "❄️ Surviving the freezing rate hikes and bear freezes...",
        "🎯 Anchoring the safety ropes on pullback support zones...",
        "💎 Polishing the golden stock multipliers...",
        "📊 Drawing the peak-to-valley equity charts...",
        "🗺️ Finalizing the high-altitude stock audit...",
        "🏔️ Planting the Sherpa flag on the S&P summit!"
    ] : [
        "🥾 Sherpa is packing the quantitative gear...",
        "🧗‍♂️ Securing the ropes on the Bollinger bands...",
        "🏔️ Climbing the historical peaks and valleys...",
        "📉 Surviving the bear traps and liquidation zones...",
        "📈 Riding the parabolic momentum curves...",
        "🛰️ Calibrating high-frequency antennas...",
        "💎 Polishing the institutional risk multipliers...",
        "📊 Plotting the private equity curves...",
        "🗺️ Mapping out the final risk audits...",
        "🏔️ Planting the Sherpa flag at the peak..."
    ];

    STATE.backtest.running = true;
    STATE.backtest.statusMessage = frames[0];
    renderView();

    let frameIdx = 1;
    const intervalId = setInterval(() => {
        if (STATE.backtest.running && frameIdx < frames.length) {
            STATE.backtest.statusMessage = frames[frameIdx];
            frameIdx++;
            renderView();
        } else {
            clearInterval(intervalId);
        }
    }, 1200);
    
    try {
        const res = await apiRequest('/backtest/run', 'POST', {
            strategy: strategy,
            capital: capital,
            risk_pct: risk
        });
        
        if (res && res.result) {
            STATE.backtest.result = res.result;
            if (res.result.max_drawdown > 25.0) {
                showToast("Warning: Max drawdown is >25%. Consider adjusting your Risk per Trade.", "warning");
            }
        }
    } catch (e) {
        console.error(e);
    } finally {
        STATE.backtest.running = false;
        clearInterval(intervalId);
        renderView();
    }
}

function resetBacktester() {
    STATE.backtest.result = null;
    renderView();
}

window.adjustBacktestDefaults = function(strategyName) {
    STATE.backtest.strategy = strategyName;
    const slider = document.getElementById('bt-risk');
    const label = document.getElementById('bt-risk-val');
    const capitalInput = document.getElementById('bt-capital');
    const submitBtn = document.getElementById('bt-submit-btn');
    const user = STATE.user || {};
    
    if (strategyName === 'Sherpa Velocity Pullback') {
        if (slider && label) {
            const risk = user.stock_risk_pct || 1.0;
            slider.value = risk;
            label.innerText = risk + '%';
        }
        if (capitalInput) {
            capitalInput.value = STATE.stock_balance ? Number(STATE.stock_balance).toFixed(2) : 10000;
        }
        if (submitBtn) {
            submitBtn.innerText = '▶ Run 5-Year Backtest';
        }
    } else {
        if (slider && label) {
            const risk = user.risk_pct || 1.0;
            slider.value = risk;
            label.innerText = risk + '%';
        }
        if (capitalInput) {
            capitalInput.value = STATE.crypto_balance ? Number(STATE.crypto_balance).toFixed(2) : 10000;
        }
        if (submitBtn) {
            submitBtn.innerText = '▶ Run 3-Year Backtest';
        }
    }
};

window.selectStrategy = function(strategy) {
    const input = document.getElementById('bt-strategy');
    if (input) input.value = strategy;
    window.adjustBacktestDefaults(strategy);
};

async function closeSinglePosition(id, type, symbol) {
    const res = await apiRequest('/trades/close', 'POST', { id, type, symbol });
    if (res) {
        showToast("Close signal submitted");
        handleRoute();
    }
}

async function panicCloseAll() {
    if (confirm("🚨 WARNING: This will panic-close EVERY active position immediately! Are you sure?")) {
        const res = await apiRequest('/trades/panic', 'POST');
        if (res) {
            showToast("PANIC CLOSE SUBMITTED", "error");
            handleRoute();
        }
    }
}

async function saveWallet() {
    const val = document.getElementById('wallet-addr').value.trim();
    const res = await apiRequest('/premium/wallet', 'POST', { source_wallet: val });
    if (res) {
        showToast("USDT source wallet registered");
        handleRoute();
    }
}

async function auditPayment() {
    const res = await apiRequest('/premium/check-payment', 'POST');
    if (res) {
        showToast(res.message, "warning");
    }
}

// ----------------- Starfield Particle Canvas -----------------
function initParticles() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    class Particle {
        constructor() {
            this.init();
        }
        init() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.size = Math.random() * 1.5 + 0.5;
            this.speedX = (Math.random() - 0.5) * 0.3;
            this.speedY = (Math.random() - 0.5) * 0.3;
            this.opacity = Math.random() * 0.4 + 0.1;
        }
        update() {
            this.x += this.speedX;
            this.y += this.speedY;
            if (this.x > canvas.width) this.x = 0;
            if (this.x < 0) this.x = canvas.width;
            if (this.y > canvas.height) this.y = 0;
            if (this.y < 0) this.y = canvas.height;
        }
        draw() {
            ctx.fillStyle = `rgba(60, 215, 255, ${this.opacity})`;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    function createParticles() {
        const count = Math.floor((canvas.width * canvas.height) / 20000);
        particles = [];
        for (let i = 0; i < count; i++) {
            particles.push(new Particle());
        }
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        requestAnimationFrame(animate);
    }

    window.addEventListener('resize', () => {
        resize();
        createParticles();
    });

    resize();
    createParticles();
    animate();
}

function bindEvents() {
    // Dynamic referral welcome banner injection if present
    const refCode = localStorage.getItem('referred_by');
    const bannerContainer = document.getElementById('referral-banner-container');
    if (refCode && bannerContainer) {
        apiRequest(`/referral/info?ref=${refCode}`).then(data => {
            if (data && data.name) {
                bannerContainer.innerHTML = `
                    <div class="glass-card w-full rounded-xl p-4 border border-tertiary/20 bg-tertiary/5 flex items-center gap-3 text-label-md mb-4 animation-fade-in text-left">
                        <span class="material-symbols-outlined text-tertiary text-2xl">group</span>
                        <div>
                            <p class="text-white font-bold">You were invited by <span class="text-tertiary">${data.name}</span></p>
                            <p class="text-on-surface-variant text-label-sm">Register & unlock 1 month of Premium when you upgrade!</p>
                        </div>
                    </div>
                `;
            }
        }).catch(err => console.error("Error loading referrer name:", err));
    }

    // Dynamic styles and event hooks on loaded HTML elements
    document.querySelectorAll('.glass-card').forEach(card => {
        card.addEventListener('touchstart', () => {
            card.style.transform = 'scale(0.98)';
            card.style.transition = 'transform 0.1s ease';
        }, { passive: true });
        card.addEventListener('touchend', () => {
            card.style.transform = 'scale(1)';
        });
    });

    // Automatically trigger toggleExchangeFields if the settings panel is rendered and exchange-id exists
    if (STATE.current_view === 'settings' && document.getElementById('exchange-id')) {
        window.toggleExchangeFields();
    }
}

// ----------------- Deployment Alert Notifier -----------------
// Ask for native browser push notification permissions on load if default
if (window.Notification && Notification.permission === "default") {
    Notification.requestPermission();
}

async function checkDeploymentAlert() {
    // Feature disabled - admin notifications and automatic reloads are turned off.
    return;
}

window.toggleProfileMenu = function(event) {
    if (event) event.stopPropagation();
    STATE.profile_menu_open = !STATE.profile_menu_open;
    renderView();
};

window.logoutUser = function() {
    STATE.profile_menu_open = false;
    handleLogout();
};

window.addEventListener('click', () => {
    if (STATE.profile_menu_open) {
        STATE.profile_menu_open = false;
        renderView();
    }
});

window.confirmClosePosition = function(id, type, symbol) {
    if (confirm(`🚨 WARNING: Are you sure you want to execute a Market Close order for ${symbol}?`)) {
        closeSinglePosition(id, type, symbol);
    }
};

window.togglePrivacySetting = async function() {
    const isCurrentlyHidden = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const newHideVal = !isCurrentlyHidden;
    
    const res = await apiRequest('/settings/preferences', 'POST', {
        risk_pct: STATE.user ? STATE.user.risk_pct : 1.0,
        stock_risk_pct: STATE.user ? STATE.user.stock_risk_pct : 1.0,
        hide_dollars: newHideVal
    });
    
    if (res) {
        if (STATE.user) {
            STATE.user.hide_dollars = newHideVal;
        }
        showToast(`Privacy mode switched ${newHideVal ? 'ON 🔒' : 'OFF 👁️'}`);
        renderView();
    }
};

function triggerConfetti() {
    const canvas = document.createElement('canvas');
    canvas.id = 'gift-confetti-canvas';
    canvas.style.position = 'fixed';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100vw';
    canvas.style.height = '100vh';
    canvas.style.zIndex = '99999';
    canvas.style.pointerEvents = 'none';
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    window.addEventListener('resize', () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    });

    const colors = ['#3cd7ff', '#ffdb3c', '#ff5a5f', '#a78bfa', '#34d399', '#fb923c'];
    const particles = [];

    for (let i = 0; i < 150; i++) {
        particles.push({
            x: Math.random() * width,
            y: Math.random() * height - height,
            r: Math.random() * 6 + 4,
            d: Math.random() * height,
            color: colors[Math.floor(Math.random() * colors.length)],
            tilt: Math.random() * 10 - 5,
            tiltAngleIncremental: Math.random() * 0.07 + 0.02,
            tiltAngle: 0
        });
    }

    let animationFrame;
    function draw() {
        ctx.clearRect(0, 0, width, height);
        let remaining = false;

        particles.forEach((p) => {
            p.tiltAngle += p.tiltAngleIncremental;
            p.y += (Math.cos(p.d) + 3 + p.r / 2) / 2;
            p.x += Math.sin(p.tiltAngle);
            p.tilt = Math.sin(p.tiltAngle - p.r / 2) * 5;

            if (p.y < height) {
                remaining = true;
            }

            ctx.beginPath();
            ctx.lineWidth = p.r;
            ctx.strokeStyle = p.color;
            ctx.moveTo(p.x + p.tilt + p.r / 2, p.y);
            ctx.lineTo(p.x + p.tilt, p.y + p.tilt + p.r / 2);
            ctx.stroke();
        });

        if (remaining) {
            animationFrame = requestAnimationFrame(draw);
        } else {
            try { document.body.removeChild(canvas); } catch(e) {}
        }
    }

    draw();

    setTimeout(() => {
        if (document.getElementById('gift-confetti-canvas')) {
            cancelAnimationFrame(animationFrame);
            try { document.body.removeChild(canvas); } catch(e) {}
        }
    }, 6000);
}

async function checkAndRedeemPendingGift() {
    const code = localStorage.getItem('pending_gift_code');
    if (!code || !STATE.user) return;
    
    localStorage.removeItem('pending_gift_code');
    
    try {
        const res = await apiRequest('/premium/redeem-gift', 'POST', { code });
        if (res && !res.error) {
            triggerConfetti();
            const profile = await apiRequest('/user/profile');
            if (profile) {
                STATE.user = profile;
            }
            showGiftSuccessModal(res.message || "Welcome to Institutional Premium!");
        } else {
            showToast(res.error || "Failed to redeem gift code.", "error");
        }
    } catch(err) {
        showToast("Error redeeming gift code.", "error");
    }
}

async function checkAndSyncPendingTelegram() {
    const tgSync = localStorage.getItem('pending_tg_sync');
    if (!tgSync || !STATE.user) return;
    
    // Clear the pending sync key to prevent repeating or looping
    localStorage.removeItem('pending_tg_sync');
    
    const parsedId = parseInt(tgSync);
    if (isNaN(parsedId)) return;
    
    if (STATE.user.telegram_chat_id === parsedId) {
        return;
    }
    
    try {
        const res = await apiRequest('/settings/telegram', 'POST', { telegram_chat_id: parsedId });
        if (res && !res.error) {
            STATE.user.telegram_chat_id = parsedId;
            showToast("Telegram account synced successfully!");
            renderView();
        } else {
            showToast(res.error || "Failed to sync Telegram account.", "error");
        }
    } catch (err) {
        showToast(err.message || "Failed to sync Telegram account.", "error");
    }
}

function showGiftSuccessModal(successMessage) {
    const backdrop = document.createElement('div');
    backdrop.id = 'gift-success-modal';
    backdrop.className = 'fixed inset-0 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md';
    backdrop.style.zIndex = '99999';
    backdrop.innerHTML = `
        <div class="glass-card max-w-[500px] w-full rounded-2xl p-8 text-center relative overflow-hidden flex flex-col items-center justify-center gap-6 animate-fade-in gold-glow" style="max-width: 500px;">
            <div class="absolute -top-24 -left-24 w-48 h-48 bg-primary/20 rounded-full blur-3xl pointer-events-none"></div>
            <div class="absolute -bottom-24 -right-24 w-48 h-48 bg-[#ffdb3c]/20 rounded-full blur-3xl pointer-events-none"></div>
            
            <div class="w-20 h-20 rounded-full bg-[#ffdb3c]/10 flex items-center justify-center border border-[#ffdb3c]/30 text-[#ffdb3c] animate-bounce">
                <span class="material-symbols-outlined text-5xl">workspace_premium</span>
            </div>
            
            <h2 class="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-primary to-[#ffdb3c]">
                Institutional Access Unlocked
            </h2>
            
            <p class="text-on-surface/80 leading-relaxed text-sm">
                Congratulations! You have successfully redeemed your gift code. Your account has been upgraded to the highest premium tier. Enjoy full access to all institutional-grade algorithms, theoretical baskets, and auto-pilot execution.
            </p>
            
            <div class="px-5 py-3 rounded-xl bg-surface-container/60 border border-white/5 text-[#ffdb3c] font-bold text-sm w-full">
                ${successMessage}
            </div>
            
            <button onclick="try { document.body.removeChild(document.getElementById('gift-success-modal')); } catch(e) {}; handleRoute();" class="mt-2 w-full h-12 bg-gradient-to-r from-primary to-[#ffdb3c] hover:opacity-90 active:scale-95 text-background font-bold rounded-xl transition-all shadow-lg neon-button-glow flex items-center justify-center gap-2">
                <span>Enter Institutional Terminal</span>
                <span class="material-symbols-outlined text-lg">arrow_forward</span>
            </button>
        </div>
    `;
    document.body.appendChild(backdrop);
}

window.generateAdminGiftCode = async function() {
    const container = document.getElementById('gift-generation-container');
    if (!container) return;
    
    const slider = document.getElementById('gift-duration-slider');
    const months = slider ? parseInt(slider.value) : 1;
    
    container.innerHTML = `
        <div class="flex items-center justify-center p-4">
            <div class="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
    `;
    
    try {
        const res = await apiRequest('/admin/generate-gift', 'POST', { months });
        if (res && res.code) {
            container.innerHTML = `
                <div class="space-y-3 animate-fade-in text-left mt-2">
                    <div class="bg-surface-container-low p-3 rounded-lg border border-white/5 space-y-1">
                        <span class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider block">Gift Code</span>
                        <div class="flex items-center justify-between gap-2">
                            <span class="font-mono text-sm text-[#ffdb3c] font-bold select-all">${res.code}</span>
                            <button onclick="navigator.clipboard.writeText('${res.code}').then(() => showToast('Gift Code copied!'))" class="text-xs text-primary font-bold hover:underline cursor-pointer">Copy</button>
                        </div>
                    </div>
                    
                    <div class="bg-surface-container-low p-3 rounded-lg border border-white/5 space-y-1">
                        <span class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider block">🌐 Web App Gift Link</span>
                        <div class="flex items-center justify-between gap-2">
                            <input type="text" readonly value="${res.web_gift_url}" autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-xs text-on-surface-variant font-mono border-none outline-none focus:ring-0 p-0 w-full select-all"/>
                            <button onclick="navigator.clipboard.writeText('${res.web_gift_url}').then(() => showToast('Web Gift Link copied!'))" class="text-xs text-primary font-bold hover:underline cursor-pointer">Copy</button>
                        </div>
                    </div>
                    
                    <div class="bg-surface-container-low p-3 rounded-lg border border-white/5 space-y-1">
                        <span class="text-[10px] text-on-surface-variant font-bold uppercase tracking-wider block">🤖 Telegram Bot Gift Link</span>
                        <div class="flex items-center justify-between gap-2">
                            <input type="text" readonly value="${res.tg_gift_url}" autocomplete="off" data-lpignore="true" data-1p-ignore style="background: transparent !important; -webkit-text-fill-color: inherit;" class="bg-transparent text-xs text-on-surface-variant font-mono border-none outline-none focus:ring-0 p-0 w-full select-all"/>
                            <button onclick="navigator.clipboard.writeText('${res.tg_gift_url}').then(() => showToast('Telegram Gift Link copied!'))" class="text-xs text-primary font-bold hover:underline cursor-pointer">Copy</button>
                        </div>
                    </div>
                    
                    <button onclick="renderView()" class="w-full h-9 bg-white/5 border border-white/10 text-on-surface text-xs font-bold rounded-lg hover:bg-white/10 transition-all cursor-pointer">
                        Generate Another Code
                    </button>
                </div>
            `;
            showToast("🎁 Universal Gift links generated successfully!");
        } else {
            showToast(res.error || "Failed to generate gift links", "error");
            renderView();
        }
    } catch(err) {
        showToast("Error generating gift links", "error");
        renderView();
    }
}



window.togglePasswordVisibility = function(inputId, btnElement) {
    const input = document.getElementById(inputId);
    const icon = btnElement.querySelector('span');
    if (input.type === 'password') {
        input.type = 'text';
        icon.innerText = 'visibility_off';
    } else {
        input.type = 'password';
        icon.innerText = 'visibility';
    }
};

window.toggleEmailNotifications = async function() {
    const user = STATE.user || {};
    const currentVal = user.email_notifications !== 0;
    const newVal = !currentVal;
    
    const res = await apiRequest('/settings/preferences', 'POST', {
        risk_pct: user.risk_pct || 1.0,
        stock_risk_pct: user.stock_risk_pct || 1.0,
        hide_dollars: user.hide_dollars !== false,
        email_notifications: newVal,
        email_frequency: user.email_frequency || 'realtime',
        browser_notifications: user.browser_notifications !== 0
    });
    
    if (res) {
        if (STATE.user) {
            STATE.user.email_notifications = newVal ? 1 : 0;
        }
        showToast(`Email Alerts switched ${newVal ? 'ON 🔔' : 'OFF 🔕'}`);
        renderView();
    }
};

window.setEmailFrequency = async function(freq) {
    const user = STATE.user || {};
    const res = await apiRequest('/settings/preferences', 'POST', {
        risk_pct: user.risk_pct || 1.0,
        stock_risk_pct: user.stock_risk_pct || 1.0,
        hide_dollars: user.hide_dollars !== false,
        email_notifications: user.email_notifications !== 0,
        email_frequency: freq,
        browser_notifications: user.browser_notifications !== 0
    });
    
    if (res) {
        if (STATE.user) {
            STATE.user.email_frequency = freq;
        }
        showToast(`Email alert frequency set to ${freq === 'realtime' ? 'Real-time ⚡' : 'Daily Summary 📅'}`);
        renderView();
    }
};

window.toggleBrowserNotifications = async function() {
    const user = STATE.user || {};
    const currentVal = user.browser_notifications !== 0;
    const newVal = !currentVal;
    
    if (newVal && window.Notification) {
        if (Notification.permission === 'default') {
            await Notification.requestPermission();
        }
    }
    
    const res = await apiRequest('/settings/preferences', 'POST', {
        risk_pct: user.risk_pct || 1.0,
        stock_risk_pct: user.stock_risk_pct || 1.0,
        hide_dollars: user.hide_dollars !== false,
        email_notifications: user.email_notifications !== 0,
        email_frequency: user.email_frequency || 'realtime',
        browser_notifications: newVal
    });
    
    if (res) {
        if (STATE.user) {
            STATE.user.browser_notifications = newVal ? 1 : 0;
        }
        showToast(`Browser Notifications switched ${newVal ? 'ON 🔔' : 'OFF 🔕'}`);
        renderView();
    }
};

window.shareStatsCard = function(tab, strategy) {
    const user = STATE.user || {};
    const refId = user.telegram_chat_id || user.id || "8";
    const refLink = `https://bot.metaversesherpa.io/#/register?ref=${refId}`;
    
    let title = "Your Crypto Performance Stats";
    if (tab === 'stock') {
        title = "Your Stocks Performance Stats";
    } else if (tab === 'free') {
        title = strategy ? `${strategy} Performance` : "Metaverse Sherpa Free Signals Performance";
    }
    
    // Prevent sharing card if personal stats are still loading
    if ((tab === 'crypto' || tab === 'stock') && (!STATE.stats || !STATE.stats[tab])) {
        showToast("Stats are still loading from the exchange, please wait a moment... 🏔️");
        return;
    }
    
    let url = `/api/share/card?type=stats&tab=${tab}`;
    if (strategy) {
        url += `&strategy=${encodeURIComponent(strategy)}`;
    }
    
    // Append pre-computed stats if available in STATE to bypass backend live fetches/DB calls
    if (tab === 'crypto' && STATE.stats && STATE.stats.crypto) {
        const stats = STATE.stats.crypto;
        const wr = stats.win_rate || 0;
        const total = stats.total_trades || 0;
        const overall = stats.overall_pnl_pct || 0;
        const daily = stats.overall_pnl_pct || 0; 
        url += `&overall_pnl_pct=${overall}&daily_pnl_pct=${daily}&win_rate=${wr}&total_trades=${total}`;
    } else if (tab === 'stock' && STATE.stats && STATE.stats.stock) {
        const stats = STATE.stats.stock;
        const wr = stats.win_rate || 0;
        const total = stats.total_trades || 0;
        const overall = stats.overall_pnl_pct || 0;
        const daily = stats.overall_pnl_pct || 0;
        url += `&overall_pnl_pct=${overall}&daily_pnl_pct=${daily}&win_rate=${wr}&total_trades=${total}`;
    } else if (tab === 'free' && STATE.free_stats) {
        if (strategy) {
            const strat = STATE.free_stats.strategies.find(s => s.name === strategy);
            if (strat) {
                const wr = strat.win_rate || 0;
                const total = (strat.wins || 0) + (strat.losses || 0);
                const overall = strat.realized_pct || 0;
                const daily = strat.realized_pct || 0;
                url += `&overall_pnl_pct=${overall}&daily_pnl_pct=${daily}&win_rate=${wr}&total_trades=${total}`;
            }
        } else {
            const strats = STATE.free_stats.strategies || [];
            let totalWins = 0, totalLosses = 0, sumRealized = 0;
            strats.forEach(s => {
                totalWins += (s.wins || 0);
                totalLosses += (s.losses || 0);
                sumRealized += (s.realized_pct || 0);
            });
            const total = totalWins + totalLosses;
            const wr = total > 0 ? (totalWins / total) * 100 : 0;
            const overall = sumRealized / (strats.length || 1);
            url += `&overall_pnl_pct=${overall}&daily_pnl_pct=${overall}&win_rate=${wr}&total_trades=${total}`;
        }
    }
    
    showShareCardModal(title, url, refLink);
};

window.shareTradeCard = function(type, symbol, side, roe, entry, mark, pnl) {
    const user = STATE.user || {};
    const refId = user.telegram_chat_id || user.id || "8";
    const refLink = `https://bot.metaversesherpa.io/#/register?ref=${refId}`;
    
    const title = `Share PnL Card - ${symbol}`;
    const url = `/api/share/card?type=trade&symbol=${encodeURIComponent(symbol)}&side=${encodeURIComponent(side)}&roe=${roe}&entry=${entry}&mark=${mark}&pnl_usdt=${pnl}`;
    
    showShareCardModal(title, url, refLink);
};

function showShareCardModal(title, cardApiUrl, refLink) {
    const modalId = 'share-card-modal';
    try {
        const existing = document.getElementById(modalId);
        if (existing) document.body.removeChild(existing);
    } catch(e) {}
    
    const backdrop = document.createElement('div');
    backdrop.id = modalId;
    backdrop.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in';
    
    backdrop.innerHTML = `
        <div class="glass-card rounded-2xl border border-white/10 w-full overflow-hidden flex flex-col gap-3 p-4 sm:p-5 relative animate-scale-up" style="max-width: 360px;">
            <div class="flex justify-between items-center pb-2 border-b border-white/10">
                <h3 class="font-bold text-on-surface text-base flex items-center gap-2">
                    <span class="material-symbols-outlined text-primary text-[20px]">share</span>
                    ${title}
                </h3>
                <button onclick="try { document.body.removeChild(document.getElementById('${modalId}')); } catch(e) {}" class="p-1.5 hover:bg-white/5 rounded-full text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer flex items-center justify-center">
                    <span class="material-symbols-outlined text-[20px]">close</span>
                </button>
            </div>
            
            <div id="share-card-content" class="flex flex-col items-center justify-center min-h-[250px] py-4">
                <div class="relative w-16 h-16 mb-4">
                    <div class="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                    <div class="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
                    <div class="absolute inset-0 flex items-center justify-center text-primary">
                        <span class="material-symbols-outlined text-2xl animate-pulse">image</span>
                    </div>
                </div>
                <p id="loading-spinner-text" class="text-xs text-on-surface-variant text-center transition-opacity duration-300">Generating your premium card...</p>
            </div>
        </div>
    `;
    
    document.body.appendChild(backdrop);
    
    const loadingText = document.getElementById('loading-spinner-text');
    let messageIndex = 0;
    const messages = [
        "Generating your premium card...",
        "Refer 3 people for 1 free month of Premium!",
        "Share with friends and family!"
    ];
    const loadingInterval = setInterval(() => {
        if (loadingText && document.body.contains(loadingText)) {
            messageIndex = (messageIndex + 1) % messages.length;
            loadingText.style.opacity = '0';
            setTimeout(() => {
                if (loadingText && document.body.contains(loadingText)) {
                    loadingText.innerText = messages[messageIndex];
                    loadingText.style.opacity = '1';
                }
            }, 300);
        } else {
            clearInterval(loadingInterval);
        }
    }, 2500);
    
    (async () => {
        try {
            const headers = {};
            const token = localStorage.getItem('session_token');
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            const res = await fetch(cardApiUrl, { headers });
            if (!res.ok) throw new Error("Failed to generate card");
            
            const blob = await res.blob();
            const objectUrl = URL.createObjectURL(blob);
            
            clearInterval(loadingInterval);
            const contentDiv = document.getElementById('share-card-content');
            if (contentDiv) {
                contentDiv.innerHTML = `
                    <div class="w-full rounded-xl overflow-hidden border border-white/10 relative shadow-2xl mb-3 bg-black/20 flex justify-center items-center">
                        <img src="${objectUrl}" class="w-full h-auto max-h-[60vh] object-contain rounded-xl" alt="PnL Card Preview" />
                    </div>
                    
                    <div class="w-full space-y-3">
                        <div class="flex gap-2">
                            <a href="${objectUrl}" download="sherpa_pnl_card.jpg" class="flex-1 h-11 bg-surface-container border border-white/10 text-on-surface font-semibold rounded-lg hover:bg-white/5 active:scale-95 transition-all text-xs flex items-center justify-center gap-2 cursor-pointer">
                                <span class="material-symbols-outlined text-[16px]">ios_share</span> Share Image
                            </a>
                            <button onclick="navigator.clipboard.writeText('${refLink}').then(() => showToast('Referral link copied!'))" class="flex-1 h-11 bg-surface-container border border-white/10 text-on-surface font-semibold rounded-lg hover:bg-white/5 active:scale-95 transition-all text-xs flex items-center justify-center gap-2 cursor-pointer">
                                <span class="material-symbols-outlined text-[16px]">link</span> Copy Invite Link
                            </button>
                        </div>
                        <p class="text-[10px] text-on-surface-variant text-center leading-normal">
                            Scan the QR code on the card or use your referral link to earn 30 days free Premium for every 3 members referred!
                        </p>
                    </div>
                `;
            }
        } catch(err) {
            clearInterval(loadingInterval);
            const contentDiv = document.getElementById('share-card-content');
            if (contentDiv) {
                contentDiv.innerHTML = `
                    <span class="material-symbols-outlined text-error text-5xl mb-3">error</span>
                    <p class="text-sm text-error font-semibold">Failed to load PnL card</p>
                    <p class="text-xs text-on-surface-variant text-center mt-1">Please ensure your exchange is connected or try again later.</p>
                `;
            }
        }
    })();
};

window.rawAdminLogs = { webapi: "", tradingbot: "" };

window.fetchAdminLogs = async function(service) {
    const container = document.getElementById(`${service}-logs-container`);
    if (!container) return;
    try {
        const res = await apiRequest(`/admin/logs?service=${service}`, 'GET');
        if (res && res.logs) {
            window.rawAdminLogs[service] = res.logs;
            window.renderAdminLogs(service);
        }
    } catch(e) {
        console.error(e);
    }
};

window.renderAdminLogs = function(service) {
    const container = document.getElementById(`${service}-logs-container`);
    const query = localStorage.getItem(`${service}_log_filter`) || "";
    if (!container) return;
    
    const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50;
    
    let rawLogs = window.rawAdminLogs[service] || "";
    let lines = rawLogs.split('\n');
    if (query) {
        const lowerQuery = query.toLowerCase();
        lines = lines.filter(line => line.toLowerCase().includes(lowerQuery));
    }
    
    let highlighted = lines.map(line => {
        let escaped = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        const lower = escaped.toLowerCase();
        
        // Coloring ERROR and WARNING
        escaped = escaped.replace(/(error)/gi, '<span class="text-[#ff4444] font-bold">$1</span>');
        escaped = escaped.replace(/(warning)/gi, '<span class="text-yellow-400 font-bold">$1</span>');
        
        // Highlight specific words
        escaped = escaped.replace(/(started|reloaded)/gi, '<b class="text-white font-black">$1</b>');
        
        let content = escaped;
        if (lower.includes('restarted') || lower.includes('reloaded') || lower.includes('restart') || lower.includes('reload') || lower.includes('starting') || lower.includes('stopping') || lower.includes('started') || lower.includes('stopped')) {
            content = `<span class="bg-[#ff4444]/30 text-[#ff4444] px-1 rounded font-bold">${escaped}</span>`;
        }
        return `<div class="hover:bg-white/10 cursor-pointer px-1 -mx-1 rounded transition-colors select-text" onclick="copyLogLine(this)" title="Click to copy line">${content}</div>`;
    }).join('');
    
    container.innerHTML = highlighted;
    if (isScrolledToBottom) {
        container.scrollTop = container.scrollHeight;
    }
};

window.promptLogFilter = function(service) {
    const currentFilter = localStorage.getItem(`${service}_log_filter`) || "";
    const promptText = prompt(`Enter text to filter ${service === 'webapi' ? 'Web API' : 'Trading Bot'} logs (leave blank to clear):`, currentFilter);
    if (promptText !== null) {
        if (promptText.trim() === '') {
            localStorage.removeItem(`${service}_log_filter`);
            window.showToast("Filter cleared.", "success");
        } else {
            localStorage.setItem(`${service}_log_filter`, promptText.trim());
            window.showToast("Filter applied.", "success");
        }
        renderView(); 
        window.renderAdminLogs(service); 
    }
};

window.copyLogLine = function(element) {
    const selection = window.getSelection().toString();
    if (selection) {
        return; // User is highlighting text manually
    }
    const text = element.innerText;
    navigator.clipboard.writeText(text).then(() => {
        window.showToast("Line copied to clipboard!", 'success');
    }).catch(err => {
        window.showToast("Failed to copy line: " + err, 'error');
    });
};

window.copyLogs = function(service) {
    const container = document.getElementById(`${service}-logs-container`);
    if (!container) return;
    
    let textToCopy = container.innerText;
    
    if (!textToCopy.trim()) {
        window.showToast("No logs to copy", "error");
        return;
    }
    
    navigator.clipboard.writeText(textToCopy).then(() => {
        window.showToast(onlyRestarts ? "Restart events copied!" : "All logs copied!", 'success');
    }).catch(err => {
        window.showToast("Failed to copy text: " + err, 'error');
    });
};

window.restartService = async function(service) {
    if (!confirm(`Are you sure you want to restart ${service}?`)) return;
    try {
        const res = await apiRequest('/admin/restart', 'POST', { service });
        if (res && (res.message || res.error)) {
            alert(res.message || res.error);
        }
    } catch (e) {
        alert("Failed to restart service.");
    }
};

if (!window.adminLogsPollerInitialized) {
    setInterval(() => {
        const isMobile = window.innerWidth <= 768;
        const activeTab = window.adminLogsMobileTab || 'webapi';
        
        if (document.getElementById('webapi-logs-container')) {
            if (!isMobile || activeTab === 'webapi') {
                window.fetchAdminLogs('webapi');
            }
        }
        if (document.getElementById('tradingbot-logs-container')) {
            if (!isMobile || activeTab === 'tradingbot') {
                window.fetchAdminLogs('tradingbot');
            }
        }
    }, 5000);
    window.adminLogsPollerInitialized = true;
}
