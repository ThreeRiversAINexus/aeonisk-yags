import { Character } from '../../../src/domain/entities/Character';
import { CharacterSchema } from '../../../src/domain/schemas/character.schema';

describe('Character Entity', () => {
  describe('Creation', () => {
    it('should create a valid character with minimal data', () => {
      const characterData = {
        name: 'Test Character',
        concept: 'Test Concept',
        origin_faction: 'Freeborn',
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {
          Brawl: 2,
          Athletics: 1
        }
      };

      const character = new Character(characterData);
      
      expect(character.name).toBe('Test Character');
      expect(character.concept).toBe('Test Concept');
      expect(character.origin_faction).toBe('Freeborn');
      expect(character.health).toBe(10); // Size * 2 = 5 * 2 = 10
      expect(character.fatigue).toBe(11); // Size * 2 + Willpower - 2 = 10 + 3 - 2 = 11
      expect(character.voidScore).toBe(0);
      expect(character.soulcredit).toBe(5);
    });

    it('should validate character data using schema', () => {
      const invalidData = {
        name: '', // Invalid: empty name
        concept: 'Test',
        attributes: {} // Invalid: missing required attributes
      };

      expect(() => CharacterSchema.parse(invalidData)).toThrow();
    });

    it('should calculate derived stats correctly', () => {
      const character = new Character({
        name: 'Strong Character',
        concept: 'Warrior',
        attributes: {
          Size: 6,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 4,
          Charisma: 3
        },
        skills: {}
      });

      expect(character.health).toBe(12); // Size * 2
      expect(character.fatigue).toBe(14); // Size * 2 + Willpower - 2
    });
  });

  describe('Void and Soulcredit Management', () => {
    let character: Character;

    beforeEach(() => {
      character = new Character({
        name: 'Test Character',
        concept: 'Test',
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {}
      });
    });

    it('should modify void score within bounds', () => {
      character.modifyVoidScore(3);
      expect(character.voidScore).toBe(3);

      character.modifyVoidScore(8); // Would exceed max
      expect(character.voidScore).toBe(10); // Capped at 10

      character.modifyVoidScore(-15); // Would go below min
      expect(character.voidScore).toBe(0); // Floored at 0
    });

    it('should modify soulcredit within bounds', () => {
      character.modifySoulcredit(3);
      expect(character.soulcredit).toBe(8);

      character.modifySoulcredit(-20); // Would go below min
      expect(character.soulcredit).toBe(-10); // Floored at -10

      character.modifySoulcredit(25); // Would exceed max
      expect(character.soulcredit).toBe(10); // Capped at 10
    });

    it('should track void corruption events', () => {
      character.modifyVoidScore(5, 'Ritual backfire');
      
      const history = character.getVoidHistory();
      expect(history).toHaveLength(1);
      expect(history[0]).toMatchObject({
        change: 5,
        reason: 'Ritual backfire',
        newScore: 5
      });
    });
  });

  describe('Seed Management', () => {
    let character: Character;

    beforeEach(() => {
      character = new Character({
        name: 'Test Character',
        concept: 'Test',
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {}
      });
    });

    it('should add raw seeds', () => {
      character.addRawSeed('seed-1', 'Found in astral current');
      
      expect(character.raw_seeds).toHaveLength(1);
      expect(character.raw_seeds[0]).toMatchObject({
        id: 'seed-1',
        source: 'Found in astral current'
      });
    });

    it('should attune seeds to elements', () => {
      character.addRawSeed('seed-1', 'Test source');
      
      const result = character.attuneSeed('seed-1', 'fire');
      
      expect(result.success).toBe(true);
      expect(character.raw_seeds).toHaveLength(0);
      expect(character.attuned_seeds['fire']).toBe(1);
    });

    it('should fail to attune non-existent seed', () => {
      const result = character.attuneSeed('non-existent', 'fire');
      
      expect(result.success).toBe(false);
      expect(result.error).toContain('not found');
    });
  });

  describe('Serialization', () => {
    it('should serialize to JSON', () => {
      const character = new Character({
        name: 'Test Character',
        concept: 'Test',
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {}
      });

      const json = character.toJSON();
      
      expect(json).toHaveProperty('id');
      expect(json).toHaveProperty('name', 'Test Character');
      expect(json).toHaveProperty('attributes');
      expect(json).toHaveProperty('skills');
    });

    it('should create from JSON', () => {
      const json = {
        id: 'test-id',
        name: 'Test Character',
        concept: 'Test',
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {},
        voidScore: 3,
        soulcredit: 7,
        raw_seeds: [],
        attuned_seeds: {},
        advantages: [],
        disadvantages: [],
        bonds: []
      };

      const character = Character.fromJSON(json);
      
      expect(character.id).toBe('test-id');
      expect(character.name).toBe('Test Character');
      expect(character.voidScore).toBe(3);
      expect(character.soulcredit).toBe(7);
    });
  });
});