import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';

const Dashboard: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center">
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.37)] max-w-2xl w-full">
        <h2 className="text-3xl font-bold text-[#f3f4f6] mb-4">Welcome back, Trader.</h2>
        <p className="text-gray-400 mb-8 leading-relaxed">
          The React SPA migration is in progress. The data stores and UI shell have been scaffolded with Zustand and Tailwind CSS v4.
        </p>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-[#1f2028] border border-[#2e303a] rounded-xl p-6 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]">
            <p className="text-xs text-cyan-400 uppercase tracking-widest font-bold mb-2">Total Equity</p>
            <p className="text-2xl font-mono text-white">$0.00</p>
          </div>
          <div className="bg-[#1f2028] border border-[#2e303a] rounded-xl p-6 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)]">
            <p className="text-xs text-emerald-400 uppercase tracking-widest font-bold mb-2">Active Positions</p>
            <p className="text-2xl font-mono text-white">0</p>
          </div>
        </div>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
