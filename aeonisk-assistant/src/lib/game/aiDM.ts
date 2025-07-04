import type { 
  AIPlayer, 
  PlayerPersonality, 
  PlayerGoal, 
  DecisionStrategy,
  Character,
  Dreamline,
  Session,
  Ritual,
  NPC,
  ActionResult,
  DecisionRecord
} from '../../types';
import { getRitualByName, resolveRitual, canCastRitual } from './ritualSystem';

// AI DM Configuration
export interface AIDMConfig {
  scenarioComplexity: 'simple' | 'moderate' | 'complex';
  voidInfluence: number; // 0-10 scale
  factionFocus: string[];
  ritualFrequency: 'low' | 'medium' | 'high';
  bondEmphasis: 'low' | 'medium' | 'high';
}

// Scenario Generation
export interface ScenarioSeed {
  theme: string;
  location: string;
  factions: string[];
  conflicts: string[];
  ritualOpportunities: string[];
  bondChallenges: string[];
  voidThreats: string[];
}

export const SCENARIO_SEEDS: ScenarioSeed[] = [
  {
    theme: 'Void Corruption',
    location: 'Abandoned Astral Node',
    factions: ['Sovereign Nexus', 'Tempest Industries'],
    conflicts: ['Void containment', 'Resource control', 'Information gathering'],
    ritualOpportunities: ['Void purification', 'Astral navigation', 'Bond strengthening'],
    bondChallenges: ['Trust in void-corrupted allies', 'Sacrifice for purification'],
    voidThreats: ['Void entities', 'Reality distortion', 'Corruption spread']
  },
  {
    theme: 'Faction Politics',
    location: 'Nexus Council Chamber',
    factions: ['Sovereign Nexus', 'Astral Commerce Group', 'Arcane Genetics'],
    conflicts: ['Policy disputes', 'Resource allocation', 'Influence competition'],
    ritualOpportunities: ['Sovereign recognition', 'Corporate influence', 'Genetic enhancement'],
    bondChallenges: ['Political alliances', 'Betrayal and loyalty'],
    voidThreats: ['Corruption of power', 'Moral compromise']
  },
  {
    theme: 'Bond Betrayal',
    location: 'Intimate Gathering Space',
    factions: ['Resonance Communes', 'Freeborn'],
    conflicts: ['Broken trust', 'Secrets revealed', 'Loyalty tested'],
    ritualOpportunities: ['Bond formation', 'Intimacy rituals', 'Truth revelation'],
    bondChallenges: ['Forgiveness', 'Rebuilding trust', 'Letting go'],
    voidThreats: ['Emotional void', 'Isolation', 'Despair']
  },
  {
    theme: 'Astral Exploration',
    location: 'Unknown Astral Current',
    factions: ['Explorer Guild', 'Void Seekers'],
    conflicts: ['Territory discovery', 'Ancient knowledge', 'Survival'],
    ritualOpportunities: ['Astral navigation', 'Dream communication', 'Void channeling'],
    bondChallenges: ['Shared danger', 'Mutual survival', 'Discovery bonds'],
    voidThreats: ['Astral hazards', 'Void corruption', 'Lost in the currents']
  }
];

// AI Player Personality Generation
export function generateAIPersonality(faction: string): PlayerPersonality {
  const basePersonality: PlayerPersonality = {
    riskTolerance: 5,
    bondPreference: 'neutral',
    voidCuriosity: 3,
    factionLoyalty: 5,
    ritualConservatism: 5,
    socialAggressiveness: 5
  };

  // Adjust based on faction
  switch (faction) {
    case 'Sovereign Nexus':
      return {
        ...basePersonality,
        riskTolerance: 3,
        bondPreference: 'seeks',
        factionLoyalty: 8,
        ritualConservatism: 7,
        socialAggressiveness: 4
      };
    case 'Tempest Industries':
      return {
        ...basePersonality,
        riskTolerance: 8,
        bondPreference: 'avoids',
        voidCuriosity: 8,
        factionLoyalty: 6,
        ritualConservatism: 2,
        socialAggressiveness: 7
      };
    case 'Arcane Genetics':
      return {
        ...basePersonality,
        riskTolerance: 6,
        bondPreference: 'neutral',
        voidCuriosity: 6,
        factionLoyalty: 7,
        ritualConservatism: 4,
        socialAggressiveness: 5
      };
    case 'Astral Commerce Group':
      return {
        ...basePersonality,
        riskTolerance: 4,
        bondPreference: 'seeks',
        voidCuriosity: 4,
        factionLoyalty: 6,
        ritualConservatism: 6,
        socialAggressiveness: 6
      };
    case 'Resonance Communes':
      return {
        ...basePersonality,
        riskTolerance: 5,
        bondPreference: 'seeks',
        voidCuriosity: 5,
        factionLoyalty: 5,
        ritualConservatism: 3,
        socialAggressiveness: 3
      };
    case 'Freeborn':
      return {
        ...basePersonality,
        riskTolerance: 7,
        bondPreference: 'avoids',
        voidCuriosity: 7,
        factionLoyalty: 3,
        ritualConservatism: 2,
        socialAggressiveness: 6
      };
    default:
      return basePersonality;
  }
}

