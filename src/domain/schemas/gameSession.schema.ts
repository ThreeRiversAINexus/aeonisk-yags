import { z } from 'zod';
import { CharacterSchema } from './character.schema';

// NPC Schema
export const NPCSchema = z.object({
  id: z.string(),
  name: z.string().min(1),
  faction: z.string().optional(),
  role: z.string().optional(),
  description: z.string().optional(),
  stats: z.record(z.string(), z.number()).optional(),
  personality: z.object({
    traits: z.array(z.string()).default([]),
    goals: z.array(z.string()).default([]),
    bonds: z.array(z.string()).default([])
  }).optional()
});

// Action Schema
export const ActionSchema = z.object({
  id: z.string(),
  characterId: z.string(),
  actionType: z.enum(['move', 'skill_check', 'ritual', 'combat', 'interact', 'dialogue', 'other']),
  description: z.string(),
  result: z.record(z.string(), z.any()).optional(),
  timestamp: z.date(),
  metadata: z.record(z.string(), z.any()).optional()
});

// Session Phase
export const SessionPhaseSchema = z.enum(['setup', 'active', 'resolution', 'completed']);

// Game Session Schema
export const GameSessionSchema = z.object({
  id: z.string().optional(),
  name: z.string().min(1),
  description: z.string().optional(),
  characters: z.array(CharacterSchema).default([]),
  npcs: z.array(NPCSchema).default([]),
  actions: z.array(ActionSchema).default([]),
  isActive: z.boolean().default(true),
  currentPhase: SessionPhaseSchema.default('setup'),
  metadata: z.record(z.string(), z.any()).optional(),
  createdAt: z.date().optional(),
  updatedAt: z.date().optional(),
  endedAt: z.date().optional()
});

export type GameSessionData = z.infer<typeof GameSessionSchema>;
export type NPCData = z.infer<typeof NPCSchema>;
export type ActionData = z.infer<typeof ActionSchema>;
export type SessionPhase = z.infer<typeof SessionPhaseSchema>;