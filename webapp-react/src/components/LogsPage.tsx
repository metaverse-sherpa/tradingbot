import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Copy, Filter, Terminal } from 'lucide-react';
import api from '../lib/api';
import { useToast } from './Toast';

type Service = 'webapi' | 'tradingbot';

const LogsPage: React.FC = () => {
  const { showToast } = useToast();
  const [mobileTab, setMobileTab] = useState<Service>('webapi');
  const [webapiLogs, setWebapiLogs] = useState<string>('');
  const [tradingbotLogs, setTradingbotLogs] = useState<string>('');
  const [webapiFilter, setWebapiFilter] = useState(() => localStorage.getItem('webapi_log_filter') || '');
  const [tradingbotFilter, setTradingbotFilter] = useState(() => localStorage.getItem('tradingbot_log_filter') || '');

  const webapiRef = useRef<HTMLDivElement>(null);
  const tradingbotRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async (service: Service) => {
    try {
      const res = await api.get(`/admin/logs?service=${service}`);
      if (res.data?.logs) {
        if (service === 'webapi') setWebapiLogs(res.data.logs);
        else setTradingbotLogs(res.data.logs);
      }
    } catch (e) {
      console.error(`Failed to fetch ${service} logs`, e);
    }
  }, []);

  // Initial fetch + polling
  useEffect(() => {
    fetchLogs('webapi');
    fetchLogs('tradingbot');

    const interval = setInterval(() => {
      const isMobile = window.innerWidth <= 768;
      if (!isMobile || mobileTab === 'webapi') fetchLogs('webapi');
      if (!isMobile || mobileTab === 'tradingbot') fetchLogs('tradingbot');
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchLogs, mobileTab]);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (webapiRef.current) {
      const el = webapiRef.current;
      const isNearBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 50;
      if (isNearBottom) el.scrollTop = el.scrollHeight;
    }
  }, [webapiLogs]);

  useEffect(() => {
    if (tradingbotRef.current) {
      const el = tradingbotRef.current;
      const isNearBottom = el.scrollHeight - el.clientHeight <= el.scrollTop + 50;
      if (isNearBottom) el.scrollTop = el.scrollHeight;
    }
  }, [tradingbotLogs]);

  const handleCopyLogs = (service: Service) => {
    const raw = service === 'webapi' ? webapiLogs : tradingbotLogs;
    if (!raw.trim()) {
      showToast('No logs to copy', 'error');
      return;
    }
    navigator.clipboard.writeText(raw).then(() => {
      showToast('All logs copied!', 'success');
    });
  };

  const handleFilter = (service: Service) => {
    const current = service === 'webapi' ? webapiFilter : tradingbotFilter;
    const result = prompt(
      `Enter text to filter ${service === 'webapi' ? 'Web API' : 'Trading Bot'} logs (leave blank to clear):`,
      current
    );
    if (result !== null) {
      const trimmed = result.trim();
      if (trimmed === '') {
        localStorage.removeItem(`${service}_log_filter`);
        if (service === 'webapi') setWebapiFilter('');
        else setTradingbotFilter('');
        showToast('Filter cleared.', 'success');
      } else {
        localStorage.setItem(`${service}_log_filter`, trimmed);
        if (service === 'webapi') setWebapiFilter(trimmed);
        else setTradingbotFilter(trimmed);
        showToast('Filter applied.', 'success');
      }
    }
  };

  const handleRestart = async (service: Service) => {
    const label = service === 'webapi' ? 'Web API' : 'Trading Bot';
    if (!confirm(`Are you sure you want to restart ${label}?`)) return;
    try {
      const res = await api.post('/admin/restart', { service });
      if (res.data?.message || res.data?.error) {
        showToast(res.data.message || res.data.error, 'info');
      }
    } catch {
      showToast('Failed to restart service.', 'error');
    }
  };

  const handleCopyLine = (text: string) => {
    const selection = window.getSelection()?.toString();
    if (selection) return; // user is highlighting text
    navigator.clipboard.writeText(text).then(() => {
      showToast('Line copied!', 'success');
    });
  };

  const renderLogLines = (rawLogs: string, filter: string, color: string) => {
    let lines = rawLogs.split('\n');
    if (filter) {
      const lower = filter.toLowerCase();
      lines = lines.filter(l => l.toLowerCase().includes(lower));
    }

    return lines.map((line, i) => {
      const lower = line.toLowerCase();
      const isRestartLine = ['restarted', 'reloaded', 'restart', 'reload', 'starting', 'stopping', 'started', 'stopped']
        .some(kw => lower.includes(kw));

      // Build highlighted HTML
      let escaped = line
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      escaped = escaped.replace(/(error)/gi, '<span class="text-[#ff4444] font-bold">$1</span>');
      escaped = escaped.replace(/(warning)/gi, '<span class="text-yellow-400 font-bold">$1</span>');
      escaped = escaped.replace(/(started|reloaded)/gi, '<b class="text-white font-black">$1</b>');

      const content = isRestartLine
        ? `<span class="bg-[#ff4444]/30 text-[#ff4444] px-1 rounded font-bold">${escaped}</span>`
        : escaped;

      return (
        <div
          key={i}
          className="hover:bg-white/10 cursor-pointer px-1 -mx-1 rounded transition-colors select-text"
          title="Click to copy line"
          onClick={() => handleCopyLine(line)}
          dangerouslySetInnerHTML={{ __html: content }}
          style={{ color }}
        />
      );
    });
  };

  const renderPanel = (service: Service) => {
    const isWebapi = service === 'webapi';
    const rawLogs = isWebapi ? webapiLogs : tradingbotLogs;
    const filter = isWebapi ? webapiFilter : tradingbotFilter;
    const color = isWebapi ? '#4ade80' : '#3cd7ff';
    const label = isWebapi ? 'Web API' : 'Trading Bot';
    const actionLabel = isWebapi ? 'Reload' : 'Restart';
    const ref = isWebapi ? webapiRef : tradingbotRef;

    return (
      <div className="flex-1 min-w-0 flex flex-col bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl shadow-lg overflow-hidden">
        {/* Panel header */}
        <div className="flex justify-between items-center p-3 border-b border-white/10 shrink-0">
          <h4 className="font-bold text-sm text-white truncate">{label}</h4>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => handleCopyLogs(service)}
              title="Copy Visible Logs"
              className="bg-[#2a2e3d] text-gray-400 hover:text-white px-2 py-1.5 rounded transition-colors"
            >
              <Copy size={12} />
            </button>
            <button
              onClick={() => handleFilter(service)}
              title="Filter Logs"
              className={`bg-[#2a2e3d] px-2 py-1.5 rounded transition-colors ${
                filter ? 'text-yellow-400 border border-yellow-400/50' : 'text-gray-400 hover:text-white'
              }`}
            >
              <Filter size={12} />
            </button>
            <button
              onClick={() => handleRestart(service)}
              className="text-[10px] bg-red-500/20 text-red-400 px-3 py-1.5 rounded hover:bg-red-500/40 transition-colors font-bold uppercase tracking-wider"
            >
              {actionLabel}
            </button>
          </div>
        </div>

        {/* Log output */}
        <div
          ref={ref}
          className="flex-1 p-3 overflow-y-auto overflow-x-auto font-mono text-[10px] leading-tight bg-black custom-scrollbar"
          style={{ whiteSpace: 'pre', height: '65vh' }}
        >
          {!rawLogs ? (
            <span className="text-gray-500">Loading {label} logs...</span>
          ) : (
            renderLogLines(rawLogs, filter, color)
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 w-full max-w-[1200px] mx-auto flex flex-col pb-20">
      {/* Header */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-4 mb-4 shadow-lg">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Terminal size={20} className="text-cyan-400" /> Server Logs
        </h2>
      </div>

      {/* Mobile tabs */}
      <div className="flex gap-2 mb-4 md:hidden">
        <button
          onClick={() => setMobileTab('webapi')}
          className={`flex-1 py-2 text-sm font-bold rounded-lg border transition-colors ${
            mobileTab === 'webapi'
              ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50'
              : 'bg-[#1b1f2c]/70 text-gray-400 border-white/10'
          }`}
        >
          Web API
        </button>
        <button
          onClick={() => setMobileTab('tradingbot')}
          className={`flex-1 py-2 text-sm font-bold rounded-lg border transition-colors ${
            mobileTab === 'tradingbot'
              ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/50'
              : 'bg-[#1b1f2c]/70 text-gray-400 border-white/10'
          }`}
        >
          Trading Bot
        </button>
      </div>

      {/* Desktop: side-by-side. Mobile: active tab only */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Desktop: always show both */}
        <div className="hidden md:contents">
          {renderPanel('webapi')}
          {renderPanel('tradingbot')}
        </div>
        {/* Mobile: show only active tab */}
        <div className="contents md:hidden">
          {renderPanel(mobileTab)}
        </div>
      </div>
    </div>
  );
};

export default LogsPage;
