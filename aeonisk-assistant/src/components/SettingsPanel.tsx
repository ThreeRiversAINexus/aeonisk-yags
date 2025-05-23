import { useState } from 'react';
import type { LLMConfig } from '../types';
import { useDebugStore } from '../stores/debugStore';
import { useProviderStore } from '../stores/providerStore';

interface SettingsPanelProps {
  onClose: () => void;
  onProviderConfig: (provider: string, config: LLMConfig) => void;
  onProviderChange: (provider: string) => void;
  currentProvider: string;
}

const PROVIDER_CONFIGS = {
  openai: {
    name: 'OpenAI',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    requiresBaseUrl: false
  },
  anthropic: {
    name: 'Anthropic',
    models: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'],
    requiresBaseUrl: false
  },
  google: {
    name: 'Google',
    models: ['gemini-1.5-pro-latest', 'gemini-1.5-flash-latest'],
    requiresBaseUrl: false
  },
  groq: {
    name: 'Groq',
    models: ['llama-3.1-70b-versatile', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
    requiresBaseUrl: false
  },
  together: {
    name: 'Together AI',
    models: ['meta-llama/Llama-3-70b-chat-hf', 'mistralai/Mixtral-8x7B-Instruct-v0.1'],
    requiresBaseUrl: false
  },
  custom: {
    name: 'Custom/OpenAI-Compatible',
    models: [],
    requiresBaseUrl: true
  }
};

export function SettingsPanel({ onClose, onProviderConfig, onProviderChange, currentProvider }: SettingsPanelProps) {
  const [selectedProvider, setSelectedProvider] = useState<string>('openai');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  const { isDebugMode, verbosityLevel, toggleDebugMode, setVerbosityLevel } = useDebugStore();
  const { setProvider: setProviderInStore } = useProviderStore();

  const handleSave = () => {
    if (!apiKey.trim()) {
      alert('Please enter an API key');
      return;
    }

    const config: LLMConfig = {
      provider: selectedProvider as any,
      apiKey: apiKey.trim(),
      model: model || PROVIDER_CONFIGS[selectedProvider as keyof typeof PROVIDER_CONFIGS].models[0]
    };

    if (PROVIDER_CONFIGS[selectedProvider as keyof typeof PROVIDER_CONFIGS].requiresBaseUrl && baseUrl.trim()) {
      config.baseURL = baseUrl.trim();
    }

    onProviderConfig(selectedProvider, config);
    
    // Clear sensitive data
    setApiKey('');
    setBaseUrl('');
  };

  const providerConfig = PROVIDER_CONFIGS[selectedProvider as keyof typeof PROVIDER_CONFIGS];

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 p-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Settings</h2>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-700 rounded transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">LLM Provider</label>
          <select
            value={selectedProvider}
            onChange={(e) => {
              setSelectedProvider(e.target.value);
              setModel('');
            }}
            className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {Object.entries(PROVIDER_CONFIGS).map(([key, config]) => (
              <option key={key} value={key}>{config.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">API Key</label>
          <div className="relative">
            <input
              type={showApiKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API key"
              className="w-full bg-gray-700 rounded px-3 py-2 pr-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
            >
              {showApiKey ? '👁️' : '👁️‍🗨️'}
            </button>
          </div>
        </div>

        {providerConfig.requiresBaseUrl && (
          <div>
            <label className="block text-sm font-medium mb-2">Base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.example.com/v1"
              className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}

        {providerConfig.models.length > 0 && (
          <div>
            <label className="block text-sm font-medium mb-2">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {providerConfig.models.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        )}

        <button
          onClick={handleSave}
          className="w-full px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
        >
          Save Configuration
        </button>

        {currentProvider && (
          <div className="mt-6 pt-6 border-t border-gray-700">
            <h3 className="text-sm font-medium mb-3">Configured Providers</h3>
            <div className="space-y-2">
              {Object.keys(PROVIDER_CONFIGS).map(provider => {
                const isConfigured = localStorage.getItem('llmConfig')?.includes(provider);
                const isCurrent = provider === currentProvider;
                
                if (!isConfigured) return null;
                
                return (
                  <button
                    key={provider}
                    onClick={() => {
                      onProviderChange(provider);
                      // Update provider store when changing providers
                      const savedConfig = localStorage.getItem('llmConfig');
                      if (savedConfig) {
                        const configs = JSON.parse(savedConfig);
                        const config = configs[provider];
                        if (config) {
                          setProviderInStore(provider, config.model || '');
                        }
                      }
                    }}
                    className={`w-full text-left px-3 py-2 rounded transition-colors ${
                      isCurrent 
                        ? 'bg-blue-600 text-white' 
                        : 'bg-gray-700 hover:bg-gray-600'
                    }`}
                  >
                    {PROVIDER_CONFIGS[provider as keyof typeof PROVIDER_CONFIGS].name}
                    {isCurrent && ' (Active)'}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Debug Mode Section */}
        <div className="mt-6 pt-6 border-t border-gray-700">
          <h3 className="text-sm font-medium mb-3">Debug Mode</h3>
          
          <div className="space-y-4">
            <label className="flex items-center justify-between">
              <span className="text-sm">Enable Debug Mode</span>
              <button
                onClick={toggleDebugMode}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  isDebugMode ? 'bg-blue-600' : 'bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    isDebugMode ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </label>

            {isDebugMode && (
              <div>
                <label className="block text-sm font-medium mb-2">Verbosity Level</label>
                <select
                  value={verbosityLevel}
                  onChange={(e) => setVerbosityLevel(e.target.value as any)}
                  className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="basic">Basic (Function calls only)</option>
                  <option value="detailed">Detailed (+ prompts & content)</option>
                  <option value="verbose">Verbose (+ all operations)</option>
                </select>
              </div>
            )}

            <div className="text-xs text-gray-400">
              Debug mode shows full prompts, retrieved content, function calls, and token usage.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