export function generatePlayerGoals(character: Character, personality: PlayerPersonality): PlayerGoal[] {
  const goals: PlayerGoal[] = [];
  
  // Personal goals based on personality
  if (personality.voidCuriosity > 6) {
    goals.push({
      type: 'void',
      description: 'Explore void manipulation and its limits',
      priority: personality.voidCuriosity,
      progress: 0
    });
  }
  
  if (personality.bondPreference === 'seeks') {
    goals.push({
      type: 'bond',
      description: 'Form meaningful bonds with others',
      priority: 8,
      progress: 0
    });
  }
  
  // Faction goals
  if (character.origin_faction && personality.factionLoyalty > 5) {
    goals.push({
      type: 'faction',
      description: `Advance the interests of ${character.origin_faction}`,
      priority: personality.factionLoyalty,
      progress: 0
    });
  }
  
  // Ritual goals
  if (character.skills['Astral Arts'] > 3) {
    goals.push({
      type: 'ritual',
      description: 'Master advanced ritual techniques',
      priority: 7,
      progress: 0
    });
  }
  
  return goals;
}

export function generateDecisionStrategy(personality: PlayerPersonality): DecisionStrategy {
  return {
    primaryFocus: personality.voidCuriosity > 6 ? 'ritual' : 
                   personality.socialAggressiveness > 6 ? 'social' : 'exploration',
    secondaryFocus: personality.riskTolerance > 6 ? 'combat' : 'survival',
    riskAssessment: personality.riskTolerance > 7 ? 'aggressive' : 
                    personality.riskTolerance < 4 ? 'conservative' : 'balanced',
    groupCooperation: personality.bondPreference === 'seeks' ? 'follower' : 'independent'
  };
}

// AI Decision Making
export function makeAIDecision(
  player: AIPlayer,
  context: string,
  options: string[]
): {
  chosenOption: string;
  reasoning: string;
  personalityFactors: Record<string, number>;
} {
  const { personality, decisionMaking, goals } = player;
  
  // Score each option based on personality and goals
  const optionScores: Record<string, number> = {};
  const personalityFactors: Record<string, number> = {};
  
  for (const option of options) {
    let score = 0;
    
    // Risk tolerance factor
    if (option.toLowerCase().includes('risk') || option.toLowerCase().includes('danger')) {
      score += personality.riskTolerance * 0.5;
      personalityFactors.riskTolerance = personality.riskTolerance;
    }
    
    // Bond preference factor
    if (option.toLowerCase().includes('bond') || option.toLowerCase().includes('trust')) {
      if (personality.bondPreference === 'seeks') {
        score += 3;
        personalityFactors.bondPreference = 1;
      } else if (personality.bondPreference === 'avoids') {
        score -= 2;
        personalityFactors.bondPreference = -1;
      }
    }
    
    // Void curiosity factor
    if (option.toLowerCase().includes('void') || option.toLowerCase().includes('corruption')) {
      score += personality.voidCuriosity * 0.3;
      personalityFactors.voidCuriosity = personality.voidCuriosity;
    }
    
    // Faction loyalty factor
    if (option.toLowerCase().includes(player.faction.toLowerCase())) {
      score += personality.factionLoyalty * 0.4;
      personalityFactors.factionLoyalty = personality.factionLoyalty;
    }
    
    // Ritual conservatism factor
    if (option.toLowerCase().includes('ritual')) {
      score -= personality.ritualConservatism * 0.3;
      personalityFactors.ritualConservatism = personality.ritualConservatism;
    }
    
    // Social aggressiveness factor
    if (option.toLowerCase().includes('confront') || option.toLowerCase().includes('attack')) {
      score += personality.socialAggressiveness * 0.4;
      personalityFactors.socialAggressiveness = personality.socialAggressiveness;
    }
    
    optionScores[option] = score;
  }
  
  // Choose the highest scoring option
  const chosenOption = Object.entries(optionScores).reduce((a, b) => 
    optionScores[a[0]] > optionScores[b[0]] ? a : b
  )[0];
  
  // Generate reasoning
  const reasoning = `Chose "${chosenOption}" based on ${Object.entries(personalityFactors)
    .filter(([_, value]) => Math.abs(value) > 0.5)
    .map(([factor, value]) => `${factor} (${value > 0 ? '+' : ''}${value.toFixed(1)})`)
    .join(', ')}`;
  
  return {
    chosenOption,
    reasoning,
    personalityFactors
  };
}

