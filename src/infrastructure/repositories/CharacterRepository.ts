import { eq } from 'drizzle-orm';
import { Character } from '../../domain/entities/Character';
import { characters } from '../database/schema';
import type { Database } from '../database';

export class CharacterRepository {
  constructor(private db: Database) {}

  async save(character: Character, userId: string): Promise<Character> {
    const data = {
      id: character.id,
      userId,
      name: character.name,
      concept: character.concept,
      originFaction: character.origin_faction,
      attributes: character.attributes,
      skills: character.skills,
      health: character.health,
      fatigue: character.fatigue,
      voidScore: character.voidScore,
      soulcredit: character.soulcredit,
      rawSeeds: character.raw_seeds,
      attunedSeeds: character.attuned_seeds,
      advantages: character.advantages,
      disadvantages: character.disadvantages,
      bonds: character.bonds,
      notes: character.notes,
      createdAt: character.createdAt,
      updatedAt: new Date()
    };

    // Check if character exists
    const existing = await this.db.select()
      .from(characters)
      .where(eq(characters.id, character.id));

    let result;
    
    if (existing.length > 0) {
      // Update existing character
      const { id, ...updateData } = data;
      result = await this.db.update(characters)
        .set(updateData)
        .where(eq(characters.id, character.id))
        .returning();
    } else {
      // Insert new character
      result = await this.db.insert(characters)
        .values(data)
        .returning();
    }

    return this.mapToEntity(result[0]);
  }

  async findById(id: string): Promise<Character | null> {
    const result = await this.db.select()
      .from(characters)
      .where(eq(characters.id, id));

    if (result.length === 0) {
      return null;
    }

    return this.mapToEntity(result[0]);
  }

  async findByUserId(userId: string): Promise<Character[]> {
    const result = await this.db.select()
      .from(characters)
      .where(eq(characters.userId, userId));

    return result.map(row => this.mapToEntity(row));
  }

  async delete(id: string): Promise<boolean> {
    const result = await this.db.delete(characters)
      .where(eq(characters.id, id));

    return (result as any).rowCount > 0;
  }

  private mapToEntity(row: any): Character {
    const data: any = {
      id: row.id,
      name: row.name,
      concept: row.concept,
      attributes: row.attributes,
      skills: row.skills,
      health: row.health,
      fatigue: row.fatigue,
      voidScore: row.voidScore,
      soulcredit: row.soulcredit,
      raw_seeds: row.rawSeeds,
      attuned_seeds: row.attunedSeeds,
      advantages: row.advantages,
      disadvantages: row.disadvantages,
      bonds: row.bonds,
      createdAt: row.createdAt,
      updatedAt: row.updatedAt
    };

    // Only add optional fields if they are not null
    if (row.originFaction !== null) {
      data.origin_faction = row.originFaction;
    }
    if (row.notes !== null) {
      data.notes = row.notes;
    }

    return new Character(data);
  }
}