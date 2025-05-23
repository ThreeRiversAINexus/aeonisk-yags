import type { Message, Tool, LLMConfig, ChatOptions, Character } from '../../types';
import { characterRegistry } from '../game/characterRegistry';

class ChatService {
  private apiKey: string = '';
  private provider: string = 'openai';
  private model: string = 'gpt-4';
  private baseURL: string = '';
  private temperature: number = 0.7;

  constructor() {
    // Initialize from localStorage if available
    this.loadSettings();
  }

  private loadSettings() {
    const savedProvider = localStorage.getItem('llm_provider');
    const savedApiKey = localStorage.getItem('llm_apiKey');
    const savedModel = localStorage.getItem('llm_model');
    const savedBaseURL = localStorage.getItem('llm_baseURL');
    const savedTemp = localStorage.getItem('llm_temperature');

    if (savedProvider) this.provider = savedProvider;
    if (savedApiKey) this.apiKey = savedApiKey;
    if (savedModel) this.model = savedModel;
    if (savedBaseURL) this.baseURL = savedBaseURL;
    if (savedTemp) this.temperature = parseFloat(savedTemp);
  }

  setConfig(config: Partial<LLMConfig>) {
    if (config.provider) {
      this.provider = config.provider;
      localStorage.setItem('llm_provider', config.provider);
    }
    if (config.apiKey) {
      this.apiKey = config.apiKey;
      localStorage.setItem('llm_apiKey', config.apiKey);
    }
    if (config.model) {
      this.model = config.model;
      localStorage.setItem('llm_model', config.model);
    }
    if (config.baseURL !== undefined) {
      this.baseURL = config.baseURL;
      localStorage.setItem('llm_baseURL', config.baseURL);
    }
    if (config.temperature !== undefined) {
      this.temperature = config.temperature;
      localStorage.setItem('llm_temperature', config.temperature.toString());
    }
  }

  getConfig(): LLMConfig {
    return {
      provider: this.provider as any,
      apiKey: this.apiKey,
      model: this.model,
      baseURL: this.baseURL,
      temperature: this.temperature,
    };
  }

  async sendMessage(
    messages: Message[],
    options?: ChatOptions
  ): Promise<{ message: Message; cost?: number; chunks?: any[] }> {
    const config = this.getConfig();
    
    if (!config.apiKey) {
      throw new Error('API key not configured');
    }

    // Add character context to messages
    const activeCharacter = characterRegistry.getActivePlayer();
    if (activeCharacter) {
      const characterContext = `Current character: ${activeCharacter.name}
Attributes: STR ${activeCharacter.attributes.strength}, HEA ${activeCharacter.attributes.health}, AGI ${activeCharacter.attributes.agility}, DEX ${activeCharacter.attributes.dexterity}, PER ${activeCharacter.attributes.perception}, INT ${activeCharacter.attributes.intelligence}, EMP ${activeCharacter.attributes.empathy}, WIL ${activeCharacter.attributes.willpower}
Talents: Athletics ${activeCharacter.talents.athletics}, Awareness ${activeCharacter.talents.awareness}, Brawl ${activeCharacter.talents.brawl}, Charm ${activeCharacter.talents.charm}, Guile ${activeCharacter.talents.guile}, Stealth ${activeCharacter.talents.stealth}
Skills: Astral Arts ${activeCharacter.skills.astral_arts || 0}, Pilot ${activeCharacter.skills.pilot || 0}
Void: ${activeCharacter.void_score}, Soulcredit: ${activeCharacter.soulcredit}`;
      
      // Prepend character context to the last user message
      if (messages.length > 0 && messages[messages.length - 1].role === 'user') {
        messages[messages.length - 1].content = `${characterContext}\n\n${messages[messages.length - 1].content}`;
      }
    }

    // TODO: Implement actual API calls based on provider
    // For now, return a mock response
    return {
      message: {
        role: 'assistant',
        content: 'This is a mock response. Please configure your LLM provider.',
        timestamp: Date.now(),
      },
      cost: 0.001,
      chunks: [],
    };
  }

  async loadContent(): Promise<void> {
    // TODO: Load YAGS and Aeonisk content for RAG
    console.log('Loading game content...');
  }

  getConversationHistory(): Message[] {
    // Load conversation history from localStorage
    const savedHistory = localStorage.getItem('conversation_history');
    if (savedHistory) {
      try {
        return JSON.parse(savedHistory);
      } catch (error) {
        console.error('Failed to parse conversation history:', error);
        return [];
      }
    }
    return [];
  }

  saveConversationHistory(messages: Message[]): void {
    // Save conversation history to localStorage
    try {
      localStorage.setItem('conversation_history', JSON.stringify(messages));
    } catch (error) {
      console.error('Failed to save conversation history:', error);
    }
  }

  rateMessage(index: number, rating: 'good' | 'bad' | 'edit'): void {
    // Store message ratings for future fine-tuning
    const ratings = JSON.parse(localStorage.getItem('message_ratings') || '{}');
    ratings[index] = rating;
    localStorage.setItem('message_ratings', JSON.stringify(ratings));
  }

