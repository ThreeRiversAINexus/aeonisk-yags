import { useState, useEffect } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { SettingsPanel } from './components/SettingsPanel';
import { CharacterPanel } from './components/CharacterPanel';
import { DebugPanel } from './components/DebugPanel';
import { getChatService } from './lib/chat/service';
import './App.css';
import { useDebugStore } from './stores/debugStore';
import { useProviderStore } from './stores/providerStore';
import { characterRegistry } from './lib/game/characterRegistry';
import { DEFAULT_CHARACTER } from './lib/game/defaultCharacter';

function App() {
  const [showSettings, setShowSettings] = useState(false);
  const [showCharacter, setShowCharacter] = useState(false);
  const [showWelcome, setShowWelcome] = useState(true);
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);
  
  const debugMode = useDebugStore(state => state.isDebugMode);
  const provider = useProviderStore(state => state.currentProvider);

  useEffect(() => {
    const chatService = getChatService();
    const config = chatService.getConfig();
    setApiKeyConfigured(!!config.apiKey);
    
    // Initialize with a default character if none exists
    if (characterRegistry.size() === 0) {
      characterRegistry.addCharacter(DEFAULT_CHARACTER);
    }
  }, [provider]);

  const handleCloseWelcome = () => {
    setShowWelcome(false);
  };

  const handleApiKeySet = () => {
    setApiKeyConfigured(true);
    setShowSettings(false);
  };

  const toggleSettings = () => {
    setShowSettings(!showSettings);
  };

  const toggleCharacter = () => {
    setShowCharacter(!showCharacter);
  };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Welcome Modal */}
      {showWelcome && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 p-8 rounded-lg max-w-2xl max-h-[80vh] overflow-y-auto">
            <h1 className="text-3xl font-bold mb-4">Welcome to Aeonisk YAGS Assistant</h1>
            
            <p className="mb-4">
              This is an AI-powered assistant for the Aeonisk YAGS roleplaying game. 
              It uses the Yet Another Game System (YAGS) with the Aeonisk science-fantasy setting.
            </p>
            
            <h2 className="text-xl font-semibold mb-2">Getting Started:</h2>
            <ol className="list-decimal list-inside mb-4 space-y-2">
              <li>Click the settings icon (⚙️) to configure your AI provider</li>
              <li>Click the character icon (👤) to create or manage characters</li>
              <li>Start playing! The AI will help run your Aeonisk adventure</li>
            </ol>
            
            <h2 className="text-xl font-semibold mb-2">Key Features:</h2>
            <ul className="list-disc list-inside mb-4 space-y-1">
              <li>YAGS dice rolling with proper attribute × skill mechanics</li>
              <li>Character management with full YAGS attributes and skills</li>
              <li>Aeonisk-specific mechanics: Void Score, Soulcredit, Bonds</li>
              <li>Export characters and sessions for dataset contribution</li>
              <li>Debug mode to see dice rolls and AI reasoning</li>
            </ul>
            
            <div className="flex justify-center">
              <button
                onClick={handleCloseWelcome}
                className="px-6 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
              >
                Get Started
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Chat Interface */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-gray-800 p-4 flex items-center justify-between border-b border-gray-700">
          <h1 className="text-xl font-bold">Aeonisk YAGS Assistant</h1>
          <div className="flex items-center gap-2">
            {!apiKeyConfigured && (
              <span className="text-yellow-400 text-sm mr-2">⚠️ Configure API key</span>
            )}
            <button
              onClick={toggleCharacter}
              className="p-2 hover:bg-gray-700 rounded transition-colors"
              title="Character Management"
            >
              👤
            </button>
            <button
              onClick={toggleSettings}
              className="p-2 hover:bg-gray-700 rounded transition-colors"
              title="Settings"
            >
              ⚙️
            </button>
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 flex">
          <ChatInterface />
          {debugMode && <DebugPanel />}
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <SettingsPanel 
          onClose={() => setShowSettings(false)} 
          onProviderConfig={(providerName, config) => { // Renamed provider to providerName to avoid conflict
            const chatService = getChatService();
            chatService.setConfig(config); // Pass LLMConfig here
            handleApiKeySet();
          }}
          onProviderChange={(providerName) => { // Renamed provider to providerName
            // This logic might need adjustment based on how SettingsPanel calls it
            // For now, assuming it passes the provider string.
            // The actual provider change (model etc) is handled within SettingsPanel or via onProviderConfig
          }}
          currentProvider={provider} // Pass the provider state from useProviderStore
        />
      )}

      {/* Character Panel */}
      {showCharacter && (
        <CharacterPanel onClose={() => setShowCharacter(false)} />
      )}
    </div>
  );
}

export default App;
