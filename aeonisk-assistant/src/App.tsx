import { useState, useEffect } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { SettingsPanel } from './components/SettingsPanel';
import { CharacterPanel } from './components/CharacterPanel';
import { DebugPanel } from './components/DebugPanel';
import { WelcomeModal } from './components/WelcomeModal';
import { CampaignDashboard } from './components/CampaignDashboard';
import { QuickGenerators } from './components/QuickGenerators';
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

  const [showCampaignDashboard, setShowCampaignDashboard] = useState(false);

  // Auto-initialize from environment variables on first load
  useEffect(() => {
    const hasConfig = checkConfiguration();
    if (hasConfig) {
      setIsConfigured(true);
      initializeFromEnv();
    } else {
      setShowWelcome(true);
    }
  }, []);

  const checkConfiguration = (): boolean => {
    const apiKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem('openai_apiKey');
    return !!apiKey;
  };

  const initializeFromEnv = () => {
    const apiKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem('openai_apiKey');
    const baseURL = import.meta.env.VITE_OPENAI_BASE_URL || localStorage.getItem('openai_baseURL');
    
    if (apiKey) {
      const config: LLMConfig = {
        provider: 'openai',
        apiKey,
        model: 'gpt-4o'
      };
      
      if (baseURL) {
        config.baseURL = baseURL;
      }
      
      try {
        chatService.configureProvider('openai', config);
        setCurrentProvider('openai');
        setProviderInStore('openai', 'gpt-4o');
        setIsConfigured(true);
      } catch (error) {
        console.error('Failed to initialize from environment:', error);
        setShowSettings(true);
      }
    }
  };

  const handleWelcomeComplete = (character: Character) => {
    setShowWelcome(false);
    setIsConfigured(true);
    // The character is already set in the chat service by the welcome modal
  };

  const handleCharacterGenerated = (character: Character) => {
    // Character is already set in the chat service, just close any open panels
    console.log('Character generated:', character.name);
  };

  const handleCampaignGenerated = (campaign: any) => {
    // Campaign is already saved to localStorage, just log it
    console.log('Campaign generated:', campaign.name);
  };

  if (!isConfigured && showWelcome) {
    return (
      <div className="h-screen bg-gray-900 text-white">
        <WelcomeModal 
          onComplete={handleWelcomeComplete}
          onClose={() => {
            setShowWelcome(false);
            setShowSettings(true);
          }}
        />
      </div>
    );
  }

  if (!isConfigured) {
    return (
      <div className="h-screen bg-gray-900 text-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4">Aeonisk AI Assistant</h1>
          <p className="mb-4">Please configure your AI provider to get started.</p>
          <button
            onClick={() => setShowSettings(true)}
            className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
          >
            Open Settings
          </button>
        </div>
        {showSettings && (
          <SettingsPanel
            onClose={() => setShowSettings(false)}
            onProviderConfig={(provider, config) => {
              chatService.configureProvider(provider, config);
              setCurrentProvider(provider);
              setIsConfigured(true);
              setShowSettings(false);
            }}
            onProviderChange={(provider) => {
              chatService.setProvider(provider);
              setCurrentProvider(provider);
            }}
            currentProvider={currentProvider}
          />
        )}
      </div>
    );
  }

  return (
    <div className="h-screen bg-gray-900 text-white flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">Aeonisk AI Assistant</h1>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">
              {currentProvider ? `Provider: ${currentProvider}` : 'No provider configured'}
            </span>
            <button
              onClick={() => setShowCampaignDashboard(!showCampaignDashboard)}
              className="px-3 py-1 bg-purple-600 rounded hover:bg-purple-700 transition-colors text-sm"
            >
              {showCampaignDashboard ? 'Hide' : 'Campaigns'}
            </button>
            <button
              onClick={() => setShowCharacter(!showCharacter)}
              className="px-3 py-1 bg-blue-600 rounded hover:bg-blue-700 transition-colors text-sm"
            >
              {showCharacter ? 'Hide' : 'Character'}
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="px-3 py-1 bg-gray-600 rounded hover:bg-gray-700 transition-colors text-sm"
            >
              {showSettings ? 'Hide' : 'Settings'}
            </button>
            {isDebugMode && (
              <button
                onClick={toggleDebugPanel}
                className="px-3 py-1 bg-yellow-600 rounded hover:bg-yellow-700 transition-colors text-sm"
              >
                Debug
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Quick Generators - Always visible at the top */}
      <div className="bg-gray-800 border-b border-gray-700 p-4">
        <QuickGenerators 
          onCharacterGenerated={handleCharacterGenerated}
          onCampaignGenerated={handleCampaignGenerated}
        />
      </div>

      {/* Campaign Dashboard */}
      {showCampaignDashboard && (
        <div className="bg-gray-800 border-b border-gray-700 max-h-64 overflow-y-auto">
          <CampaignDashboard />
        </div>
      )}

      {/* Main content: Stacked layout */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Character Panel (stacked at top, full width) */}
        {showCharacter && (
          <div className="w-full max-w-3xl mx-auto mt-4 mb-2 rounded-xl shadow-lg bg-gray-800 border border-gray-700 p-6 transition-all duration-300 max-h-[60vh] overflow-y-auto">
            <CharacterPanel onClose={() => setShowCharacter(false)} />
          </div>
        )}

        {/* Settings Panel (modal style, overlays content) */}
        {showSettings && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-60">
            <div className="w-full max-w-lg rounded-xl shadow-2xl bg-gray-800 border border-gray-700 p-6">
              <SettingsPanel
                onClose={() => setShowSettings(false)}
                onProviderConfig={(provider, config) => {
                  chatService.configureProvider(provider, config);
                  setCurrentProvider(provider);
                  setShowSettings(false);
                }}
                onProviderChange={(provider) => {
                  chatService.setProvider(provider);
                  setCurrentProvider(provider);
                }}
                currentProvider={currentProvider}
              />
            </div>
          </div>
        )}

        {/* Chat interface (always below character panel, scrolls independently) */}
        <div className="flex-1 min-h-0 w-full max-w-3xl mx-auto mb-4 rounded-xl shadow-lg bg-gray-900 border border-gray-800 p-4 overflow-y-auto transition-all duration-300">
          <ChatInterface />
        </div>
      </div>

      {/* Debug panel */}
      <DebugPanel />
    </div>
  );
}

export default App;
