import { v4 as uuidv4 } from 'uuid';
import { GameSessionSchema, GameSessionData, NPCData, ActionData, SessionPhase } from '../schemas/gameSession.schema';
import { Character } from './Character';

export class GameSession {
  id: string;
  name: string;
  description?: string;
  characters: Character[];
  npcs: NPCData[];
  actions: ActionData[];
  isActive: boolean;
  currentPhase: SessionPhase;
  metadata?: Record<string, any>;
  createdAt: Date;
  updatedAt: Date;
  endedAt?: Date;

  constructor(data: Partial<GameSessionData>) {
    const validatedData = GameSessionSchema.parse(data);

    this.id = validatedData.id || uuidv4();
    this.name = validatedData.name;
    if (validatedData.description !== undefined) {
      this.description = validatedData.description;
    }
    
    // Convert character data to Character instances
    this.characters = validatedData.characters.map(charData => 
      'toJSON' in charData ? charData as Character : new Character(charData)
    );
    
    this.npcs = validatedData.npcs;
    this.actions = validatedData.actions;
    this.isActive = validatedData.isActive;
    this.currentPhase = validatedData.currentPhase;
    
    if (validatedData.metadata !== undefined) {
      this.metadata = validatedData.metadata;
    }
    
    this.createdAt = validatedData.createdAt || new Date();
    this.updatedAt = validatedData.updatedAt || new Date();
    
    if (validatedData.endedAt !== undefined) {
      this.endedAt = validatedData.endedAt;
    }
  }

  // Character Management
  addCharacter(character: Character): void {
    if (!this.characters.find(c => c.id === character.id)) {
      this.characters.push(character);
      this.updatedAt = new Date();
    }
  }

  removeCharacter(characterId: string): boolean {
    const index = this.characters.findIndex(c => c.id === characterId);
    if (index !== -1) {
      this.characters.splice(index, 1);
      this.updatedAt = new Date();
      return true;
    }
    return false;
  }

  getCharacterById(characterId: string): Character | undefined {
    return this.characters.find(c => c.id === characterId);
  }

  // NPC Management
  addNPC(npcData: Omit<NPCData, 'id'>): NPCData {
    const npc: NPCData = {
      id: uuidv4(),
      ...npcData
    };
    this.npcs.push(npc);
    this.updatedAt = new Date();
    return npc;
  }

  removeNPC(npcId: string): boolean {
    const index = this.npcs.findIndex(n => n.id === npcId);
    if (index !== -1) {
      this.npcs.splice(index, 1);
      this.updatedAt = new Date();
      return true;
    }
    return false;
  }

  // Action Recording
  recordAction(actionData: Omit<ActionData, 'id' | 'timestamp'>): ActionData {
    const action: ActionData = {
      id: uuidv4(),
      timestamp: new Date(),
      ...actionData
    };
    this.actions.push(action);
    this.updatedAt = new Date();
    return action;
  }

  // Session State Management
  transitionToPhase(phase: SessionPhase): void {
    this.currentPhase = phase;
    this.updatedAt = new Date();
  }

  endSession(): void {
    this.isActive = false;
    this.endedAt = new Date();
    this.updatedAt = new Date();
  }

  getDurationMinutes(): number | null {
    if (!this.endedAt) return null;
    return Math.round((this.endedAt.getTime() - this.createdAt.getTime()) / (1000 * 60));
  }

  // Serialization
  toJSON(): GameSessionData & { id: string } {
    return {
      id: this.id,
      name: this.name,
      description: this.description,
      characters: this.characters.map(c => c.toJSON()),
      npcs: this.npcs,
      actions: this.actions,
      isActive: this.isActive,
      currentPhase: this.currentPhase,
      metadata: this.metadata,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      endedAt: this.endedAt
    };
  }

  static fromJSON(data: any): GameSession {
    // Convert ISO strings back to dates
    const sessionData = {
      ...data,
      createdAt: data.createdAt ? new Date(data.createdAt) : undefined,
      updatedAt: data.updatedAt ? new Date(data.updatedAt) : undefined,
      endedAt: data.endedAt ? new Date(data.endedAt) : undefined,
      actions: data.actions?.map((a: any) => ({
        ...a,
        timestamp: new Date(a.timestamp)
      })) || []
    };

    return new GameSession(sessionData);
  }
}