// Core Types for Aeonisk AI Assistant

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool' | 'progress' | 'error' | 'result';
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  timestamp?: number;
  ic?: boolean; // true = in-character, false = out-of-character
  // Additional fields for progress tracking
  progressType?: 'character-generation' | 'campaign-generation' | 'general';
  progressStatus?: 'started' | 'in-progress' | 'completed' | 'failed';
  resultData?: any; // For result messages, contains the generated data
  errorDetails?: string; // For error messages, contains detailed error information
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
  model?: string; // Model can be part of the provider's specific config
  headers?: Record<string, string>;
  temperature?: number;
  maxTokens?: number; // Optional max tokens for the provider
}

export interface ChatOptions {
  model?: string; // Optional: override provider's default model for this call
  provider?: string; // Optional: specify provider for this call if different from current
  temperature?: number;
  tools?: Tool[];
  maxTokens?: number; // Optional max tokens for this specific call
}

// YAGS Character Creation System
export type CampaignLevel = 'Mundane' | 'Skilled' | 'Exceptional' | 'Heroic';
export type PriorityLevel = 'Primary' | 'Secondary' | 'Tertiary';

export interface PriorityPools {
  attributes: PriorityLevel;
  experience: PriorityLevel;
  advantages: PriorityLevel;
}

export interface PriorityAllocation {
  attributes: {
    points: number;
    maxAttribute: number;
  };
  experience: {
    points: number;
    maxSkill: number;
  };
  advantages: {
    points: number;
  };
}

export interface Advantage {
  name: string;
  cost: number;
  description: string;
  category: 'physical' | 'supernatural' | 'background' | 'social' | 'mental';
  effects?: Record<string, any>;
}

export interface Disadvantage {
  name: string;
  cost: number; // Negative number
  description: string;
  category: 'physical' | 'supernatural' | 'background' | 'social' | 'mental';
  effects?: Record<string, any>;
}

export interface Technique {
  name: string;
  cost: number;
  description: string;
  skill: string;
  prerequisites?: string[];
  effects?: Record<string, any>;
  category: 'academic' | 'combat' | 'firearms' | 'melee' | 'outdoor' | 'physical' | 'social' | 'technical' | 'vehicle';
}

export interface Familiarity {
  name: string;
  cost: number;
  skill: string;
  description: string;
}

export interface Language {
  name: string;
  level: number; // 1-4 scale
  isNative: boolean;
}

export interface Item {
  id: string;
  name: string;
  type: string; // e.g., 'talisman', 'weapon', 'armor', 'offering', etc.
  equipped?: boolean;
  quantity?: number;
  notes?: string;
}

export type TalismanElement = 'Grain' | 'Drip' | 'Spark' | 'Breath' | 'Hollow' | 'Seed';

export interface TalismanItem extends Item {
  type: 'talisman';
  element: TalismanElement;
  current_charge: number;
  max_charge: number;
  size: 'Single' | 'Band' | 'Sigil' | 'Core' | 'Vault';
  attuned: boolean;
}

export interface Character {
  // Basic Info
  name: string;
  concept: string;
  character_level_type?: string; 
  origin_faction?: string; 
  tech_level?: string; 
  
  // YAGS Core Attributes (8)
  attributes: Record<string, number>; // Strength, Health, Agility, Dexterity, Perception, Intelligence, Empathy, Willpower
  
  // Secondary Attributes (calculated)
  secondary_attributes?: Record<string, number>; // Size, Soak, Move
  
  // Skills System
  skills: Record<string, number>; // Standard skills
  talents?: Record<string, number>; // 8 core talents (start at 2)
  knowledges?: Record<string, number>; // Knowledge skills
  
  // Languages
  languages?: {
    native_language_name?: string;
    native_language_level?: number;
    other_languages?: Array<{ name: string; level: number }>;
  };
  
  // Aeonisk Specific
  voidScore: number; 
  soulcredit: number;
  bonds: Bond[];
  trueWill?: string; 
  controller?: 'player' | 'ai' | 'gm';
  
  // Character Creation System
  campaignLevel?: CampaignLevel;
  priorityPools?: PriorityPools;
  advantages?: Advantage[];
  disadvantages?: Disadvantage[];
  techniques?: Technique[];
  familiarities?: Familiarity[];
  
  // Experience and Improvement
  experiencePoints?: number;
  backgroundExperience?: Record<string, number>; // Skills being learned through background
  jobExperience?: Record<string, number>; // Skills being learned through work
  trainingProgress?: Record<string, number>; // Skills being learned through training