// Ritual Decision Making
export function decideRitualCasting(
  player: AIPlayer,
  availableRituals: Ritual[],
  situation: string
): {
  shouldCast: boolean;
  chosenRitual?: Ritual;
  offering?: string;
  reasoning: string;
} {
  const { personality, character, goals } = player;
  
  // Check if player is ritual-focused
  if (personality.ritualConservatism > 7) {
    return {
      shouldCast: false,
      reasoning: 'Too conservative to cast rituals in this situation'
    };
  }
  
  // Filter rituals based on goals and personality
  const suitableRituals = availableRituals.filter(ritual => {
    // Check if ritual aligns with goals
    const hasVoidGoal = goals.some(g => g.type === 'void');
    const hasBondGoal = goals.some(g => g.type === 'bond');
    
    if (ritual.category === 'void' && !hasVoidGoal) return false;
    if (ritual.category === 'intimacy' && !hasBondGoal) return false;
    
    // Check faction restrictions
    if (ritual.factionRestrictions && !ritual.factionRestrictions.includes(character.origin_faction || '')) {
      return false;
    }
    
    return true;
  });
  
  if (suitableRituals.length === 0) {
    return {
      shouldCast: false,
      reasoning: 'No suitable rituals available'
    };
  }
  
  // Choose ritual based on personality and situation
  let chosenRitual = suitableRituals[0];
  
  if (personality.voidCuriosity > 6 && situation.includes('danger')) {
    const voidRitual = suitableRituals.find(r => r.category === 'void');
    if (voidRitual) chosenRitual = voidRitual;
  }
  
  if (personality.bondPreference === 'seeks' && situation.includes('social')) {
    const bondRitual = suitableRituals.find(r => r.category === 'intimacy');
    if (bondRitual) chosenRitual = bondRitual;
  }
  
  // Generate offering
  const offering = generateOffering(chosenRitual, character, personality);
  
  return {
    shouldCast: true,
    chosenRitual,
    offering,
    reasoning: `Chose ${chosenRitual.name} ritual to ${chosenRitual.category} category, offering: ${offering}`
  };
}

function generateOffering(ritual: Ritual, character: Character, personality: PlayerPersonality): string {
  const offerings = {
    'intimacy': ['a shared memory', 'a personal vulnerability', 'a moment of trust'],
    'astral': ['a navigational tool', 'a dream memory', 'an astral artifact'],
    'void': ['a piece of memory', 'an emotion', 'a fragment of soul'],
    'faction': ['proof of loyalty', 'a service record', 'a faction artifact'],
    'transformation': ['current purpose', 'a personal goal', 'a defining moment']
  };
  
  const categoryOfferings = offerings[ritual.category] || ['a personal sacrifice'];
  return categoryOfferings[Math.floor(Math.random() * categoryOfferings.length)];
}

// NPC Generation
export function generateNPC(faction: string, role: string): NPC {
  const names = {
    'Sovereign Nexus': ['Aurora', 'Elara', 'Nexus', 'Continuity', 'Harmony'],
    'Tempest Industries': ['Void', 'Storm', 'Chaos', 'Liberty', 'Dissolution'],
    'Arcane Genetics': ['Gene', 'Strain', 'Morph', 'Evolve', 'Adapt'],
    'Astral Commerce Group': ['Credit', 'Value', 'Exchange', 'Profit', 'Debt'],
    'Resonance Communes': ['Echo', 'Resonance', 'Harmony', 'Pulse', 'Wave'],
    'Freeborn': ['Free', 'Unbound', 'Wild', 'Natural', 'Pure']
  };
  
  const factionNames = names[faction as keyof typeof names] || ['Unknown'];
  const name = factionNames[Math.floor(Math.random() * factionNames.length)];
  
  return {
    name,
    faction,
    role,
    description: `A ${role} from ${faction}, with ${faction.toLowerCase()} characteristics and motivations.`
  };
}

// Campaign Generation
export function generateDreamline(
  theme: string,
  participants: AIPlayer[],
  config: AIDMConfig
): Dreamline {
  const seed = SCENARIO_SEEDS.find(s => s.theme === theme) || SCENARIO_SEEDS[0];
  
  return {
    id: `dreamline-${Date.now()}`,
    theme,
    participants: participants.map(p => ({ id: p.id, name: p.character.name, role: 'player', character: p.character })),
    sessions: [],
    timeline: [],
    canon_status: 'dreamline',
    void_influence: config.voidInfluence
  };
}

