import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import LoginMarketingContent from './LoginMarketingContent';
import ActiveStrategiesCatalog from './ActiveStrategiesCatalog';
import LiveActiveSignals from './LiveActiveSignals';
import { signInWithGoogle, getAuthInstance } from '../lib/firebase';
import { signInWithEmailAndPassword, createUserWithEmailAndPassword, sendPasswordResetEmail } from 'firebase/auth';
import { useToast } from './Toast';
import { useAuthStore } from '../store/useStore';

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { showToast } = useToast();
  
  // Default to /dashboard if no intended destination exists.
  // Avoid infinite loops by falling back to /dashboard if the intent was /login.
  const intendedDestination = location.state?.from === '/login' || !location.state?.from ? '/dashboard' : location.state.from;

  const [authMode, setAuthMode] = useState<'login' | 'register' | 'forgot'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' ? window.innerWidth < 768 : false);

  React.useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);



  // If already authenticated (e.g. from a previous session or immediately after login via global state), redirect
  const { isAuthenticated } = useAuthStore();
  React.useEffect(() => {
    if (isAuthenticated) {
      navigate(intendedDestination, { replace: true });
    }
  }, [isAuthenticated, navigate, intendedDestination]);

  const handleGoogleLogin = async () => {
    try {
      await signInWithGoogle();
      // Navigation is handled by the useEffect watching isAuthenticated
    } catch (error) {
      console.error("Login failed", error);
      showToast("Google Login failed", "error");
    }
  };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await signInWithEmailAndPassword(getAuthInstance(), email, password);
      // Navigation is handled by the useEffect watching isAuthenticated
    } catch (error: any) {
      console.error("Login failed", error);
      showToast(error.message, "error");
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await createUserWithEmailAndPassword(getAuthInstance(), email, password);
      // Navigation is handled by the useEffect watching isAuthenticated
    } catch (error: any) {
      console.error("Registration failed", error);
      showToast(error.message, "error");
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      showToast("Please enter your email address", "error");
      return;
    }
    setIsLoading(true);
    try {
      await sendPasswordResetEmail(getAuthInstance(), email);
      showToast("Password reset link sent to your email.", "success");
      setAuthMode('login');
    } catch (error: any) {
      console.error("Password reset failed", error);
      showToast(error.message, "error");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 w-full lg:max-w-[1100px] mx-auto flex flex-col gap-8 lg:gap-16 px-4 py-8 lg:py-16 min-h-[calc(100vh-80px)]">
      
      {/* Top Row: Login & System Architecture */}
      <div className="flex flex-col lg:flex-row items-center lg:items-stretch lg:justify-center gap-8 lg:gap-16 w-full">
        {/* Left Column: Login / Auth */}
        <div className="w-full lg:max-w-[420px] flex flex-col gap-6 lg:h-auto justify-between flex-1">
        {/* Header Card (Algorithmic Intelligence) */}
        <div className="relative overflow-hidden w-full rounded-2xl p-5 bg-gradient-to-br from-[#3cd7ff]/20 via-[#0c1f30] to-[#00e676]/20 border border-[#3cd7ff]/30 text-center shadow-[0_0_40px_rgba(60,215,255,0.15)]">
          <div className="absolute -right-10 -top-10 w-64 h-64 bg-[#3cd7ff]/30 rounded-full blur-[80px] pointer-events-none"></div>
          <div className="absolute -left-10 -bottom-10 w-64 h-64 bg-[#00e676]/30 rounded-full blur-[80px] pointer-events-none"></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-[#3cd7ff]/10 via-transparent to-transparent pointer-events-none"></div>
          
          <div className="relative z-10 flex flex-col items-center">
            <span className="text-[10px] flex items-center gap-1.5 text-[#3cd7ff]/90 font-bold uppercase tracking-widest bg-[#3cd7ff]/10 px-3 py-1 rounded-full border border-[#3cd7ff]/25 mb-4">
              <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#3cd7ff] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#3cd7ff]"></span>
              </span>
              Algorithmic Intelligence
            </span>
            <h2 className="text-2xl text-center font-bold leading-tight">
                <span className="text-white">Institutional-Grade</span><br/>
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#3cd7ff] to-[#00e676]">Autopilot Trading</span>
            </h2>
            <p className="text-xs text-gray-400 font-medium max-w-[360px] leading-relaxed mt-2.5">
                Summit the markets with real-time autonomous trading setups and zero-latency execution.
            </p>
          </div>
        </div>

        {/* Login Card */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border-t-2 border-t-[#3cd7ff]/40 border-l border-r border-b border-white/5 rounded-xl w-full p-5 shadow-[0_0_20px_rgba(60,215,255,0.15)] flex flex-col gap-4">
          
          <button 
            onClick={handleGoogleLogin}
            className="w-full h-[46px] bg-white hover:bg-gray-50 text-gray-700 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-3 border border-gray-200"
          >
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" className="w-5 h-5" />
            <span>Continue with Google</span>
          </button>

          <div className="flex items-center gap-4 py-1">
            <div className="flex-1 h-px bg-white/10"></div>
            <span className="text-xs text-gray-400">or</span>
            <div className="flex-1 h-px bg-white/10"></div>
          </div>

          {authMode === 'login' && (
            <form onSubmit={handleEmailLogin} className="space-y-4">
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email Address" 
                autoComplete="username"
                required
                className="w-full h-12 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:border-[#3cd7ff] focus:shadow-[0_0_15px_rgba(60,215,255,0.2)] outline-none transition-all placeholder:text-gray-500"
              />
              <div className="relative w-full">
                <input 
                  type={showPassword ? "text" : "password"} 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password" 
                  autoComplete="current-password"
                  required
                  className="w-full h-12 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg pl-4 pr-12 focus:border-[#3cd7ff] focus:shadow-[0_0_15px_rgba(60,215,255,0.2)] outline-none transition-all placeholder:text-gray-500"
                />
                <button 
                  type="button" 
                  onClick={() => setShowPassword(!showPassword)} 
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              <button 
                type="submit" 
                disabled={isLoading}
                className="w-full h-12 bg-[#00e676] hover:bg-[#00c853] text-slate-900 text-sm font-bold rounded-lg transition-all shadow-[0_0_20px_rgba(0,230,118,0.4)] hover:shadow-[0_0_30px_rgba(0,230,118,0.6)] disabled:opacity-50 mt-2"
              >
                {isLoading ? 'Signing in...' : 'Sign In'}
              </button>
              <div className="flex flex-col items-center gap-2 mt-4">
                <button type="button" onClick={() => setAuthMode('forgot')} className="text-sm font-medium text-[#3cd7ff] hover:opacity-80 transition-opacity py-2 min-h-[44px]">
                  Forgot password?
                </button>
                <p className="text-[11px] text-gray-400 mt-2">
                  Don't have an account? <button type="button" onClick={() => setAuthMode('register')} className="font-bold text-[#3cd7ff] hover:opacity-80 transition-opacity py-2 min-h-[44px]">Create one</button>
                </p>
              </div>
            </form>
          )}

          {authMode === 'register' && (
            <form onSubmit={handleEmailRegister} className="space-y-4">
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email Address" 
                autoComplete="username"
                required
                className="w-full h-12 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:border-[#3cd7ff] focus:shadow-[0_0_15px_rgba(60,215,255,0.2)] outline-none transition-all placeholder:text-gray-500"
              />
              <div className="relative w-full">
                <input 
                  type={showPassword ? "text" : "password"} 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Create Password" 
                  autoComplete="new-password"
                  required
                  className="w-full h-12 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg pl-4 pr-12 focus:border-[#3cd7ff] focus:shadow-[0_0_15px_rgba(60,215,255,0.2)] outline-none transition-all placeholder:text-gray-500"
                />
                <button 
                  type="button" 
                  onClick={() => setShowPassword(!showPassword)} 
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              <button 
                type="submit" 
                disabled={isLoading}
                className="w-full h-12 bg-[#3cd7ff] hover:bg-[#18c4ee] text-slate-900 text-sm font-bold rounded-lg transition-all shadow-[0_0_20px_rgba(60,215,255,0.4)] hover:shadow-[0_0_30px_rgba(60,215,255,0.6)] disabled:opacity-50 mt-2"
              >
                {isLoading ? 'Creating...' : 'Create Account'}
              </button>
              <div className="flex flex-col items-center gap-2 mt-4">
                <p className="text-[11px] text-gray-400">
                  Already have an account? <button type="button" onClick={() => setAuthMode('login')} className="font-bold text-[#3cd7ff] hover:opacity-80 transition-opacity py-2 min-h-[44px]">Sign in</button>
                </p>
              </div>
            </form>
          )}

          {authMode === 'forgot' && (
            <form onSubmit={handleForgotPassword} className="space-y-4">
              <p className="text-xs text-gray-400 text-center mb-4">Enter your email and we'll send a reset link.</p>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email Address" 
                autoComplete="email"
                required
                className="w-full h-12 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:border-[#3cd7ff] focus:shadow-[0_0_15px_rgba(60,215,255,0.2)] outline-none transition-all placeholder:text-gray-500"
              />
              <button 
                type="submit" 
                disabled={isLoading}
                className="w-full h-12 bg-purple-500 hover:bg-purple-400 text-white text-sm font-bold rounded-lg transition-all shadow-[0_0_20px_rgba(168,85,247,0.4)] disabled:opacity-50 mt-2"
              >
                {isLoading ? 'Sending...' : 'Send Reset Link'}
              </button>
              <div className="flex flex-col items-center gap-2 mt-4">
                <button type="button" onClick={() => setAuthMode('login')} className="text-xs font-bold text-gray-400 hover:text-white transition-colors py-2 min-h-[44px]">
                  Back to Sign In
                </button>
              </div>
            </form>
          )}
        </div>

        <footer className="text-center px-4 mt-4">
          <p className="text-[11px] text-gray-400 leading-relaxed">
              By signing in, you agree to our Terms of Service and Privacy Policy. Institutional grade encryption active.
          </p>
        </footer>
      </div>

        {/* Right Column: Marketing Content */}
        <div className="w-full lg:max-w-[500px]">
          <LoginMarketingContent />
        </div>
      </div>

      {/* Bottom Row: Active Strategies Catalog */}
      {!isMobile && (
        <div className="w-full">
          <ActiveStrategiesCatalog />
        </div>
      )}

      {/* Live Active Signals Row */}
      {!isMobile && (
        <div className="w-full">
          <LiveActiveSignals />
        </div>
      )}

    </div>
  );
};

export default LoginPage;
