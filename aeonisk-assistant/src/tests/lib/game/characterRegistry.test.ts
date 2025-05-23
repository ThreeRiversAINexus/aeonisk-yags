import { describe, it, expect, beforeEach } from 'vitest';
import { CharacterRegistry } from '../../../lib/game/characterRegistry';
import type { Character } from '../../../types';

describe('CharacterRegistry', () => {
  let registry: CharacterRegistry;
  
  beforeEach(() => {
    registry = new CharacterRegistry();
  });

  const createTestCharacter = (name: string): Character => ({
    name,
    concept: 'Test Character',
    origin_faction: 'Freeborn',
    character_level_type: 'Skilled',
    tech_level: 'Aeonisk Standard',
    attributes: {
      strength: 3,
      health: 3,
      agility: 3,
      dexterity: 3,
      perception: 3,
      intelligence: 3,
      empathy: 3,
      willpower: 3
    },
    secondary_attributes: {
      size: 5,
      soak: 12,
      move: 12
    },
    talents: {
      athletics: 2,
      awareness: 2,
      brawl: 2,
      charm: 2,
      guile: 2,
      sleight: 2,
      stealth: 2,
      throw: 2
    },
    skills: {
      astral_arts: 2,
      pilot: 1
    },
    languages: {
      native_language: 'Common',
      native_level: 4,
      other_languages: []
    },
    advantages: [],
    disadvantages: [],
    void_score: 0,
    soulcredit: 0,
    bonds: [
      { name: 'Test Bond', type: 'Kinship', status: 'Active' }
    ]
  });

  it('should add a character', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    expect(registry.hasCharacter('Test Hero')).toBe(true);
    expect(registry.size()).toBe(1);
  });

  it('should get a character by name', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    const retrieved = registry.getCharacter('Test Hero');
    expect(retrieved).toBeDefined();
    expect(retrieved?.name).toBe('Test Hero');
  });

  it('should set the first character as active player', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    const activePlayer = registry.getActivePlayer();
    expect(activePlayer).toBeDefined();
    expect(activePlayer?.name).toBe('Test Hero');
  });

  it('should remove a character', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    expect(registry.size()).toBe(1);
    
    const removed = registry.removeCharacter('Test Hero');
    expect(removed).toBe(true);
    expect(registry.size()).toBe(0);
  });

  it('should export character to JSON', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    const json = registry.exportCharacter('Test Hero');
    const parsed = JSON.parse(json);
    
    expect(parsed.name).toBe('Test Hero');
    expect(parsed.attributes.strength).toBe(3);
    expect(parsed.void_score).toBe(0);
  });

  it('should export character to YAML format', () => {
    const character = createTestCharacter('Test Hero');
    registry.addCharacter(character);
    
    const yaml = registry.exportCharacterToYAML('Test Hero');
    
    expect(yaml).toContain('character_name: "Test Hero"');
    expect(yaml).toContain('origin_faction: "Freeborn"');
    expect(yaml).toContain('strength: 3');
    expect(yaml).toContain('void_score: 0');
  });

  it('should import character from JSON', () => {
    const character = createTestCharacter('Test Hero');
    const json = JSON.stringify(character);
    
    const imported = registry.importCharacter(json);
    
    expect(imported.name).toBe('Test Hero');
    expect(registry.hasCharacter('Test Hero')).toBe(true);
  });

  it('should list all characters', () => {
    registry.addCharacter(createTestCharacter('Hero 1'));
    registry.addCharacter(createTestCharacter('Hero 2'));
    registry.addCharacter(createTestCharacter('Hero 3'));
    
    const all = registry.listAllCharacters();
    expect(all).toHaveLength(3);
    expect(all.map(c => c.name)).toContain('Hero 1');
    expect(all.map(c => c.name)).toContain('Hero 2');
    expect(all.map(c => c.name)).toContain('Hero 3');
  });

  it('should clear all characters', () => {
    registry.addCharacter(createTestCharacter('Hero 1'));
    registry.addCharacter(createTestCharacter('Hero 2'));
    
    expect(registry.size()).toBe(2);
    
    registry.clear();
    
    expect(registry.size()).toBe(0);
    expect(registry.getActivePlayer()).toBeUndefined();
  });
});
