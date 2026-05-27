const API_BASE = '/api';

let STATE = {
    user: null,
    crypto_balance: 0.0,
    stock_balance: 0.0,
    total_balance: 0.0,
    open_trades: [],
    history: [],
    free_history: [],
    active_signals: [],
    closed_signals: [],
    stats: null,
    free_stats: null,
    current_view: 'login',
    dashboard_tab: 'crypto',
    trades_mode: 'active',
    expanded_trade_id: null,
    expanded_signal_id: null,
    is_loading_signals: false,
    is_loading_dashboard: false,
    is_loading_balance: false,
    history_expanded_id: null,
    free_history_expanded_id: null,
    profile_menu_open: false,
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
        
        if (response.status === 502 || response.status === 503) {
            throw new Error("Currently pushing a new version! Sherpa will be right back.");
        }
        
        let resData;
        try {
            resData = await response.json();
        } catch (e) {
            if (!response.ok) {
                throw new Error("Currently pushing a new version! Sherpa will be right back.");
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
    
    // Check for deployment success message if admin
    const isSuperAdmin = STATE.user.telegram_chat_id === 1567788633;
    const isAdmin = STATE.user.is_admin || isSuperAdmin;
    if (isAdmin) {
        checkDeploymentAlert();
    }
    
    // Determine view route
    if (hash === '#/dashboard') {
        STATE.current_view = 'dashboard';
        STATE.is_loading_balance = true;
        
        // 1. Render immediately using cached/default state for a lightning fast load
        renderView();
        
        // 2. Fetch ALL data (including live balance) in the background
        const statsRoute = (STATE.user && STATE.user.is_premium) ? '/user/stats' : '/stats/free';
        Promise.all([
            apiRequest('/user/balance'),
            apiRequest('/signals/active'),
            apiRequest('/trades/open'),
            apiRequest(statsRoute)
        ]).then(([bal, sigs, open, stats]) => {
            STATE.is_loading_balance = false;
            let stateChanged = true; // Always re-render to remove the blur
            
            if (bal) {
                STATE.crypto_balance = bal.crypto_balance;
                STATE.stock_balance = bal.stock_balance;
                STATE.total_balance = bal.total_balance;
            }
            if (sigs) STATE.active_signals = sigs;
            if (open) STATE.open_trades = open;
            if (stats) {
                if (STATE.user && STATE.user.is_premium) STATE.stats = stats;
                else STATE.free_stats = stats;
            }
            
            // 3. Silently re-render the dashboard to "hydrate" the widgets if the user is still on it
            if (stateChanged && STATE.current_view === 'dashboard') {
                renderView();
            }
        });
    } else if (hash === '#/trades') {
        STATE.current_view = 'trades';
        const [open, hist] = await Promise.all([
            apiRequest('/trades/open'),
            apiRequest('/trades/history')
        ]);
        if (open) STATE.open_trades = open;
        if (hist) STATE.history = hist;
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
        if (STATE.user && STATE.user.is_premium) {
            const stats = await apiRequest('/user/stats');
            if (stats) STATE.stats = stats;
        } else {
            const freeStats = await apiRequest('/stats/free');
            if (freeStats) STATE.free_stats = freeStats;
        }
    } else if (hash === '#/settings') {
        STATE.current_view = 'settings';
    } else if (hash === '#/strategy') {
        STATE.current_view = 'strategy';
    } else if (hash === '#/backtest') {
        STATE.current_view = 'backtest';
    } else if (hash === '#/signals') {
        STATE.current_view = 'signals';
        if (STATE.active_signals.length === 0) {
            STATE.is_loading_signals = true;
        }
        
        // Render immediately using cached data for a lightning fast load
        renderView();
        
        // Fetch fresh data in the background (Stale-While-Revalidate)
        Promise.all([
            apiRequest('/signals/active'),
            apiRequest('/signals/closed')
        ]).then(([active, closed]) => {
            STATE.is_loading_signals = false;
            if (active) STATE.active_signals = active;
            if (closed) STATE.closed_signals = closed;
            if (STATE.current_view === 'signals') {
                renderView();
            }
        });
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

window.setDashboardTab = function(tab) {
    STATE.dashboard_tab = tab;
    renderView();
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

window.addEventListener('hashchange', handleRoute);
window.addEventListener('load', () => {
    handleRoute();
    initParticles();
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
                <div class="relative">
                    <button onclick="toggleProfileMenu(event)" class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center font-bold text-primary border border-primary/30 text-sm cursor-pointer hover:bg-surface-container-high transition-all overflow-hidden">
                        ${STATE.user && STATE.user.avatar_url ? `<img src="${STATE.user.avatar_url}" alt="Profile" class="w-full h-full object-cover">` : (STATE.user ? STATE.user.email[0].toUpperCase() : 'U')}
                    </button>
                    ${STATE.profile_menu_open ? `
                        <div class="absolute right-0 mt-2 w-40 glass-card rounded-lg border border-white/10 shadow-xl overflow-hidden z-[100] animate-fade-in" onclick="event.stopPropagation()">
                            <button onclick="logoutUser()" class="w-full text-left px-4 py-2.5 text-sm text-error hover:bg-error/10 transition-colors flex items-center gap-2 font-semibold">
                                <span class="material-symbols-outlined text-[18px]">logout</span>
                                Logout
                            </button>
                        </div>
                    ` : ''}
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
                    <input id="login-email" autocomplete="username" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <input id="login-password" autocomplete="current-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
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
                    <input id="reg-name" autocomplete="name" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Full Name" type="text" required/>
                    <input id="reg-email" autocomplete="username" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Email Address" type="email" required/>
                    <input id="reg-password" autocomplete="new-password" class="w-full h-12 bg-surface-container-low text-on-surface font-body-md text-body-md border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all placeholder:text-on-surface-variant/40" placeholder="Password" type="password" required/>
                    
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
    if (STATE.is_loading_dashboard) {
        return `
            ${renderHeader()}
            <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto flex flex-col items-center justify-center min-h-[60vh]">
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
    const isCrypto = STATE.dashboard_tab === 'crypto';
    
    const tierBadge = `
        <div class="inline-flex items-center gap-1.5 px-3 py-1 glass-card ${isPremium ? 'gold-glow' : 'cyan-glow'} rounded-full">
            <span class="text-[10px]">${isPremium ? '💎' : '🥈'}</span>
            <span class="font-label-sm text-label-sm ${isPremium ? 'text-secondary-container' : 'text-primary'}">${isPremium ? 'Premium' : 'Standard'}</span>
        </div>
    `;

    if (!isPremium) {
        return `
            ${renderHeader()}
            <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
                <div class="flex justify-between items-center">
                    ${tierBadge}
                </div>
                
                <h2 class="font-headline-sm text-headline-sm text-on-surface mt-6">🛰️ Active Signals</h2>
                    ${STATE.active_signals.length === 0 ? `
                        <div class="text-center py-12">
                            <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">satellite_alt</span>
                            <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active signals</p>
                            <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">Sherpa is waiting for a setup...</p>
                        </div>
                    ` : STATE.active_signals.map(renderSignalCard).join('')}
                </div>
            </main>
        `;
    }
    
    const activeStats = STATE.stats || STATE.free_stats || { cumulative_pnl: 0, win_rate: 0 };
    const activeStrategy = STATE.user ? (isCrypto ? (STATE.user.active_crypto_strategy || 'Mean Reversion Scalper') : (STATE.user.active_stock_strategy || 'None')) : (isCrypto ? 'Mean Reversion Scalper' : 'None');
    const balance = isCrypto ? STATE.crypto_balance : STATE.stock_balance;
    const activeTradesCount = STATE.open_trades.filter(t => t.type === (isCrypto ? 'crypto' : 'stock')).length;
    
    // Gated actions for premium
    const actionCards = `
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
            <span class="font-label-md text-label-md text-on-surface font-semibold">Alpha Signals</span>
        </a>
    `;
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const loadingBlur = STATE.is_loading_balance ? 'style="filter: blur(5px); transition: filter 0.2s ease;"' : '';
    const shouldBlurDollars = STATE.is_loading_balance || isPrivacyOn;
    
    const privacyStyle = shouldBlurDollars ? 'style="filter: blur(5px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
    const privacyClass = shouldBlurDollars ? 'privacy-blur' : '';
    const privacyHoverHandlers = shouldBlurDollars ? `onmouseenter="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='none')" onmouseleave="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='blur(5px)')"` : '';
    
    const pnlVal = activeStats.cumulative_pnl || 0;
    const startingCapital = balance - pnlVal;
    const pnlPct = startingCapital > 0 ? (pnlVal / startingCapital) * 100 : 0;
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <!-- Tier Badge & Tabs -->
            <div class="flex justify-between items-center">
                <div class="inline-flex items-center gap-1.5 px-3 py-1 glass-card ${isPremium ? 'gold-glow' : 'cyan-glow'} rounded-full">
                    <span class="text-[10px]">${isPremium ? '💎' : '🥈'}</span>
                    <span class="font-label-sm text-label-sm ${isPremium ? 'text-secondary-container' : 'text-primary'}">${isPremium ? 'Premium' : 'Standard'}</span>
                </div>
                
                <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1">
                    <button onclick="setDashboardTab('crypto')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Crypto</button>
                    <button onclick="setDashboardTab('stock')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Stocks</button>
                </div>
            </div>
            
            <!-- Balance Card -->
            <section class="glass-card cyan-glow rounded-xl p-card-padding relative overflow-hidden cursor-pointer" ${privacyHoverHandlers}>
                <div class="absolute -right-10 -top-10 w-32 h-32 bg-primary/10 blur-3xl rounded-full pointer-events-none"></div>
                <div class="relative z-10 pointer-events-none">
                    <p class="font-label-md text-label-md text-on-surface-variant mb-1">${isCrypto ? 'Crypto Equity' : 'Stock Equity'}</p>
                    <h1 class="font-display-lg text-display-lg text-on-surface drop-shadow-[0_0_12px_rgba(168,232,255,0.15)] ${privacyClass}" ${privacyStyle}>$${(balance || 0).toFixed(2)}</h1>
                    <div class="flex flex-wrap gap-2 mt-4">
                        <div class="bg-tertiary-container/20 text-tertiary px-2 py-1 rounded-lg flex items-center gap-1 w-fit">
                            <span class="material-symbols-outlined text-[14px]" ${loadingBlur}>${pnlVal >= 0 ? 'trending_up' : 'trending_down'}</span>
                            <span class="font-label-sm text-label-sm">
                                <span ${loadingBlur}>${pnlVal >= 0 ? '+' : '-'}</span><span class="${privacyClass}" ${privacyStyle}>$${Math.abs(pnlVal).toFixed(2)}</span> <span ${loadingBlur}>(${pnlVal >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%) All-Time</span>
                            </span>
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- Quick Stats -->
            <section class="grid grid-cols-2 gap-stack-gap">
                <a href="#/trades" class="glass-card rounded-lg p-3 text-center border-t-2 border-primary/40 hover:bg-white/5 transition-colors group block">
                    <p class="font-label-sm text-label-sm text-on-surface-variant mb-1 group-hover:text-primary transition-colors">Open Trades</p>
                    <p class="font-numeric-data text-numeric-data text-primary">${activeTradesCount}</p>
                </a>
                <div class="glass-card rounded-lg p-3 text-center border-t-2 border-tertiary/40">
                    <p class="font-label-sm text-label-sm text-on-surface-variant mb-1">Win Rate</p>
                    <p class="font-numeric-data text-numeric-data text-tertiary">${activeStats.win_rate || 0}%</p>
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
                        <p class="font-body-lg text-body-lg font-bold text-on-surface">${isCrypto ? '🪙' : '🦙'} ${activeStrategy}</p>
                    </div>
                </div>
                <a class="font-label-md text-label-md text-primary hover:underline" href="#/settings">Change</a>
            </section>
            
            <!-- Action Grid -->
            <section class="grid grid-cols-2 gap-stack-gap">
                ${actionCards}
            </section>
        </main>
    `;
}

function renderTradesView() {
    const isPremium = STATE.user && STATE.user.is_premium;
    
    if (!isPremium) {
        return `
            ${renderHeader()}
            <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
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
    const tradesMode = STATE.trades_mode || 'active';
    
    let listHtml = '';
    let headerText = '';
    let countText = '';
    
    if (tradesMode === 'active') {
        const filteredTrades = STATE.open_trades.filter(t => t.type === (isCrypto ? 'crypto' : 'stock'));
        headerText = 'Active Positions';
        countText = `${filteredTrades.length} trades open`;
        
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
                const pnlColor = (trade.unrealized_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                const roeColor = (trade.roe || 0) >= 0 ? 'text-tertiary' : 'text-error';
                const icon = trade.side === 'LONG' ? 'trending_up' : 'trending_down';
                const assetIcon = trade.type === 'stock' ? '🦙' : '🪙';
                const isExpanded = STATE.expanded_trade_id === trade.id;
                
                // Privacy Mode Dollar PnL Blur Class (Default to hide/blur unless hide_dollars is explicitly false)
                const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                const inlineBlur = isPrivacyOn ? 'style="filter: blur(5px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(5px)\'"' : '';
                
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
                    
                    const current_pnl_pct = trade.roe || 0;
                    const current_pnl_val = trade.unrealized_pnl || 0;
                    const target_pnl_pct = Math.abs(tp_pct);
                    const target_pnl_val = Math.abs(tp - entry) * (trade.qty || 0);
                    
                    progressBarHtml = `
                        <div class="mt-4 pt-4 border-t border-white/5 space-y-4" onclick="event.stopPropagation()">
                            <h4 class="text-xs font-bold text-on-surface-variant/80 uppercase tracking-wider">Market Analysis & Setup</h4>
                            <div class="relative w-full aspect-[16/10] bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center">
                                <img src="/api/trades/chart?symbol=${encodeURIComponent(trade.symbol)}&entry=${entry}&tp=${tp}&sl=${sl}&side=${trade.side}&open_ts=${trade.open_time}&type=${trade.type}" class="w-full h-full object-cover" alt="Trade Chart" />
                            </div>
                            
                            <div class="bg-[#121212] p-4 rounded-lg border border-white/5 space-y-4">
                                <div class="space-y-1 font-mono text-[11px] text-left leading-relaxed text-on-surface-variant">
                                    <div class="flex items-center gap-1.5 font-bold text-xs text-on-surface">
                                        <span class="inline-block w-2.5 h-2.5 rounded-full ${current_pnl_val >= 0 ? 'bg-tertiary animate-pulse shadow-[0_0_8px_#3cd7ff]' : 'bg-error animate-pulse shadow-[0_0_8px_#ff5c5c]'}"></span>
                                        ${trade.symbol} <span class="material-symbols-outlined text-[14px] ${trade.side === 'LONG' ? 'text-primary' : 'text-error'}">${trade.side === 'LONG' ? 'trending_up' : 'trending_down'}</span>
                                    </div>
                                    <div>
                                        Current PnL: <span class="${current_pnl_val >= 0 ? 'text-tertiary' : 'text-error'} font-bold">${current_pnl_pct >= 0 ? '+' : ''}${current_pnl_pct.toFixed(2)}% (<span ${inlineBlur}>${current_pnl_val >= 0 ? '+' : ''}$${current_pnl_val.toFixed(2)}</span>)</span> of <span class="text-tertiary font-bold">+${target_pnl_pct.toFixed(2)}% (<span ${inlineBlur}>+$${target_pnl_val.toFixed(2)}</span>)</span>
                                    </div>
                                    <div>
                                        • Entry: <span class="text-primary font-bold">$${entry.toFixed(2)}</span> | SL: <span class="text-error font-bold">$${sl.toFixed(2)} (${sl_pct.toFixed(0)}%)</span> | TP: <span class="text-tertiary font-bold">$${tp.toFixed(2)} (+${tp_pct.toFixed(0)}%)</span>
                                    </div>
                                </div>

                                <div class="relative py-2">
                                    <div class="h-1 w-full bg-surface-container rounded-full relative">
                                        <div class="absolute w-3.5 h-3.5 -top-1.5 bg-[#00E5FF] rounded-full border-2 border-white shadow-[0_0_8px_#00E5FF]" style="left: calc(${pct}% - 7px);"></div>
                                    </div>
                                </div>
                                <div class="flex justify-between items-center text-[10px] text-on-surface-variant font-mono">
                                    <div class="text-left">
                                        <div class="font-bold text-error">${sl_pct.toFixed(1)}%</div>
                                        <div>$${sl.toFixed(2)}</div>
                                    </div>
                                    <div class="text-center">
                                        <div class="font-bold text-white">ENTRY</div>
                                        <div>$${entry.toFixed(2)}</div>
                                    </div>
                                    <div class="text-right">
                                        <div class="font-bold text-tertiary">+${tp_pct.toFixed(1)}%</div>
                                        <div>$${tp.toFixed(2)}</div>
                                    </div>
                                </div>
                            </div>

                            <button onclick="confirmClosePosition('${trade.id}', '${trade.type}', '${trade.symbol}')" class="w-full h-10 bg-error/15 hover:bg-error/25 border border-error/30 text-error font-bold text-xs uppercase tracking-wider rounded-lg flex items-center justify-center gap-2 mt-2 cursor-pointer transition-all active:scale-[0.98]">
                                <span class="material-symbols-outlined text-[16px]">close</span>
                                Market Close ${trade.symbol}
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
                                Market Close ${trade.symbol}
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
                                    <p class="font-label-md text-label-md font-bold text-on-surface">${trade.symbol}</p>
                                    <p class="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1">
                                        <span class="material-symbols-outlined text-[16px] ${trade.side === 'LONG' ? 'text-primary' : 'text-error'}">${trade.side === 'LONG' ? 'trending_up' : 'trending_down'}</span>
                                    </p>
                                </div>
                            </div>
                            <div class="text-right">
                                <p class="font-numeric-data text-numeric-data font-bold ${pnlColor}">
                                    <span ${inlineBlur}>${(trade.unrealized_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(trade.unrealized_pnl || 0).toFixed(2)}</span>
                                    ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> / <span ${inlineBlur}>+$${(Math.abs(trade.tp_price - trade.entry_price) * (trade.qty || 0)).toFixed(2)}</span></span>` : ''}
                                </p>
                                <p class="font-numeric-data text-numeric-data text-sm ${roeColor}">
                                    ${(trade.roe || 0) >= 0 ? '+' : ''}${(trade.roe || 0).toFixed(2)}%
                                    ${trade.tp_price > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> of ${Math.abs(((trade.tp_price - trade.entry_price) / trade.entry_price) * 100).toFixed(0)}%</span>` : ''}
                                </p>
                            </div>
                        </div>
                        <div class="flex justify-between items-center pt-3 border-t border-white/10">
                            <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                SL: <span class="text-on-surface">$${(trade.sl_price || 0).toFixed(2)} (${trade.entry_price > 0 && trade.sl_price > 0 ? (((trade.sl_price - trade.entry_price) / trade.entry_price) * 100).toFixed(0) : '0'}%)</span>
                            </div>
                            <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                                TP: <span class="text-on-surface">$${(trade.tp_price || 0).toFixed(2)} (${trade.entry_price > 0 && trade.tp_price > 0 ? (((trade.tp_price - trade.entry_price) / trade.entry_price) * 100).toFixed(0) : '0'}%)</span>
                            </div>
                        </div>
                        ${progressBarHtml}
                    </div>
                `;
            }).join('');
        }
    } else {
        const filteredHistory = STATE.history.filter(t => t.type === (isCrypto ? 'crypto' : 'stock'));
        headerText = 'Trade History';
        countText = `${filteredHistory.length} trades recorded`;
        
        if (filteredHistory.length === 0) {
            listHtml = `
                <div class="text-center py-12">
                    <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                    <p class="font-body-lg text-body-lg text-on-surface font-semibold">No trade history</p>
                </div>
            `;
        } else {
            listHtml = filteredHistory.map(t => {
                const dateStr = t.close_time ? new Date(t.close_time * 1000).toLocaleDateString() : 'Recent';
                const pnlColor = (t.net_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                const roePct = t.roe !== undefined ? t.roe : (t.roe_val || 0);
                const roeColor = roePct >= 0 ? 'text-tertiary' : 'text-error';
                const assetIcon = t.type === 'stock' ? '🦙' : '🪙';
                const isLong = t.side === 'LONG' || t.side === 'l' || t.side === 'long';
                
                const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
                const inlineBlur = isPrivacyOn ? 'style="filter: blur(5px); transition: filter 0.2s ease;" onmouseenter="this.style.filter=\'none\'" onmouseleave="this.style.filter=\'blur(5px)\'"' : '';
                
                return `
                    <div class="glass-card p-4 rounded-lg flex justify-between items-center border border-white/5">
                        <div class="flex items-center gap-3">
                            <div class="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-lg">
                                ${assetIcon}
                            </div>
                            <div>
                                <p class="font-label-md text-label-md font-bold text-on-surface flex items-center gap-1">
                                    ${t.symbol}
                                    <span class="material-symbols-outlined text-[16px] ${isLong ? 'text-primary' : 'text-error'}">${isLong ? 'trending_up' : 'trending_down'}</span>
                                </p>
                                <p class="font-label-sm text-label-sm text-on-surface-variant">${dateStr}</p>
                            </div>
                        </div>
                        <div class="text-right">
                            <p class="font-numeric-data text-numeric-data font-bold ${pnlColor}">
                                <span ${inlineBlur}>${(t.net_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(t.net_pnl || 0).toFixed(2)}</span>
                            </p>
                            <p class="font-numeric-data text-numeric-data text-sm ${roeColor}">
                                ${roePct >= 0 ? '+' : ''}${roePct.toFixed(2)}%
                            </p>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="glass-card rounded-full flex border border-white/10 p-1 w-full relative overflow-hidden z-10">
                <button onclick="setTradesMode('active')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${tradesMode === 'active' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Active Positions
                </button>
                <button onclick="setTradesMode('closed')" class="flex-1 py-2 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${tradesMode === 'closed' ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Closed History
                </button>
            </div>

            <!-- Crypto vs Stocks Segmented Controller with dynamic trade count -->
            <div class="glass-card rounded-full flex border border-white/10 p-1 w-full relative overflow-hidden z-10">
                <button onclick="setDashboardTab('crypto')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Crypto (${tradesMode === 'active' ? STATE.open_trades.filter(t => t.type === 'crypto').length : STATE.history.filter(t => t.type === 'crypto').length})
                </button>
                <button onclick="setDashboardTab('stock')" class="flex-1 py-1.5 text-center rounded-full text-xs sm:text-sm font-bold whitespace-nowrap transition-all duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant/60 hover:text-on-surface'}">
                    Stocks (${tradesMode === 'active' ? STATE.open_trades.filter(t => t.type === 'stock').length : STATE.history.filter(t => t.type === 'stock').length})
                </button>
            </div>
            
            <div class="space-y-stack-gap">
                ${listHtml}
            </div>
            
            ${tradesMode === 'active' && STATE.open_trades.length > 0 ? `
                <button onclick="panicCloseAll()" class="w-full h-12 bg-red-900/40 text-error font-label-md text-label-md font-bold rounded-lg border border-error/50 hover:bg-error/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                    <span class="material-symbols-outlined">warning</span>
                    🚨 PANIC - Close All Positions
                </button>
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
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
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

function renderHistoryView() {
    if (!STATE.user || !STATE.user.is_premium) {
        return renderFreeHistoryView();
    }
    
    const isCrypto = STATE.dashboard_tab === 'crypto';
    const filteredHistory = STATE.history.filter(t => t.type === (isCrypto ? 'crypto' : 'stock'));
    
    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="flex justify-between items-center">
                <h2 class="font-headline-sm text-headline-sm text-on-surface">📜 History</h2>
                <div class="glass-card rounded-full flex overflow-hidden border border-white/10 p-1">
                    <button onclick="setDashboardTab('crypto')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Crypto</button>
                    <button onclick="setDashboardTab('stock')" class="px-4 py-1.5 rounded-full font-label-sm transition-colors duration-200 ${!isCrypto ? 'bg-primary text-on-primary shadow-[0_0_12px_rgba(168,232,255,0.4)]' : 'text-on-surface-variant hover:text-on-surface'}">Stocks</button>
                </div>
            </div>
            
            <div class="space-y-stack-gap">
                ${filteredHistory.length === 0 ? `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">history</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No trade history</p>
                    </div>
                ` : filteredHistory.map(t => {
                        const dateStr = 'Just now';
                        const pnlColor = (t.net_pnl || 0) >= 0 ? 'text-tertiary' : 'text-error';
                        const assetIcon = t.type === 'stock' ? '🦙' : '🪙';
                        
                        return `
                            <div class="glass-card p-4 rounded-lg flex justify-between items-center border border-white/5">
                                <div class="flex items-center gap-3">
                                    <div class="w-10 h-10 rounded-full bg-surface-container flex items-center justify-center text-lg">
                                        ${assetIcon}
                                    </div>
                                    <div>
                                        <p class="font-label-md text-label-md font-bold text-on-surface">${t.symbol}</p>
                                        <p class="font-label-sm text-label-sm text-on-surface-variant">${dateStr} • ${t.side}</p>
                                    </div>
                                </div>
                                <div class="text-right">
                                    <p class="font-numeric-data text-numeric-data font-bold ${pnlColor}">
                                        ${(t.net_pnl || 0) >= 0 ? '+' : ''}$${Math.abs(t.net_pnl || 0).toFixed(2)}
                                    </p>
                                    <p class="font-label-sm text-label-sm text-on-surface-variant">Closed</p>
                                </div>
                            </div>
                        `;
                    }).join('')}
            </div>
        </main>
    `;
}

function renderFreeStatsView() {
    if (!STATE.free_stats) return `${renderHeader()}<main class="pt-20 px-container-margin"><div class="text-center p-8 text-on-surface-variant">Loading stats...</div></main>`;

    const strategyIcons = {
        "Mean Reversion Scalper": "📈",
        "Valkyrie Elite Scalper": "🛡️",
        "Sherpa Velocity Pullback": "🦙"
    };

    let strategiesHtml = STATE.free_stats.strategies.map(s => {
        const icon = strategyIcons[s.name] || "📈";
        
        let activeTradesHtml = "";
        if (s.active_count > 0 && s.active_trades.length > 0) {
            activeTradesHtml = `<div class="mt-3 space-y-1 bg-surface-container-low p-3 rounded-lg border border-white/5">`;
            s.active_trades.forEach(t => {
                const isLong = String(t.side).toLowerCase() === 'long' || String(t.side).toLowerCase() === 'buy';
                const direction = isLong ? "⬆️" : "⬇️";
                const isStock = t.symbol && !t.symbol.includes('/');
                let targetPct = t.tp_price > 0 ? (((Math.abs(t.tp_price - t.entry_price)) / t.entry_price) * 100) : 0;
                if (!isStock) targetPct *= 10; // crypto leverage
                
                activeTradesHtml += `
                    <div class="flex items-center text-sm font-mono">
                        <span class="mr-2">${direction}</span>
                        <span class="text-primary">${t.symbol}</span>
                        <span class="ml-auto text-on-surface-variant">tgt: +${targetPct.toFixed(2)}%</span>
                    </div>
                `;
            });
            activeTradesHtml += `</div>`;
        }

        const realizedClass = s.realized_pct >= 0 ? "text-tertiary" : "text-error";

        return `
            <div class="glass-card rounded-xl p-4 space-y-2 border-l-4 border-primary/50">
                <h3 class="font-headline-sm text-on-surface flex items-center gap-2">
                    <span>${icon}</span> ${s.name}
                </h3>
                <div class="text-sm space-y-1">
                    <p class="text-on-surface-variant">• Win Rate: <span class="text-primary font-medium">${s.win_rate.toFixed(1)}%</span> (${s.wins} W | ${s.losses} L)</p>
                    <p class="text-on-surface-variant">• Realized PnL: <span class="${realizedClass} font-medium">${s.realized_pct > 0 ? '+' : ''}${s.realized_pct.toFixed(2)}%</span></p>
                    <p class="text-on-surface-variant">• Active Signals: <span class="text-primary font-medium">${s.active_count}</span></p>
                </div>
                ${activeTradesHtml}
            </div>
        `;
    }).join('');

    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <div class="flex items-center gap-3">
                <h2 class="font-headline-sm text-headline-sm text-on-surface">🧪 Free Forward Testing</h2>
            </div>
            <div class="bg-surface-container rounded-lg p-3 border border-white/5 inline-block">
                <p class="text-on-surface-variant text-sm">
                    • Open Free Signals: <span class="text-primary font-medium text-base">${STATE.free_stats.total_open}</span>
                </p>
            </div>
            
            <div class="space-y-4">
                ${strategiesHtml}
            </div>
            
            <p class="text-xs text-center text-on-surface-variant italic mt-4 opacity-70">
                _Each strategy starts with an independent $1,000 allocation_
            </p>
        </main>
    `;
}

function renderStatsView() {
    if (!STATE.user || !STATE.user.is_premium) {
        return renderFreeStatsView();
    }
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
                    <input id="api-key" autocomplete="username" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="API Key" type="text" required/>
                    <input id="api-secret" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="API Secret" type="password" required/>
                    <input id="api-password" autocomplete="new-password" class="w-full h-11 bg-surface-container-low text-on-surface text-sm border border-white/10 rounded-lg px-4 cyan-glow-focus transition-all" placeholder="Passphrase" type="password" required/>
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

            <!-- Privacy Mode Setting -->
            <section class="glass-card rounded-xl p-card-padding flex items-center justify-between border-t-2 border-primary/40">
                <div>
                    <h3 class="font-body-lg text-body-lg font-bold text-on-surface">Privacy Mode</h3>
                    <p class="text-xs text-on-surface-variant mt-1">🔒 Hide Dollar PnL amounts across the app</p>
                </div>
                <button onclick="togglePrivacySetting()" class="px-4 py-2 rounded-lg font-bold text-xs uppercase tracking-wider transition-all ${
                    (user.hide_dollars !== false) ? 'bg-primary/20 text-primary border border-primary/55' : 'bg-surface-container-high text-on-surface border border-white/10'
                }">
                    ${(user.hide_dollars !== false) ? 'Privacy On 🔒' : 'Privacy Off 👁️'}
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

window.toggleSignalExpand = function(id) {
    if (String(STATE.expanded_signal_id) === String(id)) {
        STATE.expanded_signal_id = null;
    } else {
        STATE.expanded_signal_id = String(id);
    }
    renderView();
}

function renderSignalCard(sig) {
    const isExpanded = String(STATE.expanded_signal_id) === String(sig.id);
    const isPrivacyOn = STATE.user ? (STATE.user.hide_dollars !== false) : true;
    const privacyStyle = isPrivacyOn ? 'style="filter: blur(5px); transition: filter 0.2s ease;"' : 'style="transition: filter 0.2s ease;"';
    const privacyClass = isPrivacyOn ? 'privacy-blur' : '';
    const privacyHoverHandlers = isPrivacyOn ? `onmouseenter="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='none')" onmouseleave="this.querySelectorAll('.privacy-blur').forEach(el => el.style.filter='blur(5px)')"` : '';
    
    const entry = sig.entry_price || 0;
    const tp = sig.tp_price || 0;
    const sl = sig.sl_price || 0;
    const isLong = sig.side === 'LONG' || sig.side === 'l' || sig.side === 'long';
    const sideStr = isLong ? 'LONG' : 'SHORT';
    
    const sl_pct = entry > 0 ? ((sl - entry) / entry) * 100 : 0;
    const tp_pct = entry > 0 ? ((tp - entry) / entry) * 100 : 0;
    
    const current_pnl_pct = sig.pnl_pct || 0;
    const current_pnl_val = sig.pnl_usdt || 0;
    const target_pnl_pct = Math.abs(tp_pct);
    const pos_size = sig.position_size || (current_pnl_pct !== 0 ? (current_pnl_val / (current_pnl_pct / 100)) : 1000);
    const simulated_target_val = (target_pnl_pct / 100) * pos_size;

    const mark = entry + (entry * (current_pnl_pct / 100) * (isLong ? 1 : -1));
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
    
    let progressBarHtml = '';
    if (isExpanded) {
        progressBarHtml = `
            <div class="mt-4 pt-4 border-t border-white/5 space-y-4" onclick="event.stopPropagation()">
                <h4 class="text-xs font-bold text-on-surface-variant/80 uppercase tracking-wider">Market Analysis & Setup</h4>
                <div class="relative w-full aspect-[16/10] bg-surface-container rounded-lg overflow-hidden border border-white/5 flex items-center justify-center">
                    <img src="/api/trades/chart?symbol=${encodeURIComponent(sig.symbol)}&entry=${entry}&tp=${tp}&sl=${sl}&side=${sideStr}&open_ts=${sig.open_time || 0}&type=${sig.symbol && sig.symbol.includes('/') ? 'crypto' : 'stock'}" class="w-full h-full object-cover" alt="Signal Chart" />
                </div>
                
                <div class="bg-[#121212] p-4 rounded-lg border border-white/5 space-y-4">
                    <div class="space-y-1 font-mono text-[11px] text-left leading-relaxed text-on-surface-variant">
                        <div class="flex items-center gap-1.5 font-bold text-xs text-on-surface">
                            <span class="inline-block w-2.5 h-2.5 rounded-full ${current_pnl_pct >= 0 ? 'bg-tertiary animate-pulse shadow-[0_0_8px_#3cd7ff]' : 'bg-error animate-pulse shadow-[0_0_8px_#ff5c5c]'}"></span>
                            ${sig.symbol} <span class="material-symbols-outlined text-[14px] ${isLong ? 'text-primary' : 'text-error'}">${isLong ? 'trending_up' : 'trending_down'}</span>
                        </div>
                        <div>
                            Current PnL: <span class="${current_pnl_pct >= 0 ? 'text-tertiary' : 'text-error'} font-bold">${current_pnl_pct >= 0 ? '+' : ''}${current_pnl_pct.toFixed(2)}% (<span class="${privacyClass}" ${privacyStyle}>${current_pnl_val >= 0 ? '+' : ''}$${Math.abs(current_pnl_val).toFixed(2)}</span>)</span> of <span class="text-tertiary font-bold">+${target_pnl_pct.toFixed(2)}% (<span class="${privacyClass}" ${privacyStyle}>+$${Math.abs(simulated_target_val).toFixed(2)}</span>)</span>
                        </div>
                        <div>
                            • Entry: <span class="text-primary font-bold">$${entry.toFixed(2)}</span> | SL: <span class="text-error font-bold">$${sl.toFixed(2)} (${sl_pct.toFixed(0)}%)</span> | TP: <span class="text-tertiary font-bold">$${tp.toFixed(2)} (+${tp_pct.toFixed(0)}%)</span>
                        </div>
                    </div>

                    <div class="relative py-2">
                        <div class="h-1 w-full bg-surface-container rounded-full relative">
                            <div class="absolute w-3.5 h-3.5 -top-1.5 bg-[#00E5FF] rounded-full border-2 border-white shadow-[0_0_8px_#00E5FF]" style="left: calc(${pct}% - 7px);"></div>
                        </div>
                    </div>
                    <div class="flex justify-between items-center text-[10px] text-on-surface-variant font-mono">
                        <div class="text-left">
                            <div class="font-bold text-error">${sl_pct.toFixed(1)}%</div>
                            <div>$${sl.toFixed(2)}</div>
                        </div>
                        <div class="text-center">
                            <div class="font-bold text-white">ENTRY</div>
                            <div>$${entry.toFixed(2)}</div>
                        </div>
                        <div class="text-right">
                            <div class="font-bold text-tertiary">+${tp_pct.toFixed(1)}%</div>
                            <div>$${tp.toFixed(2)}</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    return `
        <div onclick="toggleSignalExpand('${sig.id}')" class="glass-card rounded-lg p-4 border border-white/5 flex flex-col gap-3 cursor-pointer hover:border-white/20 transition-all group" ${privacyHoverHandlers}>
            <div class="flex justify-between items-center pointer-events-none">
                <div>
                    <h4 class="font-bold text-on-surface flex items-center gap-1">
                        ${sig.symbol} 
                        <span class="material-symbols-outlined text-[16px] ${isLong ? 'text-primary' : 'text-error'}">${isLong ? 'trending_up' : 'trending_down'}</span>
                    </h4>
                    <p class="text-xs text-on-surface-variant mt-1">${sig.strategy}</p>
                </div>
                <div class="text-right">
                    <p class="font-numeric-data text-numeric-data font-bold ${current_pnl_pct >= 0 ? 'text-tertiary' : 'text-error'}">
                        <span class="${privacyClass}" ${privacyStyle}>${current_pnl_pct >= 0 ? '+' : ''}$${Math.abs(current_pnl_val).toFixed(2)}</span>
                    </p>
                    <p class="font-numeric-data text-numeric-data text-sm ${current_pnl_pct >= 0 ? 'text-tertiary' : 'text-error'}">
                        ${current_pnl_pct >= 0 ? '+' : ''}${current_pnl_pct.toFixed(2)}%
                        ${tp > 0 ? `<span class="text-on-surface-variant/30 text-xs font-normal"> of ${Math.abs(target_pnl_pct).toFixed(0)}%</span>` : ''}
                    </p>
                </div>
            </div>
            <div class="flex justify-between items-center pt-3 border-t border-white/10 pointer-events-none">
                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                    SL: <span class="text-on-surface">$${sl.toFixed(2)} (${sl_pct.toFixed(0)}%)</span>
                </div>
                <div class="font-numeric-data text-numeric-data text-sm text-on-surface-variant">
                    TP: <span class="text-on-surface">$${tp.toFixed(2)} (+${tp_pct.toFixed(0)}%)</span>
                </div>
            </div>
            ${progressBarHtml}
        </div>
    `;
}

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

    return `
        ${renderHeader()}
        <main class="pt-20 px-container-margin pb-24 space-y-section-gap max-w-[500px] mx-auto">
            <h2 class="font-headline-sm text-headline-sm text-on-surface">🛰️ Alpha Signals</h2>
            
            <div class="space-y-stack-gap">
                ${STATE.active_signals.length === 0 ? `
                    <div class="text-center py-12">
                        <span class="material-symbols-outlined text-on-surface-variant/40 text-6xl mb-4">satellite_alt</span>
                        <p class="font-body-lg text-body-lg text-on-surface font-semibold">No active signals</p>
                        <p class="font-label-sm text-label-sm text-on-surface-variant mt-1">Sherpa is analyzing markets...</p>
                    </div>
                ` : STATE.active_signals.map(renderSignalCard).join('')}
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
}

// ----------------- Deployment Alert Notifier -----------------
// Ask for native browser push notification permissions on load if default
if (window.Notification && Notification.permission === "default") {
    Notification.requestPermission();
}

async function checkDeploymentAlert() {
    try {
        const res = await apiRequest('/admin/deployment');
        if (res && res.commit_hash) {
            const lastSeen = localStorage.getItem('last_seen_deployment');
            if (lastSeen !== res.commit_hash) {
                // Trigger the existing premium temporary toast balloon
                showToast("🚀 New deployment Successful! Reloading app...");
                localStorage.setItem('last_seen_deployment', res.commit_hash);
                
                // Trigger native OS push notification if permitted
                if (window.Notification && Notification.permission === "granted") {
                    new Notification("🚀 Metaverse Sherpa Upgraded", {
                        body: "New deployment Successful! Features are ready for testing.",
                        icon: "/favicon.ico"
                    });
                }
                
                // Force a reload to clear the cache and load the new code
                setTimeout(() => {
                    window.location.reload(true);
                }, 3000);
            }
        }
    } catch (e) {
        console.log("Not an admin or error fetching deployment info:", e);
    }
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


