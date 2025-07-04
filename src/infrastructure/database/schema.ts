import { pgTable, text, timestamp, jsonb, boolean, uuid, integer } from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

// Users table for authentication
export const users = pgTable('users', {
  id: uuid('id').primaryKey().defaultRandom(),
  email: text('email').notNull().unique(),
  passwordHash: text('password_hash').notNull(),
  username: text('username').notNull().unique(),
  isActive: boolean('is_active').default(true),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow()
});

// Characters table
export const characters = pgTable('characters', {
  id: uuid('id').primaryKey().defaultRandom(),
  userId: uuid('user_id').references(() => users.id).notNull(),
  name: text('name').notNull(),
  concept: text('concept').notNull(),
  originFaction: text('origin_faction'),
  attributes: jsonb('attributes').notNull(),
  skills: jsonb('skills').notNull(),
  health: integer('health').notNull(),
  fatigue: integer('fatigue').notNull(),
  voidScore: integer('void_score').notNull().default(0),
  soulcredit: integer('soulcredit').notNull().default(5),
  rawSeeds: jsonb('raw_seeds').default([]),
  attunedSeeds: jsonb('attuned_seeds').default({}),
  advantages: jsonb('advantages').default([]),
  disadvantages: jsonb('disadvantages').default([]),
  bonds: jsonb('bonds').default([]),
  notes: text('notes'),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow()
});

// Game Sessions table
export const gameSessions = pgTable('game_sessions', {
  id: uuid('id').primaryKey().defaultRandom(),
  ownerId: uuid('owner_id').references(() => users.id).notNull(),
  name: text('name').notNull(),
  description: text('description'),
  isActive: boolean('is_active').default(true),
  currentPhase: text('current_phase').default('setup'),
  metadata: jsonb('metadata'),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow(),
  endedAt: timestamp('ended_at')
});

// Session Characters (many-to-many relationship)
export const sessionCharacters = pgTable('session_characters', {
  id: uuid('id').primaryKey().defaultRandom(),
  sessionId: uuid('session_id').references(() => gameSessions.id).notNull(),
  characterId: uuid('character_id').references(() => characters.id).notNull(),
  joinedAt: timestamp('joined_at').defaultNow()
});

// NPCs table
export const npcs = pgTable('npcs', {
  id: uuid('id').primaryKey().defaultRandom(),
  sessionId: uuid('session_id').references(() => gameSessions.id).notNull(),
  name: text('name').notNull(),
  faction: text('faction'),
  role: text('role'),
  description: text('description'),
  stats: jsonb('stats'),
  personality: jsonb('personality'),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow()
});

// Actions table
export const actions = pgTable('actions', {
  id: uuid('id').primaryKey().defaultRandom(),
  sessionId: uuid('session_id').references(() => gameSessions.id).notNull(),
  characterId: uuid('character_id').references(() => characters.id).notNull(),
  actionType: text('action_type').notNull(),
  description: text('description').notNull(),
  result: jsonb('result'),
  metadata: jsonb('metadata'),
  timestamp: timestamp('timestamp').defaultNow()
});

// Void History table
export const voidHistory = pgTable('void_history', {
  id: uuid('id').primaryKey().defaultRandom(),
  characterId: uuid('character_id').references(() => characters.id).notNull(),
  change: integer('change').notNull(),
  reason: text('reason'),
  newScore: integer('new_score').notNull(),
  timestamp: timestamp('timestamp').defaultNow()
});

// Relations
export const usersRelations = relations(users, ({ many }) => ({
  characters: many(characters),
  gameSessions: many(gameSessions)
}));

export const charactersRelations = relations(characters, ({ one, many }) => ({
  user: one(users, {
    fields: [characters.userId],
    references: [users.id]
  }),
  sessions: many(sessionCharacters),
  actions: many(actions),
  voidHistory: many(voidHistory)
}));

export const gameSessionsRelations = relations(gameSessions, ({ one, many }) => ({
  owner: one(users, {
    fields: [gameSessions.ownerId],
    references: [users.id]
  }),
  characters: many(sessionCharacters),
  npcs: many(npcs),
  actions: many(actions)
}));

export const sessionCharactersRelations = relations(sessionCharacters, ({ one }) => ({
  session: one(gameSessions, {
    fields: [sessionCharacters.sessionId],
    references: [gameSessions.id]
  }),
  character: one(characters, {
    fields: [sessionCharacters.characterId],
    references: [characters.id]
  })
}));

export const npcsRelations = relations(npcs, ({ one }) => ({
  session: one(gameSessions, {
    fields: [npcs.sessionId],
    references: [gameSessions.id]
  })
}));

export const actionsRelations = relations(actions, ({ one }) => ({
  session: one(gameSessions, {
    fields: [actions.sessionId],
    references: [gameSessions.id]
  }),
  character: one(characters, {
    fields: [actions.characterId],
    references: [characters.id]
  })
}));

export const voidHistoryRelations = relations(voidHistory, ({ one }) => ({
  character: one(characters, {
    fields: [voidHistory.characterId],
    references: [characters.id]
  })
}));