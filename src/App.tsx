import { useState, useRef, useEffect } from 'react';
import { Send, Home, Loader2, RotateCcw, ChevronRight } from 'lucide-react';
import { sendMessage, type Message } from './services/openai';
import { LISTINGS, retrieveRelevantListings } from './services/listings';
import { PropertyCard } from './components/PropertyCard';

const SUGGESTED_PROMPTS = [
  "What's available under $600k?",
  "Show me 3-bedroom homes",
  "I want a pool and a yard",
  "Best neighborhoods for families?",
  "What's in East Austin?",
  "Compare downtown condos",
];

const WELCOME: Message = {
  id: 'welcome',
  role: 'assistant',
  content: "Hi! I'm HomeIQ, your AI real estate assistant. I have access to our current Austin listings and can help you find your perfect home. What are you looking for?",
  timestamp: new Date(),
};

export default function App() {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [relevantListings, setRelevantListings] = useState(LISTINGS.slice(0, 3));
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function handleSend(text?: string) {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    setInput('');
    setError('');

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    // Update sidebar with relevant listings for this query
    const relevant = retrieveRelevantListings(content);
    if (relevant.length > 0) setRelevantListings(relevant);

    try {
      const reply = await sendMessage(content, [...messages, userMsg]);
      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: reply,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong');
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function reset() {
    setMessages([WELCOME]);
    setInput('');
    setError('');
    setRelevantListings(LISTINGS.slice(0, 3));
  }

  return (
    <div className="app-shell min-h-screen flex flex-col" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {/* Header */}
      <header className="header-bar flex items-center justify-between px-6 py-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="logo-icon w-9 h-9 rounded-xl flex items-center justify-center">
            <Home size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-white font-semibold text-lg leading-none" style={{ fontFamily: "'DM Serif Display', serif" }}>
              HomeIQ
            </h1>
            <p className="text-stone-500 text-xs mt-0.5">Austin Real Estate · AI Assistant</p>
          </div>
        </div>
        <button onClick={reset} className="flex items-center gap-1.5 text-stone-500 hover:text-stone-300 text-xs transition-colors">
          <RotateCcw size={12} />
          New chat
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Chat Panel */}
        <main className="flex flex-col flex-1 min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {messages.map(msg => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'assistant' && (
                  <div className="ai-avatar w-7 h-7 rounded-lg flex items-center justify-center mr-2 mt-0.5 shrink-0">
                    <Home size={13} className="text-white" />
                  </div>
                )}
                <div className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'user-bubble text-white rounded-tr-sm'
                    : 'ai-bubble text-stone-200 rounded-tl-sm'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="ai-avatar w-7 h-7 rounded-lg flex items-center justify-center mr-2 mt-0.5 shrink-0">
                  <Home size={13} className="text-white" />
                </div>
                <div className="ai-bubble rounded-2xl rounded-tl-sm px-4 py-3">
                  <Loader2 size={16} className="text-amber-400 animate-spin" />
                </div>
              </div>
            )}

            {error && (
              <div className="mx-auto max-w-sm text-center text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2">
                {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Suggested Prompts */}
          {messages.length <= 1 && (
            <div className="px-4 pb-3 flex flex-wrap gap-2">
              {SUGGESTED_PROMPTS.map(p => (
                <button
                  key={p}
                  onClick={() => handleSend(p)}
                  className="suggested-pill text-xs px-3 py-1.5 rounded-full border flex items-center gap-1 transition-all hover:scale-105"
                >
                  {p}
                  <ChevronRight size={10} />
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="input-area px-4 pb-4">
            <div className="input-wrapper flex items-end gap-3 rounded-2xl px-4 py-3 border border-white/10">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about listings, neighborhoods, pricing..."
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-stone-600 text-sm resize-none outline-none leading-relaxed"
                style={{ maxHeight: '120px' }}
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                className="send-btn w-8 h-8 rounded-xl flex items-center justify-center shrink-0 disabled:opacity-30 transition-all hover:scale-110 disabled:hover:scale-100"
              >
                <Send size={14} className="text-white" />
              </button>
            </div>
            <p className="text-center text-stone-700 text-xs mt-2">
              Powered by GPT-4o-mini + RAG · Built by CFunk Creations LLC
            </p>
          </div>
        </main>

        {/* Sidebar - Listings */}
        <aside className="sidebar w-72 border-l border-white/8 overflow-y-auto px-4 py-5 hidden lg:block">
          <h2 className="text-stone-500 text-xs uppercase tracking-widest mb-4 font-medium">
            Matched Listings
          </h2>
          {relevantListings.map(p => (
            <PropertyCard key={p.id} property={p} />
          ))}
          <p className="text-stone-700 text-xs text-center mt-4">
            {LISTINGS.length} total listings in database
          </p>
        </aside>
      </div>
    </div>
  );
}
