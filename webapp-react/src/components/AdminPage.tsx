import React, { useState, useEffect } from 'react';
import { Users, ShieldAlert, Activity, Search, Loader2, MessageCircleQuestion, Plus, Edit, Trash2 } from 'lucide-react';
import api from '../lib/api';
import { Link } from 'react-router-dom';

const AdminPage: React.FC = () => {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'users' | 'faqs'>('users');
  
  const [faqs, setFaqs] = useState<any[]>([]);
  const [loadingFaqs, setLoadingFaqs] = useState(false);
  const [editingFaq, setEditingFaq] = useState<any>(null);
  const [editingUser, setEditingUser] = useState<any>(null);

  const handleSaveUserPremium = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;
    try {
      await api.put(`/admin/users/${editingUser.id}/premium`, {
        premium_expiry: editingUser.new_premium_expiry
      });
      setEditingUser(null);
      fetchUsers();
    } catch (error) {
      console.error('Failed to update premium expiry', error);
      alert('Failed to update premium expiry');
    }
  };

  const hierarchicalUsers = React.useMemo(() => {
    const userMap = new Map();
    users.forEach(u => userMap.set(u.id, u));

    const childrenMap = new Map();
    users.forEach(u => {
      const parentId = u.referred_by;
      if (parentId) {
        if (!childrenMap.has(parentId)) childrenMap.set(parentId, []);
        childrenMap.get(parentId).push(u);
      }
    });

    const flatList: any[] = [];
    const visited = new Set();

    const addNode = (u: any, depth: number) => {
      if (visited.has(u.id)) return;
      visited.add(u.id);
      flatList.push({ ...u, depth });
      const children = childrenMap.get(u.id) || [];
      children.forEach((child: any) => addNode(child, depth + 1));
    };

    const roots = users.filter(u => !u.referred_by || !userMap.has(u.referred_by));
    roots.forEach(u => addNode(u, 0));

    users.forEach(u => addNode(u, 0));

    return flatList;
  }, [users]);

  const fetchUsers = async () => {
    try {
      const res = await api.get('/admin/users');
      setUsers(res.data?.users || []);
    } catch (e) {
      console.error('Failed to fetch admin users', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchFaqs = async () => {
    setLoadingFaqs(true);
    try {
      const res = await api.get('/faq');
      setFaqs(res.data?.faqs || []);
    } catch (e) {
      console.error('Failed to fetch FAQs', e);
    } finally {
      setLoadingFaqs(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  useEffect(() => {
    if (activeTab === 'faqs' && faqs.length === 0) {
      fetchFaqs();
    }
  }, [activeTab]);

  const handleSaveFaq = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingFaq.id) {
        await api.put(`/admin/faq/${editingFaq.id}`, editingFaq);
      } else {
        await api.post('/admin/faq', editingFaq);
      }
      setEditingFaq(null);
      fetchFaqs();
    } catch (e) {
      console.error('Failed to save FAQ', e);
      alert('Failed to save FAQ');
    }
  };

  const handleDeleteFaq = async (id: number) => {
    if (!confirm('Are you sure you want to delete this FAQ?')) return;
    try {
      await api.delete(`/admin/faq/${id}`);
      fetchFaqs();
    } catch (e) {
      console.error('Failed to delete FAQ', e);
      alert('Failed to delete FAQ');
    }
  };

  return (
    <div className="flex-1 w-full max-w-6xl mx-auto space-y-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Admin Dashboard</h2>
          <p className="text-gray-400 mt-2">Manage users and system configuration.</p>
        </div>
        <Link to="/logs" className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg text-sm font-bold transition-colors flex items-center gap-2 border border-white/10">
          View Logs
        </Link>
      </div>

      <div className="flex border-b border-white/10 mb-8 space-x-8">
        <button
          onClick={() => setActiveTab('users')}
          className={`pb-4 text-sm font-bold uppercase tracking-widest transition-colors ${activeTab === 'users' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
        >
          Users
        </button>
        <button
          onClick={() => setActiveTab('faqs')}
          className={`pb-4 text-sm font-bold uppercase tracking-widest transition-colors ${activeTab === 'faqs' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
        >
          FAQs
        </button>
      </div>

      {activeTab === 'users' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
              <div className="flex items-center gap-3 mb-2 text-cyan-400">
                <Users size={20} />
                <h3 className="text-sm font-bold uppercase tracking-widest">Total Users</h3>
              </div>
              <p className="text-3xl font-bold text-white">{loading ? '...' : users.length}</p>
            </div>
            
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
              <div className="flex items-center gap-3 mb-2 text-yellow-400">
                <ShieldAlert size={20} />
                <h3 className="text-sm font-bold uppercase tracking-widest">Premium Active</h3>
              </div>
              <p className="text-3xl font-bold text-white">{loading ? '...' : users.filter(u => u.is_premium).length}</p>
            </div>

            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
              <div className="flex items-center gap-3 mb-2 text-emerald-400">
                <Activity size={20} />
                <h3 className="text-sm font-bold uppercase tracking-widest">System Load</h3>
              </div>
              <p className="text-3xl font-bold text-white">42%</p>
            </div>
          </div>

          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg overflow-hidden">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold text-white">User Management</h3>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input 
                  type="text" 
                  placeholder="Search users..." 
                  className="pl-10 pr-4 py-2 bg-[#131620] border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-cyan-500 w-64"
                />
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Email</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Referred By</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Telegram</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Plan</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Status</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Joined</th>
                    <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {loading ? (
                    <tr><td colSpan={7} className="py-8 text-center text-gray-500"><Loader2 className="animate-spin size-6 mx-auto" /></td></tr>
                  ) : (
                    hierarchicalUsers.map(u => (
                      <tr key={u.id} className="hover:bg-white/5 transition-colors">
                        <td className="py-4 px-4 text-sm text-white font-medium">
                          <div style={{ paddingLeft: `${u.depth * 1.5}rem` }} className="flex items-center gap-2">
                            {u.depth > 0 && <span className="text-gray-500 text-xs">↳</span>}
                            {u.email}
                          </div>
                        </td>
                        <td className="py-4 px-4 text-sm text-gray-400">{u.referrer_email || '-'}</td>
                        <td className="py-4 px-4 text-sm text-cyan-400 font-mono">
                          {u.telegram_username ? (
                            <a href={`https://t.me/${u.telegram_username.replace(/^@/, '')}`} target="_blank" rel="noopener noreferrer" className="hover:underline">
                              {u.telegram_username.startsWith('@') ? u.telegram_username : `@${u.telegram_username}`}
                            </a>
                          ) : (
                            u.telegram_chat_id ? String(u.telegram_chat_id) : <span className="text-gray-500 italic">None</span>
                          )}
                        </td>
                        <td className="py-4 px-4">
                          <div className="flex flex-col">
                            <span className={`w-max px-2 py-1 rounded text-xs font-bold ${u.is_premium ? 'bg-yellow-500/20 text-yellow-500' : 'bg-gray-500/20 text-gray-400'}`}>
                              {u.is_premium ? 'Premium' : 'Free'}
                            </span>
                            {u.is_premium && u.premium_expiry > 0 && (
                              <span className="text-gray-500 text-xs mt-1">
                                Exp: {new Date(u.premium_expiry * 1000).toISOString().slice(0, 10)}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-4 px-4">
                          <span className="flex items-center gap-2 text-sm text-emerald-400">
                            <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
                            Active
                          </span>
                        </td>
                        <td className="py-4 px-4 text-sm text-gray-400">{u.joined?.slice(0, 10)}</td>
                        <td className="py-4 px-4 text-right">
                          <button 
                            onClick={() => setEditingUser({ ...u, new_premium_expiry: u.premium_expiry || 0 })}
                            className="text-cyan-400 hover:text-cyan-300 text-sm font-bold transition-colors">
                            Edit
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {activeTab === 'faqs' && (
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
          <div className="flex justify-between items-center mb-6">
            <div className="flex items-center gap-3 text-white">
              <MessageCircleQuestion size={24} className="text-purple-400" />
              <h3 className="text-lg font-bold">FAQ Management</h3>
            </div>
            <button
              onClick={() => setEditingFaq({ question: '', answer: '', order_index: 0 })}
              className="flex items-center gap-2 bg-purple-500 hover:bg-purple-600 text-white px-4 py-2 rounded-xl text-sm font-bold transition-colors"
            >
              <Plus size={16} /> Add FAQ
            </button>
          </div>

          {editingFaq && (
            <form onSubmit={handleSaveFaq} className="bg-[#131620] p-6 rounded-xl border border-white/10 mb-8 space-y-4">
              <h4 className="text-white font-bold mb-2">{editingFaq.id ? 'Edit FAQ' : 'New FAQ'}</h4>
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Question</label>
                <input
                  type="text"
                  value={editingFaq.question}
                  onChange={(e) => setEditingFaq({ ...editingFaq, question: e.target.value })}
                  className="w-full bg-[#1b1f2c] border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Answer</label>
                <textarea
                  value={editingFaq.answer}
                  onChange={(e) => setEditingFaq({ ...editingFaq, answer: e.target.value })}
                  className="w-full bg-[#1b1f2c] border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 min-h-[100px]"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Order Index</label>
                <input
                  type="number"
                  value={editingFaq.order_index}
                  onChange={(e) => setEditingFaq({ ...editingFaq, order_index: parseInt(e.target.value) || 0 })}
                  className="w-full bg-[#1b1f2c] border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500"
                />
              </div>
              <div className="flex gap-4 pt-2">
                <button type="submit" className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold py-2 px-6 rounded-xl transition-colors">
                  Save
                </button>
                <button type="button" onClick={() => setEditingFaq(null)} className="bg-gray-600 hover:bg-gray-500 text-white font-bold py-2 px-6 rounded-xl transition-colors">
                  Cancel
                </button>
              </div>
            </form>
          )}

          {loadingFaqs ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-cyan-500 size-8" /></div>
          ) : (
            <div className="space-y-4">
              {faqs.map(faq => (
                <div key={faq.id} className="bg-[#131620] border border-white/10 p-5 rounded-xl flex items-start justify-between group">
                  <div className="flex-1 pr-6">
                    <h4 className="text-white font-bold mb-2 flex items-center gap-3">
                      <span className="text-gray-500 text-xs px-2 py-1 bg-white/5 rounded">#{faq.order_index}</span>
                      {faq.question}
                    </h4>
                    <p className="text-gray-400 text-sm whitespace-pre-wrap">{faq.answer}</p>
                  </div>
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => setEditingFaq(faq)} className="p-2 text-cyan-400 hover:bg-white/5 rounded-lg transition-colors">
                      <Edit size={16} />
                    </button>
                    <button onClick={() => handleDeleteFaq(faq.id)} className="p-2 text-rose-400 hover:bg-white/5 rounded-lg transition-colors">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
              {faqs.length === 0 && !editingFaq && (
                <p className="text-center text-gray-500 py-8 italic">No FAQs created yet.</p>
              )}
            </div>
          )}
        </div>
      )}

      {editingUser && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#1b1f2c] border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-4">Edit Premium Expiry</h3>
            <p className="text-gray-400 mb-6 text-sm">Editing <span className="text-cyan-400">{editingUser.email}</span></p>
            
            <form onSubmit={handleSaveUserPremium} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-400 uppercase mb-2">Expiration Date</label>
                <input
                  type="date"
                  value={editingUser.new_premium_expiry > 0 ? new Date(editingUser.new_premium_expiry * 1000).toISOString().split('T')[0] : ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) {
                      setEditingUser({ ...editingUser, new_premium_expiry: 0 });
                    } else {
                      const ts = Math.floor(new Date(val).getTime() / 1000);
                      setEditingUser({ ...editingUser, new_premium_expiry: ts });
                    }
                  }}
                  className="w-full bg-[#131620] border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500 font-mono"
                  style={{ colorScheme: 'dark' }}
                />
                <p className="text-xs text-gray-500 mt-2">
                  Clear the date to revert to Free Plan.
                </p>
              </div>
              
              <div className="flex gap-4 pt-4">
                <button type="submit" className="flex-1 bg-cyan-500 hover:bg-cyan-600 text-white font-bold py-3 rounded-xl transition-colors">
                  Save Changes
                </button>
                <button type="button" onClick={() => setEditingUser(null)} className="flex-1 bg-gray-600 hover:bg-gray-500 text-white font-bold py-3 rounded-xl transition-colors">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};

export default AdminPage;
