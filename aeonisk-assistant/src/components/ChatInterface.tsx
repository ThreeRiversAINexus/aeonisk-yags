import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getChatService } from '../lib/chat/service';
import { MessageRating } from './MessageRating';
import { ExportDialog } from './ExportDialog';
import { MessageDebugInfo } from './MessageDebugInfo';
import { useDebugStore } from '../stores/debugStore';
import type { Message } from '../types';

interface MessageWithDebug extends Message {
  debugData?: {
    tokens?: { input: number; output: number };
    cost?: number;
    model?: string;
    ragChunks?: number;
    toolCalls?: Array<{ name: string; args: any; result?: any }>;
  };
}

export function ChatInterface() {
  const [messages, setMessages] = useState<MessageWithDebug[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatService = getChatService();
  const { logs, tokenCosts } = useDebugStore();

  // Track debug data for messages
  const [messageDebugData, setMessageDebugData] = useState<Map<number, any>>(new Map());

  const [icMode, setIcMode] = useState(true);

  const [pendingAdventure, setPendingAdventure] = useState(() => {
    // If a character was just loaded, set pending adventure
    return localStorage.getItem('pendingAdventure') === 'true';
  });

  useEffect(() => {
    // Load conversation history
    const history = chatService.getConversationHistory();
    setMessages(history);

    // Register for progress updates
    const unsubscribe = chatService.onProgressUpdate((message: Message) => {
      setMessages(prev => {
        // Check if this message is already in the list to avoid duplicates
        const existingIndex = prev.findIndex(m => 
          m.timestamp === message.timestamp && m.role === message.role && m.content === message.content
        );
        
        if (existingIndex >= 0) {
          return prev;
        }
        
        return [...prev, message];
      });
    });

    // Clean up on unmount
    return () => {
      unsubscribe();
    };
  }, []);

  // Process debug logs to extract data for messages
  useEffect(() => {
    const newDebugData = new Map<number, any>();
    
    // Group logs by message index based on timing
    let currentAssistantIndex = -1;
    let pendingRAGData: any = null;
    
    logs.forEach((log, logIndex) => {
      if (log.type === 'rag') {
        // Store RAG data to be associated with next assistant message
        pendingRAGData = {
          ragChunks: log.data.totalChunks,
          ragQuery: log.data.query
        };
      } else if (log.type === 'api') {
        // New assistant message is being generated
        currentAssistantIndex = messages.findIndex((msg, idx) => 
          msg.role === 'assistant' && !newDebugData.has(idx)
        );
        
        if (currentAssistantIndex === -1) {
          // This is for the next assistant message to be added
          currentAssistantIndex = messages.length;
        }
        
        const existingData = newDebugData.get(currentAssistantIndex) || {};
        newDebugData.set(currentAssistantIndex, {
          ...existingData,
          model: log.data.model,
          ...pendingRAGData // Add pending RAG data to assistant message
        });
        pendingRAGData = null; // Clear after using
      } else if (log.type === 'cost' && currentAssistantIndex >= 0) {
        const existingData = newDebugData.get(currentAssistantIndex) || {};
        newDebugData.set(currentAssistantIndex, {
          ...existingData,
          tokens: {
            input: log.data.inputTokens,
            output: log.data.outputTokens
          },
          cost: log.data.cost
        });
      } else if (log.type === 'tool' && currentAssistantIndex >= 0) {
        const existingData = newDebugData.get(currentAssistantIndex) || {};
        const toolCalls = existingData.toolCalls || [];
        
        // Check if this is a result for an existing tool call
        const existingToolIndex = toolCalls.findIndex(
          (t: any) => t.name === log.data.name && !t.result && log.data.result
        );
        
        if (existingToolIndex >= 0 && log.data.result) {
          toolCalls[existingToolIndex].result = log.data.result;
        } else {
          toolCalls.push({
            name: log.data.name,
            args: log.data.args,
            result: log.data.result
          });
        }
        
        newDebugData.set(currentAssistantIndex, {
          ...existingData,
          toolCalls
        });
      }
    });

    setMessageDebugData(newDebugData);
  }, [logs, messages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Helper to get knowledge level
  const getKnowledgeLevel = () => localStorage.getItem('aeoniskKnowledgeLevel') || 'low';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    setMessages(prev => [...prev, { role: 'user', content: userMessage, ic: icMode }]);

    try {
      const response = await chatService.chat(userMessage, { ic: icMode, knowledge: getKnowledgeLevel() });
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
    // Remove or update this function since chatService.rateMessage does not exist
    // chatService.rateMessage(index, rating);
    // Optionally, implement rating logic here if needed
  };

  const handleClearChat = () => {
    if (confirm('Are you sure you want to clear the conversation?')) {
      chatService.clearConversation();
      setMessages([]);
      setMessageDebugData(new Map());
      // Clear debug logs
      const { clearLogs } = useDebugStore.getState();
      clearLogs();
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

  /**
   * Get the appropriate styling for different message types
   */
  const getMessageStyling = (message: Message) => {
    if (message.role === 'user') {
      return message.ic === false 
        ? 'bg-gray-600 text-white border border-yellow-400' 
        : 'bg-blue-600 text-white';
    } else if (message.role === 'assistant') {
      return message.ic === false 
        ? 'bg-gray-700 text-yellow-200 border border-yellow-400' 
        : 'bg-gray-800 text-gray-100';
    } else if (message.role === 'progress') {
      return 'bg-blue-900/30 text-blue-200 border border-blue-500';
    } else if (message.role === 'error') {
      return 'bg-red-900/30 text-red-200 border border-red-500';
    } else if (message.role === 'result') {
      return 'bg-green-900/30 text-green-200 border border-green-500';
    }
    return 'bg-gray-800 text-gray-100';
  };

  /**
   * Get the appropriate icon for different message types
   */
  const getMessageIcon = (message: Message) => {
    if (message.role === 'progress') {
      if (message.progressStatus === 'started') return '🚀';
      if (message.progressStatus === 'in-progress') return '⚙️';
      if (message.progressStatus === 'completed') return '✅';
      if (message.progressStatus === 'failed') return '❌';
      return '📋';
    } else if (message.role === 'error') {
      return '❌';
    } else if (message.role === 'result') {
      return '🎉';
    }
    return null;
  };

  // Render Begin Adventure button if pending
  const renderBeginAdventure = () => {
    // Load campaign and character from localStorage
    let campaign = null;
    let character = null;
    try {
      const campaignStr = localStorage.getItem('aeoniskCampaign');
      if (campaignStr) campaign = JSON.parse(campaignStr);
    } catch {}
    try {
      character = chatService.getCharacter();
    } catch {}

    if (!campaign) {
      return (
        <div className="flex flex-col items-center justify-center py-8">
          <div className="text-red-400 mb-2">No active campaign selected.</div>
          <div className="text-gray-300 mb-4">Please select a campaign from the dashboard above.</div>
        </div>
      );
    }

    // Use campaign's intro or first scenario if available
    let intro = '';
    if (campaign.intro) {
      intro = campaign.intro;
    } else if (campaign.scenarios && campaign.scenarios.length > 0) {
      intro = campaign.scenarios[0].description || campaign.scenarios[0].intro || '';
    }
    // Fallback to previous logic if no intro
    if (!intro) {
      if (campaign && character) {
        const location = (campaign.scenarios && campaign.scenarios[0]?.location) || 'an unknown district';
        const theme = campaign.theme || 'Adventure';
        const factions = campaign.factions?.length ? campaign.factions.join(', ') : 'various factions';
        const charName = character.name || 'yourself';
        const origin = character.origin_faction || character.concept || 'a wanderer';
        let flavor = '';
        if (origin.toLowerCase().includes('freeborn')) {
          flavor = `The air is thick with the scent of rebellion in the Freeborn district. The streets are alive with the hustle of those who have chosen not to be bound by the dynasties that seek to control them.\n\nAmong them, you stand, ${charName}, embracing the wild freedom of your kind. The graffiti on the bathroom mirror echoes the sentiment you've always felt: "You are not your dynasty's mouthpiece."\n\nAs a Freeborn, your will is wild and untamed. You can form only one Bond, but this Bond is something of immense significance, as it can only be sacrificed with great cost.\n\nNow, as you wander this district, what is it you seek? Knowledge? Connections? Or perhaps the elusive Hollow Seed, a symbol of the freedom you cherish?`;
        } else {
          flavor = `You awaken in ${location}, a place shaped by the theme of "${theme}". The influence of ${factions} is felt everywhere.\n\nAs ${charName}, ${origin}, you sense that today will be different. Whispers of strange events reach your ears, and the air is thick with anticipation.\n\nWhat do you do?`;
        }
        intro = flavor;
      } else {
        intro = `You awaken in a world of sacred trust and spiritual commerce. The air hums with the energy of talismans and the distant echo of ritual. What do you do?`;
      }
    }

    return (
      <div className="flex flex-col items-center justify-center py-8">
        <button
          className="px-6 py-3 bg-blue-700 hover:bg-blue-800 text-white text-lg rounded-lg shadow-lg transition-colors"
          onClick={() => {
            setPendingAdventure(false);
            localStorage.setItem('pendingAdventure', 'false');
            setMessages(prev => [
              ...prev,
              { role: 'assistant', content: intro, ic: true }
            ]);
            setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
          }}
        >
          Begin Adventure
        </button>
        <p className="mt-4 text-gray-300 text-center">Click to start your campaign with an immersive scene.</p>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {pendingAdventure && renderBeginAdventure()}
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
              className={`max-w-[80%] rounded-lg px-4 py-2 ${getMessageStyling(message)}`}
            >
              {/* Message header for special message types */}
              {(message.role === 'progress' || message.role === 'error' || message.role === 'result') && (
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">{getMessageIcon(message)}</span>
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {message.role === 'progress' && `${message.progressType?.replace('-', ' ') || 'Progress'}`}
                    {message.role === 'error' && 'Error'}
                    {message.role === 'result' && 'Result'}
                  </span>
                  {message.progressStatus && (
                    <span className="text-xs opacity-75">
                      ({message.progressStatus})
                    </span>
                  )}
                </div>
              )}

              {/* IC/OOC indicator */}
              {message.ic === false && (
                <span className="text-xs font-bold text-yellow-300 mr-2">[OOC]</span>
              )}

              {/* Message content */}
              {message.role === 'assistant' || message.role === 'progress' || message.role === 'error' || message.role === 'result' ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}

              {/* Action buttons for result messages */}
              {message.role === 'result' && message.resultData && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {message.progressType === 'character-generation' && (
                    <button
                      onClick={() => {
                        // Open character panel or show character details
                        console.log('Character details:', message.resultData);
                      }}
                      className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-sm transition-colors"
                    >
                      View Character
                    </button>
                  )}
                  {message.progressType === 'campaign-generation' && (
                    <button
                      onClick={() => {
                        // Set pending adventure state
                        localStorage.setItem('pendingAdventure', 'true');
                        setPendingAdventure(true);
                        // Set the generated campaign as active
                        if (message.resultData) {
                          localStorage.setItem('aeoniskCampaign', JSON.stringify(message.resultData));
                        }
                      }}
                      className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm transition-colors"
                    >
                      Begin Adventure
                    </button>
                  )}
                </div>
              )}
              
              {/* Message rating for assistant messages */}
              {message.role === 'assistant' && (
                <MessageRating
                  onRate={(rating: 'good' | 'bad' | 'edit') => handleRating(index, rating)}
                />
              )}
              
              {/* Debug info */}
              <MessageDebugInfo
                messageIndex={index}
                role={message.role}
                debugData={messageDebugData.get(index)}
              />
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
          <select
            value={icMode ? 'ic' : 'ooc'}
            onChange={e => setIcMode(e.target.value === 'ic')}
            className="bg-gray-800 text-gray-200 rounded-lg px-2 py-1 focus:outline-none border border-gray-700"
            style={{ minWidth: 70 }}
            aria-label="IC/OOC toggle"
          >
            <option value="ic">IC</option>
            <option value="ooc">OOC</option>
          </select>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={icMode ? "Speak or act in character..." : "Out-of-character (rules, clarifications, etc.)"}
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