// Session Management
export function runAISession(
  dreamline: Dreamline,
  aiPlayers: AIPlayer[],
  config: AIDMConfig
): {
  session: Session;
  actions: ActionResult[];
  decisions: DecisionRecord[];
} {
  const session: Session = {
    id: `session-${Date.now()}`,
    dreamlineId: dreamline.id,
    participants: dreamline.participants,
    actions: [],
    rituals: [],
    outcomes: [],
    mechanical_data: { skill_checks: [], attribute_checks: [], damage_dealt: [], healing: [] },
    narrative_summary: '',
    void_progression: [],
    bond_changes: [],
    timestamp: new Date()
  };
  
  const actions: ActionResult[] = [];
  const decisions: DecisionRecord[] = [];
  
  // Generate scenario based on dreamline theme
  const scenario = generateScenario(dreamline.theme, config);
  
  // Run AI player decisions
  for (const player of aiPlayers) {
    const playerActions = runAIPlayerTurn(player, scenario, config);
    actions.push(...playerActions.actions);
    decisions.push(...playerActions.decisions);
  }
  
  // Generate narrative summary
  session.narrative_summary = generateNarrativeSummary(scenario, actions, aiPlayers);
  
  return { session, actions, decisions };
}

function generateScenario(theme: string, config: AIDMConfig): string {
  const seed = SCENARIO_SEEDS.find(s => s.theme === theme) || SCENARIO_SEEDS[0];
  
  return `The scene opens at ${seed.location}. ${seed.conflicts[0]} creates tension as ${seed.factions.join(' and ')} vie for control. 
  ${seed.ritualOpportunities[0]} presents an opportunity, while ${seed.voidThreats[0]} looms as a threat. 
  The void influence level is ${config.voidInfluence}/10, affecting the environment and participants.`;
}

function runAIPlayerTurn(
  player: AIPlayer,
  scenario: string,
  config: AIDMConfig
): {
  actions: ActionResult[];
  decisions: DecisionRecord[];
} {
  const actions: ActionResult[] = [];
  const decisions: DecisionRecord[] = [];
  
  // Generate action options
  const actionOptions = [
    'Explore the environment',
    'Interact with other participants',
    'Attempt a ritual',
    'Investigate the situation',
    'Take defensive action',
    'Seek information'
  ];
  
  // Make decision
  const decision = makeAIDecision(player, scenario, actionOptions);
  decisions.push({
    context: scenario,
    options: actionOptions,
    chosen_option: decision.chosenOption,
    reasoning: decision.reasoning,
    personality_factors: decision.personalityFactors,
    timestamp: new Date()
  });
  
  // Execute action
  const action: ActionResult = {
    actor: player.character.name,
    action: decision.chosenOption,
    outcome: `Successfully ${decision.chosenOption.toLowerCase()}`,
    mechanicalEffect: {
      soulcredit: Math.random() > 0.7 ? 1 : 0,
      voidScore: Math.random() > 0.9 ? 1 : 0
    }
  };
  
  actions.push(action);
  
  // Check for ritual casting
  if (decision.chosenOption === 'Attempt a ritual' && config.ritualFrequency !== 'low') {
    const ritualDecision = decideRitualCasting(player, [], scenario);
    if (ritualDecision.shouldCast && ritualDecision.chosenRitual) {
      const ritual = getRitualByName(ritualDecision.chosenRitual.name);
      if (ritual) {
        const ritualResult = resolveRitual(ritual, player.character, ritualDecision.offering || '');
        actions.push({
          actor: player.character.name,
          action: `Cast ${ritual.name}`,
          outcome: ritualResult.success ? 'Ritual succeeded' : 'Ritual failed',
          mechanicalEffect: {
            voidGained: ritualResult.voidGained,
            soulcreditCost: ritualResult.soulcreditCost
          }
        });
      }
    }
  }
  
  return { actions, decisions };
}

function generateNarrativeSummary(
  scenario: string,
  actions: ActionResult[],
  players: AIPlayer[]
): string {
  const playerNames = players.map(p => p.character.name).join(', ');
  
  return `${scenario} ${playerNames} navigated the situation through various actions. 
  ${actions.map(a => `${a.actor} ${a.action.toLowerCase()}`).join(', ')}. 
  The session concluded with mixed outcomes as the void influence continues to affect the dreamline.`;
} 