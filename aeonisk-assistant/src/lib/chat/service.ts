import { UnifiedLLMClient } from '../llm/adapters';
import { AIEnhancedRAG } from '../rag';
import { ContentProcessor } from '../content/processor';
import { ConversationManager } from '../conversation/manager';
import { aeoniskTools, executeTool } from '../game/tools';
import { useDebugStore } from '../../stores/debugStore';
import { useProviderStore } from '../../stores/providerStore';
import type { Message, ContentChunk, GameState, LLMConfig, ChatOptions, Character } from '../../types';
import { getCharacterRegistry } from '../game/characterRegistry'; // Added for character access

export class AeoniskChatService {
  private llmClient: UnifiedLLMClient;
  private rag: AIEnhancedRAG;
  private conversationManager: ConversationManager;
  private gameState: GameState = {}; // Should be properly initialized
  private contentLoaded = false;

  constructor() {
    this.llmClient = new UnifiedLLMClient();
    this.rag = new AIEnhancedRAG();
    this.conversationManager = new ConversationManager();
    this.loadCharacterFromRegistry(); // Load character on init
  }

  private loadCharacterFromRegistry() {
    const characterRegistry = getCharacterRegistry();
    const activeCharacter = characterRegistry.getActivePlayer();
    if (activeCharacter) {
      this.gameState.character = activeCharacter;
    } else {
      // Fallback or load default if necessary
      const defaultChar = localStorage.getItem('character');
      if (defaultChar) {
        try {
          this.gameState.character = JSON.parse(defaultChar);
          characterRegistry.addCharacter(this.gameState.character!);
          characterRegistry.setActivePlayer(this.gameState.character!.name);
        } catch (e) { console.error("Failed to load default char for service", e); }
      }
    }
  }

  async initialize() {
    if (this.contentLoaded) return;

    try {
      await this.rag.initialize();
      this.contentLoaded = true;
    } catch (error) {
      console.error('Failed to initialize chat service:', error);
      throw error;
    }
  }

  configureProvider(provider: string, config: LLMConfig) {
    this.llmClient.addAdapter(provider, config);
    this.llmClient.setProvider(provider);
     // Persist this to localStorage via providerStore if needed
    const providerStore = useProviderStore.getState();
    providerStore.setProvider(provider, config.model || '');
    // Also save API key if present
    if (config.apiKey) localStorage.setItem(`${provider}_apiKey`, config.apiKey);
    if (config.baseURL) localStorage.setItem(`${provider}_baseURL`, config.baseURL);
  }

  getConfiguredProviders(): string[] {
    return this.llmClient.getConfiguredProviders();
  }

  setProvider(provider: string) {
    this.llmClient.setProvider(provider);
    const providerStore = useProviderStore.getState();
    const model = providerStore.currentModel; // Assuming model is stored per provider
    providerStore.setProvider(provider, model);
  }
  
  // Ensure this method exists and is used by CharacterPanel
  setCharacter(character: Character) {
    this.gameState.character = character;
    const characterRegistry = getCharacterRegistry();
    characterRegistry.addCharacter(character);
    characterRegistry.setActivePlayer(character.name); // Ensure registry is also updated
  }

  getCharacter(): Character | undefined {
    // Always get from the single source of truth: CharacterRegistry
    return getCharacterRegistry().getActivePlayer() || undefined;
  }


