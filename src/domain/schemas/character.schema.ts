import { z } from 'zod';

// Attribute schema
export const AttributesSchema = z.object({
  Size: z.number().min(1).max(10),
  Dexterity: z.number().min(1).max(10),
  Perception: z.number().min(1).max(10),
  Intelligence: z.number().min(1).max(10),
  Willpower: z.number().min(1).max(10),
  Charisma: z.number().min(1).max(10)
});

// Skills schema - dynamic record of skill names to values
export const SkillsSchema = z.record(z.string(), z.number().min(0).max(10));

// Seed schemas
export const RawSeedSchema = z.object({
  id: z.string(),
  source: z.string(),
  acquiredAt: z.date()
});

export const AttunedSeedsSchema = z.record(z.string(), z.number().min(0));

// Advantage/Disadvantage schemas
export const AdvantageSchema = z.object({
  name: z.string(),
  description: z.string(),
  cost: z.number()
});

export const DisadvantageSchema = z.object({
  name: z.string(),
  description: z.string(),
  value: z.number()
});

// Bond schema
export const BondSchema = z.object({
  targetId: z.string(),
  targetName: z.string(),
  strength: z.number().min(0).max(10),
  type: z.enum(['trust', 'love', 'rivalry', 'fear', 'respect']),
  description: z.string().optional()
});

// Main Character schema
export const CharacterSchema = z.object({
  id: z.string().optional(),
  name: z.string().min(1),
  concept: z.string().min(1),
  origin_faction: z.string().optional(),
  attributes: AttributesSchema,
  skills: SkillsSchema,
  health: z.number().optional(),
  fatigue: z.number().optional(),
  voidScore: z.number().min(0).max(10).default(0),
  soulcredit: z.number().min(-10).max(10).default(5),
  raw_seeds: z.array(RawSeedSchema).default([]),
  attuned_seeds: AttunedSeedsSchema.default({}),
  advantages: z.array(AdvantageSchema).default([]),
  disadvantages: z.array(DisadvantageSchema).default([]),
  bonds: z.array(BondSchema).default([]),
  notes: z.string().optional(),
  createdAt: z.date().optional(),
  updatedAt: z.date().optional()
});

export type CharacterData = z.infer<typeof CharacterSchema>;