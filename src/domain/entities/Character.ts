import { v4 as uuidv4 } from 'uuid';
import { CharacterSchema, CharacterData } from '../schemas/character.schema';

interface VoidHistoryEntry {
  timestamp: Date;
  change: number;
  reason?: string;
  newScore: number;
}

interface AttunementResult {
  success: boolean;
  error?: string;
}

export class Character {
  id: string;
  name: string;
  concept: string;
  origin_faction?: string;
  attributes: CharacterData['attributes'];
  skills: CharacterData['skills'];
  health: number;
  fatigue: number;
  voidScore: number;
  soulcredit: number;
  raw_seeds: CharacterData['raw_seeds'];
  attuned_seeds: CharacterData['attuned_seeds'];
  advantages: CharacterData['advantages'];
  disadvantages: CharacterData['disadvantages'];
  bonds: CharacterData['bonds'];
  notes?: string;
  createdAt: Date;
  updatedAt: Date;

  private voidHistory: VoidHistoryEntry[] = [];

  constructor(data: Partial<CharacterData>) {
    // Validate data
    const validatedData = CharacterSchema.parse(data);

    // Assign properties
    this.id = validatedData.id || uuidv4();
    this.name = validatedData.name;
    this.concept = validatedData.concept;
    if (validatedData.origin_faction !== undefined) {
      this.origin_faction = validatedData.origin_faction;
    }
    this.attributes = validatedData.attributes;
    this.skills = validatedData.skills;
    
    // Calculate derived stats
    this.health = validatedData.health || this.calculateHealth();
    this.fatigue = validatedData.fatigue || this.calculateFatigue();
    
    this.voidScore = validatedData.voidScore;
    this.soulcredit = validatedData.soulcredit;
    this.raw_seeds = validatedData.raw_seeds;
    this.attuned_seeds = validatedData.attuned_seeds;
    this.advantages = validatedData.advantages;
    this.disadvantages = validatedData.disadvantages;
    this.bonds = validatedData.bonds;
    if (validatedData.notes !== undefined) {
      this.notes = validatedData.notes;
    }
    
    this.createdAt = validatedData.createdAt || new Date();
    this.updatedAt = validatedData.updatedAt || new Date();
  }

  private calculateHealth(): number {
    return this.attributes.Size * 2;
  }

  private calculateFatigue(): number {
    return this.attributes.Size * 2 + this.attributes.Willpower - 2;
  }

  modifyVoidScore(change: number, reason?: string): void {
    this.voidScore = Math.max(0, Math.min(10, this.voidScore + change));
    
    if (reason !== undefined) {
      this.voidHistory.push({
        timestamp: new Date(),
        change,
        reason,
        newScore: this.voidScore
      });
    } else {
      this.voidHistory.push({
        timestamp: new Date(),
        change,
        newScore: this.voidScore
      });
    }

    this.updatedAt = new Date();
  }

  modifySoulcredit(change: number): void {
    this.soulcredit = Math.max(-10, Math.min(10, this.soulcredit + change));
    this.updatedAt = new Date();
  }

  getVoidHistory(): VoidHistoryEntry[] {
    return [...this.voidHistory];
  }

  addRawSeed(seedId: string, source: string): void {
    this.raw_seeds.push({
      id: seedId,
      source,
      acquiredAt: new Date()
    });
    this.updatedAt = new Date();
  }

  attuneSeed(seedId: string, element: string): AttunementResult {
    const seedIndex = this.raw_seeds.findIndex((seed: CharacterData['raw_seeds'][number]) => seed.id === seedId);
    
    if (seedIndex === -1) {
      return { success: false, error: `Seed ${seedId} not found` };
    }

    // Remove from raw seeds
    this.raw_seeds.splice(seedIndex, 1);
    
    // Add to attuned seeds
    this.attuned_seeds[element] = (this.attuned_seeds[element] || 0) + 1;
    
    this.updatedAt = new Date();
    
    return { success: true };
  }

  toJSON(): CharacterData & { id: string } {
    return {
      id: this.id,
      name: this.name,
      concept: this.concept,
      origin_faction: this.origin_faction,
      attributes: this.attributes,
      skills: this.skills,
      health: this.health,
      fatigue: this.fatigue,
      voidScore: this.voidScore,
      soulcredit: this.soulcredit,
      raw_seeds: this.raw_seeds,
      attuned_seeds: this.attuned_seeds,
      advantages: this.advantages,
      disadvantages: this.disadvantages,
      bonds: this.bonds,
      notes: this.notes,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt
    };
  }

  static fromJSON(data: CharacterData & { id: string }): Character {
    return new Character(data);
  }
}