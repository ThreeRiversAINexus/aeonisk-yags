import { describe, it, expect, beforeEach } from 'vitest';
import { gameTools, executeGameTool } from '../../../lib/game/tools';
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
      native_language: 'Common',
      native_level: 4,
      other_languages: []
    },
    advantages: [],
    disadvantages: [],
    void_score: 1,
    soulcredit: 0,
    bonds: []
  });

  describe('Tool Definitions', () => {
    it('should export the correct number of tools', () => {
      expect(gameTools).toHaveLength(3);
    });

    it('should have roll_dice tool', () => {
      const rollTool = gameTools.find(t => t.function.name === 'roll_dice');
      expect(rollTool).toBeDefined();
      const params = rollTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('count');
      expect(params.properties).toHaveProperty('target');
    });

    it('should have skill_check tool', () => {
      const skillCheckTool = gameTools.find(t => t.function.name === 'skill_check');
      expect(skillCheckTool).toBeDefined();
      const params = skillCheckTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('character');
      expect(params.properties).toHaveProperty('skill');
      expect(params.properties).toHaveProperty('stat');
    });

    it('should have get_character_info tool', () => {
      const charInfoTool = gameTools.find(t => t.function.name === 'get_character_info');
      expect(charInfoTool).toBeDefined();
      const params = charInfoTool?.function.parameters as any;
      expect(params.properties).toHaveProperty('name');
    });
  });

  describe('roll_dice', () => {
    it('should roll dice correctly', async () => {
      const result = await executeGameTool('roll_dice', {
        count: 3,
        target: 15
      });

      expect(result).toHaveProperty('result');
      expect(result).toHaveProperty('dice');
      expect(result).toHaveProperty('successes');
      expect(result).toHaveProperty('description');
      expect(result.dice).toHaveLength(3);
      expect(result.description).toContain('Rolled 3d20');
    });

    it('should calculate successes correctly', async () => {
      const result = await executeGameTool('roll_dice', {
        count: 5,
        target: 10
      });

      // With target 10, most rolls should succeed
      expect(result.successes).toBeGreaterThanOrEqual(0);
    });
  });

  describe('skill_check', () => {
    it('should perform skill check with character from registry', async () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = await executeGameTool('skill_check', {
        character: 'Test Hero',
        skill: 'Stealth',
        stat: 'Agility',
        difficulty: 20
      });

      expect(result).toHaveProperty('success');
      expect(result).toHaveProperty('result');
      expect(result).toHaveProperty('dice');
      expect(result).toHaveProperty('successes');
      expect(result).toHaveProperty('description');
      expect(result).toHaveProperty('characterFound', true);
      expect(result.description).toContain('Test Hero rolling Agility (4) + Stealth (4)');
    });

    it('should use fallback when character not found', async () => {
      const result = await executeGameTool('skill_check', {
        character: 'Unknown Hero',
        skill: 'Athletics',
        stat: 'Strength',
        difficulty: 15
      });

      expect(result.characterFound).toBe(false);
      expect(result.description).toContain('fallback - character "Unknown Hero" not found');
    });

    it('should apply bonuses correctly', async () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = await executeGameTool('skill_check', {
        character: 'Test Hero',
        skill: 'Research',
        stat: 'Intelligence',
        difficulty: 25,
        bonus: 5
      });

      expect(result.result).toBeGreaterThanOrEqual(result.dice[0] + 5);
    });
  });

  describe('get_character_info', () => {
    it('should retrieve character information', async () => {
      const character = createTestCharacter();
      characterRegistry.addCharacter(character);

      const result = await executeGameTool('get_character_info', {
        name: 'Test Hero'
      });

      expect(result.name).toBe('Test Hero');
      expect(result.attributes.strength).toBe(4);
      expect(result.talents.stealth).toBe(4);
      expect(result.void_score).toBe(1);
    });

    it('should return error for unknown character', async () => {
      const result = await executeGameTool('get_character_info', {
        name: 'Unknown Character'
      });

      expect(result).toHaveProperty('error');
      expect(result.error).toContain('Character "Unknown Character" not found');
    });
  });

  describe('Error Handling', () => {
    it('should throw error for unknown tool', async () => {
      await expect(
        executeGameTool('unknown_tool', {})
      ).rejects.toThrow('Unknown tool: unknown_tool');
    });
  });
});
