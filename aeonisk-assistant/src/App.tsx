import { useState, useEffect } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { SettingsPanel } from './components/SettingsPanel';
import { CharacterPanel } from './components/CharacterPanel';
import { DebugPanel } from './components/DebugPanel';
import { WelcomeModal } from './components/WelcomeModal';
import { getChatService } from './lib/chat/service';
import { useDebugStore } from './stores/debugStore';
import { useProviderStore } from './stores/providerStore';
import type { LLMConfig, Character } from './types';

function App() {
  const [showSettings, setShowSettings] = useState(false);
  const [showCharacter, setShowCharacter] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);
  const [isConfigured, setIsConfigured] = useState(false);
  const [currentProvider, setCurrentProvider] = useState<string>('');
  
  const chatService = getChatService();
  const { isDebugMode, toggleDebugPanel } = useDebugStore();
  const { setProvider: setProviderInStore } = useProviderStore();

  useEffect(() => {
    // First check for environment variable
    const envApiKey = import.meta.env.VITE_OPENAI_API_KEY;
    if (envApiKey) {
      // Auto-configure OpenAI with env var
      const openAIConfig: LLMConfig = {
        provider: 'openai',
        apiKey: envApiKey,
        model: 'gpt-4o'
      };
      
      chatService.configureProvider('openai', openAIConfig);
      chatService.setProvider('openai');
      setCurrentProvider('openai');
      setProviderInStore('openai', 'gpt-4o');
      setIsConfigured(true);
      
      // Save to localStorage so it persists
      const configs = { openai: openAIConfig };
      localStorage.setItem('llmConfig', JSON.stringify(configs));
      localStorage.setItem('currentProvider', 'openai');
    } else {
      // Check for saved configuration if no env var
      const savedConfig = localStorage.getItem('llmConfig');
      if (savedConfig) {
        try {
          const configs = JSON.parse(savedConfig);
          Object.entries(configs).forEach(([provider, config]) => {
            chatService.configureProvider(provider, config as LLMConfig);
          });
          const savedProvider = localStorage.getItem('currentProvider');
          if (savedProvider) {
            chatService.setProvider(savedProvider);
            setCurrentProvider(savedProvider);
          }
          setIsConfigured(true);
          
          // Load saved character if exists
          const savedCharacter = localStorage.getItem('character');
          if (savedCharacter) {
            try {
              const character = JSON.parse(savedCharacter);
              chatService.setCharacter(character);
            } catch (e) {
              console.error('Failed to load saved character:', e);
            }
          }
          
          // Check if this is a first-time user
          const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
          if (!hasSeenWelcome && !savedCharacter) {
            setShowWelcome(true);
          }
        } catch (error) {
          console.error('Failed to load saved config:', error);
        }
      }
    }
    
    // Always load saved character if exists
    const savedCharacter = localStorage.getItem('character');
    if (savedCharacter) {
      try {
        const character = JSON.parse(savedCharacter);
        chatService.setCharacter(character);
      } catch (e) {
        console.error('Failed to load saved character:', e);
      }
    }
    
    // Check if this is a first-time user
    const hasSeenWelcome = localStorage.getItem('hasSeenWelcome');
    if (!hasSeenWelcome && !savedCharacter) {
      setShowWelcome(true);
    }
  }, []);

  const handleProviderConfig = (provider: string, config: LLMConfig) => {
    chatService.configureProvider(provider, config);
    
    // Save to localStorage
    const savedConfig = localStorage.getItem('llmConfig') || '{}';
    const configs = JSON.parse(savedConfig);
    configs[provider] = config;
    localStorage.setItem('llmConfig', JSON.stringify(configs));
    
    // Update provider store
    setProviderInStore(provider, config.model || '');
    
    // Set as current if it's the first
    if (!currentProvider) {
      chatService.setProvider(provider);
      setCurrentProvider(provider);
      localStorage.setItem('currentProvider', provider);
    }
    
    setIsConfigured(true);
  };

  const handleProviderChange = (provider: string) => {
    chatService.setProvider(provider);
    setCurrentProvider(provider);
    localStorage.setItem('currentProvider', provider);
  };

  const handleCharacterComplete = (character: Character) => {
    chatService.setCharacter(character);
    localStorage.setItem('character', JSON.stringify(character));
    localStorage.setItem('hasSeenWelcome', 'true');
    setShowWelcome(false);
  };

  const handleWelcomeClose = () => {
    localStorage.setItem('hasSeenWelcome', 'true');
    setShowWelcome(false);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700">
        <h1 className="text-xl font-bold">Aeonisk AI Assistant</h1>
        <div className="flex items-center gap-2">
          {isConfigured && (
            <span className="text-sm text-gray-400">
              {currentProvider}
            </span>
          )}
          <button
            onClick={() => setShowWelcome(true)}
            className="p-2 rounded hover:bg-gray-700 transition-colors"
            title="New Character"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
            </svg>
          </button>
          <button
            onClick={() => setShowCharacter(!showCharacter)}
            className="p-2 rounded hover:bg-gray-700 transition-colors"
            title="Character"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
            </svg>
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded hover:bg-gray-700 transition-colors"
            title="Settings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
            </svg>
          </button>
          {isDebugMode && (
            <button
              onClick={toggleDebugPanel}
              className="p-2 rounded hover:bg-gray-700 transition-colors"
              title="Debug Panel"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat area */}
        <div className="flex-1">
          {isConfigured ? (
            <ChatInterface />
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-gray-400 mb-4">Please configure an LLM provider to start</p>
                <button
                  onClick={() => setShowSettings(true)}
                  className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
                >
                  Open Settings
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Side panels */}
        {showCharacter && (
          <CharacterPanel onClose={() => setShowCharacter(false)} />
        )}
        
        {showSettings && (
          <SettingsPanel
            onClose={() => setShowSettings(false)}
            onProviderConfig={handleProviderConfig}
            onProviderChange={handleProviderChange}
            currentProvider={currentProvider}
          />
        )}
      </div>

      {/* Debug Panel */}
      <DebugPanel />
      
      {/* Welcome Modal */}
      {showWelcome && isConfigured && (
        <WelcomeModal
          onComplete={handleCharacterComplete}
          onClose={handleWelcomeClose}
        />
      )}
    </div>
  );
}

export default App;
