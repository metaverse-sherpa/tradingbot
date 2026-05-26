const API_BASE = '/api';

let STATE = {
    user: null,
    crypto_balance: 12450.0,
    stock_balance: 0.0,
    total_balance: 12450.0,
    open_trades: [],
    history: [],
    active_signals: [],
    closed_signals: [],
    stats: { wins: 14, losses: 5, win_rate: 72.5, cumulative_pnl: 342.10, profit_factor: 2.45 },
    current_view: 'login',
    backtest: { running: false, result: null, period: '3 Years', capital: 1000, strategy: 'Mean Reversion Scalper' }
};

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
        toast.classList.remove('translate-y-2', 'opacity-0');
    }, 10);
    
    setTimeout(() => {
        toast.classList.add('translate-y-2', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
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
    const token = localStorage.getItem('session_token');
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(url, options);
        if (response.status === 401 && window.location.hash !== '#/login' && window.location.hash !== '#/register') {
            // Unauthorized → redirect to login
            STATE.user = null;
            navigate('#/login');
            return null;
        }
        
        const resData = await response.json();
        if (!response.ok) {
            throw new Error(resData.error || "Something went wrong");
        }
        return resData;
    } catch (err) {
        showToast(err.message, "error");
        return null;
    }
}

// ----------------- Google Sign In Initialization -----------------
async function initGoogleSignIn() {
    // Fetch the client ID from the backend securely so it's not hardcoded in the frontend repository
    const config = await apiRequest('/config', 'GET');
    const clientId = config ? config.google_client_id : null;
    
    if (!clientId) {
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
            if (window.google) {
                window.google.accounts.id.initialize({
                    client_id: clientId,
                    callback: handleGoogleCredentialResponse
                });
            }
        };
        document.head.appendChild(script);
    }
}

async function handleGoogleCredentialResponse(response) {
    const credential = response.credential;
    const res = await apiRequest('/auth/google', 'POST', { credential });
    if (res) {
        STATE.user = res.user;
        if (res.token) localStorage.setItem('session_token', res.token);
        showToast("Logged in with Google!");
        navigate('#/dashboard');
    }
}

// ----------------- Routing & View Management -----------------
function navigate(hash) {
    window.location.hash = hash;
}

async function handleRoute() {
    const hash = window.location.hash || '#/dashboard';
    
    // Auth Guard
    if (hash === '#/login' || hash === '#/register') {
        STATE.current_view = hash.substring(2);
        renderView();
        if (STATE.current_view === 'login') {
            initGoogleSignIn();
        }
        return;
    }
    
    // Fetch profile status on every navigation to keep session sync
    const profile = await apiRequest('/user/profile');
    if (!profile) {
        // Redirection handled by apiRequest if unauthorized
        return;
    }
    STATE.user = profile;
    
    // Determine view route
    if (hash === '#/dashboard') {
        STATE.current_view = 'dashboard';
        const bal = await apiRequest('/user/balance');
        if (bal) {
            STATE.crypto_balance = bal.crypto_balance;
            STATE.stock_balance = bal.stock_balance;
            STATE.total_balance = bal.total_balance;
        }
        const sigs = await apiRequest('/signals/active');
        if (sigs) STATE.active_signals = sigs;
    } else if (hash === '#/trades') {
        STATE.current_view = 'trades';
        const open = await apiRequest('/trades/open');
        if (open) STATE.open_trades = open;
    } else if (hash === '#/history') {
        STATE.current_view = 'history';
        const hist = await apiRequest('/trades/history');
        if (hist) STATE.history = hist;
    } else if (hash === '#/stats') {
        STATE.current_view = 'stats';
        const stats = await apiRequest('/user/stats');
        if (stats) STATE.stats = stats;
    } else if (hash === '#/settings') {
        STATE.current_view = 'settings';
    } else if (hash === '#/strategy') {
        STATE.current_view = 'strategy';
    } else if (hash === '#/backtest') {
        STATE.current_view = 'backtest';
    } else if (hash === '#/signals') {
        STATE.current_view = 'signals';
        const active = await apiRequest('/signals/active');
        if (active) STATE.active_signals = active;
        const closed = await apiRequest('/signals/closed');
        if (closed) STATE.closed_signals = closed;
    } else if (hash === '#/premium') {
        STATE.current_view = 'premium';
    } else if (hash === '#/referral') {
        STATE.current_view = 'referral';
        const ref = await apiRequest('/referral/stats');
        if (ref) {
            STATE.user.referral_count = ref.referral_count;
            STATE.user.referral_credits = ref.referral_credits;
            STATE.user.invite_link = ref.invite_link;
        }
    } else if (hash === '#/help') {
        STATE.current_view = 'help';
    }
    
    renderView();
}

