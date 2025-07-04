import { UnifiedLLMClient } from '../llm/adapters';
import { AIEnhancedRAG } from '../rag';
import { ContentProcessor } from '../content/processor';
import { ConversationManager } from '../conversation/manager';
import { aeoniskTools, executeTool, toolDefinitions } from '../game/tools';
import { useDebugStore } from '../../stores/debugStore';
import { useProviderStore } from '../../stores/providerStore';
import type { Message, ContentChunk, GameState, LLMConfig, ChatOptions, Character } from '../../types';
import { getCharacterRegistry } from '../game/characterRegistry'; // Added for character access
import YAML from 'yaml';

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
    
    // Set up embedding provider for RAG
    this.rag.setEmbeddingProvider({
      generateEmbedding: async (text: string) => {
        const apiKey = import.meta.env.VITE_OPENAI_API_KEY || localStorage.getItem('openai_apiKey');
        if (!apiKey) {
          console.log('No OpenAI API key found, skipping embeddings');
          throw new Error('No OpenAI API key configured');
        }
        
        try {
          console.log('Generating embedding for text chunk...');
          const response = await fetch('https://api.openai.com/v1/embeddings', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${apiKey}`
            },
            body: JSON.stringify({
              input: text.substring(0, 8000), // OpenAI has a limit
              model: 'text-embedding-ada-002'
            })
          });
          
          if (!response.ok) {
            const errorText = await response.text();
            console.error('Embedding API error:', response.status, errorText);
            throw new Error(`Embedding API error: ${response.status} - ${errorText}`);
          }
          
          const data = await response.json();
          console.log('Successfully generated embedding');
          return data.data[0].embedding;
        } catch (error) {
          console.error('Failed to generate embedding:', error);
          throw error;
        }
      }
    });
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

  forceReinitializeFromEnv(): void {
    this.llmClient.forceReinitializeFromEnv();
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


  async chat(messageContent: string, options?: ChatOptions & { ic?: boolean, knowledge?: string }): Promise<Message> {
    await this.initialize();
    this.loadCharacterFromRegistry();

    const context = {
      recentMessages: this.conversationManager.getRecentMessages(5),
      gameContext: this.gameState
    };

    // Filter out 'tool' messages from recentMessages for LLM context
    const filteredRecentMessages = context.recentMessages.filter(m => m.role !== 'tool');

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

    // Add IC/OOC context and knowledge level to the system prompt
    let systemPrompt = this.buildSystemPrompt(retrieval.chunks, (options as any)?.ic !== false, (options as any)?.knowledge || 'low');
    if (typeof options?.ic === 'boolean') {
      if (options.ic) {
        systemPrompt += '\n\nAll chat is in-character (IC) unless the user marks it as OOC. Respond as the character would in the current scene.';
      } else {
        systemPrompt += '\n\nThe user is speaking out-of-character (OOC). Respond as the AI DM, not as an in-world character.';
      }
    }

    const messages: Message[] = [
      { role: 'system', content: systemPrompt },
      ...filteredRecentMessages,
      { role: 'user', content: messageContent, ic: options?.ic }
    ];

    if (debugStore.isDebugMode && debugStore.verbosityLevel === 'verbose') {
      const fullPrompt = messages.map(m => `${m.role}: ${m.content}`).join('\n\n');
      debugStore.addLog('prompt', {
        prompt: fullPrompt,
        tokens: fullPrompt.length / 4,
        hasCharacter: !!this.gameState.character
      });
    }

    const tools = this.llmClient.supportsTools() ? toolDefinitions : undefined;

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
        this.conversationManager.addMessage({ role: 'user', content: messageContent, ic: options?.ic });
        this.conversationManager.addMessage(finalResponse);
        return finalResponse;
      }

      this.conversationManager.addMessage({ role: 'user', content: messageContent, ic: options?.ic });
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
    const systemPrompt = this.buildSystemPrompt(retrieval.chunks, (options as any)?.ic !== false);
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

  private buildSystemPrompt(chunks: ContentChunk[], icMode: boolean = true, knowledge: string = 'low'): string {
    let prompt = `You are the AI DM for the Aeonisk YAGS tabletop RPG. Your job is to run immersive, in-character campaign scenes, narrate the world, play NPCs, and respond to the player as their character. Only break character if the user marks their message as OOC (out-of-character).\n\nIMPORTANT: Base your answers on the provided game content. If something isn't covered in the context, say so rather than inventing rules.`;

    // Add knowledge level context
    if (knowledge === 'low') {
      prompt += `\n\nThe player is new to Aeonisk. Assume they know nothing about the setting, rules, or terminology. Explain things clearly, avoid jargon, and provide context for any setting-specific details.`;
    } else if (knowledge === 'medium') {
      prompt += `\n\nThe player has some familiarity with Aeonisk. You can use basic setting terms, but provide brief explanations for advanced concepts.`;
    } else {
      prompt += `\n\nThe player is experienced with Aeonisk. You can use setting terms and assume they know the basics.`;
    }

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

    // Add strong IC/OOC instructions
    prompt += `\n\n## Roleplaying and IC/OOC Instructions:`;
    prompt += `\n- If the user's message is in-character (IC), always respond as the in-world DM. Narrate the scene, play NPCs, and address the user as their character. Never break character or reference rules unless the player asks OOC.`;
    prompt += `\n- If the user's message is out-of-character (OOC), step out of the game world. Answer rules, meta, or clarifications as a helpful assistant. Clearly mark your response as [OOC] at the start.`;
    prompt += `\n- Never mix IC and OOC in the same response. Always match the user's mode.`;
    prompt += `\n- When in doubt, default to immersive, in-character narration and actionable choices.`;
    prompt += `\n- Never refer to the user as 'player' or 'user' in-character; use their character's name. Only use 'player' or 'user' in OOC responses.`;

    if (this.gameState.character) {
      const char = this.gameState.character;
      prompt += `\n\n## Current Character: ${char.name}\n`;
      prompt += `Concept: ${char.concept}\n`;
      prompt += `Attributes: ${JSON.stringify(char.attributes)}\n`;
      prompt += `Skills: ${JSON.stringify(Object.fromEntries(Object.entries(char.skills || {}).filter(([,val]) => val > 0)))}\n`;
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

  /**
   * Generate a campaign proposal using the LLM, based on the provided character.
   * Returns a CampaignData object (theme, location, factions, npcs, scenario seed, etc.).
   */
  async generateCampaignProposalFromCharacter(character: Character): Promise<any> {
    const systemPrompt = `You are the AI DM for the Aeonisk YAGS tabletop RPG. Your job is to propose a campaign setup tailored to the following player character. Generate a JSON or YAML object with the following fields: name, description, theme, factions (array), npcs (array of {name, faction, role, description}), scenarios (array of {id, name, description, location, factions, objectives, complications}), and dreamlines (array, can be empty). Be creative, immersive, and make sure the campaign fits the character's background, origin, and skills.\n\nCharacter:\n${JSON.stringify(character, null, 2)}\n\nRespond ONLY with the campaign object, no extra commentary.`;
    const messages: Message[] = [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: 'Please generate the campaign proposal.' }
    ];
    const response = await this.llmClient.chat(messages, { temperature: 0.8, model: undefined });
    let content = response.content || '';
    // Log the raw LLM response for debugging
    console.log('[LLM Campaign Proposal] Raw response:', content);
    // Always extract and parse code block content first (if present)
    let campaign = null;
    const codeBlockMatch = content.match(/```(?:json|yaml)?([\s\S]*?)```/i);
    if (codeBlockMatch) {
      const code = codeBlockMatch[1].trim();
      try {
        campaign = JSON.parse(code);
      } catch {
        try {
          campaign = YAML.parse(code);
        } catch {}
      }
    }
    // Only fall back to parsing the whole string if there is no code block
    if (!campaign) {
      try {
        campaign = JSON.parse(content);
      } catch {
        try {
          campaign = YAML.parse(content);
        } catch {}
      }
    }
    // If campaign is a function/tool output (OpenAI style), extract from 'properties' array
    if (campaign && Array.isArray(campaign.properties)) {
      const obj: any = {};
      for (const prop of campaign.properties) {
        if (prop.name && prop.value !== undefined) {
          obj[prop.name] = prop.value;
        }
      }
      campaign = obj;
    }
    // If campaign is still not a usable object, fallback to null
    if (!campaign || typeof campaign !== 'object' || Array.isArray(campaign) || Object.keys(campaign).length === 0) {
      throw new Error('Failed to parse campaign proposal from LLM response.');
    }
    return campaign;
  }
}

let chatServiceInstance: AeoniskChatService | null = null;
export function getChatService(): AeoniskChatService {
  if (!chatServiceInstance) {
    chatServiceInstance = new AeoniskChatService();
  }
  return chatServiceInstance;
}