  async chat(messageContent: string, options?: ChatOptions): Promise<Message> {
    await this.initialize();
    this.loadCharacterFromRegistry(); // Ensure character state is fresh

    const context = {
      recentMessages: this.conversationManager.getRecentMessages(5),
      gameContext: this.gameState
    };

    const retrieval = await this.rag.retrieve(messageContent, 5);
    const debugStore = useDebugStore.getState();

    if (debugStore.isDebugMode && debugStore.verbosityLevel !== 'basic') {
      debugStore.addLog('rag', {
        query: messageContent,
        chunks: retrieval.chunks.map(chunk => ({
          text: chunk.text.substring(0, 200) + '...',
          metadata: chunk.metadata
        })),
        totalChunks: retrieval.chunks.length
      });
    }

    const systemPrompt = this.buildSystemPrompt(retrieval.chunks);
    const messages: Message[] = [
      { role: 'system', content: systemPrompt },
      ...context.recentMessages,
      { role: 'user', content: messageContent }
    ];

    if (debugStore.isDebugMode && debugStore.verbosityLevel === 'verbose') {
      const fullPrompt = messages.map(m => `${m.role}: ${m.content}`).join('\n\n');
      debugStore.addLog('prompt', {
        prompt: fullPrompt,
        tokens: fullPrompt.length / 4,
        hasCharacter: !!this.gameState.character
      });
    }

    const tools = this.llmClient.supportsTools() ? aeoniskTools : undefined;

    if (debugStore.isDebugMode) {
      debugStore.addLog('api', {
        provider: this.llmClient.getCurrentProvider(),
        model: options?.model || useProviderStore.getState().currentModel || 'gpt-4o',
        temperature: options?.temperature || 0.7,
        tools: !!tools
      });
    }

    try {
      const response = await this.llmClient.chat(messages, {
        ...options,
        tools,
        model: options?.model || useProviderStore.getState().currentModel || undefined
      });

      if (response.tool_calls && response.tool_calls.length > 0) {
        const toolResults = await this.handleToolCalls(response.tool_calls);
        const toolMessage: Message = {
          role: 'tool',
          content: JSON.stringify(toolResults),
          tool_call_id: response.tool_calls[0].id
        };
        const finalResponse = await this.llmClient.chat(
          [...messages, response, toolMessage],
          {...options, model: options?.model || useProviderStore.getState().currentModel || undefined }
        );
        this.conversationManager.addMessage({ role: 'user', content: messageContent });
        this.conversationManager.addMessage(finalResponse);
        return finalResponse;
      }

      this.conversationManager.addMessage({ role: 'user', content: messageContent });
      this.conversationManager.addMessage(response);
      return response;
    } catch (error) {
      console.error('Chat error:', error);
      throw error;
    }
  }

  async *streamChat(messageContent: string, options?: ChatOptions) {
    await this.initialize();
    this.loadCharacterFromRegistry();

    const context = {
      recentMessages: this.conversationManager.getRecentMessages(5),
      gameContext: this.gameState
    };

    const retrieval = await this.rag.retrieve(messageContent, 5);
    const systemPrompt = this.buildSystemPrompt(retrieval.chunks);
    const messages: Message[] = [
      { role: 'system', content: systemPrompt },
      ...context.recentMessages,
      { role: 'user', content: messageContent }
    ];

    try {
      const stream = this.llmClient.streamChat(messages, {...options, model: options?.model || useProviderStore.getState().currentModel || undefined});
      let fullResponse = '';
      for await (const chunk of stream) {
        fullResponse += chunk.content || '';
        yield chunk;
      }
      this.conversationManager.addMessage({ role: 'user', content: messageContent });
      this.conversationManager.addMessage({
        role: 'assistant',
        content: fullResponse
      });
    } catch (error) {
      console.error('Stream chat error:', error);
      throw error;
    }
  }

  private buildSystemPrompt(chunks: ContentChunk[]): string {
    let prompt = `You are an AI assistant for the Aeonisk YAGS tabletop RPG. You help players and GMs with rules questions, character creation, and running game sessions.

IMPORTANT: Base your answers on the provided game content. If something isn't covered in the context, say so rather than inventing rules.`;

    if (chunks.length > 0) {
      prompt += `\n\n## Relevant Game Content:\n`;
      for (const chunk of chunks) {
        prompt += `\n### ${chunk.metadata.source} - ${chunk.metadata.section}`;
        if (chunk.metadata.subsection) {
          prompt += ` - ${chunk.metadata.subsection}`;
        }
        prompt += `\n${chunk.text}\n`;
      }
    }

    if (this.gameState.character) {
      const char = this.gameState.character;
      prompt += `\n\n## Current Character: ${char.name}\n`;
      prompt += `Concept: ${char.concept}\n`;
      prompt += `Attributes: ${JSON.stringify(char.attributes)}\n`;
      prompt += `Skills: ${JSON.stringify(Object.fromEntries(Object.entries(char.skills).filter(([,val]) => val > 0)))}\n`;
      prompt += `Void Score: ${char.voidScore}\n`;
      prompt += `Soulcredit: ${char.soulcredit}\n`;
      if (char.trueWill) prompt += `True Will: ${char.trueWill}\n`;
    }

    prompt += `\n\nRespond conversationally, and offer to roll dice or perform game actions when appropriate.`;
    return prompt;
  }

