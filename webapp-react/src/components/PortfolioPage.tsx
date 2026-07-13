import React, { useState, useEffect, useRef } from 'react';

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import {
  Sparkles, FileUp, Plus, Edit2, Trash2, Search,
  RefreshCw, X, Wallet,
  UploadCloud, Zap, ArrowUp, ArrowDown,
  Landmark, Coins, ChevronLeft, ChevronRight, Check
} from 'lucide-react';
import api from '../lib/api';

import { useToast } from './Toast';
import { useAuthStore } from '../store/useStore';

const COLORS = ['#3cd7ff', '#00C853', '#8A2BE2', '#FF8C00', '#FF1493', '#00CED1', '#ADFF2F', '#A9A9A9'];

const analysisMessages = [
  "Consulting the crypto oracles...",
  "Dusting off the blockchain...",
  "Negotiating with rogue trading bots...",
  "Polishing your diamond hands...",
  "Calibrating the moon trajectory...",
  "Feeding the AI hamsters...",
  "Decoding Elon's latest tweet...",
  "Searching for lost Bitcoin in couch cushions...",
  "Asking the Metaverse Sherpa for directions...",
  "Translating bear market roars...",
  "Applying paper hands repellent...",
  "Calculating the optimal time to HODL...",
  "Waiting for the blockchain to untangle...",
  "Bribing the algorithmic overlords...",
  "Analyzing your risk of getting rekt...",
  "Loading the hopium dispensers...",
  "Summoning the ghost of Satoshi...",
  "Checking if the trend is still your friend...",
  "Consulting the magic 8-ball of finance...",
  "Converting fiat tears into crypto gains...",
  "Mining digital gold with a virtual pickaxe...",
  "Pumping the algorithmic iron...",
  "Checking the alignment of the financial stars...",
  "Trekking through the digital Himalayas...",
  "Finalizing your ticket to the moon..."
];


