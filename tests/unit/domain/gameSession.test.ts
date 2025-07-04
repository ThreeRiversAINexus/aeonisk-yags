import { GameSession } from '../../../src/domain/entities/GameSession';
import { Character } from '../../../src/domain/entities/Character';
import { GameSessionSchema } from '../../../src/domain/schemas/gameSession.schema';

describe('GameSession Entity', () => {
  let testCharacter: Character;

  beforeEach(() => {
    testCharacter = new Character({
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
  });

  describe('Creation', () => {
    it('should create a valid game session', () => {
      const session = new GameSession({
        name: 'Test Campaign',
        description: 'A test campaign for unit testing'
      });

      expect(session.name).toBe('Test Campaign');
      expect(session.description).toBe('A test campaign for unit testing');
      expect(session.characters).toEqual([]);
      expect(session.npcs).toEqual([]);
      expect(session.isActive).toBe(true);
      expect(session.currentPhase).toBe('setup');
    });

    it('should validate session data using schema', () => {
      const invalidData = {
        name: '', // Invalid: empty name
        description: 'Test'
      };

      expect(() => GameSessionSchema.parse(invalidData)).toThrow();
    });
  });

  describe('Character Management', () => {
    let session: GameSession;

    beforeEach(() => {
      session = new GameSession({
        name: 'Test Campaign',
        description: 'Test'
      });
    });

    it('should add characters to the session', () => {
      session.addCharacter(testCharacter);

      expect(session.characters).toHaveLength(1);
      expect(session.characters[0]).toBe(testCharacter);
    });

    it('should remove characters from the session', () => {
      session.addCharacter(testCharacter);
      const removed = session.removeCharacter(testCharacter.id);

      expect(removed).toBe(true);
      expect(session.characters).toHaveLength(0);
    });

    it('should not add duplicate characters', () => {
      session.addCharacter(testCharacter);
      session.addCharacter(testCharacter);

      expect(session.characters).toHaveLength(1);
    });

    it('should get character by id', () => {
      session.addCharacter(testCharacter);
      const found = session.getCharacterById(testCharacter.id);

      expect(found).toBe(testCharacter);
    });
  });

  describe('Action Recording', () => {
    let session: GameSession;

    beforeEach(() => {
      session = new GameSession({
        name: 'Test Campaign',
        description: 'Test'
      });
      session.addCharacter(testCharacter);
    });

    it('should record player actions', () => {
      const action = session.recordAction({
        characterId: testCharacter.id,
        actionType: 'skill_check',
        description: 'Athletics check to climb wall',
        result: {
          success: true,
          margin: 3,
          details: 'Successfully climbed the wall'
        }
      });

      expect(session.actions).toHaveLength(1);
      expect(action.characterId).toBe(testCharacter.id);
      expect(action.actionType).toBe('skill_check');
      expect(action.result?.['success']).toBe(true);
    });

    it('should record ritual casting', () => {
      const action = session.recordAction({
        characterId: testCharacter.id,
        actionType: 'ritual',
        description: 'Cast Void Channeling',
        result: {
          success: true,
          voidGained: 2,
          soulcreditCost: 1
        }
      });

      expect(action.actionType).toBe('ritual');
      expect(action.result?.['voidGained']).toBe(2);
    });

    it('should maintain action history order', () => {
      session.recordAction({
        characterId: testCharacter.id,
        actionType: 'move',
        description: 'Move to the altar'
      });

      session.recordAction({
        characterId: testCharacter.id,
        actionType: 'interact',
        description: 'Examine the altar'
      });

      expect(session.actions).toHaveLength(2);
      expect(session.actions[0]?.description).toContain('Move');
      expect(session.actions[1]?.description).toContain('Examine');
    });
  });

  describe('Session State Management', () => {
    let session: GameSession;

    beforeEach(() => {
      session = new GameSession({
        name: 'Test Campaign',
        description: 'Test'
      });
    });

    it('should transition between phases', () => {
      expect(session.currentPhase).toBe('setup');

      session.transitionToPhase('active');
      expect(session.currentPhase).toBe('active');

      session.transitionToPhase('resolution');
      expect(session.currentPhase).toBe('resolution');
    });

    it('should end session', () => {
      session.endSession();

      expect(session.isActive).toBe(false);
      expect(session.endedAt).toBeDefined();
    });

    it('should calculate session duration', () => {
      // Mock the creation time to be 1 hour ago
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      session.createdAt = oneHourAgo;
      
      session.endSession();
      const duration = session.getDurationMinutes();

      expect(duration).toBeCloseTo(60, 0);
    });
  });

  describe('NPC Management', () => {
    let session: GameSession;

    beforeEach(() => {
      session = new GameSession({
        name: 'Test Campaign',
        description: 'Test'
      });
    });

    it('should add NPCs to the session', () => {
      const npc = session.addNPC({
        name: 'Guard Captain',
        faction: 'Sovereign Nexus',
        role: 'Authority Figure',
        description: 'A stern guard captain'
      });

      expect(session.npcs).toHaveLength(1);
      expect(npc.name).toBe('Guard Captain');
      expect(npc.faction).toBe('Sovereign Nexus');
    });

    it('should remove NPCs from the session', () => {
      const npc = session.addNPC({
        name: 'Merchant',
        faction: 'Astral Commerce Group',
        role: 'Trader'
      });

      const removed = session.removeNPC(npc.id);

      expect(removed).toBe(true);
      expect(session.npcs).toHaveLength(0);
    });
  });

  describe('Serialization', () => {
    it('should serialize to JSON', () => {
      const session = new GameSession({
        name: 'Test Campaign',
        description: 'Test campaign for serialization'
      });

      session.addCharacter(testCharacter);

      const json = session.toJSON();

      expect(json).toHaveProperty('id');
      expect(json).toHaveProperty('name', 'Test Campaign');
      expect(json).toHaveProperty('characters');
      expect(json.characters).toHaveLength(1);
    });

    it('should create from JSON', () => {
      const json = {
        id: 'test-session-id',
        name: 'Restored Campaign',
        description: 'A restored campaign',
        characters: [testCharacter.toJSON()],
        npcs: [],
        actions: [],
        isActive: true,
        currentPhase: 'active' as const,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };

      const session = GameSession.fromJSON(json);

      expect(session.id).toBe('test-session-id');
      expect(session.name).toBe('Restored Campaign');
      expect(session.characters).toHaveLength(1);
      expect(session.characters[0]?.name).toBe('Test Character');
    });
  });
});