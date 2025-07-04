import { useState } from 'react';
import { useDebugStore } from '../stores/debugStore';
import { useProviderStore } from '../stores/providerStore';
import { getChatService } from '../lib/chat/service';

export function DebugPanel() {
  const { logs, tokenCosts, showDebugPanel, toggleDebugPanel, clearLogs } = useDebugStore();
  const { currentProvider, currentModel } = useProviderStore();
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());

  const handleReinitializeFromEnv = () => {
    try {
      getChatService().forceReinitializeFromEnv();
      // Force a re-render by updating the provider store
      const providerStore = useProviderStore.getState();
      providerStore.setProvider('openai', 'gpt-4o');
      console.log('Reinitialized from environment variables');
    } catch (error) {
      console.error('Failed to reinitialize from environment:', error);
    }
  };

  if (!showDebugPanel) {
    return null;
  }

  const toggleExpanded = (logId: string) => {
    setExpandedLogs(prev => {
      const next = new Set(prev);
      if (next.has(logId)) {
        next.delete(logId);
      } else {
        next.add(logId);
      }
      return next;
    });
  };

  const formatCost = (cost: number) => {
    if (cost < 0.01) {
      return `$${cost.toFixed(4)}`;
    }
    return `$${cost.toFixed(2)}`;
  };

  const getLogIcon = (type: string) => {
    switch (type) {
      case 'prompt': return '📝';
      case 'rag': return '🔍';
      case 'tool': return '🔧';
      case 'api': return '🌐';
      case 'cost': return '💰';
      default: return '📋';
    }
  };

  const getLogColor = (type: string) => {
    switch (type) {
      case 'prompt': return 'text-blue-400';
      case 'rag': return 'text-green-400';
      case 'tool': return 'text-yellow-400';
      case 'api': return 'text-purple-400';
      case 'cost': return 'text-orange-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 h-96 bg-gray-900 border-t border-gray-700 flex flex-col z-40">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-4">
          <h3 className="text-sm font-medium">Debug Panel</h3>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>Provider: {currentProvider || 'None'}</span>
            <span>•</span>
            <span>Model: {currentModel || 'None'}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Token Costs */}
          <div className="flex items-center gap-3 text-xs">
            <span className="text-gray-400">
              Input: {tokenCosts.input.toLocaleString()} tokens
            </span>
            <span className="text-gray-400">
              Output: {tokenCosts.output.toLocaleString()} tokens
            </span>
            <span className="font-medium text-green-400">
              Cost: {formatCost(tokenCosts.cost)}
            </span>
          </div>
          <button
            onClick={clearLogs}
            className="text-xs text-gray-400 hover:text-gray-300"
          >
            Clear Logs
          </button>
          <button
            onClick={handleReinitializeFromEnv}
            className="text-xs text-blue-400 hover:text-blue-300"
            title="Force reinitialize LLM from environment variables"
          >
            Reinit from Env
          </button>
          <button
            onClick={toggleDebugPanel}
            className="p-1 hover:bg-gray-700 rounded"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Logs */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {logs.map(log => {
          const isExpanded = expandedLogs.has(log.id);
          const timestamp = new Date(log.timestamp).toLocaleTimeString();

          return (
            <div key={log.id} className="bg-gray-800 rounded-lg p-3">
              <button
                onClick={() => toggleExpanded(log.id)}
                className="w-full text-left"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{getLogIcon(log.type)}</span>
                    <span className={`text-sm font-medium ${getLogColor(log.type)}`}>
                      {log.type.toUpperCase()}
                    </span>
                    <span className="text-xs text-gray-500">{timestamp}</span>
                  </div>
                  <svg 
                    className={`w-4 h-4 text-gray-400 transform transition-transform ${isExpanded ? 'rotate-180' : ''}`} 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {isExpanded && (
                <div className="mt-3 space-y-2">
                  {log.type === 'prompt' && (
                    <div className="space-y-2">
                      <div className="text-xs text-gray-400">
                        Tokens: {log.data.tokens} | Character Context: {log.data.hasCharacter ? 'Yes' : 'No'}
                      </div>
                      <pre className="text-xs bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                        {log.data.prompt}
                      </pre>
                    </div>
                  )}

                  {log.type === 'rag' && (
                    <div className="space-y-2">
                      <div className="text-xs text-gray-400">
                        Query: "{log.data.query}"
                      </div>
                      <div className="text-xs text-gray-400">
                        Intent: {log.data.analysis?.intent_type || 'Unknown'}
                      </div>
                      <div className="text-xs">
                        Retrieved {log.data.chunks?.length || 0} chunks:
                      </div>
                      {log.data.chunks?.map((chunk: any, idx: number) => (
                        <div key={idx} className="text-xs bg-gray-900 rounded p-2">
                          <div className="font-medium text-gray-300">
                            {chunk.metadata.source} - {chunk.metadata.section}
                          </div>
                          <div className="text-gray-400 mt-1">
                            {chunk.text.substring(0, 150)}...
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {log.type === 'tool' && (
                    <div className="space-y-2">
                      <div className="text-xs text-yellow-400">
                        Function: {log.data.name}
                      </div>
                      <div className="text-xs bg-gray-900 rounded p-2">
                        <div className="font-medium text-gray-300 mb-1">Parameters:</div>
                        <pre className="text-gray-400">{JSON.stringify(log.data.args, null, 2)}</pre>
                      </div>
                      {log.data.result && (
                        <div className="text-xs bg-gray-900 rounded p-2">
                          <div className="font-medium text-gray-300 mb-1">Result:</div>
                          <pre className="text-gray-400">{JSON.stringify(log.data.result, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  )}

                  {log.type === 'api' && (
                    <div className="space-y-2 text-xs">
                      <div>Provider: {log.data.provider}</div>
                      <div>Model: {log.data.model}</div>
                      <div>Temperature: {log.data.temperature}</div>
                      <div>Tools Available: {log.data.tools ? 'Yes' : 'No'}</div>
                      {log.data.error && (
                        <div className="text-red-400">Error: {log.data.error}</div>
                      )}
                    </div>
                  )}

                  {log.type === 'cost' && (
                    <div className="space-y-2 text-xs">
                      <div>Input Tokens: {log.data.inputTokens}</div>
                      <div>Output Tokens: {log.data.outputTokens}</div>
                      <div>Cost: {formatCost(log.data.cost)}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {logs.length === 0 && (
          <div className="text-center text-gray-500 text-sm mt-8">
            No debug logs yet. Start a conversation to see logs.
          </div>
        )}
      </div>
    </div>
  );
}
