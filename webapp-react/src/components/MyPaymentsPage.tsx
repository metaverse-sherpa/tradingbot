import React, { useEffect, useState } from 'react';
import { ArrowLeft, Clock, Search, ShieldCheck, CheckCircle2, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../lib/api';
import { useToast } from './Toast';

interface Payment {
  tx_hash: string;
  timestamp: number;
  start_date: number;
  end_date: number;
}

const MyPaymentsPage: React.FC = () => {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { showToast } = useToast();

  useEffect(() => {
    const fetchPayments = async () => {
      try {
        const res = await api.get('/premium/my-payments');
        setPayments(res.data.payments || []);
      } catch (err) {
        showToast('Failed to load payment history', 'error');
      } finally {
        setIsLoading(false);
      }
    };
    fetchPayments();
  }, [showToast]);

  const now = Date.now() / 1000;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-4 mb-8">
        <Link to="/settings" className="p-2 hover:bg-white/10 rounded-xl transition-colors">
          <ArrowLeft size={24} className="text-gray-400 hover:text-white" />
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">My Payments</h1>
          <p className="text-gray-400 mt-1">History of your cryptocurrency payments.</p>
        </div>
      </div>

      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-3xl overflow-hidden shadow-2xl">
        <div className="p-6 border-b border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/20 rounded-xl">
              <ShieldCheck className="text-emerald-400" size={24} />
            </div>
            <h2 className="text-xl font-bold text-white">Payment History</h2>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 flex justify-center">
            <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : payments.length === 0 ? (
          <div className="p-12 flex flex-col items-center justify-center text-center">
            <Search className="text-gray-500 mb-4" size={48} />
            <h3 className="text-xl font-bold text-white mb-2">No Payments Found</h3>
            <p className="text-gray-400">You haven't made any verified payments yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-400 uppercase bg-black/20 border-b border-white/5">
                <tr>
                  <th className="px-6 py-4 font-semibold">Date Paid</th>
                  <th className="px-6 py-4 font-semibold">Transaction Hash</th>
                  <th className="px-6 py-4 font-semibold">Subscription Start</th>
                  <th className="px-6 py-4 font-semibold">Subscription End</th>
                  <th className="px-6 py-4 font-semibold text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {payments.map((p, idx) => {
                  const isActive = now >= p.start_date && now <= p.end_date;
                  return (
                    <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-6 py-4 text-gray-300">
                        {new Date(p.timestamp * 1000).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-emerald-400">
                        <a 
                          href={`https://tronscan.org/#/transaction/${p.tx_hash}`} 
                          target="_blank" 
                          rel="noreferrer"
                          className="hover:underline flex items-center gap-1"
                        >
                          {p.tx_hash.substring(0, 12)}...{p.tx_hash.substring(p.tx_hash.length - 12)}
                          <ExternalLink size={12} />
                        </a>
                      </td>
                      <td className="px-6 py-4 text-gray-300">
                        {new Date(p.start_date * 1000).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-gray-300">
                        {new Date(p.end_date * 1000).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {isActive ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <CheckCircle2 size={14} /> Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20">
                            <Clock size={14} /> Expired
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default MyPaymentsPage;
