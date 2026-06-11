'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, RotateCcw } from 'lucide-react';
import { getChatbotAnswer } from '@/lib/api';

const SUGGESTED = [
  'What are the main risk factors?',
  'Were any meeting requests detected?',
  'Is there evidence of secrecy patterns?',
  'Summarize the explicit content found.',
  'Which sentences had the highest confidence?',
];

const Chatbot = ({ reportId }) => {
  const [messages, setMessages] = useState([
    {
      role: 'bot',
      content: 'Hello! I\'m **Aura**, your AI safety analyst. Ask me anything about this audio analysis — findings, evidence, risk scores, or specific patterns detected.'
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const sendMessage = async (text) => {
    const msg = (text || input).trim();
    if (!msg || isLoading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setIsLoading(true);
    try {
      const response = await getChatbotAnswer(reportId, msg);
      setMessages(prev => [...prev, { role: 'bot', content: response.answer || response.response || JSON.stringify(response) }]);
    } catch {
      setMessages(prev => [...prev, {
        role: 'bot',
        content: '⚠ Failed to get a response. Make sure the backend is running and the report is fully processed.',
        isError: true
      }]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleSubmit = (e) => { e.preventDefault(); sendMessage(); };

  const reset = () => setMessages([{
    role: 'bot',
    content: 'Chat cleared. Ask me anything about this analysis report.'
  }]);

  const renderContent = (text) =>
    text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={i} style={{ color: 'var(--text-primary)' }}>{part.slice(2, -2)}</strong>
        : part
    );

  return (
    <div className="chat-container glass-panel" style={{ height: '100%', minHeight: 500 }}>
      <div style={{
        padding: '0.875rem 1.25rem',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex', alignItems: 'center', gap: '0.6rem'
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
        }}>
          <Bot size={16} color="white" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>Aura AI</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--status-safe)', display: 'flex', alignItems: 'center', gap: 3 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--status-safe)', display: 'inline-block' }} />
            RAG • Powered by Ollama
          </div>
        </div>
        <button
          onClick={reset}
          title="Clear chat"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: 4 }}
        >
          <RotateCcw size={15} />
        </button>
      </div>

      <div className="chat-messages" style={{ flex: 1 }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex',
            gap: '0.5rem',
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '90%',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            alignItems: 'flex-end'
          }}>
            <div style={{
              width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
              background: msg.role === 'user'
                ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))'
                : 'var(--bg-tertiary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: '1px solid var(--border-color)'
            }}>
              {msg.role === 'user' ? <User size={13} color="white" /> : <Bot size={13} color="var(--accent-primary)" />}
            </div>

            <div className={`message ${msg.role}`} style={{
              background: msg.isError ? 'rgba(239,68,68,0.1)' : undefined,
              border: msg.isError ? '1px solid rgba(239,68,68,0.3)' : undefined,
              lineHeight: 1.65, fontSize: '0.875rem'
            }}>
              {renderContent(msg.content)}
            </div>
          </div>
        ))}

        {isLoading && (
          <div style={{ display: 'flex', gap: '0.5rem', alignSelf: 'flex-start', alignItems: 'flex-end' }}>
            <div style={{
              width: 26, height: 26, borderRadius: '50%', background: 'var(--bg-tertiary)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--border-color)'
            }}>
              <Bot size={13} color="var(--accent-primary)" />
            </div>
            <div className="message bot" style={{ display: 'flex', gap: 5, alignItems: 'center', padding: '0.75rem 1rem' }}>
              {[0, 150, 300].map(delay => (
                <span key={delay} style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--accent-primary)', display: 'inline-block',
                  animation: 'typingBounce 1s infinite',
                  animationDelay: `${delay}ms`
                }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length <= 2 && !isLoading && (
        <div style={{
          padding: '0.5rem 1rem',
          borderTop: '1px solid var(--border-color)',
          display: 'flex', flexWrap: 'wrap', gap: '0.4rem'
        }}>
          <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
            <Sparkles size={11} style={{ color: 'var(--accent-primary)' }} />
            <span style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Suggested</span>
          </div>
          {SUGGESTED.map((q, i) => (
            <button
              key={i}
              onClick={() => sendMessage(q)}
              style={{
                background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)',
                color: 'var(--accent-primary)', borderRadius: 'var(--radius-full)',
                fontSize: '0.72rem', padding: '0.25rem 0.7rem', cursor: 'pointer',
                transition: 'all 0.2s', whiteSpace: 'nowrap'
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="chat-input-area">
        <input
          ref={inputRef}
          type="text"
          className="chat-input"
          placeholder="Ask about findings, risk, patterns..."
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={isLoading}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={isLoading || !input.trim()}
          style={{ borderRadius: 'var(--radius-full)', padding: '0.75rem', flexShrink: 0 }}
        >
          <Send size={16} />
        </button>
      </form>

      <style>{`
        @keyframes typingBounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-5px); opacity: 1; }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

export default Chatbot;
