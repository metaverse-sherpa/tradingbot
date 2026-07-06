import React, { useState, useEffect } from 'react';
import { MessageCircle, FileText, HelpCircle, Mail, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import api from '../lib/api';

const HelpPage: React.FC = () => {
  const [faqs, setFaqs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openFaqId, setOpenFaqId] = useState<number | null>(null);

  useEffect(() => {
    const fetchFaqs = async () => {
      try {
        const res = await api.get('/faq');
        setFaqs(res.data?.faqs || []);
      } catch (e) {
        console.error('Failed to fetch FAQs', e);
      } finally {
        setLoading(false);
      }
    };
    fetchFaqs();
  }, []);

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto space-y-8 pb-12">
      
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

        <a href="https://t.me/+2pYhCm5BOoI0Mjkx" target="_blank" rel="noopener noreferrer" className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-emerald-500/30 transition-colors cursor-pointer group block">
          <MessageCircle size={32} className="text-emerald-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">Telegram Community</h3>
          <p className="text-gray-400">Join our active Telegram group to discuss strategies, share profits, and get help from other members.</p>
        </a>

        <div onClick={() => document.getElementById('faq-section')?.scrollIntoView({ behavior: 'smooth' })} className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-purple-500/30 transition-colors cursor-pointer group">
          <HelpCircle size={32} className="text-purple-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">FAQ</h3>
          <p className="text-gray-400">Browse answers to the most commonly asked questions about billing, performance, and security.</p>
        </div>

        <a href="mailto:sherpa@metaversesherpa.io" className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg hover:border-rose-500/30 transition-colors cursor-pointer group block">
          <Mail size={32} className="text-rose-400 mb-4 group-hover:scale-110 transition-transform" />
          <h3 className="text-xl font-bold text-white mb-2">Contact Support</h3>
          <p className="text-gray-400">Can't find what you're looking for? Send us an email and our team will get back to you within 24 hours.</p>
        </a>

      </div>

      <div id="faq-section" className="pt-8">
        <h2 className="text-2xl font-bold text-[#f3f4f6] mb-6">Frequently Asked Questions</h2>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="animate-spin text-cyan-500 size-8" />
          </div>
        ) : faqs.length === 0 ? (
          <p className="text-gray-400 italic">No FAQs available at the moment.</p>
        ) : (
          <div className="space-y-4">
            {faqs.map((faq) => (
              <div 
                key={faq.id} 
                className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-xl overflow-hidden transition-colors hover:border-white/20 cursor-pointer"
                onClick={() => setOpenFaqId(openFaqId === faq.id ? null : faq.id)}
              >
                <div className="p-5 flex items-center justify-between">
                  <h4 className="text-lg font-semibold text-white">{faq.question}</h4>
                  <div className="text-gray-400">
                    {openFaqId === faq.id ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                  </div>
                </div>
                {openFaqId === faq.id && (
                  <div className="px-5 pb-5 text-gray-400 border-t border-white/5 pt-4 whitespace-pre-wrap">
                    {faq.answer}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
};

export default HelpPage;
