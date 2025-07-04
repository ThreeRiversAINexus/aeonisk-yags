import { CharacterRepository } from '../../../src/infrastructure/repositories/CharacterRepository';
import { Character } from '../../../src/domain/entities/Character';
import { db } from '../../../src/infrastructure/database';

// Mock the database
jest.mock('../../../src/infrastructure/database');

describe('CharacterRepository', () => {
  let repository: CharacterRepository;
  let testUserId: string;

  beforeEach(() => {
    repository = new CharacterRepository(db);
    testUserId = 'test-user-id';
    jest.clearAllMocks();
  });

  describe('save', () => {
    it('should save a new character', async () => {
      const character = new Character({
        name: 'Test Character',
        concept: 'Test Concept',
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

      const mockDbResponse = [{
        id: character.id,
        userId: testUserId,
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
        updatedAt: character.updatedAt
      }];

      // Mock the db.select for existence check
      (db.select as jest.Mock).mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockResolvedValue([])
        })
      });

      (db.insert as jest.Mock).mockReturnValue({
        values: jest.fn().mockReturnValue({
          returning: jest.fn().mockResolvedValue(mockDbResponse)
        })
      });

      const saved = await repository.save(character, testUserId);

      expect(saved.id).toBe(character.id);
      expect(saved.name).toBe('Test Character');
      expect(db.insert).toHaveBeenCalled();
    });

    it('should update an existing character', async () => {
      const character = new Character({
        id: 'existing-character-id',
        name: 'Updated Character',
        concept: 'Updated Concept',
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

      const mockDbResponse = [{
        id: character.id,
        userId: testUserId,
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
        updatedAt: character.updatedAt
      }];

      // Mock the exists check
      (db.select as jest.Mock).mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockResolvedValue([{ id: character.id }])
        })
      });

      // Mock the update
      (db.update as jest.Mock).mockReturnValue({
        set: jest.fn().mockReturnValue({
          where: jest.fn().mockReturnValue({
            returning: jest.fn().mockResolvedValue(mockDbResponse)
          })
        })
      });

      const saved = await repository.save(character, testUserId);

      expect(saved.id).toBe(character.id);
      expect(saved.name).toBe('Updated Character');
      expect(db.update).toHaveBeenCalled();
    });
  });

  describe('findById', () => {
    it('should find a character by id', async () => {
      const mockDbResponse = [{
        id: 'test-id',
        userId: testUserId,
        name: 'Found Character',
        concept: 'Test Concept',
        originFaction: null,
        attributes: {
          Size: 5,
          Dexterity: 3,
          Perception: 3,
          Intelligence: 3,
          Willpower: 3,
          Charisma: 3
        },
        skills: {},
        health: 10,
        fatigue: 11,
        voidScore: 0,
        soulcredit: 5,
        rawSeeds: [],
        attunedSeeds: {},
        advantages: [],
        disadvantages: [],
        bonds: [],
        notes: null,
        createdAt: new Date(),
        updatedAt: new Date()
      }];

      (db.select as jest.Mock).mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockResolvedValue(mockDbResponse)
        })
      });

      const character = await repository.findById('test-id');

      expect(character).toBeDefined();
      expect(character?.name).toBe('Found Character');
    });

    it('should return null when character not found', async () => {
      (db.select as jest.Mock).mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockResolvedValue([])
        })
      });

      const character = await repository.findById('non-existent-id');

      expect(character).toBeNull();
    });
  });

  describe('findByUserId', () => {
    it('should find all characters for a user', async () => {
      const mockDbResponse = [
        {
          id: 'char-1',
          userId: testUserId,
          name: 'Character 1',
          concept: 'Concept 1',
          originFaction: null,
          attributes: {
            Size: 5,
            Dexterity: 3,
            Perception: 3,
            Intelligence: 3,
            Willpower: 3,
            Charisma: 3
          },
          skills: {},
          health: 10,
          fatigue: 11,
          voidScore: 0,
          soulcredit: 5,
          rawSeeds: [],
          attunedSeeds: {},
          advantages: [],
          disadvantages: [],
          bonds: [],
          notes: null,
          createdAt: new Date(),
          updatedAt: new Date()
        },
        {
          id: 'char-2',
          userId: testUserId,
          name: 'Character 2',
          concept: 'Concept 2',
          originFaction: 'Freeborn',
          attributes: {
            Size: 5,
            Dexterity: 3,
            Perception: 3,
            Intelligence: 3,
            Willpower: 3,
            Charisma: 3
          },
          skills: {},
          health: 10,
          fatigue: 11,
          voidScore: 0,
          soulcredit: 5,
          rawSeeds: [],
          attunedSeeds: {},
          advantages: [],
          disadvantages: [],
          bonds: [],
          notes: null,
          createdAt: new Date(),
          updatedAt: new Date()
        }
      ];

      (db.select as jest.Mock).mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockResolvedValue(mockDbResponse)
        })
      });

      const characters = await repository.findByUserId(testUserId);

      expect(characters).toHaveLength(2);
      expect(characters[0]?.name).toBe('Character 1');
      expect(characters[1]?.name).toBe('Character 2');
    });
  });

  describe('delete', () => {
    it('should delete a character', async () => {
      (db.delete as jest.Mock).mockReturnValue({
        where: jest.fn().mockResolvedValue({ rowCount: 1 })
      });

      const result = await repository.delete('test-id');

      expect(result).toBe(true);
      expect(db.delete).toHaveBeenCalled();
    });

    it('should return false when character not found', async () => {
      (db.delete as jest.Mock).mockReturnValue({
        where: jest.fn().mockResolvedValue({ rowCount: 0 })
      });

      const result = await repository.delete('non-existent-id');

      expect(result).toBe(false);
    });
  });
});