  private async handleToolCalls(toolCalls: any[]): Promise<any[]> {
    const results = [];
    const debugStore = useDebugStore.getState();
    const characterRegistry = getCharacterRegistry();

    for (const toolCall of toolCalls) {
      const { name, arguments: argsString } = toolCall.function;
      const parsedArgs = JSON.parse(argsString);
      
      // Ensure character_name is passed or use active character
      if (!parsedArgs.character_name && (name === 'roll_skill_check' || name === 'perform_ritual' || name === 'modify_character' || name === 'roll_combat')) {
        const activeChar = characterRegistry.getActivePlayer();
        if (activeChar) {
          parsedArgs.character_name = activeChar.name;
        } else if (this.gameState.character) {
           parsedArgs.character_name = this.gameState.character.name;
        }
      }

      if (debugStore.isDebugMode) {
        debugStore.addLog('tool', { name, args: parsedArgs });
      }

      try {
        const result = await executeTool(name, parsedArgs);
        if (name === 'modify_character') {
          this.updateGameState(result.changes);
        }
        if (debugStore.isDebugMode) {
          debugStore.addLog('tool', { name, args: parsedArgs, result });
        }
        results.push({ tool_call_id: toolCall.id, result });
      } catch (error) {
        results.push({ tool_call_id: toolCall.id, error: error instanceof Error ? error.message : String(error) });
      }
    }
    return results;
  }

  private updateGameState(changes: any) {
    const characterRegistry = getCharacterRegistry();
    const charToUpdate = characterRegistry.getCharacter(changes.character_name) || (this.gameState.character?.name === changes.character_name ? this.gameState.character : null);

    if (!charToUpdate) return;

    if (changes.void_change) {
      charToUpdate.voidScore = Math.max(0, Math.min(10, (charToUpdate.voidScore || 0) + changes.void_change));
    }
    if (changes.soulcredit_change) {
      charToUpdate.soulcredit = Math.max(-10, Math.min(10, (charToUpdate.soulcredit || 0) + changes.soulcredit_change));
    }
    // Persist change
    characterRegistry.addCharacter(charToUpdate); 
    if (this.gameState.character?.name === charToUpdate.name) {
        this.gameState.character = charToUpdate; // also update local game state if it's the current one
    }
  }

  private async loadContentFiles(): Promise<{ [filename: string]: string }> {
    const contentFiles = [
      'Aeonisk - YAGS Module - v1.2.0.md',
      'Aeonisk - Lore Book - v1.2.0.md',
      'Aeonisk - Gear & Tech Reference - v1.2.0.md',
      'aeonisk_glossary.md',
      'experimental/Aeonisk - Tactical Module - v1.2.0.md' // Added tactical module
    ];
    const files: { [filename: string]: string } = {};
    for (const filename of contentFiles) {
      try {
        const response = await fetch(`/content/${filename}`);
        if (response.ok) {
          files[filename] = await response.text();
        } else {
          console.warn(`Failed to load content file: ${filename}`);
        }
      } catch (error) {
        console.error(`Error loading content file ${filename}:`, error);
      }
    }
    return files;
  }

  getConversationHistory(): Message[] {
    return this.conversationManager.getMessages();
  }

  clearConversation() {
    this.conversationManager.clearConversation();
    localStorage.removeItem('conversation_history'); // Ensure localStorage is also cleared
  }

  exportConversation(): string {
    return this.conversationManager.exportConversation();
  }

  getConversationSummary(): string {
    return this.conversationManager.getConversationSummary();
  }
}

let chatServiceInstance: AeoniskChatService | null = null;
export function getChatService(): AeoniskChatService {
  if (!chatServiceInstance) {
    chatServiceInstance = new AeoniskChatService();
  }
  return chatServiceInstance;
}
