import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getChatService } from '../lib/chat/service';
import { MessageRating } from './MessageRating';
import { ExportDialog } from './ExportDialog';
import type { Message } from '../types';

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatService = getChatService();

  useEffect(() => {
    // Load conversation history
    const history = chatService.getConversationHistory();
    setMessages(history);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    // Add user message to display
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    try {
      // Get response from chat service
      const response = await chatService.chat(userMessage);
      
      // Update messages with the response
      setMessages(chatService.getConversationHistory());
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please check your settings and try again.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRating = (index: number, rating: 'good' | 'bad' | 'edit') => {
    chatService.rateMessage(index, rating);
  };

  const handleClearChat = () => {
    if (confirm('Are you sure you want to clear the conversation?')) {
      chatService.clearConversation();
      setMessages([]);
    }
  };

  const handleExport = (format: 'jsonl' | 'finetune' | 'assistant' | 'sharegpt') => {
    const data = chatService.exportConversation(format);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aeonisk-chat-${format}-${Date.now()}.${format === 'jsonl' || format === 'finetune' ? 'jsonl' : 'json'}`;
    a.click();
    URL.revokeObjectURL(url);
    setShowExport(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-8">
            <p>Welcome to Aeonisk AI Assistant!</p>
            <p className="text-sm mt-2">Ask me about rules, lore, or let me help you run your game.</p>
          </div>
        )}
        
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-100'
              }`}
            >
              {message.role === 'assistant' ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}
              
              {message.role === 'assistant' && (
                <MessageRating
                  onRate={(rating) => handleRating(index, rating)}
                />
              )}
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-lg px-4 py-2">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-100" />
                <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-200" />
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-gray-700 p-4">
        <div className="flex gap-2 mb-2">
          <button
            onClick={handleClearChat}
            className="text-sm text-gray-400 hover:text-gray-300 transition-colors"
          >
            Clear Chat
          </button>
          <button
            onClick={() => setShowExport(true)}
            className="text-sm text-gray-400 hover:text-gray-300 transition-colors"
          >
            Export
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about rules, lore, or describe an action..."
            className="flex-1 bg-gray-800 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>
      </div>

      {/* Export dialog */}
      {showExport && (
        <ExportDialog
          onExport={handleExport}
          onClose={() => setShowExport(false)}
        />
      )}
    </div>
  );
}
