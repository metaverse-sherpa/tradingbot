import React, { useState, useEffect } from 'react';
import { Activity, Cpu, Database, Network, TrendingUp } from 'lucide-react';

const MESSAGES = [
  { text: "Consulting the Metaverse Sherpa...", icon: Cpu },
  { text: "Analyzing the markets...", icon: TrendingUp },
  { text: "Checking open positions...", icon: Activity },
  { text: "Crunching the numbers...", icon: Database },
  { text: "Fetching real-time data...", icon: Network }
];

const LoadingDisplay: React.FC = () => {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % MESSAGES.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  const CurrentIcon = MESSAGES[messageIndex].icon;

  return (
    <div className="flex flex-col items-center justify-center space-y-4 p-8">
      <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-cyan-500/10 border border-cyan-500/20">
        <div className="absolute inset-0 border-t-2 border-cyan-400 rounded-full animate-spin"></div>
        <CurrentIcon size={24} className="text-cyan-400 animate-pulse" />
      </div>
      <div className="h-6 overflow-hidden">
        <p key={messageIndex} className="text-sm font-medium text-cyan-400/80 tracking-wide animate-in slide-in-from-bottom-2 fade-in duration-300">
          {MESSAGES[messageIndex].text}
        </p>
      </div>
    </div>
  );
};

export default LoadingDisplay;
