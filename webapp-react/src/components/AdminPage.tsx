import React, { useState, useEffect } from 'react';
import { Users, ShieldAlert, Activity, Search, Loader2 } from 'lucide-react';
import api from '../lib/api';

const AdminPage: React.FC = () => {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
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
    fetchUsers();
  }, []);

  return (
    <div className="flex-1 w-full max-w-6xl mx-auto space-y-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Admin Dashboard</h2>
          <p className="text-gray-400 mt-2">Manage users and system configuration.</p>
        </div>
      </div>

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
                <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Plan</th>
                <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Status</th>
                <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest">Joined</th>
                <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-widest text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr><td colSpan={5} className="py-8 text-center text-gray-500"><Loader2 className="animate-spin size-6 mx-auto" /></td></tr>
              ) : (
                users.map(u => (
                  <tr key={u.id} className="hover:bg-white/5 transition-colors">
                    <td className="py-4 px-4 text-sm text-white font-medium">{u.email}</td>
                    <td className="py-4 px-4">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${u.is_premium ? 'bg-yellow-500/20 text-yellow-500' : 'bg-gray-500/20 text-gray-400'}`}>
                        {u.is_premium ? 'Premium' : 'Free'}
                      </span>
                    </td>
                    <td className="py-4 px-4">
                      <span className="flex items-center gap-2 text-sm text-emerald-400">
                        <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
                        Active
                      </span>
                    </td>
                    <td className="py-4 px-4 text-sm text-gray-400">{u.joined.slice(0, 10)}</td>
                    <td className="py-4 px-4 text-right">
                      <button className="text-cyan-400 hover:text-cyan-300 text-sm font-bold transition-colors">Edit</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
};

export default AdminPage;
