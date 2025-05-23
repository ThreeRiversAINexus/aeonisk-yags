import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// Token costs per million tokens (in USD)
export const DEFAULT_TOKEN_COSTS = {
  openai: {
    'gpt-4o': { input: 5.00, output: 15.00 },
    'gpt-4o-mini': { input: 0.15, output: 0.60 },
    'gpt-4-turbo': { input: 10.00, output: 30.00 },
    'gpt-3.5-turbo': { input: 0.50, output: 1.50 },
  },
  anthropic: {
    'claude-3-5-sonnet-20241022': { input: 3.00, output: 15.00 },
    'claude-3-opus-20240229': { input: 15.00, output: 75.00 },
    'claude-3-haiku-20240307': { input: 0.25, output: 1.25 },
  },
  google: {
    'gemini-1.5-pro-latest': { input: 3.50, output: 10.50 },
    'gemini-1.5-flash-latest': { input: 0.35, output: 1.05 },
  },
  groq: {
    'llama-3.1-70b-versatile': { input: 0.59, output: 0.79 },
    'mixtral-8x7b-32768': { input: 0.27, output: 0.27 },
    'gemma2-9b-it': { input: 0.20, output: 0.20 },
  },
  together: {
    'meta-llama/Llama-3-70b-chat-hf': { input: 0.90, output: 0.90 },
    'mistralai/Mixtral-8x7B-Instruct-v0.1': { input: 0.60, output: 0.60 },
  },
};

interface ProviderConfig {
  provider: string;
  model: string;
  tokenCosts?: {
    input: number;
    output: number;
  };
}

interface ProviderState {
  currentProvider: string;
  currentModel: string;
  customCosts: Record<string, Record<string, { input: number; output: number }>>;
  
  // Actions
  setProvider: (provider: string, model: string) => void;
  setCustomCost: (provider: string, model: string, costs: { input: number; output: number }) => void;
  getCurrentCosts: () => { input: number; output: number } | null;
}

export const useProviderStore = create<ProviderState>()(
  persist(
    (set, get) => ({
      currentProvider: '',
      currentModel: '',
      customCosts: {},

      setProvider: (provider, model) => set({ currentProvider: provider, currentModel: model }),

      setCustomCost: (provider, model, costs) => {
        set((state) => ({
          customCosts: {
            ...state.customCosts,
            [provider]: {
              ...state.customCosts[provider],
              [model]: costs,
            },
          },
        }));
      },

      getCurrentCosts: () => {
        const { currentProvider, currentModel, customCosts } = get();
        
        // Check custom costs first
        if (customCosts[currentProvider]?.[currentModel]) {
          return customCosts[currentProvider][currentModel];
        }
        
        // Check default costs
        const providerCosts = DEFAULT_TOKEN_COSTS[currentProvider as keyof typeof DEFAULT_TOKEN_COSTS];
        if (providerCosts && providerCosts[currentModel as keyof typeof providerCosts]) {
          return providerCosts[currentModel as keyof typeof providerCosts];
        }
        
        // Default fallback
        return { input: 0, output: 0 };
      },
    }),
    {
      name: 'aeonisk-provider-store',
    }
  )
);