const PortfolioPage: React.FC = () => {
  const { showToast } = useToast();
  const { user } = useAuthStore();

  // Positions and general stats
  const [positions, setPositions] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({});
  const [allocationTab, setAllocationTab] = useState<'all' | 'stock' | 'crypto'>('all');
  const [holdingsTab, setHoldingsTab] = useState<'all' | 'stock' | 'crypto'>('all');
  const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' } | null>(null);

  // AI analysis and news
  const [analysisHistory, setAnalysisHistory] = useState<any[]>([]);
  const [currentAnalysisIndex, setCurrentAnalysisIndex] = useState(0);
  const analysis = analysisHistory[currentAnalysisIndex] || null;
  const prevScore = analysisHistory[currentAnalysisIndex + 1]?.score || null;
  const [news, setNews] = useState<any[]>([]);
  const [newsCounts, setNewsCounts] = useState<any>({ bullish: 0, bearish: 0, neutral: 0 });

  // Loading states
  const [loading, setLoading] = useState(true);
  const [newsLoading, setNewsLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisMessageIndex, setAnalysisMessageIndex] = useState(0);
  const [parsingCSV, setParsingCSV] = useState(false);

  // Any Good Buys state
  const [goodBuys, setGoodBuys] = useState<any[] | null>(null);
  const [loadingGoodBuys, setLoadingGoodBuys] = useState(false);
  const [showGoodBuys, setShowGoodBuys] = useState(false);

  // Search
  const [searchQuery, setSearchQuery] = useState('');

  // Add / Edit position modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPosition, setEditingPosition] = useState<any>(null);
  const [formSymbol, setFormSymbol] = useState('');
  const [formCategory, setFormCategory] = useState<'stock' | 'crypto'>('stock');
  const [formQty, setFormQty] = useState('');
  const [formEntryPrice, setFormEntryPrice] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formYield, setFormYield] = useState('');

  // CSV Modal state
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [imageBase64, setImageBase64] = useState('');
  const [imageMimeType, setImageMimeType] = useState('');
  const [parsedCSVPositions, setParsedCSVPositions] = useState<any[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Show detailed instructions state
  const [showHowOpen, setShowHowOpen] = useState(false);

  // AI Config Modal state
  const [cashModalOpen, setCashModalOpen] = useState(false);
  const [cashInputVal, setCashInputVal] = useState('');
  
  // Custom Delete Modal State
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [positionToDelete, setPositionToDelete] = useState<any>(null);
  const [addProceedsToCash, setAddProceedsToCash] = useState(true);
  const [customProceeds, setCustomProceeds] = useState('');
  
  // Add Position Deduct Checkbox State
  const [deductFromCash, setDeductFromCash] = useState(true);
  
  // Insufficient Cash Dialog State
  const [insufficientCashOpen, setInsufficientCashOpen] = useState(false);
  const [pendingPositionPayload, setPendingPositionPayload] = useState<any>(null);

  const [riskProfile, setRiskProfile] = useState(user?.risk_profile || 'Moderate');
  const [investmentGoal, setInvestmentGoal] = useState(user?.investment_goal || 'Growth');

  // Active signals and selected signal for modal
  const [activeSignals, setActiveSignals] = useState<any[]>([]);
  const [selectedSignal, setSelectedSignal] = useState<any | null>(null);

  // Fetch portfolio data
  const fetchPortfolioData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await api.get('/portfolio');
      setPositions(res.data.positions || []);
      setStats(res.data.stats || {});
    } catch (err) {
      console.error("Failed to fetch portfolio data", err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Fetch news
  const fetchNews = async () => {
    setNewsLoading(true);
    try {
      const res = await api.get('/portfolio/news');
      setNews(res.data.news || []);
      setNewsCounts(res.data.counts || { bullish: 0, bearish: 0, neutral: 0 });
    } catch (err) {
      console.error("Failed to fetch news", err);
    } finally {
      setNewsLoading(false);
    }
  };

  // Fetch latest AI analysis
  const fetchAnalysis = async () => {
    try {
      const res = await api.get('/portfolio/analysis/history');
      if (res.data && res.data.history && res.data.history.length > 0) {
        setAnalysisHistory(res.data.history);
        setCurrentAnalysisIndex(0);
      } else {
        setAnalysisHistory([]);
      }
    } catch (err) {
      console.error("Failed to fetch latest analysis", err);
    }
  };

  // Fetch active signals
  const fetchActiveSignals = async () => {
    try {
      const res = await api.get('/signals/active');
      setActiveSignals(res.data || []);
    } catch (err) {
      console.error("Failed to fetch active signals", err);
    }
  };

  // Mount effects
  useEffect(() => {
    fetchPortfolioData();
    fetchAnalysis();
    fetchNews();
    fetchActiveSignals();
  }, []);

  useEffect(() => {
    if (user?.risk_profile) setRiskProfile(user.risk_profile);
    if (user?.investment_goal) setInvestmentGoal(user.investment_goal);
  }, [user]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (analyzing) {
      setAnalysisMessageIndex(0);
      interval = setInterval(() => {
        setAnalysisMessageIndex((prev) => (prev + 1) % analysisMessages.length);
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [analyzing]);

  // AI analysis trigger
  const runAIAnalysis = async () => {

    setAnalyzing(true);
    try {
      await api.post('/portfolio/analyze', {
        risk_profile: riskProfile,
        investment_goal: investmentGoal
      });

      // Fetch score details to get updated previous score banner logic
      await fetchAnalysis();

      if ((window as any).dataLayer) {
        (window as any).dataLayer.push({
          event: 'portfolio_analysis_run'
        });
      }
    } catch (err: any) {
      if (err.response?.status === 429) {
        showToast(err.response.data?.error || "You can only run a new analysis once every 24 hours unless you update your holdings.", "error");
      } else {
        console.error("AI Analysis failed", err);
        showToast("AI Portfolio Analysis failed. Please check your Gemini settings.", "error");
      }
    } finally {
      setAnalyzing(false);
    }
  };

  // Fetch Good Buys
  const fetchGoodBuys = async () => {
    setLoadingGoodBuys(true);
    setShowGoodBuys(true);
    setGoodBuys(null); // clear old
    try {
      const res = await api.post('/portfolio/good-buys', {
        risk_profile: riskProfile,
        investment_goal: investmentGoal
      });
      setGoodBuys(res.data.suggestions || []);
      // Re-fetch analysis so the updated Detailed Implementation Plan includes the good buys
      fetchAnalysis();
    } catch (err: any) {
      console.error("Failed to fetch good buys", err);
      showToast(err.response?.data?.error || "Failed to generate good buys.", "error");
      setShowGoodBuys(false);
    } finally {
      setLoadingGoodBuys(false);
    }
  };

  // Toggle action plan item
  const toggleAction = async (idx: number) => {
    if (!analysis || !analysis.id) return;
    
    const newCompleted = [...(analysis.completed_actions || [])];
    while (newCompleted.length <= idx) {
      newCompleted.push(false);
    }
    newCompleted[idx] = !newCompleted[idx];
    
    // Optimistic UI update
    const updatedHistory = [...analysisHistory];
    updatedHistory[currentAnalysisIndex] = {
      ...analysis,
      completed_actions: newCompleted
    };
    setAnalysisHistory(updatedHistory);
    
    try {
      await api.post(`/portfolio/analysis/${analysis.id}/check`, {
        completed_actions: newCompleted
      });
    } catch (err) {
      console.error("Failed to update action checklist", err);
    }
  };

  // Delete position handler
  const triggerDelete = (position: any) => {
    setPositionToDelete(position);
    setAddProceedsToCash(true);
    setCustomProceeds(position.market_value ? position.market_value.toString() : (position.quantity * position.avg_entry_price).toString());
    setDeleteConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!positionToDelete) return;
    try {
      const proceeds = parseFloat(customProceeds) || 0;
      await api.delete(`/portfolio/position/${positionToDelete.id}?add_to_cash=${addProceedsToCash}&proceeds=${proceeds}`);
      setDeleteConfirmOpen(false);
      setPositionToDelete(null);
      fetchPortfolioData(true);
      fetchNews();
    } catch (err) {
      console.error(err);
      showToast("Failed to delete position.", "error");
    }
  };

  // Manual Add / Edit Submit handler
  const handleSavePosition = async (e?: React.FormEvent, forceTopUp = false) => {
    if (e) e.preventDefault();
    if (!formSymbol || !formQty || !formEntryPrice || !formDate) {
      showToast("Please fill out all required fields.", "error");
      return;
    }

    const qty = parseFloat(formQty);
    const price = parseFloat(formEntryPrice);

    const payload = {
      symbol: formSymbol,
      category: formCategory,
      quantity: qty,
      avg_entry_price: price,
      purchase_date: formDate,
      dividend_yield: formYield ? parseFloat(formYield) : 0.0,
      deduct_from_cash: deductFromCash && !editingPosition,
      auto_top_up: forceTopUp
    };

    if (deductFromCash && !editingPosition && !forceTopUp) {
      const requiredCash = qty * price;
      if (requiredCash > (stats.cash_balance || 0)) {
        setPendingPositionPayload(payload);
        setInsufficientCashOpen(true);
        return; // wait for user confirmation
      }
    }

    try {
      if (editingPosition) {
        await api.put(`/portfolio/position/${editingPosition.id}`, payload);
      } else {
        await api.post('/portfolio/position', payload);
      }
      setModalOpen(false);
      setInsufficientCashOpen(false);
      setPendingPositionPayload(null);
      showToast("Position saved successfully!");
      fetchPortfolioData(true);
      fetchNews();
    } catch (err) {
      console.error(err);
      showToast("Failed to save position.", "error");
    }
  };

  const saveCashBalance = async () => {
    try {
      const val = parseFloat(cashInputVal);
      if (isNaN(val)) throw new Error("Invalid number");
      await api.post('/portfolio/cash', { cash_balance: val });
      setCashModalOpen(false);
      fetchPortfolioData(true);
      showToast("Cash balance updated!");
    } catch (err) {
      showToast("Failed to update cash balance.", "error");
    }
  };

  // Parse CSV via backend AI
  const handleParseCSV = async () => {
    if (!csvText && !imageBase64) {
      showToast("Please upload an image, enter CSV text, or select a CSV file first.", "error");
      return;
    }
    setParsingCSV(true);
    try {
      let res;
      if (imageBase64) {
        res = await api.post('/portfolio/parse-image', { image_base64: imageBase64, mime_type: imageMimeType });
      } else {
        res = await api.post('/portfolio/parse-csv', { csv_content: csvText });
      }
      setParsedCSVPositions(res.data.positions || []);
    } catch (err) {
      console.error(err);
      showToast("Failed to parse with AI. Please check your file layout.", "error");
    } finally {
      setParsingCSV(false);
    }
  };

  // Save CSV imports
  const handleImportCSVPositions = async () => {
    if (parsedCSVPositions.length === 0) return;
    try {
      await api.post('/portfolio/import', { positions: parsedCSVPositions });
      setCsvModalOpen(false);
      setParsedCSVPositions([]);
      setCsvText('');
      setImageBase64('');
      setImageMimeType('');
      setCsvFile(null);
      fetchPortfolioData(true);
      fetchNews();
    } catch (err) {
      console.error(err);
      showToast("Failed to import CSV positions.", "error");
    }
  };

  // File selection for CSV
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setCsvFile(file);
      setCsvText('');
      setImageBase64('');
      setImageMimeType('');

      const reader = new FileReader();
      if (file.type.startsWith('image/')) {
        reader.onload = (event) => {
          const result = event.target?.result as string;
          const base64Data = result.split(',')[1];
          setImageBase64(base64Data);
          setImageMimeType(file.type);
        };
        reader.readAsDataURL(file);
      } else {
        reader.onload = (event) => {
          const text = event.target?.result as string;
          setCsvText(text);
        };
        reader.readAsText(file);
      }
    }
  };

  // Open add modal helper
  const openAddModal = () => {
    setEditingPosition(null);
    setFormSymbol('');
    setFormCategory('stock');
    setFormQty('');
    setFormEntryPrice('');
    setFormDate(new Date().toISOString().split('T')[0]);
    setFormYield('');
    setModalOpen(true);
  };

  // Open edit modal helper
  const openEditModal = (pos: any) => {
    setEditingPosition(pos);
    setFormSymbol(pos.symbol);
    setFormCategory(pos.category);
    setFormQty(pos.quantity.toString());
    setFormEntryPrice(pos.avg_entry_price.toString());
    setFormDate(pos.purchase_date);
    setFormYield(pos.dividend_yield ? (pos.dividend_yield * 100).toFixed(2) : '');
    setModalOpen(true);
  };

  // Filter positions by search query and category tab
  const filteredPositions = positions.filter(p =>
    (holdingsTab === 'all' || p.category === holdingsTab) &&
    (p.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
     p.name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const displayAllocations = React.useMemo(() => {
    const filtered = positions.filter(p => allocationTab === 'all' || p.category === allocationTab);
    
    const allocMap = new Map<string, number>();
    let totalValue = 0;
    
    filtered.forEach(p => {
      const current = allocMap.get(p.symbol) || 0;
      const val = p.market_value || 0;
      if (val > 0) {
        allocMap.set(p.symbol, current + val);
        totalValue += val;
      }
    });
    
    return Array.from(allocMap.entries()).map(([name, value]) => ({
      name,
      value,
      percentage: totalValue > 0 ? (value / totalValue) * 100 : 0
    })).sort((a, b) => b.value - a.value);
  }, [positions, allocationTab]);

  const sortedPositions = React.useMemo(() => {
    let sortableItems = [...filteredPositions];
    if (sortConfig !== null) {
      sortableItems.sort((a, b) => {
        let aValue = a[sortConfig.key];
        let bValue = b[sortConfig.key];

        if (aValue === undefined || aValue === null) aValue = '';
        if (bValue === undefined || bValue === null) bValue = '';

        if (aValue < bValue) {
          return sortConfig.direction === 'asc' ? -1 : 1;
        }
        if (aValue > bValue) {
          return sortConfig.direction === 'asc' ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [filteredPositions, sortConfig]);

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'desc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc';
    }
    setSortConfig({ key, direction });
  };

  const renderSortIcon = (key: string) => {
    if (sortConfig?.key === key) {
      return sortConfig.direction === 'asc' ? <ArrowUp size={12} className="inline ml-1 text-cyan-400" /> : <ArrowDown size={12} className="inline ml-1 text-cyan-400" />;
    }
    return <ArrowDown size={12} className="inline ml-1 opacity-0 group-hover:opacity-50 transition-opacity" />;
  };

  if (loading) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center gap-4">
        <RefreshCw className="animate-spin text-cyan-400" size={32} />
        <span className="text-gray-400 text-sm">Loading portfolio holdings & live market prices...</span>
      </div>
    );
  }

  // Format currencies helper
  const fmt = (val: any) => {
    const num = parseFloat(val);
    if (isNaN(num)) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
  };

  // Color mapper helper for sentiment
  const getSentimentStyle = (sentiment: string) => {
    if (sentiment === 'Bullish') return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    if (sentiment === 'Bearish') return 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
    return 'bg-gray-500/10 text-gray-400 border border-gray-500/20';
  };

  return (
    <div className="w-full min-w-0 space-y-6 max-w-7xl mx-auto px-1 md:px-0 animate-in fade-in duration-300">

      {/* 🚀 Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl md:text-2xl font-black text-[#f3f4f6] flex items-center gap-2 md:gap-3 tracking-wide uppercase">
            <span className="bg-cyan-500/15 p-2 md:p-2.5 rounded-xl border border-cyan-500/30 text-cyan-400">
              <Wallet size={18} />
            </span>
            Stock & Crypto Portfolio
          </h2>
          <p className="text-gray-400 text-[11px] md:text-sm mt-1">Track static holdings, perform real-time AI audits and analysis.</p>
        </div>

        <div className="grid grid-cols-2 sm:flex sm:items-center gap-2 w-full sm:w-auto">
          {positions.length > 0 && (
            <>
              <button
                onClick={runAIAnalysis}
                disabled={analyzing}
                className="flex items-center justify-center gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white px-3 py-2 rounded-xl text-xs md:text-sm font-bold shadow-[0_0_15px_rgba(138,43,226,0.3)] transition-all uppercase tracking-wider disabled:opacity-50 w-full sm:w-auto"
              >
                {analyzing ? <RefreshCw className="animate-spin" size={14} /> : <Sparkles size={14} />}
                {analyzing ? 'Analyzing...' : 'AI Analysis'}
              </button>
              
              <button
                onClick={fetchGoodBuys}
                disabled={loadingGoodBuys}
                className="flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white px-3 py-2 rounded-xl text-xs md:text-sm font-bold shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all uppercase tracking-wider disabled:opacity-50 w-full sm:w-auto"
              >
                {loadingGoodBuys ? <RefreshCw className="animate-spin" size={14} /> : <Search size={14} />}
                {loadingGoodBuys ? 'Searching...' : 'Good Buys?'}
              </button>
            </>
          )}

          <button
            onClick={() => setCsvModalOpen(true)}
            className="flex items-center justify-center gap-2 bg-[#1f2028] border border-white/10 hover:border-white/20 text-gray-200 px-3 py-2 rounded-xl text-xs md:text-sm font-bold transition-all uppercase tracking-wider w-full sm:w-auto"
          >
            <FileUp size={14} /> Import
          </button>

          <button
            onClick={openAddModal}
            className="flex items-center justify-center gap-2 bg-[#00C853] hover:bg-[#00E676] text-black px-4 py-2 rounded-xl text-xs md:text-sm font-black shadow-[0_0_15px_rgba(0,200,83,0.3)] transition-all uppercase tracking-wider w-full sm:w-auto"
          >
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="bg-[#131620] border border-white/5 p-12 rounded-2xl flex flex-col items-center justify-center text-center space-y-4 mt-8 animate-in zoom-in-95 duration-500">
          <div className="bg-cyan-500/10 p-5 rounded-full text-cyan-400 mb-2 border border-cyan-500/20">
            <Wallet size={48} />
          </div>
          <h3 className="text-2xl md:text-3xl font-black text-white uppercase tracking-wide">Welcome to your Portfolio</h3>
          <p className="text-sm text-gray-400 max-w-md leading-relaxed">
            Import a CSV or add your positions manually to get started. Once you've added your holdings, we'll unlock real-time AI analysis, KPI dashboards, and your automated news feed.
          </p>
          <div className="flex gap-4 pt-4">
            <button
              onClick={() => setCsvModalOpen(true)}
              className="flex items-center justify-center gap-2 bg-[#1f2028] border border-white/10 hover:border-white/20 text-gray-200 px-6 py-3 rounded-xl text-sm font-bold transition-all uppercase tracking-wider"
            >
              <FileUp size={16} /> Import Holdings
            </button>

            <button
              onClick={openAddModal}
              className="flex items-center justify-center gap-2 bg-[#00C853] hover:bg-[#00E676] text-black px-6 py-3 rounded-xl text-sm font-black shadow-[0_0_15px_rgba(0,200,83,0.3)] transition-all uppercase tracking-wider"
            >
              <Plus size={16} /> Add Position
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* 🎉 Score Banner or Analyzing Overlay */}
          <div className="relative min-h-[80px]">
            {analysis && (
              <div className={`bg-[#14231E]/40 border border-emerald-500/20 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in slide-in-from-top-4 duration-300 ${analyzing ? 'blur-sm opacity-30 pointer-events-none' : ''}`}>
              <div className="flex items-start sm:items-center gap-3">
                <span className="bg-emerald-500/10 text-emerald-400 p-2 rounded-lg text-lg flex-shrink-0">🏆</span>
                <div>
                  <h4 className="text-sm font-bold text-white uppercase tracking-wider">Portfolio Health Audited!</h4>
                  <p className="text-xs text-gray-400 mt-0.5 leading-normal">
                    Current health score: <span className="text-emerald-400 font-bold">{analysis.score}/100</span>
                    {prevScore !== null && prevScore !== analysis.score && (
                      <span>
                        {" "}(from <span className="text-gray-300">{prevScore}/100</span>, {" "}
                        <span className={analysis.score > prevScore ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                          {analysis.score > prevScore ? `+${analysis.score - prevScore}` : `${analysis.score - prevScore}`} pts
                        </span>)
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowHowOpen(!showHowOpen)}
                className="w-full sm:w-auto bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-emerald-400 font-bold px-3 py-2 sm:py-1.5 rounded-lg text-xs tracking-wider uppercase transition-colors text-center"
              >
                {showHowOpen ? 'Hide Guide' : 'Show me how'}
              </button>
            </div>
            )}
            
            {/* Analyzing Overlay */}
            {analyzing && (
              <div className="absolute inset-0 flex flex-col items-center justify-center rounded-2xl z-10 backdrop-blur-[2px]">
                <div className="flex items-center gap-3 bg-[#1f2028] border border-purple-500/30 text-white px-5 py-3 rounded-xl shadow-lg">
                  <RefreshCw className="animate-spin text-purple-400" size={18} />
                  <span className="font-bold tracking-wider animate-pulse">
                    {analysisMessages[analysisMessageIndex]}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* 📊 KPI Cards Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
            {/* Card 1: Total Balance */}
            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Total Balance</span>
              <h3 className="text-lg md:text-2xl font-black text-white mt-1 md:mt-2">{fmt(stats.total_portfolio_value || stats.market_value)}</h3>
              <p className="text-gray-500 text-[9px] md:text-[10px] mt-1">Positions + Cash</p>
            </div>

            {/* Card 2: Cash Available */}
            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden group">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider flex items-center justify-between">
                Cash Available
                <button 
                  onClick={() => { setCashInputVal((stats.cash_balance || 0).toString()); setCashModalOpen(true); }}
                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-white transition-opacity p-0.5 rounded"
                >
                  <Edit2 size={12} />
                </button>
              </span>
              <h3 className="text-lg md:text-2xl font-black text-white mt-1 md:mt-2">{fmt(stats.cash_balance || 0)}</h3>
              <p 
                className="text-gray-500 text-[9px] md:text-[10px] mt-1 cursor-pointer hover:text-emerald-400"
                onClick={() => { setCashInputVal((stats.cash_balance || 0).toString()); setCashModalOpen(true); }}
              >
                Manage cash
              </p>
            </div>

            {/* Card 3: Holdings Value (Renamed from Market Value) */}
            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Holdings Value</span>
              <h3 className="text-lg md:text-2xl font-black text-white mt-1 md:mt-2">{fmt(stats.market_value)}</h3>
              <p className="text-gray-500 text-[9px] md:text-[10px] mt-1">Invested: {fmt(stats.cost_basis)}</p>
            </div>

            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Total P/L</span>
              <h3 className={`text-lg md:text-2xl font-black mt-1 md:mt-2 ${stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.total_pnl >= 0 ? '+' : ''}{fmt(stats.total_pnl)}
              </h3>
              <p className={`text-[9px] md:text-[10px] mt-1 font-bold ${stats.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.total_pnl_pct >= 0 ? '▲' : '▼'} {stats.total_pnl_pct.toFixed(2)}%
              </p>
            </div>

            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Daily P/L</span>
              <h3 className={`text-lg md:text-2xl font-black mt-1 md:mt-2 ${stats.daily_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.daily_pnl >= 0 ? '+' : ''}{fmt(stats.daily_pnl)}
              </h3>
              <p className={`text-[9px] md:text-[10px] mt-1 font-bold ${stats.daily_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.daily_pnl_pct >= 0 ? '▲' : '▼'} {stats.daily_pnl_pct.toFixed(2)}%
              </p>
            </div>

            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Today's Top Mover</span>
              <h3 className="text-base md:text-lg font-black text-white mt-1 md:mt-2 truncate">
                {stats.top_mover ? stats.top_mover : '-'}
              </h3>
              <p className={`text-[9px] md:text-[10px] mt-1.5 font-bold ${stats.top_mover_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.top_mover_pct >= 0 ? '▲' : '▼'} {stats.top_mover_pct.toFixed(2)}%
              </p>
            </div>

            <div className="bg-[#131620] border border-white/5 p-4 rounded-2xl relative overflow-hidden col-span-2 lg:col-span-1">
              <span className="text-gray-500 text-[10px] md:text-xs font-bold uppercase tracking-wider">Est. Annual Div</span>
              <h3 className="text-lg md:text-2xl font-black text-white mt-1 md:mt-2">{fmt(stats.annual_dividends)}</h3>
              <p className="text-gray-500 text-[9px] md:text-[10px] mt-1 font-bold">{stats.dividend_yield_pct.toFixed(2)}% Yield</p>
            </div>
          </div>

          {/* 🧭 Show Me How detailed guide */}
          {analysis && showHowOpen && (
            <div className="bg-[#1f2028] border border-white/10 rounded-2xl p-6 space-y-4 animate-in zoom-in-95 duration-200">
              <div className="flex flex-col sm:flex-row sm:justify-between items-start sm:items-center gap-3 border-b border-white/10 pb-3">
                <div className="flex items-center gap-3">
                  <h3 className="text-md font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Sparkles className="text-emerald-400" size={18} /> Detailed Implementation Guide
                  </h3>
                  
                  {analysisHistory.length > 1 && (
                    <div className="flex items-center gap-1 bg-black/40 rounded-lg p-0.5 border border-white/5">
                      <button 
                        onClick={() => setCurrentAnalysisIndex(Math.min(analysisHistory.length - 1, currentAnalysisIndex + 1))}
                        disabled={currentAnalysisIndex === analysisHistory.length - 1}
                        className="p-1 rounded hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                        title="Older analysis"
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <span className="text-[10px] text-gray-400 font-bold px-1">
                        {analysisHistory.length - currentAnalysisIndex} OF {analysisHistory.length}
                      </span>
                      <button 
                        onClick={() => setCurrentAnalysisIndex(Math.max(0, currentAnalysisIndex - 1))}
                        disabled={currentAnalysisIndex === 0}
                        className="p-1 rounded hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                        title="Newer analysis"
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  )}
                </div>
                <button onClick={() => setShowHowOpen(false)} className="text-gray-400 hover:text-white transition-colors self-end sm:self-auto">
                  <X size={18} />
                </button>
              </div>
              <div className="prose prose-invert max-w-none text-xs md:text-sm text-gray-300 leading-relaxed space-y-3">
                {analysis.show_me_how.split('\n').map((line: string, i: number) => {
                  if (line.startsWith('###')) return <h4 key={i} className="text-sm font-bold text-white uppercase mt-4 tracking-wide">{line.replace('###', '')}</h4>;
                  if (line.startsWith('##')) return <h3 key={i} className="text-base font-black text-white uppercase mt-4 tracking-wide">{line.replace('##', '')}</h3>;
                  return <p key={i}>{line}</p>;
                })}
              </div>
            </div>
          )}

          {/* ⚡ Action Plan & recommendations */}
          {analysis && (
            <div className="bg-[#131620] border border-white/5 rounded-2xl p-5 space-y-3.5">
              <div className="flex flex-col sm:flex-row sm:justify-between items-start sm:items-center gap-3">
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-bold text-white uppercase tracking-widest flex items-center gap-2">
                    🧭 Recommended Action Plan
                  </h3>
                  
                  {analysisHistory.length > 1 && (
                    <div className="flex items-center gap-1 bg-black/40 rounded-lg p-0.5 border border-white/5">
                      <button 
                        onClick={() => setCurrentAnalysisIndex(Math.min(analysisHistory.length - 1, currentAnalysisIndex + 1))}
                        disabled={currentAnalysisIndex === analysisHistory.length - 1}
                        className="p-1 rounded hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                        title="Older analysis"
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <span className="text-[10px] text-gray-400 font-bold px-1">
                        {analysisHistory.length - currentAnalysisIndex} OF {analysisHistory.length}
                      </span>
                      <button 
                        onClick={() => setCurrentAnalysisIndex(Math.max(0, currentAnalysisIndex - 1))}
                        disabled={currentAnalysisIndex === 0}
                        className="p-1 rounded hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                        title="Newer analysis"
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setShowHowOpen(!showHowOpen)}
                  className="flex items-center gap-1 bg-gradient-to-r from-emerald-500/15 to-teal-500/15 hover:from-emerald-500/25 hover:to-teal-500/25 border border-emerald-500/30 text-emerald-400 text-xs font-black px-3 py-1.5 rounded-lg uppercase tracking-wider transition-all"
                >
                  <Sparkles size={13} /> Show me how
                </button>
              </div>
              <div className="space-y-2">
                {analysis.action_plan && analysis.action_plan.map((act: string, idx: number) => {
                  const isChecked = analysis.completed_actions?.[idx] === true;
                  return (
                    <div 
                      key={idx} 
                      onClick={() => toggleAction(idx)}
                      className={`cursor-pointer border p-3.5 rounded-xl text-xs md:text-sm flex items-start gap-3 transition-colors ${isChecked ? 'bg-emerald-500/5 border-emerald-500/20 text-gray-400' : 'bg-[#1c1f2e]/60 border-white/5 text-gray-300'}`}
                    >
                      <div className={`w-5 h-5 flex items-center justify-center rounded-md border flex-shrink-0 mt-0.5 transition-colors ${isChecked ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-gray-500 bg-black/40 text-transparent'}`}>
                        {isChecked && <Check size={12} strokeWidth={4} />}
                      </div>
                      <span className={`leading-relaxed ${isChecked ? 'line-through opacity-50' : ''}`}>{act}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 📊 Mini stats bar */}
          <div className="bg-[#131620] border border-white/5 p-3 rounded-2xl grid grid-cols-2 md:grid-cols-7 gap-3 text-center">
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Avg. Daily P&L</p>
              <p className={`text-xs md:text-sm font-bold mt-1 ${stats.avg_daily_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {stats.avg_daily_pnl >= 0 ? '+' : ''}{fmt(stats.avg_daily_pnl)}/day
              </p>
            </div>
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Win Rate</p>
              <p className="text-xs md:text-sm font-bold text-white mt-1">{stats.win_rate.toFixed(0)}% profitable</p>
            </div>
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Best Performer</p>
              <p className="text-xs md:text-sm font-bold text-emerald-400 mt-1 truncate">
                {stats.best_performer ? `${stats.best_performer} +${stats.best_performer_pct.toFixed(1)}%` : '-'}
              </p>
            </div>
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Worst Performer</p>
              <p className="text-xs md:text-sm font-bold text-rose-400 mt-1 truncate">
                {stats.worst_performer ? `${stats.worst_performer} ${stats.worst_performer_pct.toFixed(1)}%` : '-'}
              </p>
            </div>
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Avg. Hold Time</p>
              <p className="text-xs md:text-sm font-bold text-white mt-1">{stats.avg_hold_time_days}d</p>
            </div>
            <div className="md:border-r border-white/5 last:border-0 md:last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Portfolio Age</p>
              <p className="text-xs md:text-sm font-bold text-white mt-1">
                {stats.portfolio_age_days > 365
                  ? `${(stats.portfolio_age_days / 365).toFixed(1)}y`
                  : `${stats.portfolio_age_days}d`}
              </p>
            </div>
            <div className="last:border-0 py-1">
              <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Positions</p>
              <p className="text-xs md:text-sm font-bold text-white mt-1">{stats.positions_count}</p>
            </div>
          </div>

          {/* Donut allocation chart & breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Allocations Card */}
            <div className="bg-[#131620] border border-white/5 rounded-2xl p-5 flex flex-col md:flex-row items-center gap-6">
              <div className="w-full md:w-1/2 flex flex-col items-center">
                <div className="flex flex-col sm:flex-row items-center justify-between w-full mb-4">
                  <span className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-2 sm:mb-0">Portfolio Allocation</span>
                  <div className="flex bg-white/5 p-1 rounded-lg">
                    {(['all', 'stock', 'crypto'] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => setAllocationTab(tab)}
                        className={`px-3 py-1 text-[10px] font-bold uppercase rounded-md transition-colors ${
                          allocationTab === tab 
                            ? 'bg-cyan-500/20 text-cyan-400' 
                            : 'text-gray-500 hover:text-white'
                        }`}
                      >
                        {tab === 'all' ? 'All' : tab === 'stock' ? 'Stocks' : 'Crypto'}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="w-48 h-48 relative">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={displayAllocations}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {displayAllocations.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: any) => fmt(value)} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-2xl font-black text-white">{displayAllocations.length}</span>
                    <span className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">Positions</span>
                  </div>
                </div>
              </div>

              <div className="w-full md:w-1/2 space-y-2 max-h-56 overflow-y-auto pr-1">
                <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">Holdings Breakdown</span>
                <div className="space-y-1.5">
                  {displayAllocations.slice(0, 5).map((alloc, idx) => (
                    <div key={idx} className="bg-white/5 border border-white/5 rounded-xl p-2.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                          style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                        />
                        <span className="text-xs font-bold text-white uppercase">{alloc.name}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-xs font-black text-white block">{fmt(alloc.value)}</span>
                        <span className="text-[10px] text-emerald-400 font-bold">{alloc.percentage.toFixed(1)}%</span>
                      </div>
                    </div>
                  ))}
                  {displayAllocations.length > 5 && (
                    <div className="text-center text-[10px] text-gray-500 font-bold pt-1">
                      + {displayAllocations.length - 5} other holdings
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 📰 Real-Time News feed */}
            <div className="bg-[#131620] border border-white/5 rounded-2xl p-5 flex flex-col justify-between max-h-[300px] md:max-h-none overflow-hidden">
              <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 border-b border-white/5 pb-2.5 mb-3">
                <h3 className="text-xs font-bold text-white uppercase tracking-widest">Holdings News Feed</h3>
                <div className="flex flex-wrap gap-1.5">
                  <span className="bg-emerald-500/10 text-emerald-400 text-[9px] font-bold px-2 py-0.5 rounded border border-emerald-500/20 uppercase whitespace-nowrap">
                    {newsCounts.bullish} Bullish
                  </span>
                  <span className="bg-rose-500/10 text-rose-400 text-[9px] font-bold px-2 py-0.5 rounded border border-rose-500/20 uppercase whitespace-nowrap">
                    {newsCounts.bearish} Bearish
                  </span>
                  <span className="bg-gray-500/10 text-gray-400 text-[9px] font-bold px-2 py-0.5 rounded border border-gray-500/20 uppercase whitespace-nowrap">
                    {newsCounts.neutral} Neutral
                  </span>
                </div>
              </div>

              {newsLoading ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-2 py-8">
                  <RefreshCw className="animate-spin text-cyan-400" size={20} />
                  <span className="text-[10px] text-gray-500 font-bold uppercase">Refreshing news...</span>
                </div>
              ) : news.length === 0 ? (
                <div className="text-center py-8 text-xs text-gray-500 font-bold uppercase">
                  No news found for current holdings.
                </div>
              ) : (
                <div className="space-y-2.5 overflow-y-auto max-h-[220px] pr-1">
                  {news.map((item, idx) => (
                    <a
                      key={idx}
                      href={item.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="bg-white/5 hover:bg-white/10 border border-white/5 rounded-xl p-3 block transition-all"
                    >
                      <div className="flex justify-between items-start gap-3">
                        <span className="text-[10px] bg-[#3cd7ff]/10 border border-[#3cd7ff]/20 text-[#3cd7ff] px-2 py-0.5 rounded font-black uppercase">
                          {item.symbol}
                        </span>
                        <span className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase ${getSentimentStyle(item.sentiment)}`}>
                          {item.sentiment}
                        </span>
                      </div>
                      <h4 className="text-xs font-bold text-white mt-1.5 line-clamp-1 leading-normal">{item.title}</h4>
                      <div className="flex items-center justify-between text-[9px] text-gray-500 mt-2 font-bold uppercase">
                        <span>{item.provider}</span>
                        <span>{item.pubDate ? new Date(item.pubDate).toLocaleDateString() : ''}</span>
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 📋 Positions Table */}
          <div className="bg-[#131620] border border-white/5 rounded-2xl p-5 space-y-4">
            <div className="flex flex-col md:flex-row items-center justify-between gap-3 border-b border-white/5 pb-3">
              <div className="flex flex-col sm:flex-row items-center gap-4 w-full md:w-auto">
                <h3 className="text-sm font-bold text-white uppercase tracking-widest whitespace-nowrap">All Holdings</h3>
                
                <div className="flex bg-white/5 p-1 rounded-lg">
                  {(['all', 'stock', 'crypto'] as const).map(tab => {
                    const count = positions.filter(p => tab === 'all' || p.category === tab).length;
                    return (
                      <button
                        key={tab}
                        onClick={() => setHoldingsTab(tab)}
                        className={`px-3 py-1.5 text-[10px] font-bold uppercase rounded-md transition-colors ${
                          holdingsTab === tab 
                            ? 'bg-cyan-500/20 text-cyan-400' 
                            : 'text-gray-500 hover:text-white'
                        }`}
                      >
                        {tab === 'all' ? 'All' : tab === 'stock' ? 'Stocks' : 'Crypto'} ({count})
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="relative w-full md:w-64">
                <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500">
                  <Search size={14} />
                </span>
                <input
                  type="text"
                  placeholder="Search by symbol or name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-[#1f2028] border border-[#2e303a] rounded-xl pl-9 pr-4 py-2 text-xs md:text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500 transition-colors"
                />
              </div>
            </div>

            <div className="max-w-full overflow-auto max-h-[70vh] pb-2">
              <table className="w-full min-w-[600px] text-left border-collapse text-xs md:text-sm relative">
                <thead className="sticky top-0 bg-[#131620] z-10 shadow-[0_4px_6px_-1px_rgba(0,0,0,0.1)]">
                  <tr className="border-b border-white/5 text-gray-500 font-bold uppercase tracking-wider text-[10px]">
                    <th className="pb-3 text-center w-8 hidden lg:table-cell">#</th>
                    <th className="pb-3 cursor-pointer group select-none" onClick={() => handleSort('symbol')}>Symbol{renderSortIcon('symbol')}</th>
                    <th className="pb-3 text-right cursor-pointer group select-none" onClick={() => handleSort('daily_pnl')}>Daily P&L{renderSortIcon('daily_pnl')}</th>
                    <th className="pb-3 text-right cursor-pointer group select-none" onClick={() => handleSort('overall_pnl')}>Overall P&L{renderSortIcon('overall_pnl')}</th>
                    <th className="pb-3 text-right hidden md:table-cell cursor-pointer group select-none" onClick={() => handleSort('cost_basis')}>Cost Basis{renderSortIcon('cost_basis')}</th>
                    <th className="pb-3 text-right hidden md:table-cell cursor-pointer group select-none" onClick={() => handleSort('current_price')}>Current Price{renderSortIcon('current_price')}</th>
                    <th className="pb-3 text-right cursor-pointer group select-none" onClick={() => handleSort('market_value')}>Mkt Value{renderSortIcon('market_value')}</th>
                    <th className="pb-3 text-right hidden lg:table-cell cursor-pointer group select-none" onClick={() => handleSort('dividend_yield')}>Div Yield{renderSortIcon('dividend_yield')}</th>
                    <th className="pb-3 text-right hidden sm:table-cell cursor-pointer group select-none" onClick={() => handleSort('allocation_pct')}>% of Port{renderSortIcon('allocation_pct')}</th>
                    <th className="pb-3 text-center hidden lg:table-cell cursor-pointer group select-none" onClick={() => handleSort('purchase_date')}>Purchase Date{renderSortIcon('purchase_date')}</th>
                    <th className="pb-3 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPositions.map((pos, idx) => (
                    <tr key={pos.id} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors">
                      <td className="py-4 text-center text-gray-500 font-bold hidden lg:table-cell">{idx + 1}</td>

                      <td className="py-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs ${pos.category === 'crypto' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' : 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'}`}>
                            {pos.category === 'crypto' ? <Coins size={16} /> : <Landmark size={16} />}
                          </span>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-white uppercase block">
                                {pos.symbol}
                              </span>
                              {activeSignals.find(s => s.symbol === pos.symbol) && (
                                <button
                                  onClick={() => setSelectedSignal(activeSignals.find(s => s.symbol === pos.symbol))}
                                  className="text-amber-400 hover:text-amber-300 transition-colors p-0.5 rounded-full hover:bg-amber-400/10"
                                  title="Active Signal"
                                >
                                  <Zap size={14} fill="currentColor" />
                                </button>
                              )}
                            </div>
                            <span className="text-[10px] text-gray-500 block max-w-[120px] truncate">{pos.name}</span>
                          </div>
                        </div>
                      </td>

                      <td className="py-4 text-right">
                        <span className={`font-bold block ${pos.daily_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {pos.daily_pnl >= 0 ? '+' : ''}{fmt(pos.daily_pnl)}
                        </span>
                        <span className={`text-[10px] font-bold block ${pos.daily_change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {pos.daily_change_pct >= 0 ? '+' : ''}{pos.daily_change_pct.toFixed(2)}%
                        </span>
                      </td>

                      <td className="py-4 text-right">
                        <span className={`font-bold block ${pos.overall_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {pos.overall_pnl >= 0 ? '+' : ''}{fmt(pos.overall_pnl)}
                        </span>
                        <span className={`text-[10px] font-bold block ${pos.overall_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {pos.overall_pnl_pct >= 0 ? '+' : ''}{pos.overall_pnl_pct.toFixed(2)}%
                        </span>
                      </td>

                      <td className="py-4 text-right hidden md:table-cell">
                        <span className="font-bold text-white block">{fmt(pos.cost_basis)}</span>
                        <span className="text-[10px] text-gray-500 block">
                          {pos.quantity.toString().slice(0, 6)} @ {fmt(pos.avg_entry_price)}
                        </span>
                      </td>

                      <td className="py-4 text-right hidden md:table-cell font-bold text-white">{fmt(pos.current_price)}</td>

                      <td className="py-4 text-right font-black text-white">{fmt(pos.market_value)}</td>

                      <td className="py-4 text-right font-bold text-gray-300 hidden lg:table-cell">
                        {pos.dividend_yield > 0 ? (
                          <>
                            <span className="block text-white">{(pos.dividend_yield * 100).toFixed(2)}%</span>
                            <span className="block text-[10px] text-gray-500">{fmt(pos.annual_dividend)}/yr</span>
                          </>
                        ) : '-'}
                      </td>

                      <td className="py-4 text-right hidden sm:table-cell">
                        <span className="font-bold text-cyan-400">{pos.allocation_pct.toFixed(1)}%</span>
                      </td>

                      <td className="py-4 text-center font-medium text-gray-300 hidden lg:table-cell">
                        {pos.purchase_date}
                      </td>

                      <td className="py-4 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            onClick={() => openEditModal(pos)}
                            className="bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/10 text-gray-400 hover:text-[#3cd7ff] p-1.5 rounded-lg transition-colors"
                          >
                            <Edit2 size={13} />
                          </button>
                          <button
                            onClick={() => triggerDelete(pos)}
                            className="bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/10 text-gray-400 hover:text-rose-400 p-1.5 rounded-lg transition-colors"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filteredPositions.length === 0 && (
                    <tr>
                      <td colSpan={11} className="text-center py-8 text-gray-500 font-bold uppercase tracking-wider">
                        No positions found matching your search.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* 📝 Add / Edit Modal */}
      {modalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1f2028] border border-white/10 rounded-2xl w-full max-w-md p-6 relative overflow-hidden animate-in zoom-in-95 duration-200">
            <button
              onClick={() => setModalOpen(false)}
              className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>

            <h3 className="text-lg font-black text-white uppercase tracking-wider mb-4">
              {editingPosition ? '🛠️ Edit Position' : '🆕 Add Position'}
            </h3>

            <form onSubmit={handleSavePosition} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Category</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setFormCategory('stock')}
                      className={`flex-1 py-2 text-xs font-bold rounded-lg border transition-all ${formCategory === 'stock' ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' : 'bg-transparent text-gray-400 border-white/5 hover:border-white/10'}`}
                    >
                      Stock
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormCategory('crypto')}
                      className={`flex-1 py-2 text-xs font-bold rounded-lg border transition-all ${formCategory === 'crypto' ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' : 'bg-transparent text-gray-400 border-white/5 hover:border-white/10'}`}
                    >
                      Crypto
                    </button>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Symbol</label>
                  <input
                    type="text"
                    required
                    placeholder="AAPL, BTC, etc."
                    value={formSymbol}
                    onChange={(e) => setFormSymbol(e.target.value.toUpperCase())}
                    className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-cyan-500 uppercase"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Quantity</label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="0.00"
                    value={formQty}
                    onChange={(e) => setFormQty(e.target.value)}
                    className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Avg Entry Price</label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="$0.00"
                    value={formEntryPrice}
                    onChange={(e) => setFormEntryPrice(e.target.value)}
                    className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Purchase Date</label>
                  <input
                    type="date"
                    required
                    value={formDate}
                    onChange={(e) => setFormDate(e.target.value)}
                    className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Div Yield % (Annual)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="e.g. 2.85"
                    value={formYield}
                    onChange={(e) => setFormYield(e.target.value)}
                    className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
                </div>
              </div>
              
              {!editingPosition && (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    id="deductFromCash"
                    checked={deductFromCash}
                    onChange={(e) => setDeductFromCash(e.target.checked)}
                    className="w-4 h-4 rounded border-white/10 bg-[#131620] text-cyan-500 focus:ring-cyan-500"
                  />
                  <label htmlFor="deductFromCash" className="text-xs text-gray-400">
                    Deduct cost from Cash Available
                  </label>
                </div>
              )}

              <div className="pt-2 flex gap-3">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="flex-1 bg-[#131620] hover:bg-[#181C28] border border-white/5 rounded-xl py-2 text-xs md:text-sm font-bold text-gray-400 hover:text-white transition-all uppercase tracking-wider"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 bg-[#00C853] hover:bg-[#00E676] rounded-xl py-2 text-xs md:text-sm font-black text-black shadow-[0_0_15px_rgba(0,200,83,0.3)] transition-all uppercase tracking-wider"
                >
                  Save
                </button>
              </div>
            </form>
          </div>
          </div>
        </div>
      )}

      {/* 💵 Cash Balance Modal */}
      {cashModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1f2028] border border-white/10 rounded-2xl w-full max-w-sm p-6 relative overflow-hidden animate-in zoom-in-95 duration-200">
            <button
              onClick={() => setCashModalOpen(false)}
              className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
            <h3 className="text-lg font-black text-white uppercase tracking-wider mb-4">
              💵 Update Cash Balance
            </h3>
            <div className="mb-4">
              <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block mb-1.5">Available Cash</label>
              <input
                type="number"
                step="any"
                required
                placeholder="$0.00"
                value={cashInputVal}
                onChange={(e) => setCashInputVal(e.target.value)}
                className="w-full bg-[#131620] border border-[#2e303a] rounded-lg px-3 py-2 text-xs md:text-sm text-white focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setCashModalOpen(false)}
                className="flex-1 bg-[#131620] hover:bg-[#181C28] border border-white/5 rounded-xl py-2 text-xs md:text-sm font-bold text-gray-400 hover:text-white transition-all uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveCashBalance}
                className="flex-1 bg-emerald-500 hover:bg-emerald-400 rounded-xl py-2 text-xs md:text-sm font-black text-black shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all uppercase tracking-wider"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ⚠️ Insufficient Cash Dialog */}
      {insufficientCashOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1f2028] border border-rose-500/30 rounded-2xl w-full max-w-sm p-6 relative overflow-hidden animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-black text-white uppercase tracking-wider mb-2 flex items-center gap-2">
              <AlertTriangle className="text-rose-400" size={20} />
              Insufficient Cash
            </h3>
            <p className="text-xs text-gray-400 mb-6">
              You do not have enough cash balance to cover this purchase. Would you like to automatically top up your cash balance to proceed?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => { setInsufficientCashOpen(false); setPendingPositionPayload(null); }}
                className="flex-1 bg-[#131620] border border-white/5 py-2 rounded-xl text-xs font-bold text-gray-400 hover:text-white transition-colors uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                onClick={() => { handleSavePosition(undefined, true); }}
                className="flex-1 bg-emerald-500 hover:bg-emerald-400 py-2 rounded-xl text-xs font-bold text-black shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-colors uppercase tracking-wider"
              >
                Top Up & Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🗑️ Custom Delete Confirm Modal */}
      {deleteConfirmOpen && positionToDelete && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60] flex items-center justify-center p-4">
          <div className="bg-[#1f2028] border border-rose-500/30 rounded-2xl w-full max-w-sm p-6 relative overflow-hidden animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-black text-white uppercase tracking-wider mb-2 flex items-center gap-2">
              <Trash2 className="text-rose-400" size={20} />
              Delete {positionToDelete.symbol}?
            </h3>
            <p className="text-xs text-gray-400 mb-4">
              Are you sure you want to remove this position from your portfolio?
            </p>
            
            <div className="bg-[#131620] rounded-xl p-3 mb-6 border border-white/5">
              <div className="flex items-center gap-2 mb-3">
                <input
                  type="checkbox"
                  id="addProceedsToCash"
                  checked={addProceedsToCash}
                  onChange={(e) => setAddProceedsToCash(e.target.checked)}
                  className="w-4 h-4 rounded border-white/10 bg-[#131620] text-emerald-500 focus:ring-emerald-500"
                />
                <label htmlFor="addProceedsToCash" className="text-xs font-bold text-gray-300">
                  Add sale proceeds to Cash Available
                </label>
              </div>
              
              {addProceedsToCash && (
                <div>
                  <label className="text-[10px] text-gray-500 uppercase tracking-wider font-bold mb-1 block">Proceeds Amount</label>
                  <input
                    type="number"
                    step="any"
                    value={customProceeds}
                    onChange={(e) => setCustomProceeds(e.target.value)}
                    className="w-full bg-[#1f2028] border border-[#2e303a] rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => { setDeleteConfirmOpen(false); setPositionToDelete(null); }}
                className="flex-1 bg-[#131620] border border-white/5 py-2 rounded-xl text-xs font-bold text-gray-400 hover:text-white transition-colors uppercase tracking-wider"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="flex-1 bg-rose-500 hover:bg-rose-400 py-2 rounded-xl text-xs font-bold text-white shadow-[0_0_15px_rgba(244,63,94,0.3)] transition-colors uppercase tracking-wider"
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {csvModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1f2028] border border-white/10 rounded-2xl w-full max-w-xl p-6 relative overflow-hidden animate-in zoom-in-95 duration-200">
            <button
              onClick={() => { setCsvModalOpen(false); setParsedCSVPositions([]); }}
              className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>

            <h3 className="text-lg font-black text-white uppercase tracking-wider mb-2">
              📄 Import Holdings
            </h3>
            <p className="text-xs text-gray-500 mb-4">Paste raw CSV text or drop a file (CSV or Image screenshot). Gemini AI detects tickers, quantity, and dates automatically.</p>

            {parsedCSVPositions.length === 0 ? (
              <div className="space-y-4">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-[#2e303a] hover:border-cyan-500/40 rounded-xl p-8 text-center cursor-pointer bg-[#131620]/30 transition-all flex flex-col items-center justify-center gap-3.5 group relative"
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    accept=".csv, image/*"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  {imageBase64 ? (
                    <img src={`data:${imageMimeType};base64,${imageBase64}`} alt="preview" className="max-h-32 rounded-lg border border-white/10" />
                  ) : (
                    <UploadCloud size={32} className="text-gray-500 group-hover:text-cyan-400 transition-colors animate-bounce" />
                  )}
                  <div>
                    <p className="text-xs md:text-sm font-bold text-white">Drag & drop your CSV or Image here, or <span className="text-cyan-400 group-hover:underline">Browse Files</span></p>
                    <p className="text-[10px] text-gray-500 mt-1 uppercase">Any format accepted (AI parses images & text)</p>
                  </div>
                  {csvFile && !imageBase64 && (
                    <span className="text-xs bg-[#3cd7ff]/10 border border-[#3cd7ff]/20 text-[#3cd7ff] px-3 py-1 rounded-full font-bold">
                      {csvFile.name}
                    </span>
                  )}
                </div>

                {!imageBase64 && (
                  <div className="space-y-2">
                    <label className="text-xs text-gray-400 font-bold uppercase tracking-wider block">Or Paste CSV Text</label>
                    <textarea
                      rows={6}
                      placeholder="Symbol, Qty, Price, Date&#10;AAPL, 10, 180.20, 2025-04-08&#10;BTC, 0.45, 63400.0, 2025-05-12"
                      value={csvText}
                      onChange={(e) => setCsvText(e.target.value)}
                      className="w-full bg-[#131620] border border-[#2e303a] rounded-xl px-4 py-3 text-xs md:text-sm text-white placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono resize-none"
                    />
                  </div>
                )}

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => setCsvModalOpen(false)}
                    className="flex-1 bg-[#131620] hover:bg-[#181C28] border border-white/5 rounded-xl py-2.5 text-xs md:text-sm font-bold text-gray-400 hover:text-white transition-all uppercase tracking-wider"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleParseCSV}
                    disabled={parsingCSV || (!csvText && !imageBase64)}
                    className="flex-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl py-2.5 text-xs md:text-sm font-bold shadow-[0_0_15px_rgba(138,43,226,0.3)] transition-all uppercase tracking-wider disabled:opacity-50"
                  >
                    {parsingCSV ? <RefreshCw className="animate-spin mr-2 inline" size={14} /> : null}
                    {parsingCSV ? 'AI Parsing...' : 'Parse with AI'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="border border-[#2e303a] rounded-xl max-h-72 overflow-y-auto bg-[#131620]/30">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-[#2e303a] text-gray-500 font-bold uppercase tracking-wider text-[10px] bg-[#1c1d24] sticky top-0">
                        <th className="py-2.5 px-3">Symbol</th>
                        <th className="py-2.5 px-3 hidden sm:table-cell">Category</th>
                        <th className="py-2.5 px-3 text-right">Quantity</th>
                        <th className="py-2.5 px-3 text-right">Avg Entry</th>
                        <th className="py-2.5 px-3 text-center hidden sm:table-cell">Purchase Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsedCSVPositions.map((pos, idx) => (
                        <tr key={idx} className="border-b border-[#2e303a]/40 last:border-0 hover:bg-white/5">
                          <td className="py-2 px-3 font-bold text-white uppercase">{pos.symbol}</td>
                          <td className="py-2 px-3 hidden sm:table-cell">
                            <span className={`px-1.5 py-0.5 rounded font-bold text-[9px] uppercase ${pos.category === 'crypto' ? 'bg-purple-500/10 text-purple-400' : 'bg-cyan-500/10 text-cyan-400'}`}>
                              {pos.category}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-right font-medium text-gray-300">{pos.quantity}</td>
                          <td className="py-2 px-3 text-right font-medium text-gray-300">{fmt(pos.avg_entry_price)}</td>
                          <td className="py-2 px-3 text-center font-medium text-gray-400 hidden sm:table-cell">{pos.purchase_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => setParsedCSVPositions([])}
                    className="flex-1 bg-[#131620] hover:bg-[#181C28] border border-white/5 rounded-xl py-2.5 text-xs md:text-sm font-bold text-gray-400 hover:text-white transition-all uppercase tracking-wider"
                  >
                    Back / Re-Upload
                  </button>
                  <button
                    onClick={handleImportCSVPositions}
                    className="flex-1 bg-[#00C853] hover:bg-[#00E676] rounded-xl py-2.5 text-xs md:text-sm font-black text-black shadow-[0_0_15px_rgba(0,200,83,0.3)] transition-all uppercase tracking-wider"
                  >
                    Import {parsedCSVPositions.length} Positions
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Selected Signal Modal */}
      {selectedSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#0b0d14] border border-white/10 p-6 rounded-2xl w-full max-w-sm shadow-2xl animate-slide-up relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-amber-400 to-orange-500"></div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                <Zap className="text-amber-400" size={18} fill="currentColor" />
                Active Signal: {selectedSignal.symbol}
              </h3>
              <button
                onClick={() => setSelectedSignal(null)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center bg-[#131620] p-3 rounded-xl border border-white/5">
                <span className="text-xs text-gray-400 font-bold uppercase">Strategy</span>
                <span className="text-sm font-bold text-white">{selectedSignal.strategy || 'N/A'}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-[#131620] p-3 rounded-xl border border-white/5 text-center">
                  <span className="text-[10px] text-gray-500 font-bold uppercase block mb-1">Entry</span>
                  <span className="text-sm font-bold text-white">{selectedSignal.entry_price || 'MKT'}</span>
                </div>
                <div className="bg-emerald-500/10 p-3 rounded-xl border border-emerald-500/20 text-center">
                  <span className="text-[10px] text-emerald-500 font-bold uppercase block mb-1">Take Profit</span>
                  <span className="text-sm font-bold text-emerald-400">{selectedSignal.tp_price || '-'}</span>
                </div>
                <div className="bg-rose-500/10 p-3 rounded-xl border border-rose-500/20 text-center">
                  <span className="text-[10px] text-rose-500 font-bold uppercase block mb-1">Stop Loss</span>
                  <span className="text-sm font-bold text-rose-400">{selectedSignal.sl_price || '-'}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Good Buys Modal */}
      {showGoodBuys && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#0b0d14] border border-white/10 p-6 rounded-2xl w-full max-w-2xl shadow-2xl animate-slide-up relative overflow-hidden max-h-[85vh] flex flex-col">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-emerald-400 to-teal-500"></div>
            <div className="flex items-center justify-between mb-6 flex-shrink-0">
              <h3 className="text-xl font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                <Search className="text-emerald-400" size={24} />
                Fresh Investment Ideas
              </h3>
              <button
                onClick={() => setShowGoodBuys(false)}
                className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="overflow-y-auto pr-2 space-y-4 flex-grow custom-scrollbar">
              {loadingGoodBuys ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-4">
                  <RefreshCw className="animate-spin text-emerald-500" size={32} />
                  <p className="text-sm font-bold text-gray-400 uppercase tracking-widest animate-pulse">
                    Scanning Markets & Signals...
                  </p>
                </div>
              ) : goodBuys && goodBuys.length > 0 ? (
                goodBuys.map((buy, idx) => (
                  <div key={idx} className="bg-[#131620] border border-white/5 p-4 rounded-xl relative group hover:border-emerald-500/30 transition-colors">
                    {buy.is_active_signal && (
                      <div className="absolute -top-2.5 -right-2.5 bg-emerald-500 text-black text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider shadow-[0_0_10px_rgba(16,185,129,0.5)] flex items-center gap-1">
                        <Zap size={10} fill="currentColor" /> Active Signal
                      </div>
                    )}
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`p-2 rounded-lg ${buy.type === 'stock' ? 'bg-blue-500/10 text-blue-400' : 'bg-orange-500/10 text-orange-400'}`}>
                        {buy.type === 'stock' ? <Landmark size={18} /> : <Coins size={18} />}
                      </div>
                      <div>
                        <h4 className="text-lg font-black text-white leading-tight">{buy.symbol}</h4>
                        <span className="text-xs font-medium text-gray-400">{buy.name || (buy.type === 'stock' ? 'Stock' : 'Crypto')}</span>
                      </div>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed mt-3">
                      {buy.rationale}
                    </p>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-gray-400">
                  <p>No active ideas found for your risk profile at this moment.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default PortfolioPage;
