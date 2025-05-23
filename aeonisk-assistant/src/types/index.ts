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
  name: string;
  concept: string;
  attributes: Record<string, number>;
  skills: Record<string, number>;
  voidScore: number;
  soulcredit: number;
  bonds: Bond[];
  trueWill?: string;
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
