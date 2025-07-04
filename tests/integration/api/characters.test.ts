import request from 'supertest';
import { app } from '../../../src/app';
import { db } from '../../../src/infrastructure/database';
import { users, characters } from '../../../src/infrastructure/database/schema';
import { eq } from 'drizzle-orm';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';

describe('Character API Endpoints', () => {
  let authToken: string;
  let userId: string;

  beforeAll(async () => {
    // Create test user
    const hashedPassword = await bcrypt.hash('testpassword', 10);
    const [user] = await db.insert(users).values({
      email: 'test@example.com',
      username: 'testuser',
      passwordHash: hashedPassword
    }).returning();
    
    userId = user.id;
    authToken = jwt.sign({ userId: user.id }, process.env['JWT_SECRET'] || 'test-secret');
  });

  afterAll(async () => {
    // Clean up test data
    await db.delete(characters).where(eq(characters.userId, userId));
    await db.delete(users).where(eq(users.id, userId));
  });

  describe('POST /api/characters', () => {
    it('should create a new character', async () => {
      const characterData = {
        name: 'Test Hero',
        concept: 'Brave Adventurer',
        origin_faction: 'Freeborn',
        attributes: {
          Size: 5,
          Dexterity: 4,
          Perception: 3,
          Intelligence: 3,
          Willpower: 4,
          Charisma: 3
        },
        skills: {
          Brawl: 3,
          Athletics: 2,
          Stealth: 1
        }
      };

      const response = await request(app)
        .post('/api/characters')
        .set('Authorization', `Bearer ${authToken}`)
        .send(characterData)
        .expect(201);

      expect(response.body).toHaveProperty('id');
      expect(response.body.name).toBe('Test Hero');
      expect(response.body.concept).toBe('Brave Adventurer');
      expect(response.body.health).toBe(10);
      expect(response.body.fatigue).toBe(12);
    });

    it('should reject invalid character data', async () => {
      const invalidData = {
        name: '', // Invalid: empty name
        concept: 'Test',
        attributes: {} // Invalid: missing attributes
      };

      await request(app)
        .post('/api/characters')
        .set('Authorization', `Bearer ${authToken}`)
        .send(invalidData)
        .expect(400);
    });

    it('should require authentication', async () => {
      const characterData = {
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
      };

      await request(app)
        .post('/api/characters')
        .send(characterData)
        .expect(401);
    });
  });

  describe('GET /api/characters', () => {
    let characterId: string;

    beforeEach(async () => {
      // Create a test character
      const [character] = await db.insert(characters).values({
        userId,
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
        skills: {},
        health: 10,
        fatigue: 11,
        voidScore: 0,
        soulcredit: 5
      }).returning();
      
      characterId = character.id;
    });

    afterEach(async () => {
      await db.delete(characters).where(eq(characters.id, characterId));
    });

    it('should list all characters for authenticated user', async () => {
      const response = await request(app)
        .get('/api/characters')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(200);

      expect(Array.isArray(response.body)).toBe(true);
      expect(response.body.length).toBeGreaterThan(0);
      expect(response.body[0].name).toBe('Test Character');
    });

    it('should not return characters for other users', async () => {
      // Create another user
      const [otherUser] = await db.insert(users).values({
        email: 'other@example.com',
        username: 'otheruser',
        passwordHash: 'hashedpassword'
      }).returning();

      const otherToken = jwt.sign({ userId: otherUser.id }, process.env['JWT_SECRET'] || 'test-secret');

      const response = await request(app)
        .get('/api/characters')
        .set('Authorization', `Bearer ${otherToken}`)
        .expect(200);

      expect(response.body).toHaveLength(0);

      // Clean up
      await db.delete(users).where(eq(users.id, otherUser.id));
    });
  });

  describe('GET /api/characters/:id', () => {
    let characterId: string;

    beforeEach(async () => {
      const [character] = await db.insert(characters).values({
        userId,
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
        skills: {},
        health: 10,
        fatigue: 11,
        voidScore: 0,
        soulcredit: 5
      }).returning();
      
      characterId = character.id;
    });

    afterEach(async () => {
      await db.delete(characters).where(eq(characters.id, characterId));
    });

    it('should get a specific character', async () => {
      const response = await request(app)
        .get(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .expect(200);

      expect(response.body.id).toBe(characterId);
      expect(response.body.name).toBe('Test Character');
    });

    it('should return 404 for non-existent character', async () => {
      await request(app)
        .get('/api/characters/non-existent-id')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(404);
    });

    it('should not allow access to other users characters', async () => {
      const [otherUser] = await db.insert(users).values({
        email: 'other2@example.com',
        username: 'otheruser2',
        passwordHash: 'hashedpassword'
      }).returning();

      const otherToken = jwt.sign({ userId: otherUser.id }, process.env['JWT_SECRET'] || 'test-secret');

      await request(app)
        .get(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${otherToken}`)
        .expect(403);

      // Clean up
      await db.delete(users).where(eq(users.id, otherUser.id));
    });
  });

  describe('PUT /api/characters/:id', () => {
    let characterId: string;

    beforeEach(async () => {
      const [character] = await db.insert(characters).values({
        userId,
        name: 'Original Name',
        concept: 'Original Concept',
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
        soulcredit: 5
      }).returning();
      
      characterId = character.id;
    });

    afterEach(async () => {
      await db.delete(characters).where(eq(characters.id, characterId));
    });

    it('should update a character', async () => {
      const updateData = {
        name: 'Updated Name',
        concept: 'Updated Concept',
        skills: {
          Brawl: 4,
          Athletics: 3
        }
      };

      const response = await request(app)
        .put(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send(updateData)
        .expect(200);

      expect(response.body.name).toBe('Updated Name');
      expect(response.body.concept).toBe('Updated Concept');
      expect(response.body.skills.Brawl).toBe(4);
    });

    it('should not allow updating other users characters', async () => {
      const [otherUser] = await db.insert(users).values({
        email: 'other3@example.com',
        username: 'otheruser3',
        passwordHash: 'hashedpassword'
      }).returning();

      const otherToken = jwt.sign({ userId: otherUser.id }, process.env['JWT_SECRET'] || 'test-secret');

      await request(app)
        .put(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${otherToken}`)
        .send({ name: 'Hacked Name' })
        .expect(403);

      // Clean up
      await db.delete(users).where(eq(users.id, otherUser.id));
    });
  });

  describe('DELETE /api/characters/:id', () => {
    let characterId: string;

    beforeEach(async () => {
      const [character] = await db.insert(characters).values({
        userId,
        name: 'To Delete',
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
        health: 10,
        fatigue: 11,
        voidScore: 0,
        soulcredit: 5
      }).returning();
      
      characterId = character.id;
    });

    it('should delete a character', async () => {
      await request(app)
        .delete(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${authToken}`)
        .expect(204);

      // Verify deletion
      const result = await db.select()
        .from(characters)
        .where(eq(characters.id, characterId));
      
      expect(result).toHaveLength(0);
    });

    it('should not allow deleting other users characters', async () => {
      const [otherUser] = await db.insert(users).values({
        email: 'other4@example.com',
        username: 'otheruser4',
        passwordHash: 'hashedpassword'
      }).returning();

      const otherToken = jwt.sign({ userId: otherUser.id }, process.env['JWT_SECRET'] || 'test-secret');

      await request(app)
        .delete(`/api/characters/${characterId}`)
        .set('Authorization', `Bearer ${otherToken}`)
        .expect(403);

      // Verify character still exists
      const result = await db.select()
        .from(characters)
        .where(eq(characters.id, characterId));
      
      expect(result).toHaveLength(1);

      // Clean up
      await db.delete(characters).where(eq(characters.id, characterId));
      await db.delete(users).where(eq(users.id, otherUser.id));
    });
  });
});