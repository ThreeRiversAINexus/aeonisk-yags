// Core Types for Aeonisk AI Assistant

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  timestamp?: number;
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface Tool {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: object;
  };
}

export interface ContentChunk {
  id: string;
  text: string;
  metadata: {
    source: string;
    section: string;
    type: 'rules' | 'lore' | 'faction' | 'ritual' | 'skill' | 'combat' | 'gear';
    keywords: string[];
    subsection?: string;
  };
  embedding?: number[];
}

export interface GlossaryEntry {
  term: string;
  definition: string;
  related: string[];
  category: string;
}

export interface GameContent {
  // YAGS Core
  yagsCore: ContentChunk[];
  yagsCombat: ContentChunk[];
  yagsCharacters: ContentChunk[];
  yagsScifi: ContentChunk[];
  yagsBestiary: ContentChunk[];
  
  // Aeonisk
  aeoniskModule: ContentChunk[];
  aeoniskLore: ContentChunk[];
  aeoniskGear: ContentChunk[];
  aeoniskTactical: ContentChunk[];
  
  // Glossaries and indexes
  glossary: GlossaryEntry[];
  crossReferences: Map<string, string[]>;
}

export interface LLMConfig {
  provider: 'openai' | 'anthropic' | 'google' | 'groq' | 'together' | 'ollama' | 'custom';
  apiKey: string;
  baseURL?: string;
  model?: string;
  headers?: Record<string, string>;
  temperature?: number;
  maxTokens?: number;
}

export interface ChatOptions {
  model: string;
  provider: string;
  temperature?: number;
  tools?: Tool[];
}

export interface Character {
  // Core Identity
  name: string;
  player_name?: string;
  campaign?: string;
  origin_faction?: string;
  concept?: string;
  character_level_type?: 'Mundane' | 'Skilled' | 'Exceptional' | 'Heroic';
  tech_level?: string;
  
  // YAGS Primary Attributes (8)
  attributes: {
    strength: number;
    health: number;
    agility: number;
    dexterity: number;
    perception: number;
    intelligence: number;
    empathy: number;
    willpower: number;
  };
  
  // YAGS Secondary Attributes
  secondary_attributes: {
    size: number;
    soak: number;
    move: number;
  };
  
  // YAGS Talents (start at 2)
  talents: {
    athletics: number;
    awareness: number;
    brawl: number;
    charm: number;
    guile: number;
    sleight: number;
    stealth: number;
    throw: number;
  };
  
  // Skills (Knowledges, Standard, Aeonisk-specific)
  skills: {
    // Aeonisk Core
    astral_arts?: number;
    magick_theory?: number;
    intimacy_ritual?: number;
    corporate_influence?: number;
    debt_law?: number;
    pilot?: number;
    drone_operation?: number;
    dreamwork?: number;
    attunement?: number;
    
    // Additional skills
    [key: string]: number | undefined;
  };
  
  // Languages
  languages: {
    native_language: string;
    native_level: number;
    other_languages?: Array<{name: string; level: number}>;
  };
  
  // Techniques & Advantages
  techniques?: Array<{
    name: string;
    skill_basis: string;
    cost_level: number;
    description: string;
  }>;
  
  advantages?: Array<{
    name: string;
    cost?: number;
    description: string;
  }>;
  
  disadvantages?: Array<{
    name: string;
    cost?: number;
    description: string;
  }>;
  
  // Aeonisk Specific
  void_score: number;
  soulcredit: number;
  
  true_will?: {
    declared: boolean;
    statement: string;
    alignment_bonus_active: boolean;
  };
  
  bonds: Bond[];
  
  primary_ritual_item?: {
    name: string;
    description: string;
    effects_if_lost: string;
  };
  
  offerings?: Array<{
    name: string;
    description: string;
  }>;
  
  // Status Tracking
  wounds?: WoundTrack;
  stuns?: StunTrack;
  fatigue?: FatigueTrack;
}

export interface WoundTrack {
  current_level: string;
  current_penalty: number;
}

export interface StunTrack {
  current_level: string;
  current_penalty: number;
}

export interface FatigueTrack {
  current_level: string;
  current_penalty: number;
}

export interface Bond {
  name: string;
  type: string;
  status: 'Active' | 'Dormant' | 'Severed';
  strength?: number;
  partner?: string;
}

export interface GameState {
  character?: Character;
  scenario?: string;
  npcs?: NPC[];
}

export interface NPC {
  name: string;
  faction?: string;
  role?: string;
  description: string;
}

export interface ConversationContext {
  recentMessages: Message[];
  gameContext?: GameState;
}

export interface RetrievalResult {
  chunks: ContentChunk[];
  relevanceScores: number[];
}

export interface ConversationExport {
  format: 'jsonl' | 'finetune' | 'assistant' | 'sharegpt';
  includeContext: boolean;
  filterByRating?: number;
}

export interface TacticalSession {
  id: string;
  players: Player[];
  currentRound: number;
  phase: 'planning' | 'declaration' | 'resolution';
  actionQueue: DeclaredAction[];
  gameState: CombatState;
}

export interface Player {
  id: string;
  name: string;
  role: 'gm' | 'player';
  character?: Character;
}

export interface DeclaredAction {
  playerId: string;
  raw: string;
  parsed?: ParsedAction;
  timestamp: number;
}

export interface ParsedAction {
  type: string;
  target?: string;
  parameters?: Record<string, any>;
}

export interface CombatState {
  participants: CombatParticipant[];
  environment: string;
  round: number;
}

export interface CombatParticipant {
  id: string;
  name: string;
  initiative: number;
  wounds: number;
  stuns: number;
  position?: string;
}

export interface ActionResult {
  actor: string;
  action: string;
  outcome: string;
  mechanicalEffect?: Record<string, any>;
}