window.addEventListener('hashchange', handleRoute);
window.addEventListener('load', () => {
    handleRoute();
    initParticles();
});

// ----------------- Bottom Navigation Component -----------------
function renderBottomNav() {
    if (['login', 'register'].includes(STATE.current_view)) return '';
    
    return `
        <nav class="fixed bottom-0 left-0 w-full z-50 pb-safe bg-surface-container/90 backdrop-blur-[40px] border-t border-white/10 shadow-[0_-4px_20px_rgba(0,0,0,0.4)] flex justify-around items-center h-16 px-4">
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'dashboard' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200" href="#/dashboard">
                <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' ${STATE.current_view === 'dashboard' ? 1 : 0};">dashboard</span>
                <span class="font-label-sm text-label-sm">Dashboard</span>
            </a>
            <a class="flex flex-col items-center justify-center ${['trades', 'history'].includes(STATE.current_view) ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200" href="#/trades">
                <span class="material-symbols-outlined">swap_horiz</span>
                <span class="font-label-sm text-label-sm">Trades</span>
            </a>
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'stats' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200" href="#/stats">
                <span class="material-symbols-outlined">query_stats</span>
                <span class="font-label-sm text-label-sm">Stats</span>
            </a>
            <a class="flex flex-col items-center justify-center ${STATE.current_view === 'settings' ? 'text-primary relative after:content-[\'\'] after:absolute after:-bottom-1 after:w-1 after:h-1 after:bg-primary after:rounded-full after:shadow-[0_0_8px_#3cd7ff]' : 'text-on-surface-variant/60 hover:text-primary'} transition-colors duration-200" href="#/settings">
                <span class="material-symbols-outlined">settings</span>
                <span class="font-label-sm text-label-sm">Settings</span>
            </a>
        </nav>
    `;
}

