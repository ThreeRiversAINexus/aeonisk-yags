import { Character } from '../domain/entities/Character';
import { CharacterRepository } from '../infrastructure/repositories/CharacterRepository';
import { ApiError } from '../api/middleware/errorHandler';

export class CharacterService {
  constructor(private repository: CharacterRepository) {}

  async createCharacter(userId: string, characterData: any): Promise<Character> {
    const character = new Character(characterData);
    return this.repository.save(character, userId);
  }

  async getCharactersByUser(userId: string): Promise<Character[]> {
    return this.repository.findByUserId(userId);
  }

  async getCharacterById(characterId: string, userId: string): Promise<Character> {
    const character = await this.repository.findById(characterId);
    
    if (!character) {
      throw new ApiError(404, 'Character not found');
    }

    // Check ownership
    const userCharacters = await this.repository.findByUserId(userId);
    const isOwner = userCharacters.some(c => c.id === characterId);
    
    if (!isOwner) {
      throw new ApiError(403, 'Access denied');
    }

    return character;
  }

  async updateCharacter(
    characterId: string, 
    userId: string, 
    updateData: any
  ): Promise<Character> {
    // First check ownership
    await this.getCharacterById(characterId, userId);
    
    // Get the existing character
    const existingCharacter = await this.repository.findById(characterId);
    if (!existingCharacter) {
      throw new ApiError(404, 'Character not found');
    }

    // Merge the update data with existing data
    const updatedCharacterData = {
      ...existingCharacter.toJSON(),
      ...updateData,
      id: characterId // Ensure ID doesn't change
    };

    const updatedCharacter = new Character(updatedCharacterData);
    return this.repository.save(updatedCharacter, userId);
  }

  async deleteCharacter(characterId: string, userId: string): Promise<void> {
    // First check ownership
    await this.getCharacterById(characterId, userId);
    
    const deleted = await this.repository.delete(characterId);
    if (!deleted) {
      throw new ApiError(404, 'Character not found');
    }
  }

  async modifyVoidScore(
    characterId: string, 
    userId: string, 
    change: number, 
    reason?: string
  ): Promise<Character> {
    const character = await this.getCharacterById(characterId, userId);
    character.modifyVoidScore(change, reason);
    return this.repository.save(character, userId);
  }

  async modifySoulcredit(
    characterId: string, 
    userId: string, 
    change: number
  ): Promise<Character> {
    const character = await this.getCharacterById(characterId, userId);
    character.modifySoulcredit(change);
    return this.repository.save(character, userId);
  }

  async addRawSeed(
    characterId: string, 
    userId: string, 
    seedId: string, 
    source: string
  ): Promise<Character> {
    const character = await this.getCharacterById(characterId, userId);
    character.addRawSeed(seedId, source);
    return this.repository.save(character, userId);
  }

  async attuneSeed(
    characterId: string, 
    userId: string, 
    seedId: string, 
    element: string
  ): Promise<{ character: Character; result: any }> {
    const character = await this.getCharacterById(characterId, userId);
    const result = character.attuneSeed(seedId, element);
    
    if (!result.success) {
      throw new ApiError(400, result.error || 'Failed to attune seed');
    }

    const savedCharacter = await this.repository.save(character, userId);
    return { character: savedCharacter, result };
  }
}