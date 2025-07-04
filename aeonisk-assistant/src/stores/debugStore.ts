import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DebugLog {
  id: string;
  timestamp: number;
  type: 'prompt' | 'rag' | 'tool' | 'api' | 'cost';
  data: any;
}

interface DebugState {
  isDebugMode: boolean;
  verbosityLevel: 'basic' | 'detailed' | 'verbose';
  logs: DebugLog[];
  showDebugPanel: boolean;
  tokenCosts: {
    input: number;
    output: number;
    total: number;
    cost: number;
  };
  simulateInProgress: boolean;
  toggleSimulateInProgress: () => void;
  
  // Actions
  toggleDebugMode: () => void;
  setVerbosityLevel: (level: 'basic' | 'detailed' | 'verbose') => void;
  toggleDebugPanel: () => void;
  addLog: (type: DebugLog['type'], data: any) => void;
  clearLogs: () => void;
  updateTokenCosts: (input: number, output: number, costPerMillion: { input: number; output: number }) => void;
}

export const useDebugStore = create<DebugState>()(
  persist(
    (set) => ({
      isDebugMode: false,
      verbosityLevel: 'detailed',
      logs: [],
      showDebugPanel: false,
      tokenCosts: {
        input: 0,
        output: 0,
        total: 0,
        cost: 0,
      },
      simulateInProgress: false,
      toggleSimulateInProgress: () => set((state) => ({ simulateInProgress: !state.simulateInProgress })),

      toggleDebugMode: () => set((state) => ({ isDebugMode: !state.isDebugMode })),
      
      setVerbosityLevel: (level) => set({ verbosityLevel: level }),
      
      toggleDebugPanel: () => set((state) => ({ showDebugPanel: !state.showDebugPanel })),
      
      addLog: (type, data) => {
        set((state) => {
          const log: DebugLog = {
            id: crypto.randomUUID(),
            timestamp: Date.now(),
            type,
            data,
          };

          // Log to console in debug mode
          if (state.isDebugMode) {
            const prefix = `[AEONISK] ${type.toUpperCase()}`;
            console.group(prefix);
            console.log(data);
            console.groupEnd();
          }

          // Keep only last 100 logs
          const logs = [...state.logs, log].slice(-100);
          return { logs };
        });
      },
      
      clearLogs: () => set({ logs: [] }),
      
      updateTokenCosts: (input, output, costPerMillion) => {
        set((state) => {
          const newInput = state.tokenCosts.input + input;
          const newOutput = state.tokenCosts.output + output;
          const newTotal = newInput + newOutput;
          const inputCost = (newInput / 1_000_000) * costPerMillion.input;
          const outputCost = (newOutput / 1_000_000) * costPerMillion.output;
          const newCost = inputCost + outputCost;

          return {
            tokenCosts: {
              input: newInput,
              output: newOutput,
              total: newTotal,
              cost: newCost,
            },
          };
        });
      },
    }),
    {
      name: 'aeonisk-debug-store',
      partialize: (state) => ({
        isDebugMode: state.isDebugMode,
        verbosityLevel: state.verbosityLevel,
      }),
    }
  )
);