// ----------------- Header Component -----------------
function renderHeader(title) {
    return `
        <header class="fixed top-0 left-0 w-full z-50 bg-surface/80 backdrop-blur-xl border-b border-white/10 shadow-[0_2px_10px_rgba(0,212,255,0.1)] flex justify-between items-center px-container-margin py-3">
            <div class="font-headline-sm text-headline-sm font-bold text-primary tracking-tight flex items-center gap-2">
                <span class="material-symbols-outlined text-primary" style="font-variation-settings: 'FILL' 1;">terrain</span>
                Metaverse Sherpa
            </div>
            <div class="flex items-center gap-4">
                <a class="text-on-surface-variant hover:opacity-80 transition-opacity" href="#/help">
                    <span class="material-symbols-outlined">help</span>
                </a>
                <div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center font-bold text-primary border border-primary/30 text-sm">
                    ${STATE.user ? STATE.user.email[0].toUpperCase() : 'U'}
                </div>
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
                <p class="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest opacity-80">Institutional-Grade AI Trading</p>
            </header>
            
            <div class="mb-10 text-center">
                <h2 class="font-display-lg text-display-lg text-white font-bold leading-tight">Trade Smarter.<br/>Not Harder.</h2>
            </div>
            
            <div class="glass-card w-full rounded-xl p-card-padding flex flex-col gap-stack-gap">
                <!-- Google Authentication Hook -->
                <button onclick="triggerGoogleLogin()" class="w-full h-12 bg-white text-surface-dim font-label-md text-label-md rounded-full flex items-center justify-center gap-3 hover:bg-white/90 transition-colors">
                    <svg height="20" viewbox="0 0 24 24" width="20">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"></path>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"></path>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"></path>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z" fill="#EA4335"></path>
                    </svg>
                    Continue with Google
                </button>
                
                <div class="flex items-center gap-4 py-1">
                    <div class="h-[1px] flex-1 bg-white/10"></div>
                    <span class="font-label-sm text-label-sm text-on-surface-variant/50">or</span>
                    <div class="h-[1px] flex-1 bg-white/10"></div>
                </div>
                
                <form id="login-form" class="space-y-4" onsubmit="handleEmailLogin(event)">
                    <input id="login-email" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <input id="login-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
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
            
            <div class="glass-card w-full rounded-xl p-card-padding flex flex-col gap-stack-gap">
                <form id="register-form" class="space-y-4" onsubmit="handleEmailRegister(event)">
                    <input id="reg-name" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Full Name" type="text" required/>
                    <input id="reg-email" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <input id="reg-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                    
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

function renderDashboardView() {
    const isPremium = STATE.user && STATE.user.is_premium;
    const activeStrategy = STATE.user ? (STATE.user.active_crypto_strategy || 'Mean Reversion Scalper') : 'Mean Reversion Scalper';
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <!-- Tier Badge -->
            <div class="flex justify-start">
                <div class="inline-flex items-center gap-1.5 px-3 py-1 glass-card ${isPremium ? 'gold-glow' : 'cyan-glow'} rounded-full">
                    <span class="text-[10px]">${isPremium ? '💎' : '🥈'}</span>
                    <span class="font-label-sm text-label-sm ${isPremium ? 'text-secondary-container' : 'text-primary'}">${isPremium ? 'Premium' : 'Standard'}</span>
                </div>
            </div>
            
            <!-- Balance Card -->
            <section class="glass-card cyan-glow rounded-xl p-card-padding relative overflow-hidden">
                <div class="absolute -right-10 -top-10 w-32 h-32 bg-primary/10 blur-3xl rounded-full"></div>
                <div class="relative z-10">
                    <p class="font-label-md text-label-md text-on-surface-variant mb-1">Total Equity</p>
                    <h1 class="font-display-lg text-display-lg text-on-surface drop-shadow-[0_0_12px_rgba(168,232,255,0.15)]">$${STATE.total_balance.toFixed(2)}</h1>
                    <div class="flex flex-wrap gap-2 mt-4">
                        <div class="bg-tertiary-container/20 text-tertiary px-2 py-1 rounded-lg flex items-center gap-1">
                            <span class="material-symbols-outlined text-[14px]">trending_up</span>
                            <span class="font-label-sm text-label-sm">+$${STATE.stats.cumulative_pnl.toFixed(2)} Today</span>
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- Quick Stats -->
            <section class="grid grid-cols-2 gap-stack-gap">
                <div class="glass-card rounded-lg p-3 text-center border-t-2 border-primary/40">
                    <p class="font-label-sm text-label-sm text-on-surface-variant mb-1">Open Trades</p>
                    <p class="font-numeric-data text-numeric-data text-primary">${STATE.open_trades.length}</p>
                </div>
                <div class="glass-card rounded-lg p-3 text-center border-t-2 border-tertiary/40">
                    <p class="font-label-sm text-label-sm text-on-surface-variant mb-1">Win Rate</p>
                    <p class="font-numeric-data text-numeric-data text-tertiary">${STATE.stats.win_rate}%</p>
                </div>
            </section>
            
            <!-- Strategy Banner -->
            <section class="bg-surface-container-high rounded-xl p-4 flex items-center justify-between border border-white/5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                        <span class="material-symbols-outlined">query_stats</span>
                    </div>
                    <div>
                        <p class="font-label-sm text-label-sm text-on-surface-variant">Active Strategy</p>
                        <p class="font-body-lg text-body-lg font-bold text-on-surface">🪙 ${activeStrategy}</p>
                    </div>
                </div>
                <a class="font-label-md text-label-md text-primary hover:underline" href="#/strategy">Change</a>
            </section>
            
            <!-- Action Grid -->
            <section class="grid grid-cols-2 gap-stack-gap">
                <a href="#/trades" class="glass-card rounded-xl p-5 flex flex-col items-center gap-3 hover:bg-white/5 transition-colors group text-center">
                    <span class="material-symbols-outlined text-primary text-3xl group-hover:scale-110 transition-transform">data_exploration</span>
                    <span class="font-label-md text-label-md text-on-surface font-semibold">Live Trades</span>
                </a>
                <a href="#/history" class="glass-card rounded-xl p-5 flex flex-col items-center gap-3 hover:bg-white/5 transition-colors group text-center">
                    <span class="material-symbols-outlined text-primary text-3xl group-hover:scale-110 transition-transform">history</span>
                    <span class="font-label-md text-label-md text-on-surface font-semibold">Trade History</span>
                </a>
                <a href="#/stats" class="glass-card rounded-xl p-5 flex flex-col items-center gap-3 hover:bg-white/5 transition-colors group text-center">
                    <span class="material-symbols-outlined text-primary text-3xl group-hover:scale-110 transition-transform">insights</span>
                    <span class="font-label-md text-label-md text-on-surface font-semibold">My Stats</span>
                </a>
                <a href="#/backtest" class="glass-card rounded-xl p-5 flex flex-col items-center gap-3 hover:bg-white/5 transition-colors group text-center">
                    <span class="material-symbols-outlined text-primary text-3xl group-hover:scale-110 transition-transform">science</span>
                    <span class="font-label-md text-label-md text-on-surface font-semibold">Backtest</span>
                </a>
                <a href="#/signals" class="glass-card rounded-xl p-5 flex flex-col items-center gap-3 hover:bg-white/5 transition-colors group text-center col-span-2">
                    <span class="material-symbols-outlined text-primary text-3xl group-hover:scale-110 transition-transform">satellite_alt</span>
                    <span class="font-label-md text-label-md text-on-surface font-semibold">Free Alpha Signals</span>
                </a>
            </section>
        </main>
    `;
}

