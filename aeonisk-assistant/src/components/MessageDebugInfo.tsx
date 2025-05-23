import { useState } from 'react';
import { useDebugStore } from '../stores/debugStore';

interface DebugData {
  tokens?: {
    input: number;
    output: number;
  };
  cost?: number;
  model?: string;
  ragChunks?: number;
  toolCalls?: Array<{
    name: string;
    args: any;
    result?: any;
  }>;
}

interface MessageDebugInfoProps {
  messageIndex: number;
  role: string;
  debugData?: DebugData;
}

export function MessageDebugInfo({ messageIndex, role, debugData }: MessageDebugInfoProps) {
  const { isDebugMode } = useDebugStore();
  const [isExpanded, setIsExpanded] = useState(false);

  if (!isDebugMode || !debugData) return null;

  const formatCost = (cost: number) => {
    if (cost < 0.01) {
      return `$${cost.toFixed(4)}`;
    }
    return `$${cost.toFixed(2)}`;
  };

  const formatTokens = (tokens: { input: number; output: number }) => {
    return `${tokens.input} → ${tokens.output}`;
  };

  return (
    <div className="mt-2 text-xs">
      {/* Compact badges */}
      <div className="flex flex-wrap gap-2 items-center">
        {role === 'user' && debugData.ragChunks !== undefined && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-900/50 text-green-400 rounded">
            📚 {debugData.ragChunks} chunks
          </span>
        )}
        
        {role === 'assistant' && (
          <>
            {debugData.model && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-900/50 text-purple-400 rounded">
                🤖 {debugData.model}
              </span>
            )}
            
            {debugData.tokens && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-900/50 text-blue-400 rounded">
                🪙 {formatTokens(debugData.tokens)} tokens
              </span>
            )}
            
            {debugData.cost !== undefined && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-900/50 text-yellow-400 rounded">
                💰 {formatCost(debugData.cost)}
              </span>
            )}
            
            {debugData.toolCalls && debugData.toolCalls.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-orange-900/50 text-orange-400 rounded">
                🔧 {debugData.toolCalls.length} tool{debugData.toolCalls.length > 1 ? 's' : ''}
              </span>
            )}
          </>
        )}
        
        {/* Expand button */}
        {(debugData.toolCalls?.length || 0) > 0 && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-500 hover:text-gray-400 transition-colors"
          >
            {isExpanded ? '▼' : '▶'} Details
          </button>
        )}
      </div>

      {/* Expanded details */}
      {isExpanded && debugData.toolCalls && (
        <div className="mt-2 space-y-2 pl-2 border-l-2 border-gray-700">
          {debugData.toolCalls.map((tool, idx) => (
            <div key={idx} className="space-y-1">
              <div className="font-medium text-yellow-400">
                🔧 {tool.name}
              </div>
              <div className="text-gray-400">
                <pre className="text-xs bg-gray-900/50 rounded p-2 overflow-x-auto">
                  {JSON.stringify(tool.args, null, 2)}
                </pre>
              </div>
              {tool.result && (
                <div className="text-gray-400">
                  <div className="text-xs text-gray-500">Result:</div>
                  <pre className="text-xs bg-gray-900/50 rounded p-2 overflow-x-auto">
                    {JSON.stringify(tool.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
