import React from 'react';
import { MessageCircle, FileText, HelpCircle, Mail } from 'lucide-react';

const HelpPage: React.FC = () => {
  return (
    <div className="flex-1 w-full max-w-4xl mx-auto space-y-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Help & Support</h2>
          <p className="text-gray-400 mt-2">Get assistance with your MetaVerse Sherpa account and bots.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-cyan-500/30 transition-colors cursor-pointer group">
          <FileText size={32} className="text-cyan-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">Documentation</h3>
          <p className="text-gray-400">Read detailed guides on setting up your API keys, configuring risk management, and understanding the algorithms.</p>
        </div>

        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-emerald-500/30 transition-colors cursor-pointer group">
          <MessageCircle size={32} className="text-emerald-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">Telegram Community</h3>
          <p className="text-gray-400">Join our active Telegram group to discuss strategies, share profits, and get help from other members.</p>
        </div>

        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-purple-500/30 transition-colors cursor-pointer group">
          <HelpCircle size={32} className="text-purple-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">FAQ</h3>
          <p className="text-gray-400">Browse answers to the most commonly asked questions about billing, performance, and security.</p>
        </div>

        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-rose-500/30 transition-colors cursor-pointer group">
          <Mail size={32} className="text-rose-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">Contact Support</h3>
          <p className="text-gray-400">Can't find what you're looking for? Send us an email and our team will get back to you within 24 hours.</p>
        </div>

      </div>

    </div>
  );
};

export default HelpPage;
