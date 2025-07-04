import type { Message, LLMConfig, ChatOptions, Tool, ToolCall } from '../../types';

export interface LLMAdapter {
  chat(messages: Message[], options?: ChatOptions): Promise<Message>;
  streamChat?(messages: Message[], options?: ChatOptions): AsyncGenerator<Message>;
  supportsTools(): boolean;
}

export class OpenAICompatibleAdapter implements LLMAdapter {
  private apiKey: string;
  private baseURL: string;
  private model: string;

  constructor(config: LLMConfig) {
    this.apiKey = config.apiKey || '';
    this.baseURL = config.baseURL || 'https://api.openai.com/v1';
    this.model = config.model || 'gpt-4o'; // Default model
  }

  supportsTools(): boolean {
    // Most OpenAI compatible endpoints support tools/function calling
    return true; 
  }

  async chat(messages: Message[], options?: ChatOptions): Promise<Message> {
    const requestBody: any = {
      model: options?.model || this.model,
      messages: messages.map(m => ({ role: m.role, content: m.content })),
      temperature: options?.temperature || 0.7,
    };

    if (options?.maxTokens) {
      requestBody.max_tokens = options.maxTokens;
    }

    if (options && (options as any).tools && this.supportsTools()) {
      requestBody.tools = (options as any).tools;
      requestBody.tool_choice = "auto"; // Or specific if needed
    }
    
    const response = await fetch(`${this.baseURL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(`API Error: ${response.status} ${response.statusText} - ${errorData.error?.message}`);
    }

    const data = await response.json();
    const choice = data.choices[0].message;

    return {
      role: 'assistant',
      content: choice.content || '',
      tool_calls: choice.tool_calls as ToolCall[] | undefined,
    };
  }

  async *streamChat(messages: Message[], options?: ChatOptions): AsyncGenerator<Message> {
    const requestBody: any = {
      model: options?.model || this.model,
      messages: messages.map(m => ({ role: m.role, content: m.content })),
      temperature: options?.temperature || 0.7,
      stream: true,
    };

    if (options?.maxTokens) {
      requestBody.max_tokens = options.maxTokens;
    }
    
    // Streaming with tools is more complex and varies by provider.
    // For simplicity, this basic stream doesn't include tool calls in the stream itself.
    // A more robust solution would handle streamed tool calls if the API supports it.

    const response = await fetch(`${this.baseURL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok || !response.body) {
      const errorData = await response.json();
      throw new Error(`API Error: ${response.status} ${response.statusText} - ${errorData.error?.message}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      let eolIndex;
      while ((eolIndex = buffer.indexOf('\n')) >= 0) {
        const line = buffer.substring(0, eolIndex).trim();
        buffer = buffer.substring(eolIndex + 1);

        if (line.startsWith('data: ')) {
          const jsonData = line.substring(6);
          if (jsonData === '[DONE]') {
            return;
          }
          try {
            const parsed = JSON.parse(jsonData);
            if (parsed.choices && parsed.choices[0].delta) {
              yield { role: 'assistant', content: parsed.choices[0].delta.content || '' };
            }
          } catch (e) {
            console.error('Error parsing stream data:', e, jsonData);
          }
        }
      }
    }
  }
}

export class UnifiedLLMClient {
  private adapters: Map<string, LLMAdapter> = new Map();
  private currentProvider: string | null = null;

  constructor() {
    // Auto-initialize OpenAI if environment variable is available
    this.autoInitializeOpenAI();
  }

  private autoInitializeOpenAI(): void {
    const envApiKey = import.meta.env.VITE_OPENAI_API_KEY;
    if (envApiKey && envApiKey.trim() !== '') {
      console.log('Auto-initializing OpenAI from environment variable');
      this.addAdapter('openai', {
        provider: 'openai',
        apiKey: envApiKey,
        model: 'gpt-4o'
      });
      this.currentProvider = 'openai';
      
      // Clear any invalid localStorage configurations that might interfere
      this.clearInvalidConfigurations();
    }
  }

  private clearInvalidConfigurations(): void {
    // Clear any blank or invalid API keys from localStorage
    const providers = ['openai', 'anthropic', 'google', 'groq', 'together', 'custom'];
    for (const provider of providers) {
      const storedKey = localStorage.getItem(`${provider}_apiKey`);
      if (storedKey && (storedKey.trim() === '' || storedKey === 'undefined' || storedKey === 'null')) {
        console.log(`Clearing invalid ${provider} API key from localStorage`);
        localStorage.removeItem(`${provider}_apiKey`);
      }
    }
  }

  addAdapter(providerName: string, config: LLMConfig): void {
    // For now, assume all are OpenAI compatible.
    // Later, we can add specific adapters for Anthropic, Google, etc.
    this.adapters.set(providerName, new OpenAICompatibleAdapter(config));
    if (!this.currentProvider) {
      this.currentProvider = providerName;
    }
  }

  setProvider(providerName: string): void {
    if (!this.adapters.has(providerName)) {
      // Attempt to load config from environment or localStorage if not already configured
      let apiKey = null;
      if (providerName === 'openai') {
        // Check environment variable first, then localStorage
        apiKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem(`${providerName}_apiKey`);
      } else {
        apiKey = localStorage.getItem(`${providerName}_apiKey`);
      }
      const baseURL = localStorage.getItem(`${providerName}_baseURL`);
      const model = localStorage.getItem(`${providerName}_model`); // Or get from providerStore

      if (apiKey && apiKey.trim() !== '') {
        this.addAdapter(providerName, { 
          provider: providerName as any, 
          apiKey, 
          baseURL: baseURL || undefined, 
          model: model || undefined 
        });
      } else {
        console.warn(`Provider ${providerName} not configured and no valid API key found.`);
        // Do not set if not configured and no stored key
        return;
      }
    }
    this.currentProvider = providerName;
  }

  getCurrentProvider(): string | null {
    return this.currentProvider;
  }
  
  getConfiguredProviders(): string[] {
    return Array.from(this.adapters.keys());
  }

  forceReinitializeFromEnv(): void {
    // Clear all adapters and reinitialize from environment
    this.adapters.clear();
    this.currentProvider = null;
    this.autoInitializeOpenAI();
  }

  private getAdapter(): LLMAdapter {
    if (!this.currentProvider || !this.adapters.has(this.currentProvider)) {
      // Fallback or attempt to load default from localStorage
      const defaultProvider = localStorage.getItem('currentProvider');
      if (defaultProvider && this.adapters.has(defaultProvider)) {
        this.currentProvider = defaultProvider;
      } else if (this.adapters.size > 0) {
        // Fallback to the first configured adapter
        this.currentProvider = this.adapters.keys().next().value || null;
      } else {
         throw new Error('No LLM provider configured or selected.');
      }
    }
    return this.adapters.get(this.currentProvider!)!;
  }

  supportsTools(): boolean {
    try {
      return this.getAdapter().supportsTools();
    } catch (e) {
      return false; // If no adapter, no tools
    }
  }

  async chat(messages: Message[], options?: ChatOptions): Promise<Message> {
    return this.getAdapter().chat(messages, options);
  }

  streamChat(messages: Message[], options?: ChatOptions): AsyncGenerator<Message> {
    const adapter = this.getAdapter();
    if (!adapter.streamChat) {
      throw new Error(`Provider ${this.currentProvider} does not support streaming.`);
    }
    return adapter.streamChat(messages, options);
  }
}
