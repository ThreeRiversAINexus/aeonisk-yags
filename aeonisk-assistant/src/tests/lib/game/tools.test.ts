import { describe, it, expect, beforeEach } from 'vitest';
import { aeoniskTools, toolDefinitions, rollDice, executeSkillCheck } from '../../../lib/game/tools';
import { characterRegistry } from '../../../lib/game/characterRegistry';
import type { Character } from '../../../types';

describe('Aeonisk Game Tools', () => {
  beforeEach(() => {
    // Clear the registry before each test
    characterRegistry.clear();
  });

  const createTestCharacter = (): Character => ({
    name: 'Test Hero',
    concept: 'Test Character',
    origin_faction: 'Freeborn',
    character_level_type: 'Skilled',
    tech_level: 'Aeonisk Standard',
    attributes: {
      strength: 4,
      health: 3,
      agility: 4,
      dexterity: 3,
      perception: 3,
      intelligence: 5,
      empathy: 3,
      willpower: 4
    },
    secondary_attributes: {
      size: 5,
      soak: 12,
      move: 12
    },
    talents: {
      athletics: 3,
      awareness: 2,
      brawl: 2,
      charm: 2,
      guile: 2,
      sleight: 2,
      stealth: 4,
      throw: 2
    },
    skills: {
      astral_arts: 3,
      pilot: 1,
      research: 4
    },
    languages: {
      native_language_name: 'Common',
      native_language_level: 4,
      other_languages: []
    },
    advantages: [],
    disadvantages: [],
    voidScore: 1,
    soulcredit: 0,
    bonds: []
  });

  describe('Tool Definitions', () => {
    it('should export tool definitions', () => {
      expect(toolDefinitions).toBeDefined();
      expect(Array.isArray(toolDefinitions)).toBe(true);
      expect(toolDefinitions.length).toBeGreaterThan(0);
    });

    it('should have createCharacter tool', () => {
      const createCharacterTool = toolDefinitions.find(t => t.function.name === 'createCharacter');
      expect(createCharacterTool).toBeDefined();
      const params = createCharacterTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('name');
      expect(params.properties).toHaveProperty('concept');
    });

    it('should have skillCheck tool', () => {
      const skillCheckTool = toolDefinitions.find(t => t.function.name === 'skillCheck');
      expect(skillCheckTool).toBeDefined();
      const params = skillCheckTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('characterName');
      expect(params.properties).toHaveProperty('skill');
      expect(params.properties).toHaveProperty('attribute');
    });

    it('should have castRitual tool', () => {
      const castRitualTool = toolDefinitions.find(t => t.function.name === 'castRitual');
      expect(castRitualTool).toBeDefined();
      const params = castRitualTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('ritualName');
      expect(params.properties).toHaveProperty('casterName');
    });
  });

  describe('rollDice', () => {
    it('should roll dice correctly', () => {
      const result = rollDice(3, 15);

      expect(result).toHaveProperty('result');
      expect(result).toHaveProperty('dice');
      expect(result).toHaveProperty('successes');
      expect(result.dice).toHaveLength(3);
      expect(result.result).toBeGreaterThan(0);
      expect(result.successes).toBeGreaterThanOrEqual(0);
    });

    it('should handle advantage correctly', () => {
      const result = rollDice(4, 15, true, false);

      expect(result.dice).toHaveLength(4);
      expect(result.result).toBeGreaterThan(0);
    });

    it('should handle disadvantage correctly', () => {
      const result = rollDice(4, 15, false, true);

      expect(result.dice).toHaveLength(4);
      expect(result.result).toBeGreaterThan(0);
    });
  });

  describe('executeSkillCheck', () => {
    it('should perform skill check with character from registry', () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = executeSkillCheck('Test Hero', 'Stealth', 'Agility', 20);

      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('result');
      expect(result).toHaveProperty('dice');
      expect(result).toHaveProperty('successes');
      expect(result).toHaveProperty('description');
      expect(result).toHaveProperty('characterFound', true);
      expect(result.description).toContain('Test Hero rolling Agility (4) + Stealth (4)');
    });

    it('should use fallback when character not found', () => {
      const result = executeSkillCheck('Unknown Hero', 'Athletics', 'Strength', 15);

      expect(result.characterFound).toBe(false);
      expect(result.description).toContain('fallback - character "Unknown Hero" not found');
    });

    it('should apply bonuses correctly', () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = executeSkillCheck('Test Hero', 'Research', 'Intelligence', 25, { bonus: 5 });

      expect(result.result).toBeGreaterThan(0);
      expect(result.description).toContain('Test Hero rolling Intelligence (5) + Research (4)');
    });

    it('should handle talents correctly', () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = executeSkillCheck('Test Hero', 'Athletics', 'Strength', 15);

      expect(result.characterFound).toBe(true);
      expect(result.description).toContain('Test Hero rolling Strength (4) + Athletics (3)');
    });
  });

  describe('aeoniskTools', () => {
    it('should create a character', () => {
      const character = aeoniskTools.createCharacter('Test Character', 'Void Seeker', 'Freeborn');
      
      expect(character.name).toBe('Test Character');
      expect(character.concept).toBe('Void Seeker');
      expect(character.origin_faction).toBe('Freeborn');
      expect(character.attributes).toBeDefined();
      expect(character.talents).toBeDefined();
    });

    it('should get character from registry', () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const retrieved = aeoniskTools.getCharacter('Test Hero');
      expect(retrieved).toBeDefined();
      expect(retrieved?.name).toBe('Test Hero');
    });

    it('should list all characters', () => {
      const character1 = createTestCharacter();
      const character2 = { ...createTestCharacter(), name: 'Test Hero 2' };
      
      characterRegistry.addCharacter(character1);
      characterRegistry.addCharacter(character2);

      const all = aeoniskTools.getAllCharacters();
      expect(all).toHaveLength(2);
      expect(all.map(c => c.name)).toContain('Test Hero');
      expect(all.map(c => c.name)).toContain('Test Hero 2');
    });

    it('should perform skill check using character registry', () => {
      const character = createTestCharacter();
      
      const result = aeoniskTools.skillCheck(character, 'intelligence', 'research', 20);
      
      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('total');
      expect(result).toHaveProperty('roll');
      expect(result).toHaveProperty('attribute');
      expect(result).toHaveProperty('skill');
      expect(result.character).toBe('Test Hero');
    });

    it('should get available skills', () => {
      const skills = aeoniskTools.getAllAvailableSkills();
      expect(skills).toBeDefined();
      expect(typeof skills).toBe('object');
      expect(Array.isArray(skills.aeonisk)).toBe(true);
      expect(Array.isArray(skills.standard)).toBe(true);
      expect(Array.isArray(skills.knowledge)).toBe(true);
      expect(Array.isArray(skills.professional)).toBe(true);
      expect(Array.isArray(skills.vehicle)).toBe(true);
    });

    it('should get skills by category', () => {
      const skillsByCategory = aeoniskTools.getSkillsByCategory();
      expect(skillsByCategory).toBeDefined();
      expect(typeof skillsByCategory).toBe('object');
    });
  });
});
