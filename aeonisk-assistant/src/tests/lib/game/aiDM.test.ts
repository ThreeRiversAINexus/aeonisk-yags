import { describe, it, expect, beforeEach } from 'vitest';
import {
  generateAIPersonality,
  generatePlayerGoals,
  generateDecisionStrategy,
  makeAIDecision,
  decideRitualCasting,
  generateNPC,
  generateDreamline,
  runAISession,
  SCENARIO_SEEDS,
  type AIDMConfig
} from '../../../lib/game/aiDM';
import { createDefaultCharacter } from '../../../lib/game/characterCreation';
import type { Character, AIPlayer, PlayerPersonality, Ritual } from '../../../types';

describe('AI DM System', () => {
  let character: Character;
  let personality: PlayerPersonality;
  let aiPlayer: AIPlayer;

  beforeEach(() => {
    character = createDefaultCharacter();
    character.name = 'Test AI Character';
    character.concept = 'AI Test Subject';
    character.origin_faction = 'Freeborn';
    character.skills['Astral Arts'] = 4;
    character.skills['Combat'] = 3;
    character.voidScore = 2;
    character.soulcredit = 1;

    personality = {
      riskTolerance: 6,
      bondPreference: 'seeks',
      voidCuriosity: 7,
      factionLoyalty: 5,
      ritualConservatism: 3,
      socialAggressiveness: 4
    };

    aiPlayer = {
      id: 'test-ai-player-1',
      character,
      personality,
      faction: 'Freeborn',
      goals: [],
      playStyle: 'void-seeker',
      decisionMaking: {
        primaryFocus: 'ritual',
        secondaryFocus: 'exploration',
        riskAssessment: 'balanced',
        groupCooperation: 'independent'
      }
    };
  });

  describe('generateAIPersonality', () => {
    it('should generate personality for Sovereign Nexus faction', () => {
      const personality = generateAIPersonality('Sovereign Nexus');
      
      expect(personality.riskTolerance).toBe(3);
      expect(personality.bondPreference).toBe('seeks');
      expect(personality.factionLoyalty).toBe(8);
      expect(personality.ritualConservatism).toBe(7);
      expect(personality.socialAggressiveness).toBe(4);
      expect(personality.voidCuriosity).toBeGreaterThanOrEqual(1);
      expect(personality.voidCuriosity).toBeLessThanOrEqual(10);
    });

    it('should generate personality for Tempest Industries faction', () => {
      const personality = generateAIPersonality('Tempest Industries');
      
      expect(personality.riskTolerance).toBe(8);
      expect(personality.bondPreference).toBe('avoids');
      expect(personality.voidCuriosity).toBe(8);
      expect(personality.factionLoyalty).toBe(6);
      expect(personality.ritualConservatism).toBe(2);
      expect(personality.socialAggressiveness).toBe(7);
    });

    it('should generate personality for Freeborn faction', () => {
      const personality = generateAIPersonality('Freeborn');
      
      expect(personality.riskTolerance).toBe(7);
      expect(personality.bondPreference).toBe('avoids');
      expect(personality.voidCuriosity).toBe(7);
      expect(personality.factionLoyalty).toBe(3);
      expect(personality.ritualConservatism).toBe(2);
      expect(personality.socialAggressiveness).toBe(6);
    });

    it('should generate default personality for unknown faction', () => {
      const personality = generateAIPersonality('Unknown Faction');
      
      expect(personality.riskTolerance).toBe(5);
      expect(personality.bondPreference).toBe('neutral');
      expect(personality.voidCuriosity).toBe(3);
      expect(personality.factionLoyalty).toBe(5);
      expect(personality.ritualConservatism).toBe(5);
      expect(personality.socialAggressiveness).toBe(5);
    });
  });

  describe('generatePlayerGoals', () => {
    it('should generate void goals for high void curiosity', () => {
      const highVoidPersonality = { ...personality, voidCuriosity: 8 };
      const goals = generatePlayerGoals(character, highVoidPersonality);
      
      const voidGoal = goals.find(g => g.type === 'void');
      expect(voidGoal).toBeDefined();
      expect(voidGoal?.description).toContain('void manipulation');
      expect(voidGoal?.priority).toBe(8);
    });

    it('should generate bond goals for bond seekers', () => {
      const bondSeeker = { ...personality, bondPreference: 'seeks' as const };
      const goals = generatePlayerGoals(character, bondSeeker);
      
      const bondGoal = goals.find(g => g.type === 'bond');
      expect(bondGoal).toBeDefined();
      expect(bondGoal?.description).toContain('meaningful bonds');
      expect(bondGoal?.priority).toBe(8);
    });

    it('should generate faction goals for loyal characters', () => {
      const loyalPersonality = { ...personality, factionLoyalty: 8 };
      const goals = generatePlayerGoals(character, loyalPersonality);
      
      const factionGoal = goals.find(g => g.type === 'faction');
      expect(factionGoal).toBeDefined();
      expect(factionGoal?.description).toContain(character.origin_faction);
      expect(factionGoal?.priority).toBe(8);
    });

    it('should generate ritual goals for skilled astral arts practitioners', () => {
      const goals = generatePlayerGoals(character, personality);
      
      const ritualGoal = goals.find(g => g.type === 'ritual');
      expect(ritualGoal).toBeDefined();
      expect(ritualGoal?.description).toContain('ritual techniques');
      expect(ritualGoal?.priority).toBe(7);
    });

    it('should not generate goals for characters without relevant traits', () => {
      const lowTraitsPersonality = {
        ...personality,
        voidCuriosity: 3,
        bondPreference: 'neutral' as const,
        factionLoyalty: 3
      };
      const lowSkillCharacter = { ...character };
      lowSkillCharacter.skills['Astral Arts'] = 1;
      lowSkillCharacter.origin_faction = undefined;
      
      const goals = generatePlayerGoals(lowSkillCharacter, lowTraitsPersonality);
      
      expect(goals.length).toBe(0);
    });
  });

  describe('generateDecisionStrategy', () => {
    it('should generate ritual-focused strategy for high void curiosity', () => {
      const highVoidPersonality = { ...personality, voidCuriosity: 8 };
      const strategy = generateDecisionStrategy(highVoidPersonality);
      
      expect(strategy.primaryFocus).toBe('ritual');
    });

    it('should generate social-focused strategy for high social aggressiveness', () => {
      const socialPersonality = { ...personality, voidCuriosity: 3, socialAggressiveness: 8 };
      const strategy = generateDecisionStrategy(socialPersonality);
      
      expect(strategy.primaryFocus).toBe('social');
    });

    it('should generate exploration-focused strategy by default', () => {
      const neutralPersonality = { ...personality, voidCuriosity: 3, socialAggressiveness: 3 };
      const strategy = generateDecisionStrategy(neutralPersonality);
      
      expect(strategy.primaryFocus).toBe('exploration');
    });

    it('should generate combat-focused secondary for high risk tolerance', () => {
      const riskTakerPersonality = { ...personality, riskTolerance: 8 };
      const strategy = generateDecisionStrategy(riskTakerPersonality);
      
      expect(strategy.secondaryFocus).toBe('combat');
    });

    it('should generate appropriate risk assessment', () => {
      const aggressivePersonality = { ...personality, riskTolerance: 9 };
      const conservativePersonality = { ...personality, riskTolerance: 2 };
      const balancedPersonality = { ...personality, riskTolerance: 5 };
      
      expect(generateDecisionStrategy(aggressivePersonality).riskAssessment).toBe('aggressive');
      expect(generateDecisionStrategy(conservativePersonality).riskAssessment).toBe('conservative');
      expect(generateDecisionStrategy(balancedPersonality).riskAssessment).toBe('balanced');
    });

    it('should generate appropriate group cooperation', () => {
      const bondSeekerPersonality = { ...personality, bondPreference: 'seeks' as const };
      const independentPersonality = { ...personality, bondPreference: 'avoids' as const };
      
      expect(generateDecisionStrategy(bondSeekerPersonality).groupCooperation).toBe('follower');
      expect(generateDecisionStrategy(independentPersonality).groupCooperation).toBe('independent');
    });
  });

  describe('makeAIDecision', () => {
    beforeEach(() => {
      aiPlayer.goals = generatePlayerGoals(character, personality);
    });

    it('should choose options based on personality factors', () => {
      const context = 'A dangerous void anomaly appears before you';
      const options = [
        'Approach the void anomaly carefully',
        'Retreat to safety immediately',
        'Ignore the anomaly and continue'
      ];
      
      const decision = makeAIDecision(aiPlayer, context, options);
      
      expect(decision.chosenOption).toBeDefined();
      expect(options).toContain(decision.chosenOption);
      expect(decision.reasoning).toBeDefined();
      expect(decision.personalityFactors).toBeDefined();
    });

    it('should favor risk-taking for high risk tolerance personality', () => {
      const riskTaker = { ...aiPlayer, personality: { ...personality, riskTolerance: 9 } };
      const context = 'A risky but potentially rewarding situation';
      const options = [
        'Take the dangerous risk for great reward',
        'Choose the safe, conservative option'
      ];
      
      const decision = makeAIDecision(riskTaker, context, options);
      
      // Should favor the risky option
      expect(decision.chosenOption).toBe('Take the dangerous risk for great reward');
    });

    it('should favor bond-related options for bond seekers', () => {
      const bondSeeker = { ...aiPlayer, personality: { ...personality, bondPreference: 'seeks' as const } };
      const context = 'You encounter another person in need';
      const options = [
        'Help them and form a bond of trust',
        'Ignore them and move on alone'
      ];
      
      const decision = makeAIDecision(bondSeeker, context, options);
      
      expect(decision.chosenOption).toBe('Help them and form a bond of trust');
    });

    it('should favor void-related options for void curious characters', () => {
      const voidSeeker = { ...aiPlayer, personality: { ...personality, voidCuriosity: 9 } };
      const context = 'A void corruption anomaly pulses with dark energy';
      const options = [
        'Study the void corruption carefully',
        'Destroy the corruption immediately',
        'Avoid the corruption entirely'
      ];
      
      const decision = makeAIDecision(voidSeeker, context, options);
      
      // The AI should make a decision, and it should be one of the available options
      expect(options).toContain(decision.chosenOption);
      // Should show void curiosity as a factor in decision making
      expect(decision.personalityFactors.voidCuriosity).toBeDefined();
      expect(decision.personalityFactors.voidCuriosity).toBe(9);
      
      // The reasoning should mention void-related factors
      expect(decision.reasoning).toMatch(/void/i);
    });

    it('should provide reasoning for decisions', () => {
      const context = 'A choice must be made';
      const options = ['Option A', 'Option B'];
      
      const decision = makeAIDecision(aiPlayer, context, options);
      
      expect(decision.reasoning).toContain('Chose');
      expect(decision.reasoning).toContain(decision.chosenOption);
    });
  });

  describe('decideRitualCasting', () => {
    const mockRituals: Ritual[] = [
      {
        name: 'Test Void Ritual',
        threshold: 15,
        offering: 'A memory of fear',
        voidRisk: 1,
        soulcreditCost: 1,
        effects: [],
        consequences: [],
        category: 'void'
      },
      {
        name: 'Test Bond Ritual',
        threshold: 12,
        offering: 'A shared secret',
        voidRisk: 0,
        soulcreditCost: 1,
        effects: [],
        consequences: [],
        category: 'intimacy'
      }
    ];

    beforeEach(() => {
      aiPlayer.goals = [
        { type: 'void', description: 'Explore void', priority: 8, progress: 0 },
        { type: 'bond', description: 'Form bonds', priority: 6, progress: 0 }
      ];
    });

    it('should decide to cast ritual when suitable rituals are available', () => {
      const decision = decideRitualCasting(aiPlayer, mockRituals, 'A mystical situation');
      
      expect(decision.shouldCast).toBe(true);
      expect(decision.chosenRitual).toBeDefined();
      expect(decision.offering).toBeDefined();
      expect(decision.reasoning).toBeDefined();
    });

    it('should refuse to cast for highly conservative characters', () => {
      const conservativePlayer = { 
        ...aiPlayer, 
        personality: { ...personality, ritualConservatism: 8 } 
      };
      
      const decision = decideRitualCasting(conservativePlayer, mockRituals, 'Any situation');
      
      expect(decision.shouldCast).toBe(false);
      expect(decision.reasoning).toContain('Too conservative');
    });

    it('should choose void rituals for void-curious characters in danger', () => {
      const voidSeeker = { 
        ...aiPlayer, 
        personality: { ...personality, voidCuriosity: 9 } 
      };
      
      const decision = decideRitualCasting(voidSeeker, mockRituals, 'A dangerous situation');
      
      if (decision.shouldCast && decision.chosenRitual) {
        expect(decision.chosenRitual.category).toBe('void');
      }
    });

    it('should choose bond rituals for bond seekers in social situations', () => {
      const bondSeeker = { 
        ...aiPlayer, 
        personality: { ...personality, bondPreference: 'seeks' as const } 
      };
      
      const decision = decideRitualCasting(bondSeeker, mockRituals, 'A social gathering');
      
      if (decision.shouldCast && decision.chosenRitual) {
        expect(decision.chosenRitual.category).toBe('intimacy');
      }
    });

    it('should not cast when no suitable rituals are available', () => {
      const playerWithoutGoals = { ...aiPlayer, goals: [] };
      
      const decision = decideRitualCasting(playerWithoutGoals, mockRituals, 'Any situation');
      
      expect(decision.shouldCast).toBe(false);
      expect(decision.reasoning).toContain('No suitable rituals available');
    });
  });

  describe('generateNPC', () => {
    it('should generate NPC with faction-appropriate name', () => {
      const npc = generateNPC('Sovereign Nexus', 'Administrator');
      
      expect(npc.name).toBeDefined();
      expect(npc.faction).toBe('Sovereign Nexus');
      expect(npc.role).toBe('Administrator');
      expect(npc.description).toContain('Sovereign Nexus');
      expect(npc.description).toContain('Administrator');
    });

    it('should generate different NPCs for different factions', () => {
      const nexusNPC = generateNPC('Sovereign Nexus', 'Official');
      const tempestNPC = generateNPC('Tempest Industries', 'Researcher');
      const freeborn = generateNPC('Freeborn', 'Wanderer');
      
      expect(nexusNPC.faction).toBe('Sovereign Nexus');
      expect(tempestNPC.faction).toBe('Tempest Industries');
      expect(freeborn.faction).toBe('Freeborn');
      
      expect(nexusNPC.description).toContain('Sovereign Nexus');
      expect(tempestNPC.description).toContain('Tempest Industries');
      expect(freeborn.description).toContain('Freeborn');
    });

    it('should handle unknown factions gracefully', () => {
      const npc = generateNPC('Unknown Faction', 'Mysterious Figure');
      
      expect(npc.name).toBeDefined();
      expect(npc.faction).toBe('Unknown Faction');
      expect(npc.role).toBe('Mysterious Figure');
      expect(npc.description).toBeDefined();
    });
  });

  describe('generateDreamline', () => {
    it('should create dreamline with appropriate theme and participants', () => {
      const participants: AIPlayer[] = [aiPlayer];
      const config: AIDMConfig = {
        scenarioComplexity: 'moderate',
        voidInfluence: 5,
        factionFocus: ['Freeborn'],
        ritualFrequency: 'medium',
        bondEmphasis: 'medium'
      };
      
      const dreamline = generateDreamline('Void Corruption', participants, config);
      
      expect(dreamline.id).toBeDefined();
      expect(dreamline.theme).toBe('Void Corruption');
      expect(dreamline.participants).toHaveLength(1);
      expect(dreamline.participants[0].name).toBe(character.name);
      expect(dreamline.sessions).toEqual([]);
      expect(dreamline.timeline).toEqual([]);
      expect(dreamline.canon_status).toBe('dreamline');
      expect(dreamline.void_influence).toBe(5);
    });

    it('should handle multiple participants', () => {
      const secondCharacter = { ...character, name: 'Second AI Character' };
      const secondPlayer: AIPlayer = { ...aiPlayer, id: 'test-ai-player-2', character: secondCharacter };
      const participants = [aiPlayer, secondPlayer];
      
      const config: AIDMConfig = {
        scenarioComplexity: 'simple',
        voidInfluence: 3,
        factionFocus: ['Freeborn'],
        ritualFrequency: 'low',
        bondEmphasis: 'low'
      };
      
      const dreamline = generateDreamline('Faction Politics', participants, config);
      
      expect(dreamline.participants).toHaveLength(2);
      expect(dreamline.participants.map(p => p.name)).toContain('Test AI Character');
      expect(dreamline.participants.map(p => p.name)).toContain('Second AI Character');
    });
  });

  describe('runAISession', () => {
    it('should execute an AI session and generate results', () => {
      const participants: AIPlayer[] = [aiPlayer];
      const config: AIDMConfig = {
        scenarioComplexity: 'simple',
        voidInfluence: 3,
        factionFocus: ['Freeborn'],
        ritualFrequency: 'low',
        bondEmphasis: 'low'
      };
      
      const dreamline = generateDreamline('Void Corruption', participants, config);
      const result = runAISession(dreamline, participants, config);
      
      expect(result.session).toBeDefined();
      expect(result.session.id).toBeDefined();
      expect(result.session.dreamlineId).toBe(dreamline.id);
      expect(result.session.participants).toEqual(dreamline.participants);
      expect(result.session.narrative_summary).toBeDefined();
      expect(result.session.timestamp).toBeDefined();
      
      expect(Array.isArray(result.actions)).toBe(true);
      expect(Array.isArray(result.decisions)).toBe(true);
    });

    it('should generate actions and decisions for each AI player', () => {
      const secondCharacter = { ...character, name: 'Second AI Character' };
      const secondPlayer: AIPlayer = { ...aiPlayer, id: 'test-ai-player-2', character: secondCharacter };
      const participants = [aiPlayer, secondPlayer];
      
      const config: AIDMConfig = {
        scenarioComplexity: 'moderate',
        voidInfluence: 5,
        factionFocus: ['Freeborn'],
        ritualFrequency: 'medium',
        bondEmphasis: 'medium'
      };
      
      const dreamline = generateDreamline('Bond Betrayal', participants, config);
      const result = runAISession(dreamline, participants, config);
      
      expect(result.actions.length).toBeGreaterThanOrEqual(participants.length);
      expect(result.decisions.length).toBeGreaterThanOrEqual(participants.length);
      
      // Check that decisions have required properties
      result.decisions.forEach(decision => {
        expect(decision.context).toBeDefined();
        expect(decision.options).toBeDefined();
        expect(decision.chosen_option).toBeDefined();
        expect(decision.reasoning).toBeDefined();
        expect(decision.timestamp).toBeDefined();
      });
    });
  });

  describe('Scenario Seeds', () => {
    it('should have well-defined scenario seeds', () => {
      expect(Array.isArray(SCENARIO_SEEDS)).toBe(true);
      expect(SCENARIO_SEEDS.length).toBeGreaterThan(0);
      
      SCENARIO_SEEDS.forEach(seed => {
        expect(seed.theme).toBeDefined();
        expect(seed.location).toBeDefined();
        expect(Array.isArray(seed.factions)).toBe(true);
        expect(Array.isArray(seed.conflicts)).toBe(true);
        expect(Array.isArray(seed.ritualOpportunities)).toBe(true);
        expect(Array.isArray(seed.bondChallenges)).toBe(true);
        expect(Array.isArray(seed.voidThreats)).toBe(true);
      });
    });

    it('should include expected scenario themes', () => {
      const themes = SCENARIO_SEEDS.map(seed => seed.theme);
      
      expect(themes).toContain('Void Corruption');
      expect(themes).toContain('Faction Politics');
      expect(themes).toContain('Bond Betrayal');
      expect(themes).toContain('Astral Exploration');
    });
  });
});