  clearConversation(): void {
    // Clear conversation history from localStorage
    localStorage.removeItem('conversation_history');
    localStorage.removeItem('message_ratings');
  }

  exportConversation(format: string): string {
    const messages = this.getConversationHistory();
    if (format === 'aeonisk-dataset') {
      return this.exportAsAeoniskDataset(messages);
    }
    
    // Default JSON export
    return JSON.stringify(messages, null, 2);
  }

  private exportAsAeoniskDataset(messages: Message[]): string {
    const entries: any[] = [];
    let taskId = 1;
    
    // Find tool use messages and create dataset entries
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      
      if (msg.role === 'assistant' && msg.tool_calls) {
        for (const toolCall of msg.tool_calls) {
          const fn = JSON.parse(toolCall.function.arguments);
          
          if (toolCall.function.name === 'skill_check') {
            // Find the context message before this
            const contextMsg = i > 0 ? messages[i - 1] : null;
            const resultMsg = i < messages.length - 1 ? messages[i + 1] : null;
            
            const entry = this.createSkillCheckEntry(
              `YAGS-AEONISK-SESSION-${String(taskId).padStart(3, '0')}`,
              contextMsg?.content || 'Character attempts an action',
              fn,
              resultMsg
            );
            
            entries.push(entry);
            taskId++;
          }
        }
      }
    }
    
    return entries.map(e => this.formatYAMLEntry(e)).join('\n---\n');
  }

  private createSkillCheckEntry(
    taskId: string,
    scenario: string,
    args: any,
    resultMsg: Message | null
  ): any {
    const character = characterRegistry.getCharacter(args.character);
    
    return {
      task_id: taskId,
      domain: {
        core: 'rule_application',
        subdomain: `skill_check_${args.skill.toLowerCase()}`
      },
      scenario: scenario.substring(0, 200),
      environment: 'Interactive game session',
      stakes: 'Success or failure determines narrative outcome',
      characters: character ? [{
        name: character.name,
        tech_level: character.tech_level || 'Aeonisk Standard',
        attributes: character.attributes,
        skills: Object.fromEntries(
          Object.entries(character.skills).filter(([_, v]) => v && v > 0)
        ),
        current_void: character.void_score,
        soulcredit: character.soulcredit
      }] : [{
        name: args.character,
        tech_level: 'Aeonisk Standard',
        attributes: { strength: 3, health: 3, agility: 3, dexterity: 3, perception: 3, intelligence: 3, empathy: 3, willpower: 3 },
        skills: {}
      }],
      goal: `Perform ${args.skill} check using ${args.stat}`,
      expected_fields: ['attribute_used', 'skill_used', 'roll_formula', 'difficulty_guess', 'outcome_explanation', 'rationale'],
      gold_answer: {
        attribute_used: args.stat,
        skill_used: args.skill,
        roll_formula: this.getFormula(character, args),
        difficulty_guess: args.difficulty || 20,
        outcome_explanation: {
          critical_failure: {
            narrative: 'The attempt fails catastrophically',
            mechanical_effect: 'Objective failed with severe consequences'
          },
          failure: {
            narrative: 'The attempt fails',
            mechanical_effect: 'No progress made'
          },
          moderate_success: {
            narrative: 'The attempt succeeds',
            mechanical_effect: 'Objective achieved'
          },
          good_success: {
            narrative: 'The attempt succeeds well',
            mechanical_effect: 'Objective achieved with minor benefit'
          },
          excellent_success: {
            narrative: 'The attempt succeeds excellently',
            mechanical_effect: 'Objective achieved with significant advantage'
          },
          exceptional_success: {
            narrative: 'The attempt succeeds exceptionally',
            mechanical_effect: 'Exceptional outcome with major positive side-effect'
          }
        },
        rationale: `${args.stat} x ${args.skill} for the attempted action`
      },
      aeonisk_extra_data: {
        module: 'Aeonisk - YAGS Module',
        version: 'v1.2.0',
        tags: ['session_export']
      }
    };
  }

  private getFormula(character: Character | undefined, args: any): string {
    if (!character) {
      return '3 x 0 = 0; 0 + d20';
    }
    
    const attr = character.attributes[args.stat.toLowerCase() as keyof typeof character.attributes] || 3;
    const skillValue = character.skills[args.skill.toLowerCase() as keyof typeof character.skills] || 
                      character.talents[args.skill.toLowerCase() as keyof typeof character.talents] || 0;
    
    return `${args.stat} ${attr} x ${args.skill} ${skillValue} = ${attr * skillValue}; ${attr * skillValue} + d20`;
  }

  private formatYAMLEntry(entry: any): string {
    // Simple YAML formatter - in production you'd use a proper YAML library
    return JSON.stringify(entry, null, 2)
      .replace(/^{/, '')
      .replace(/}$/, '')
      .replace(/",$/gm, '"')
      .replace(/": /g, ': ')
      .replace(/^  "/gm, '  ');
  }
}

// Singleton instance
let chatServiceInstance: ChatService | null = null;

export function getChatService(): ChatService {
  if (!chatServiceInstance) {
    chatServiceInstance = new ChatService();
  }
  return chatServiceInstance;
}
