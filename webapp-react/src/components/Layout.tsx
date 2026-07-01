import React from 'react';
import ParticlesBackground from './ParticlesBackground';
import { Outlet } from 'react-router-dom';

const Layout: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#0f131f] text-[#6b6375] dark:text-[#9ca3af] dark:bg-[#16171d] font-sans flex flex-col items-center">
      <ParticlesBackground />
      
      {/* Main Content Shell - Max width restricted for large screens like legacy app */}
      <div className="relative z-10 w-full max-w-[1126px] min-h-screen border-x border-[#e5e4e7] dark:border-[#2e303a] flex flex-col px-4 lg:px-8 py-6">
        
        {/* Simple Navbar Placeholder */}
        <header className="flex justify-between items-center mb-8 pb-4 border-b border-[#e5e4e7] dark:border-[#2e303a]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400 flex items-center justify-center text-white font-bold text-lg shadow-[0_0_15px_rgba(60,215,255,0.4)]">
              M
            </div>
            <div>
              <h1 className="text-xl font-bold text-[#08060d] dark:text-[#f3f4f6] tracking-tight m-0 leading-none">Metaverse Sherpa</h1>
              <p className="text-xs text-cyan-500 font-medium tracking-wider uppercase mt-1">Institutional Engine</p>
            </div>
          </div>
          <nav className="flex gap-4">
            {/* Nav links will go here */}
          </nav>
        </header>

        {/* Dynamic Route Content */}
        <main className="flex-1 flex flex-col">
          <Outlet />
        </main>
        
        {/* Footer */}
        <footer className="mt-12 py-6 border-t border-[#e5e4e7] dark:border-[#2e303a] text-center text-sm">
          <p>© {new Date().getFullYear()} Metaverse Sherpa. All rights reserved.</p>
        </footer>
      </div>
    </div>
  );
};

export default Layout;