function renderTradesView() {
    let listHtml = '';
    if (STATE.open_trades.length === 0) {
        listHtml = `
            <div class="text-center py-12">
                <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">hourglass_empty</span>
                <p class="font-body-lg text-body-lg text-on-surface font-semibold">No open positions</p>
                <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">The Sherpa engine is scanning the markets...</p>
            </div>
        `;
    } else {
        listHtml = STATE.open_trades.map(trade => `
            <div class="glass-card rounded-xl p-card-padding flex flex-col gap-3 relative overflow-hidden border border-white/10">
                <div class="flex justify-between items-center">
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">${trade.symbol}</h3>
                    <span class="px-2.5 py-0.5 rounded text-[10px] font-bold ${
                        trade.side === 'LONG' ? 'bg-tertiary-fixed-dim/20 text-tertiary' : 'bg-error-container/20 text-error'
                    }">${trade.side}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 text-sm">
                    <div>
                        <span class="text-on-surface-variant">Entry Price:</span>
                        <span class="text-on-surface font-medium">$${trade.entry_price}</span>
                    </div>
                    <div>
                        <span class="text-on-surface-variant">Qty:</span>
                        <span class="text-on-surface font-medium">${trade.qty}</span>
                    </div>
                </div>
                <div class="flex justify-between items-end border-t border-white/5 pt-2">
                    <div>
                        <p class="text-xs text-on-surface-variant">Unrealized PnL</p>
                        <p class="text-lg font-bold ${trade.unrealized_pnl >= 0 ? 'text-tertiary' : 'text-error'}">
                            ${trade.unrealized_pnl >= 0 ? '+' : ''}$${trade.unrealized_pnl.toFixed(2)} (${trade.roe}%)
                        </p>
                    </div>
                    <button onclick="closeSinglePosition('${trade.id}', '${trade.type}')" class="px-3 py-1.5 rounded-lg border border-error/40 hover:bg-error/10 text-error text-xs font-semibold">
                        Close
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="flex justify-between items-center">
                <div>
                    <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Active Positions</h2>
                    <p class="font-label-sm text-label-sm text-on-surface-variant">${STATE.open_trades.length} trades open</p>
                </div>
                <button onclick="handleRoute()" class="text-primary hover:opacity-80">
                    <span class="material-symbols-outlined">refresh</span>
                </button>
            </div>
            
            <div class="space-y-stack-gap">
                ${listHtml}
            </div>
            
            ${STATE.open_trades.length > 0 ? `
                <button onclick="panicCloseAll()" class="w-full h-12 bg-red-900/40 text-error font-label-md text-label-md font-bold rounded-lg border border-error/50 hover:bg-error/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                    <span class="material-symbols-outlined">warning</span>
                    🚨 PANIC - Close All Positions
                </button>
            ` : ''}
        </main>
    `;
}

function renderHistoryView() {
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">📜 History</h2>
            
            <div class="glass-card rounded-xl p-card-padding">
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="border-b border-white/10 text-xs text-on-surface-variant uppercase font-semibold">
                                <th class="pb-2">Symbol</th>
                                <th class="pb-2">Side</th>
                                <th class="pb-2">PnL</th>
                                <th class="pb-2">Date</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-white/5 text-sm">
                            ${STATE.history.map(tr => `
                                <tr>
                                    <td class="py-3 font-semibold text-on-surface">${tr.symbol}</td>
                                    <td class="py-3 font-medium ${tr.side === 'LONG' ? 'text-tertiary' : 'text-error'}">${tr.side}</td>
                                    <td class="py-3 font-bold ${tr.pnl_raw >= 0 ? 'text-tertiary' : 'text-error'}">
                                        ${tr.pnl_raw >= 0 ? '+' : ''}$${tr.pnl_raw.toFixed(2)}
                                    </td>
                                    <td class="py-3 text-xs text-on-surface-variant">Just now</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </main>
    `;
}

function renderStatsView() {
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">📊 Performance</h2>
            
            <div class="glass-card rounded-xl p-6 text-center border-t-2 border-primary/40 relative overflow-hidden">
                <div class="inline-flex items-center justify-center w-24 h-24 rounded-full border-4 border-tertiary shadow-[0_0_15px_rgba(0,255,136,0.3)] mb-4">
                    <span class="text-2xl font-bold text-on-surface">${STATE.stats.win_rate}%</span>
                </div>
                <h3 class="text-on-surface-variant font-label-md text-label-md uppercase tracking-wider">Overall Win Rate</h3>
                <p class="text-on-surface font-numeric-data text-numeric-data mt-2">
                    ${STATE.stats.wins} Wins / ${STATE.stats.losses} Losses
                </p>
            </div>
            
            <div class="grid grid-cols-2 gap-stack-gap">
                <div class="glass-card rounded-lg p-4">
                    <p class="text-xs text-on-surface-variant">Cumulative PnL</p>
                    <p class="text-xl font-bold text-tertiary mt-1">+$${STATE.stats.cumulative_pnl.toFixed(2)}</p>
                </div>
                <div class="glass-card rounded-lg p-4">
                    <p class="text-xs text-on-surface-variant">Profit Factor</p>
                    <p class="text-xl font-bold text-secondary-container mt-1">${STATE.stats.profit_factor}</p>
                </div>
            </div>
        </main>
    `;
}

function renderSettingsView() {
    const user = STATE.user || {};
    const isActive = user.is_active;
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">⚙️ Settings</h2>
            
            <!-- Bot Status Panel -->
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
            
            <!-- Connect Exchange Wizard -->
            <section class="glass-card rounded-xl p-card-padding space-y-4">
                <h3 class="font-body-lg text-body-lg font-bold text-on-surface">🔌 Connect Exchange (Blofin)</h3>
                <form onsubmit="handleExchangeSetup(event)" class="space-y-3">
                    <input id="api-key" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="API Key" type="text" required/>
                    <input id="api-secret" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="API Secret" type="password" required/>
                    <input id="api-password" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="Passphrase" type="password" required/>
                    <button type="submit" class="w-full h-11 bg-primary-container text-on-primary-container font-label-md text-label-md font-bold rounded-lg hover:brightness-110 transition-all mt-2">
                        Save Keys
                    </button>
                </form>
            </section>
            
            <!-- Telegram Sync -->
            <section class="glass-card rounded-xl p-card-padding space-y-4">
                <h3 class="font-body-lg text-body-lg font-bold text-on-surface">📱 Telegram Sync</h3>
                <p class="text-xs text-on-surface-variant">Sync your web account with the Telegram bot to receive live signals and portfolio updates. Send /start to the bot to get your Chat ID.</p>
                <form onsubmit="handleTelegramSetup(event)" class="space-y-3">
                    <input id="telegram-chat-id" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="Telegram Chat ID (e.g. 123456789)" type="text" value="${user.telegram_chat_id || ''}" required/>
                    <button type="submit" class="w-full h-11 bg-secondary-container text-on-secondary-container font-label-md text-label-md font-bold rounded-lg hover:brightness-110 transition-all mt-2">
                        Link Telegram
                    </button>
                </form>
            </section>
            
            <!-- Risk Sizing Slider -->
            <section class="glass-card rounded-xl p-card-padding space-y-4">
                <h3 class="font-body-lg text-body-lg font-bold text-on-surface">⚖️ Risk & Sizing</h3>
                <div class="space-y-2">
                    <div class="flex justify-between text-sm">
                        <span class="text-on-surface-variant">Crypto Risk per Trade</span>
                        <span id="risk-val" class="text-primary font-bold">${user.risk_pct || '1.0'}%</span>
                    </div>
                    <input id="risk-slider" class="w-full accent-primary bg-white/10 h-1.5 rounded-lg appearance-none cursor-pointer" type="range" min="0.5" max="5" step="0.1" value="${user.risk_pct || '1.0'}" oninput="document.getElementById('risk-val').innerText = this.value + '%'"/>
                </div>
                <button onclick="savePreferences()" class="w-full h-11 bg-surface-container text-on-surface font-label-md text-label-md border border-white/10 rounded-lg hover:bg-white/5 transition-all">
                    Apply Sizing
                </button>
            </section>

            <!-- Premium & Referral Buttons -->
            <section class="grid grid-cols-2 gap-stack-gap">
                <a href="#/premium" class="glass-card rounded-lg p-4 flex flex-col items-center gap-2 hover:bg-white/5 transition-colors text-center">
                    <span class="material-symbols-outlined text-secondary-container text-2xl">diamond</span>
                    <span class="text-xs font-semibold text-on-surface">Premium Plan</span>
                </a>
                <a href="#/referral" class="glass-card rounded-lg p-4 flex flex-col items-center gap-2 hover:bg-white/5 transition-colors text-center">
                    <span class="material-symbols-outlined text-tertiary text-2xl">diversity_3</span>
                    <span class="text-xs font-semibold text-on-surface">Refer & Earn</span>
                </a>
            </section>

            <!-- Logout Link -->
            <button onclick="handleLogout()" class="w-full py-3 bg-red-950/20 text-error font-bold rounded-lg border border-error/30 hover:bg-red-950/40 text-center">
                Logout Session
            </button>
        </main>
    `;
}

function renderStrategyView() {
    const user = STATE.user || {};
    const current = user.active_crypto_strategy || 'Mean Reversion Scalper';
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">⚖️ Strategy</h2>
            
            <div class="glass-card rounded-xl p-card-padding border-t-2 border-primary/40">
                <p class="text-xs text-on-surface-variant uppercase">Current Active</p>
                <h3 class="text-lg font-bold text-on-surface mt-1">🪙 ${current}</h3>
            </div>
            
            <div class="space-y-stack-gap">
                <button onclick="changeStrategy('Mean Reversion Scalper')" class="w-full glass-card rounded-xl p-4 flex justify-between items-center hover:bg-white/5 text-left border ${current === 'Mean Reversion Scalper' ? 'border-primary' : 'border-white/10'}">
                    <div>
                        <h4 class="font-semibold text-on-surface">Mean Reversion Scalper</h4>
                        <p class="text-xs text-on-surface-variant mt-1">Scalps volatile assets under extreme RSI overbought/oversold boundaries.</p>
                    </div>
                    ${current === 'Mean Reversion Scalper' ? '<span class="material-symbols-outlined text-primary">check_circle</span>' : ''}
                </button>
                
                <button onclick="changeStrategy('Sherpa Velocity Pullback')" class="w-full glass-card rounded-xl p-4 flex justify-between items-center hover:bg-white/5 text-left border ${current === 'Sherpa Velocity Pullback' ? 'border-primary' : 'border-white/10'}">
                    <div>
                        <h4 class="font-semibold text-on-surface">Sherpa Velocity Pullback</h4>
                        <p class="text-xs text-on-surface-variant mt-1">Captures high-volume momentum trends with strict trailing stops.</p>
                    </div>
                    ${current === 'Sherpa Velocity Pullback' ? '<span class="material-symbols-outlined text-primary">check_circle</span>' : ''}
                </button>
            </div>
        </main>
    `;
}

function renderBacktestView() {
    const bt = STATE.backtest;
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🔬 Backtest Engine</h2>
            
            ${bt.running ? `
                <div class="glass-card rounded-xl p-8 text-center space-y-4">
                    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-primary border-t-transparent mb-2"></div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Sherpa Engine is Crunching Alpha...</h3>
                    <p class="text-xs text-on-surface-variant">Scanning 3 years of historical market candles...</p>
                </div>
            ` : bt.result ? `
                <div class="glass-card rounded-xl p-card-padding space-y-4">
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Backtest Complete!</h3>
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
                            <p class="text-xs text-on-surface-variant">Net PnL</p>
                            <p class="text-lg font-bold text-tertiary">+$${bt.result.net_pnl.toFixed(2)}</p>
                        </div>
                        <div class="bg-surface-container rounded-lg p-3 text-center">
                            <p class="text-xs text-on-surface-variant">Profit Factor</p>
                            <p class="text-lg font-bold text-secondary-container">${bt.result.profit_factor}</p>
                        </div>
                    </div>
                    <button onclick="resetBacktester()" class="w-full h-11 bg-primary-container text-on-primary-container font-bold rounded-lg hover:brightness-110 transition-all">
                        Run New Backtest
                    </button>
                </div>
            ` : `
                <div class="glass-card rounded-xl p-card-padding space-y-4">
                    <div class="space-y-2">
                        <label class="text-xs text-on-surface-variant font-semibold uppercase">Strategy</label>
                        <select id="bt-strategy" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4">
                            <option value="Mean Reversion Scalper">Mean Reversion Scalper</option>
                            <option value="Sherpa Velocity Pullback">Sherpa Velocity Pullback</option>
                        </select>
                    </div>
                    <button onclick="triggerBacktest()" class="w-full h-11 bg-primary-container text-on-primary-container font-bold rounded-lg hover:brightness-110 transition-all">
                        ▶ Run 3-Year Backtest
                    </button>
                </div>
            `}
        </main>
    `;
}

function renderSignalsView() {
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Alpha Signals</h2>
            
            <div class="space-y-stack-gap">
                ${STATE.active_signals.map(sig => `
                    <div class="glass-card rounded-xl p-card-padding border border-white/10 flex justify-between items-center">
                        <div>
                            <h4 class="font-bold text-on-surface">${sig.symbol}</h4>
                            <p class="text-xs text-on-surface-variant mt-1">${sig.strategy}</p>
                            <p class="text-xs text-tertiary mt-2">Entry target: $${sig.entry_price}</p>
                        </div>
                        <span class="px-2.5 py-0.5 rounded text-[10px] font-bold bg-tertiary-fixed-dim/20 text-tertiary uppercase">Active</span>
                    </div>
                `).join('')}
            </div>
        </main>
    `;
}

function renderPremiumView() {
    const user = STATE.user || {};
    const isPremium = user.is_premium;
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
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
                <div class="bg-surface-container rounded-lg p-3 border border-white/5 space-y-2">
                    <p class="text-xs text-on-surface-variant uppercase">USDT TRC-20 Treasury</p>
                    <p class="text-sm font-mono text-on-surface select-all overflow-x-auto whitespace-nowrap">TY1V64xJc24abG9aq4UXGeMJtvPhSDCgoj</p>
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
    const inviteLink = user.invite_link || `https://metaversesherpa.io/#/register?ref=${user.id}`;
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
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
                <h4 class="font-semibold text-on-surface">Your Personal Invite Link</h4>
                <div class="flex gap-2">
                    <input class="flex-1 h-11 bg-surface-container-low text-on-surface text-xs font-mono border border-white/10 rounded-lg px-4 select-all" type="text" readonly value="${inviteLink}"/>
                    <button onclick="navigator.clipboard.writeText('${inviteLink}').then(() => showToast('Invite link copied!'))" class="h-11 px-3 bg-surface-container border border-white/10 rounded-lg text-primary hover:bg-white/5">
                        Copy
                    </button>
                </div>
            </div>
        </main>
    `;
}

function renderHelpView() {
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">❓ User Manual</h2>
            
            <div class="space-y-stack-gap">
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface">🚀 Fast Exchange Connection</h3>
                    <p class="text-xs text-on-surface-variant mt-2 leading-relaxed">
                        To activate autonomous copy-trading, go to Settings, paste your API credentials from Blofin or Alpaca, configure your target risk size per signal, and toggle "Start Bot".
                    </p>
                </div>
                <div class="glass-card rounded-xl p-card-padding">
                    <h3 class="font-bold text-on-surface">🔒 Cryptographic Security</h3>
                    <p class="text-xs text-on-surface-variant mt-2 leading-relaxed">
                        All exchange API secrets are encrypted server-side using multi-layer Fernet keys. The bot possesses zero permission to withdraw assets from your exchange.
                    </p>
                </div>
            </div>
        </main>
    `;
}

// ----------------- Event Handlers & Forms -----------------
async function handleEmailLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    const res = await apiRequest('/auth/login', 'POST', { email, password });
    if (res) {
        STATE.user = res.user;
        if (res.token) localStorage.setItem('session_token', res.token);
        showToast("Welcome back, Sherpa trader!");
        navigate('#/dashboard');
    }
}

async function handleEmailRegister(e) {
    e.preventDefault();
    const name = document.getElementById('reg-name').value;
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;
    
    const res = await apiRequest('/auth/register', 'POST', { full_name: name, email, password });
    if (res) {
        STATE.user = res.user;
        if (res.token) localStorage.setItem('session_token', res.token);
        showToast("Account successfully registered!");
        navigate('#/dashboard');
    }
}

async function triggerGoogleLogin() {
    // Falls back to direct instructions if Google SDK is uninitialized/blocked
    if (window.google) {
        window.google.accounts.id.prompt();
    } else {
        showToast("Initializing Google Sign-in... Please try again in a moment.", "warning");
        initGoogleSignIn();
    }
}

async function handleLogout() {
    await apiRequest('/auth/logout', 'POST');
    STATE.user = null;
    localStorage.removeItem('session_token');
    showToast("Logged out successfully");
    navigate('#/login');
}

async function handleExchangeSetup(e) {
    e.preventDefault();
    const key = document.getElementById('api-key').value;
    const secret = document.getElementById('api-secret').value;
    const pwd = document.getElementById('api-password').value;
    
    const res = await apiRequest('/settings/exchange', 'POST', {
        exchange_id: 'blofin',
        api_key: key,
        api_secret: secret,
        api_password: pwd
    });
    
    if (res) {
        showToast("Exchange keys saved successfully!");
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
        showToast(res.message);
    }
}

async function savePreferences() {
    const val = parseFloat(document.getElementById('risk-slider').value);
    const res = await apiRequest('/settings/preferences', 'POST', { risk_pct: val });
    if (res) {
        showToast("Risk configuration updated");
        handleRoute();
    }
}

async function changeStrategy(strategyName) {
    const res = await apiRequest('/settings/strategy', 'POST', { strategy: strategyName });
    if (res) {
        showToast(`Strategy switched to ${strategyName}`);
        navigate('#/dashboard');
    }
}

async function triggerBacktest() {
    STATE.backtest.running = true;
    renderView();
    
    setTimeout(async () => {
        const res = await apiRequest('/backtest/run', 'POST', {
            strategy: document.getElementById('bt-strategy').value
        });
        STATE.backtest.running = false;
        if (res) {
            STATE.backtest.result = res.result;
        }
        renderView();
    }, 1500);
}

function resetBacktester() {
    STATE.backtest.result = null;
    renderView();
}

async function closeSinglePosition(id, type) {
    const res = await apiRequest('/trades/close', 'POST', { id, type });
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
    const val = document.getElementById('wallet-addr').value.strip();
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
    // Dynamic styles and event hooks on loaded HTML elements
    document.querySelectorAll('.glass-card').forEach(card => {
        card.addEventListener('touchstart', () => {
            card.style.transform = 'scale(0.98)';
            card.style.transition = 'transform 0.1s ease';
        });
        card.addEventListener('touchend', () => {
            card.style.transform = 'scale(1)';
        });
    });
}