  // Inventory System
  inventory?: Item[]; // All items, including talismans, offerings, gear, etc.
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

// AI DM and Multiplayer System
export interface AIPlayer {
  id: string;
  character: Character;
  personality: PlayerPersonality;
  faction: string;
  goals: PlayerGoal[];
  playStyle: 'aggressive' | 'cautious' | 'ritual-focused' | 'bond-builder' | 'void-seeker';
  decisionMaking: DecisionStrategy;
}

export interface PlayerPersonality {
  riskTolerance: number; // 1-10 scale
  bondPreference: 'seeks' | 'avoids' | 'neutral';
  voidCuriosity: number; // 1-10 scale
  factionLoyalty: number; // 1-10 scale
  ritualConservatism: number; // 1-10 scale
  socialAggressiveness: number; // 1-10 scale
}

export interface PlayerGoal {
  type: 'personal' | 'faction' | 'ritual' | 'bond' | 'void';
  description: string;
  priority: number; // 1-10 scale
  progress: number; // 0-100%
}

export interface DecisionStrategy {
  primaryFocus: 'combat' | 'social' | 'ritual' | 'exploration' | 'survival';
  secondaryFocus: 'combat' | 'social' | 'ritual' | 'exploration' | 'survival';
  riskAssessment: 'conservative' | 'balanced' | 'aggressive';
  groupCooperation: 'leader' | 'follower' | 'independent';
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

// Ritual System
export interface Ritual {
  name: string;
  threshold: number; // Willpower × Astral Arts + d20 vs threshold
  offering: string; // Required sacrifice
  voidRisk: number; // Base chance of void gain
  soulcreditCost: number;
  effects: RitualEffect[];
  consequences: RitualConsequence[];
  factionRestrictions?: string[];
  bondRequirements?: BondRequirement[];
  category: 'intimacy' | 'astral' | 'void' | 'faction' | 'transformation';
}

export interface RitualEffect {
  type: 'narrative' | 'mechanical' | 'world' | 'character';
  description: string;
  magnitude: number; // Based on success margin
  duration: 'instant' | 'scene' | 'session' | 'permanent';
}

export interface RitualConsequence {
  type: 'void_gain' | 'soulcredit_loss' | 'bond_strain' | 'narrative_complication';
  description: string;
  probability: number; // 0-1
  severity: number; // 1-10 scale
}

export interface BondRequirement {
  type: 'existing_bond' | 'new_bond' | 'bond_strength';
  description: string;
  minimumStrength?: number;
}

// Campaign and Dreamline System
export interface Dreamline {
  id: string;
  theme: string; // e.g., "Void Corruption", "Faction War", "Bond Betrayal"
  participants: Player[];
  sessions: Session[];
  timeline: TimelineEvent[];
  canon_status: 'canon' | 'dreamline' | 'void-corrupted';
  void_influence: number; // How much void affects this dreamline
}

export interface Session {
  id: string;
  dreamlineId: string;
  participants: Player[];
  actions: ActionRecord[];
  rituals: RitualRecord[];
  outcomes: OutcomeRecord[];
  mechanical_data: MechanicalRecord[];
  narrative_summary: string;
  void_progression: VoidRecord[];
  bond_changes: BondRecord[];
  timestamp: Date;
}

export interface TimelineEvent {
  id: string;
  description: string;
  timestamp: Date;
  participants: string[];
  effects: Record<string, any>;
  void_influence: number;
}

// Dataset Export System
export interface DatasetEntry {
  session_id: string;
  dreamline_id: string;
  participants: PlayerRecord[];
  actions: ActionRecord[];
  rituals: RitualRecord[];
  outcomes: OutcomeRecord[];
  mechanical_data: MechanicalRecord[];
  narrative_summary: string;
  void_progression: VoidRecord[];
  bond_changes: BondRecord[];
}

export interface PlayerRecord {
  id: string;
  name: string;
  character: Character;
  personality: PlayerPersonality;
  decisions: DecisionRecord[];
}

export interface ActionRecord {
  actor: string;
  action: string;
  target?: string;
  parameters?: Record<string, any>;
  outcome: string;
  success: boolean;
  margin?: number;
  timestamp: Date;
}

export interface RitualRecord {
  caster: string;
  ritual: string;
  offering: string;
  threshold: number;
  roll: number;
  success: boolean;
  margin: number;
  void_gained: number;
  soulcredit_cost: number;
  effects: RitualEffect[];
  consequences: RitualConsequence[];
  timestamp: Date;
}

export interface OutcomeRecord {
  type: 'success' | 'failure' | 'partial' | 'complication';
  description: string;
  mechanical_effects: Record<string, any>;
  narrative_impact: string;
  void_influence: number;
}

export interface MechanicalRecord {
  skill_checks: SkillCheckRecord[];
  attribute_checks: AttributeCheckRecord[];
  damage_dealt: DamageRecord[];
  healing: HealingRecord[];
}

export interface SkillCheckRecord {
  actor: string;
  attribute: string;
  skill: string;
  difficulty: number;
  roll: number;
  success: boolean;
  margin: number;
}

export interface AttributeCheckRecord {
  actor: string;
  attribute: string;
  difficulty: number;
  roll: number;
  success: boolean;
  margin: number;
}

export interface DamageRecord {
  attacker: string;
  target: string;
  damage: number;
  type: 'physical' | 'void' | 'astral';
  location?: string;
}

export interface HealingRecord {
  healer: string;
  target: string;
  amount: number;
  type: 'physical' | 'ritual' | 'natural';
}

export interface VoidRecord {
  character: string;
  previous_score: number;
  new_score: number;
  source: string;
  ritual?: string;
  timestamp: Date;
}

export interface BondRecord {
  character: string;
  bond_name: string;
  previous_status: string;
  new_status: string;
  strength_change?: number;
  reason: string;
  timestamp: Date;
}

export interface DecisionRecord {
  context: string;
  options: string[];
  chosen_option: string;
  reasoning: string;
  personality_factors: Record<string, number>;
  timestamp: Date;
}
