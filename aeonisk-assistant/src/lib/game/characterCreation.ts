import type { 
  Character, 
  CampaignLevel, 
  PriorityPools, 
  PriorityAllocation, 
  Advantage, 
  Disadvantage, 
  Technique,
  Familiarity,
  Language,
  Bond,
  Ritual
} from '../../types';

// Type definitions for Aeonisk
export type Faction = 'Sovereign Nexus' | 'Astral Commerce Group' | 'Pantheon Security' | 'Aether Dynamics' | 'Arcane Genetics' | 'Tempest Industries' | 'Freeborn';
export type Attribute = 'Strength' | 'Health' | 'Agility' | 'Dexterity' | 'Perception' | 'Intelligence' | 'Empathy' | 'Willpower';
export type Skill = string; // Skills are dynamic strings

// Campaign Level Definitions
export const CAMPAIGN_LEVELS: Record<CampaignLevel, PriorityAllocation> = {
  Mundane: {
    attributes: { points: 5, maxAttribute: 5 },
    experience: { points: 50, maxSkill: 6 },
    advantages: { points: 3 }
  },
  Skilled: {
    attributes: { points: 5, maxAttribute: 5 },
    experience: { points: 100, maxSkill: 6 },
    advantages: { points: 3 }
  },
  Exceptional: {
    attributes: { points: 8, maxAttribute: 6 },
    experience: { points: 100, maxSkill: 7 },
    advantages: { points: 4 }
  },
  Heroic: {
    attributes: { points: 12, maxAttribute: 8 },
    experience: { points: 200, maxSkill: 10 },
    advantages: { points: 6 }
  }
};

// YAGS Core Attributes
export const YAGS_ATTRIBUTES = [
  'Strength', 'Health', 'Agility', 'Dexterity', 
  'Perception', 'Intelligence', 'Empathy', 'Willpower'
];

// YAGS Talents (start at 2 for all characters)
export const YAGS_TALENTS = [
  'Athletics', 'Awareness', 'Brawl', 'Charm', 
  'Guile', 'Sleight', 'Stealth', 'Throw'
];

// Aeonisk-Specific Skills (Core to the setting)
export const AEONISK_SKILLS = [
  'Astral Arts', 'Magick Theory', 'Intimacy Ritual', 
  'Corporate Influence', 'Debt Law', 'Void Manipulation',
  'Bond Weaving', 'Soulcredit Management', 'Ritual Casting'
];

// Standard Skills (Modern/Sci-fi setting)
export const STANDARD_SKILLS = [
  // Core YAGS Skills
  'Academics', 'Area Lore', 'Art', 'Athletics', 'Awareness', 'Brawl',
  'Charm', 'Computers', 'Craft', 'Drive', 'First Aid', 'Guile',
  'Guns', 'Intimidation', 'Investigation', 'Language', 'Leadership',
  'Medicine', 'Melee', 'Navigation', 'Outdoors', 'Perception',
  'Persuasion', 'Pilot', 'Profession', 'Religion', 'Science',
  'Sleight', 'Stealth', 'Survival', 'Swimming', 'Teaching',
  'Technology', 'Trade', 'Throw', 'Tracking',
  
  // Sci-fi Skills (from YAGS SF module)
  'Spaceship Piloting', 'Orbital Navigation', 'Jump Navigation',
  'Spaceship Systems', 'Sophontology', 'Drone Operation',
  'Hacking', 'Cybernetics', 'Biotech', 'Nanotech',
  
  // Fantasy Skills (adapted for Aeonisk)
  'Arcana', 'Alchemy', 'Memory', 'Forgery', 'Herbalism',
  'Ritual Preparation', 'Astral Projection', 'Void Sensing'
];

// Knowledge Skills (Expanded)
export const KNOWLEDGE_SKILLS = [
  // Academic Knowledge
  'Anthropology', 'Archaeology', 'Architecture', 'Art History',
  'Astronomy', 'Biology', 'Chemistry', 'Economics', 'Engineering',
  'Geography', 'Geology', 'History', 'Law', 'Linguistics',
  'Mathematics', 'Meteorology', 'Military Science', 'Music',
  'Philosophy', 'Physics', 'Political Science', 'Psychology',
  'Sociology', 'Theology', 'Zoology',
  
  // Sci-fi Knowledge
  'Xenobiology', 'Quantum Physics', 'Cybernetics Theory',
  'Nanotechnology', 'Artificial Intelligence', 'Space Engineering',
  'Planetary Science', 'Stellar Cartography',
  
  // Aeonisk-Specific Knowledge
  'Void Theory', 'Astral Mechanics', 'Bond Dynamics',
  'Corporate Law', 'Debt Economics', 'Ritual Theory',
  'Faction Politics', 'Soulcredit Economics'
];

// Professional Skills (Career-based)
export const PROFESSIONAL_SKILLS = [
  // Corporate
  'Corporate Finance', 'Business Administration', 'Marketing',
  'Human Resources', 'Legal Compliance', 'Risk Management',
  
  // Criminal
  'Lockpicking', 'Pickpocketing', 'Smuggling', 'Fencing',
  'Counterfeiting', 'Security Systems',
  
  // Military/Security
  'Tactics', 'Strategy', 'Security Protocols', 'Weapon Maintenance',
  'Combat Training', 'Intelligence Analysis',
  
  // Technical
  'Software Development', 'Hardware Engineering', 'Network Security',
  'Data Analysis', 'System Administration', 'Quality Assurance'
];

// Vehicle Skills (Expanded)
export const VEHICLE_SKILLS = [
  'Ground Vehicle', 'Aircraft', 'Watercraft', 'Spaceship',
  'Drone', 'Robot', 'Exoskeleton', 'Hovercraft'
];



// Advantages Database
export const ADVANTAGES: Advantage[] = [
  {
    name: 'Rich',
    cost: 3,
    description: 'You are wealthy, with significant financial resources.',
    category: 'background',
    effects: { wealth: 'high' }
  },
  {
    name: 'Good Looking',
    cost: 1,
    description: 'You are attractive and charismatic.',
    category: 'physical',
    effects: { charmBonus: 1 }
  },
  {
    name: 'Lucky',
    cost: 2,
    description: 'You have good fortune and tend to succeed when it matters.',
    category: 'mental',
    effects: { luckBonus: 1 }
  },
  {
    name: 'Educated',
    cost: 1,
    description: 'You have a good education and broad knowledge.',
    category: 'background',
    effects: { education: 'higher' }
  },
  {
    name: 'Well Connected',
    cost: 2,
    description: 'You have useful contacts and social connections.',
    category: 'social',
    effects: { contacts: 'extensive' }
  },
  {
    name: 'Void Touched',
    cost: 2,
    description: 'You have a natural affinity for void manipulation.',
    category: 'supernatural',
    effects: { voidAffinity: 1 }
  },
  {
    name: 'Bond Sensitive',
    cost: 1,
    description: 'You are particularly attuned to the formation and maintenance of bonds.',
    category: 'supernatural',
    effects: { bondAffinity: 1 }
  },
  {
    name: 'Astral Resonance',
    cost: 3,
    description: 'You have a strong connection to the astral plane.',
    category: 'supernatural',
    effects: { astralAffinity: 2 }
  }
];

// Disadvantages Database
export const DISADVANTAGES: Disadvantage[] = [
  {
    name: 'Poor',
    cost: -2,
    description: 'You have limited financial resources.',
    category: 'background',
    effects: { wealth: 'low' }
  },
  {
    name: 'Bad Reputation',
    cost: -1,
    description: 'You have a poor reputation that precedes you.',
    category: 'social',
    effects: { reputation: 'poor' }
  },
  {
    name: 'Void Corruption',
    cost: -3,
    description: 'You are already corrupted by the void.',
    category: 'supernatural',
    effects: { voidScore: 3 }
  },
  {
    name: 'Bond Scarred',
    cost: -2,
    description: 'You have been hurt by broken bonds in the past.',
    category: 'supernatural',
    effects: { bondDifficulty: 1 }
  },
  {
    name: 'Illiterate',
    cost: -1,
    description: 'You cannot read or write.',
    category: 'mental',
    effects: { literacy: false }
  },
  {
    name: 'Addiction',
    cost: -2,
    description: 'You are addicted to a substance or behavior.',
    category: 'mental',
    effects: { addiction: true }
  },
  {
    name: 'Bad Back',
    cost: -1,
    description: 'You have a chronic back condition.',
    category: 'physical',
    effects: { physicalPenalty: 1 }
  },
  {
    name: 'Paranoid',
    cost: -1,
    description: 'You are suspicious and distrustful of others.',
    category: 'mental',
    effects: { trustIssues: true }
  }
];

// Techniques Database
export const TECHNIQUES: Technique[] = [
  // Academic Techniques
  {
    name: 'Research',
    cost: 2,
    description: 'You are skilled at finding and analyzing information.',
    skill: 'Academics',
    category: 'academic',
    effects: { researchBonus: 1 }
  },
  {
    name: 'Critical Analysis',
    cost: 3,
    description: 'You can quickly identify flaws and weaknesses.',
    skill: 'Academics',
    category: 'academic',
    effects: { analysisBonus: 1 }
  },
  
  // Combat Techniques
  {
    name: 'Hard to Kill',
    cost: 2,
    description: 'You are particularly resilient in combat.',
    skill: 'Brawl',
    category: 'combat',
    effects: { soakBonus: 1 }
  },
  {
    name: 'Ignore Pain',
    cost: 4,
    description: 'You can continue fighting despite serious injuries.',
    skill: 'Brawl',
    prerequisites: ['Hard to Kill'],
    category: 'combat',
    effects: { painResistance: true }
  },
  
  // Social Techniques
  {
    name: 'Fast Talk',
    cost: 2,
    description: 'You can quickly convince people with fast talking.',
    skill: 'Charm',
    category: 'social',
    effects: { fastTalkBonus: 1 }
  },
  {
    name: 'Intimidation',
    cost: 2,
    description: 'You are skilled at intimidating others.',
    skill: 'Intimidation',
    category: 'social',
    effects: { intimidationBonus: 1 }
  },
  
  // Aeonisk-Specific Techniques
  {
    name: 'Void Channeling',
    cost: 3,
    description: 'You can channel void energy more safely.',
    skill: 'Astral Arts',
    category: 'academic',
    effects: { voidChanneling: true }
  },
  {
    name: 'Bond Weaving',
    cost: 2,
    description: 'You are skilled at creating and maintaining bonds.',
    skill: 'Intimacy Ritual',
    category: 'social',
    effects: { bondWeaving: true }
  }
];

// Familiarities Database
export const FAMILIARITIES: Familiarity[] = [
  {
    name: 'Cars',
    cost: 2,
    skill: 'Drive',
    description: 'Familiarity with automobiles and similar vehicles.'
  },
  {
    name: 'Motorcycles',
    cost: 2,
    skill: 'Drive',
    description: 'Familiarity with motorcycles and similar vehicles.'
  },
  {
    name: 'Heavy Vehicles',
    cost: 2,
    skill: 'Drive',
    description: 'Familiarity with trucks, buses, and heavy vehicles.'
  },
  {
    name: 'Pistols',
    cost: 2,
    skill: 'Guns',
    description: 'Familiarity with handguns and pistols.'
  },
  {
    name: 'Rifles',
    cost: 2,
    skill: 'Guns',
    description: 'Familiarity with rifles and long guns.'
  },
  {
    name: 'Shotguns',
    cost: 2,
    skill: 'Guns',
    description: 'Familiarity with shotguns and scatter guns.'
  }
];

// Aeonisk-specific character creation based on actual content mechanics
export interface CharacterCreationData {
  name: string;
  faction: Faction;
  attributes: Record<Attribute, number>;
  skills: Record<string, number>;
  soulcredit: number; // -10 to +10, spiritual trust/standing
  voidScore: number; // 0-10, spiritual corruption
  bonds: Bond[];
  trueWill?: string; // Declared during play, not creation
  ritualDebt: number;
  offerings: string[];
}

// Faction-specific starting values from Aeonisk content
export const FACTION_STARTING_VALUES: Record<Faction, {
  soulcredit: number;
  void: number;
  ritualDebt: number;
  bondLimit: number;
  specialAbilities: string[];
}> = {
  'Sovereign Nexus': {
    soulcredit: 1,
    void: 0,
    ritualDebt: 0,
    bondLimit: 3,
    specialAbilities: ['Ritual Authority', 'Void Cleansing', 'Hierarchical Access']
  },
  'Astral Commerce Group': {
    soulcredit: 1,
    void: 0,
    ritualDebt: 1,
    bondLimit: 3,
    specialAbilities: ['Contract Binding', 'Soulcredit Tracking', 'Debt Law Expertise']
  },
  'Pantheon Security': {
    soulcredit: 0,
    void: 0,
    ritualDebt: 0,
    bondLimit: 3,
    specialAbilities: ['Tactical Ritual', 'Void Containment', 'Loyalty Protocols']
  },
  'Aether Dynamics': {
    soulcredit: 0,
    void: 0,
    ritualDebt: 0,
    bondLimit: 3,
    specialAbilities: ['Leyline Attunement', 'Ecological Harmony', 'Fluid Ritual']
  },
  'Arcane Genetics': {
    soulcredit: 0,
    void: 1,
    ritualDebt: 0,
    bondLimit: 3,
    specialAbilities: ['Fleshcrafting', 'Programmable Purity', 'Biotech Fusion']
  },
  'Tempest Industries': {
    soulcredit: -1,
    void: 2,
    ritualDebt: 2,
    bondLimit: 2,
    specialAbilities: ['Forbidden Ritual', 'Void Tools', 'Subversive Tech']
  },
  'Freeborn': {
    soulcredit: 0,
    void: 0,
    ritualDebt: 0,
    bondLimit: 1,
    specialAbilities: ['Unbound Will', 'Truth Seeking', 'Scarce Bonds']
  }
};

// YAGS Core Mechanics
export const YAGS_MECHANICS = {
  // Core dice mechanic: Attribute × Skill + d20 vs Difficulty
  skillCheck: (attribute: number, skill: number, d20Roll: number) => attribute * skill + d20Roll,
  attributeCheck: (attribute: number, d20Roll: number) => attribute * 4 + d20Roll,
  
  // Standard difficulties (Aeonisk uses 15-20 for standard checks)
  difficulties: {
    veryEasy: 10,
    easy: 15,
    moderate: 20,
    challenging: 25,
    difficult: 30,
    veryDifficult: 40,
    extreme: 50,
    heroic: 60,
    sheerFolly: 75,
    absurd: 100
  },
  
  // Degrees of success
  successLevels: {
    moderate: 0,      // Meet difficulty
    good: 10,         // Exceed by 10+
    excellent: 20,    // Exceed by 20+
    superb: 30,       // Exceed by 30+
    fantastic: 40,    // Exceed by 40+
    amazing: 50       // Exceed by 50+
  },
  
  // Fumble and critical
  fumble: 1,          // Natural 1 is automatic failure
  critical: 20        // Natural 20 in contests wins if skill higher
};

// Soulcredit effects by score (from Aeonisk content)
export const SOULCREDIT_EFFECTS: Record<string, {
  status: string;
  socialEffects: string[];
  access: string[];
}> = {
  '6-10': {
    status: 'Ritually Exalted',
    socialEffects: ['Trusted by sacred factions', 'Leadership position'],
    access: ['High-tier rituals', 'Elite tech', 'Nexus authority']
  },
  '1-5': {
    status: 'Clean / Reliable',
    socialEffects: ['Generally accepted', 'Standard standing'],
    access: ['Standard access', 'Normal pricing', 'Regular permissions']
  },
  '0': {
    status: 'Neutral / Unknown',
    socialEffects: ['No strong opinions', 'Default state'],
    access: ['Basic access', 'Standard permissions']
  },
  '-1--5': {
    status: 'Flagged / Unreliable',
    socialEffects: ['Watched by auditors', 'Social suspicion'],
    access: ['Limited access', 'ACG monitoring', 'Restricted permissions']
  },
  '-6--9': {
    status: 'Rejected / Debt-Marked',
    socialEffects: ['Pariah status', 'Hunted by debt collectors'],
    access: ['Excluded from sacred spaces', 'No ritual access', 'Blacklisted']
  },
  '-10': {
    status: 'Spiritually Bankrupt',
    socialEffects: ['Astrally toxic', 'Considered null'],
    access: ['Targeted for cleansing', 'Complete exclusion', 'Containment risk']
  }
};

// Void effects (from Aeonisk content)
export const VOID_EFFECTS: Record<number, {
  level: string;
  effects: string[];
  techInterference: string[];
}> = {
  0: { level: 'Pure', effects: ['No corruption'], techInterference: ['None'] },
  1: { level: 'Tainted', effects: ['Minor spiritual unease'], techInterference: ['Occasional glitches'] },
  2: { level: 'Corrupted', effects: ['Noticeable spiritual weight'], techInterference: ['Frequent malfunctions'] },
  3: { level: 'Stained', effects: ['Spiritual discomfort', 'Dream disturbances'], techInterference: ['Regular jams'] },
  4: { level: 'Marked', effects: ['Spiritual pain', 'Void sensitivity'], techInterference: ['Persistent issues'] },
  5: { level: 'Void-Touched', effects: ['Reality warping begins', 'Void Spike risk'], techInterference: ['Environmental disruption'] },
  6: { level: 'Void-Corrupted', effects: ['Reality distortion', 'Spiritual decay'], techInterference: ['Hallucinations', 'Inverted function'] },
  7: { level: 'Void-Bound', effects: ['Bonds become dormant', 'Severe corruption'], techInterference: ['Possession risk', 'Corruption spread'] },
  8: { level: 'Void-Dominated', effects: ['Reality rejection', 'Spiritual death'], techInterference: ['Complete malfunction', 'Void possession'] },
  9: { level: 'Void-Infused', effects: ['Void entity influence', 'Reality breakdown'], techInterference: ['Void tech only', 'Corruption field'] },
  10: { level: 'Void-Null', effects: ['Complete void alignment', 'Reality nullification'], techInterference: ['Void tech enhancement', 'Reality warping'] }
};

// Bond types from Aeonisk content
export const BOND_TYPES = [
  'Kinship',      // Ancestral, chosen, or ritualized family
  'Ascendancy',   // Subordination to higher Will
  'Debt',         // Owed spiritual/material obligation
  'Voidward',     // Alignment with nullity/taboo forces
  'Passion',      // Intense emotional/creative entanglement
  'Faction'       // Formal allegiance to institution
] as const;

// Character Creation Functions
export function calculatePriorityAllocation(
  campaignLevel: CampaignLevel,
  priorityPools: PriorityPools
): PriorityAllocation {
  const base = CAMPAIGN_LEVELS[campaignLevel];
  
  const allocation: PriorityAllocation = {
    attributes: { points: 0, maxAttribute: 0 },
    experience: { points: 0, maxSkill: 0 },
    advantages: { points: 0 }
  };

  // Apply priority bonuses
  if (priorityPools.attributes === 'Primary') {
    allocation.attributes.points = base.attributes.points + 5;
    allocation.attributes.maxAttribute = base.attributes.maxAttribute + 1;
  } else if (priorityPools.attributes === 'Secondary') {
    allocation.attributes.points = base.attributes.points + 2;
    allocation.attributes.maxAttribute = base.attributes.maxAttribute;
  } else {
    allocation.attributes.points = 0;
    allocation.attributes.maxAttribute = base.attributes.maxAttribute;
  }

  if (priorityPools.experience === 'Primary') {
    allocation.experience.points = base.experience.points + 50;
    allocation.experience.maxSkill = base.experience.maxSkill + 1;
  } else if (priorityPools.experience === 'Secondary') {
    allocation.experience.points = base.experience.points + 20;
    allocation.experience.maxSkill = base.experience.maxSkill;
  } else {
    allocation.experience.points = base.experience.points;
    allocation.experience.maxSkill = base.experience.maxSkill;
  }

  if (priorityPools.advantages === 'Primary') {
    allocation.advantages.points = base.advantages.points + 2;
  } else if (priorityPools.advantages === 'Secondary') {
    allocation.advantages.points = base.advantages.points + 1;
  } else {
    allocation.advantages.points = base.advantages.points;
  }

  return allocation;
}

export function createDefaultCharacter(): Character {
  return {
    name: '',
    concept: '',
    attributes: {
      Strength: 3,
      Health: 3,
      Agility: 3,
      Dexterity: 3,
      Perception: 3,
      Intelligence: 3,
      Empathy: 3,
      Willpower: 3
    },
    secondary_attributes: {
      Size: 5,
      Soak: 12,
      Move: 12
    },
    skills: {
      // Initialize with some basic skills appropriate for Aeonisk
      'Area Lore': 1,
      'First Aid': 1,
      'Language': 1,
      'Computers': 1,
      'Technology': 1
    },
    talents: {
      Athletics: 2,
      Awareness: 2,
      Brawl: 2,
      Charm: 2,
      Guile: 2,
      Sleight: 2,
      Stealth: 2,
      Throw: 2
    },
    knowledges: {},
    languages: {
      native_language_name: 'Common',
      native_language_level: 4,
      other_languages: []
    },
    voidScore: 0,
    soulcredit: 0,
    bonds: [],
    campaignLevel: 'Skilled',
    priorityPools: {
      attributes: 'Secondary',
      experience: 'Primary',
      advantages: 'Tertiary'
    },
    advantages: [],
    disadvantages: [],
    techniques: [],
    familiarities: [],
    experiencePoints: 0
  };
}

export function calculateSecondaryAttributes(character: Character): Record<string, number> {
  const { attributes } = character;
  const size = 5; // Default human size
  
  return {
    Size: size,
    Soak: 12, // Base soak for humans
    Move: size + attributes.Agility + attributes.Strength + 1
  };
}

// Helper to get attribute bonuses for a character (including Freeborn)
export function getFactionAttributeBonuses(character: Character, freebornBonuses: string[] = []): Record<string, number> {
  const faction = character.origin_faction;
  if (!faction) return {};
  if (faction === 'Freeborn') {
    const bonuses: Record<string, number> = {};
    freebornBonuses.forEach(attr => {
      bonuses[attr] = (bonuses[attr] || 0) + 1;
    });
    return bonuses;
  }
  // Find the faction definition
  const FACTIONS = [
    'Sovereign Nexus',
    'Astral Commerce Group',
    'Pantheon Security',
    'Aether Dynamics',
    'Arcane Genetics',
    'Tempest Industries',
    'Freeborn'
  ];
  if (!FACTIONS.includes(faction)) return {};
  // Hardcode bonuses for now (should match UI)
  const factionBonuses: Record<string, Record<string, number>> = {
    'Sovereign Nexus': { Willpower: 1, Intelligence: 1 },
    'Astral Commerce Group': { Intelligence: 1, Empathy: 1 },
    'Pantheon Security': { Strength: 1, Agility: 1 },
    'Aether Dynamics': { Empathy: 1, Perception: 1 },
    'Arcane Genetics': { Health: 1, Dexterity: 1 },
    'Tempest Industries': { Dexterity: 1, Perception: 1 },
    'Freeborn': {} // handled above
  };
  return factionBonuses[faction] || {};
}

// In validateCharacter, only count base attribute values (not bonuses)
export function validateCharacter(character: Character, freebornBonuses: string[] = []): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  // Check required fields
  if (!character.name.trim()) {
    errors.push('Character name is required');
  }
  
  if (!character.concept.trim()) {
    errors.push('Character concept is required');
  }
  
  // Check attributes are within bounds
  const allocation = calculatePriorityAllocation(
    character.campaignLevel || 'Skilled',
    character.priorityPools || { attributes: 'Secondary', experience: 'Primary', advantages: 'Tertiary' }
  );
  
  // Calculate attribute point cost (base only)
  let attributePointsSpent = 0;
  const bonuses = getFactionAttributeBonuses(character, freebornBonuses);
  for (const [attr, value] of Object.entries(character.attributes)) {
    const bonus = bonuses[attr] || 0;
    if (value > (character.priorityPools ? calculatePriorityAllocation(character.campaignLevel || 'Skilled', character.priorityPools).attributes.maxAttribute : 8)) {
      errors.push(`${attr} cannot exceed max base value`);
    }
    if (value < 1) {
      errors.push(`${attr} cannot be less than 1`);
    }
    // Only count base value above 3 for point spending
    if (value > 3) {
      attributePointsSpent += (value - 3);
    }
  }
  
  if (attributePointsSpent > allocation.attributes.points) {
    errors.push(`Attribute points spent (${attributePointsSpent}) exceeds available points (${allocation.attributes.points})`);
  }
  
  // Calculate skill point cost
  let skillPointsSpent = 0;
  for (const [skill, value] of Object.entries(character.skills)) {
    if (value > allocation.experience.maxSkill) {
      errors.push(`${skill} cannot exceed ${allocation.experience.maxSkill}`);
    }
    if (value < 0) {
      errors.push(`${skill} cannot be negative`);
    }
    skillPointsSpent += value;
  }
  
  if (skillPointsSpent > allocation.experience.points) {
    errors.push(`Skill points spent (${skillPointsSpent}) exceeds available points (${allocation.experience.points})`);
  }
  
  // Check advantages/disadvantages balance
  const advantageCost = character.advantages?.reduce((sum, adv) => sum + adv.cost, 0) || 0;
  const disadvantagePoints = character.disadvantages?.reduce((sum, dis) => sum + Math.abs(dis.cost), 0) || 0;
  const totalAdvantagePoints = allocation.advantages.points + disadvantagePoints;
  
  if (advantageCost > totalAdvantagePoints) {
    errors.push(`Advantage cost (${advantageCost}) exceeds available points (${totalAdvantagePoints})`);
  }
  
  // Check Aeonisk-specific validations
  if (character.soulcredit < -10 || character.soulcredit > 10) {
    errors.push('Soulcredit must be between -10 and +10');
  }
  
  if (character.voidScore < 0 || character.voidScore > 10) {
    errors.push('Void Score must be between 0 and 10');
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

export function calculateExperienceCost(character: Character): number {
  let cost = 0;
  
  // Calculate attribute cost
  for (const [attr, value] of Object.entries(character.attributes)) {
    if (value > 3) { // Base is 3, so only pay for points above 3
      cost += (value - 3);
    }
  }
  
  // Calculate skill cost
  for (const [skill, value] of Object.entries(character.skills)) {
    cost += value;
  }
  
  // Calculate knowledge cost
  for (const [knowledge, value] of Object.entries(character.knowledges || {})) {
    cost += value;
  }
  
  // Calculate technique cost
  for (const technique of character.techniques || []) {
    cost += technique.cost;
  }
  
  // Calculate familiarity cost
  for (const familiarity of character.familiarities || []) {
    cost += familiarity.cost;
  }
  
  return cost;
}

export function getAvailableAdvantages(character: Character): Advantage[] {
  const allocation = calculatePriorityAllocation(
    character.campaignLevel || 'Skilled',
    character.priorityPools || { attributes: 'Secondary', experience: 'Primary', advantages: 'Tertiary' }
  );
  
  const currentCost = character.advantages?.reduce((sum, adv) => sum + adv.cost, 0) || 0;
  const disadvantagePoints = character.disadvantages?.reduce((sum, dis) => sum + Math.abs(dis.cost), 0) || 0;
  const availablePoints = allocation.advantages.points + disadvantagePoints;
  
  return ADVANTAGES.filter(adv => {
    const newCost = currentCost + adv.cost;
    return newCost <= availablePoints;
  });
}

export function getAvailableDisadvantages(character: Character): Disadvantage[] {
  const allocation = calculatePriorityAllocation(
    character.campaignLevel || 'Skilled',
    character.priorityPools || { attributes: 'Secondary', experience: 'Primary', advantages: 'Tertiary' }
  );
  
  const currentDisadvantages = character.disadvantages?.length || 0;
  const maxDisadvantages = Math.floor(allocation.advantages.points / 3) + 1;
  
  if (currentDisadvantages >= maxDisadvantages) {
    return [];
  }
  
  return DISADVANTAGES;
}

export function getAvailableTechniques(character: Character): Technique[] {
  return TECHNIQUES.filter(technique => {
    // Check if character has the required skill level
    const skillLevel = character.skills[technique.skill] || 0;
    if (skillLevel < technique.cost) {
      return false;
    }
    
    // Check prerequisites
    if (technique.prerequisites) {
      for (const prereq of technique.prerequisites) {
        const hasPrereq = character.techniques?.some(t => t.name === prereq);
        if (!hasPrereq) {
          return false;
        }
      }
    }
    
    // Check if already purchased
    const alreadyPurchased = character.techniques?.some(t => t.name === technique.name);
    return !alreadyPurchased;
  });
}

export function getAvailableFamiliarities(character: Character): Familiarity[] {
  return FAMILIARITIES.filter(familiarity => {
    // Check if character has the skill
    const skillLevel = character.skills[familiarity.skill] || 0;
    if (skillLevel < 1) {
      return false;
    }
    
    // Check if already purchased
    const alreadyPurchased = character.familiarities?.some(f => f.name === familiarity.name);
    return !alreadyPurchased;
  });
}

// Get all available skills for character creation
export function getAllAvailableSkills(): {
  aeonisk: string[];
  standard: string[];
  knowledge: string[];
  professional: string[];
  vehicle: string[];
} {
  return {
    aeonisk: AEONISK_SKILLS,
    standard: STANDARD_SKILLS,
    knowledge: KNOWLEDGE_SKILLS,
    professional: PROFESSIONAL_SKILLS,
    vehicle: VEHICLE_SKILLS
  };
}

// Get skills by category for easier selection
export function getSkillsByCategory(): Record<string, string[]> {
  return {
    'Aeonisk Core': AEONISK_SKILLS,
    'Combat': ['Brawl', 'Guns', 'Melee', 'Throw', 'Tactics', 'Strategy'],
    'Social': ['Charm', 'Intimidation', 'Leadership', 'Persuasion', 'Guile'],
    'Technical': ['Computers', 'Technology', 'Hacking', 'Cybernetics', 'Biotech', 'Nanotech'],
    'Vehicles': VEHICLE_SKILLS,
    'Knowledge': KNOWLEDGE_SKILLS,
    'Professions': PROFESSIONAL_SKILLS,
    'Survival': ['Outdoors', 'Survival', 'Tracking', 'Navigation'],
    'Stealth': ['Stealth', 'Sleight', 'Forgery', 'Lockpicking'],
    'Medical': ['First Aid', 'Medicine', 'Herbalism'],
    'Magic': ['Astral Arts', 'Magick Theory', 'Ritual Casting', 'Void Manipulation', 'Bond Weaving']
  };
}

// Create a new character with proper Aeonisk mechanics
export function createCharacter(data: CharacterCreationData): Character {
  const factionData = FACTION_STARTING_VALUES[data.faction];
  
  // Validate Soulcredit range (-10 to +10)
  const soulcredit = Math.max(-10, Math.min(10, data.soulcredit));
  
  // Validate Void range (0-10)
  const voidScore = Math.max(0, Math.min(10, data.voidScore));
  
  // Validate bond limit
  const bonds = data.bonds.slice(0, factionData.bondLimit);
  
  const character: Character = {
    name: data.name,
    concept: `${data.name} - ${data.faction} member`,
    origin_faction: data.faction,
    attributes: data.attributes,
    skills: data.skills,
    soulcredit,
    voidScore,
    bonds,
    trueWill: data.trueWill
  };
  
  return character;
}

// Calculate Soulcredit effects for a character
export function getSoulcreditEffects(soulcredit: number) {
  if (soulcredit >= 6) return SOULCREDIT_EFFECTS['6-10'];
  if (soulcredit >= 1) return SOULCREDIT_EFFECTS['1-5'];
  if (soulcredit === 0) return SOULCREDIT_EFFECTS['0'];
  if (soulcredit >= -5) return SOULCREDIT_EFFECTS['-1--5'];
  if (soulcredit >= -9) return SOULCREDIT_EFFECTS['-6--9'];
  return SOULCREDIT_EFFECTS['-10'];
}

// Calculate Void effects for a character
export function getVoidEffects(voidScore: number) {
  return VOID_EFFECTS[Math.min(10, Math.max(0, voidScore))] || VOID_EFFECTS[0];
}

// YAGS skill check with proper mechanics
export function performSkillCheck(
  attribute: number, 
  skill: number, 
  difficulty: number,
  d20Roll: number = Math.floor(Math.random() * 20) + 1
): {
  success: boolean;
  margin: number;
  level: string;
  fumble: boolean;
  critical: boolean;
} {
  const total = YAGS_MECHANICS.skillCheck(attribute, skill, d20Roll);
  const margin = total - difficulty;
  const success = total >= difficulty;
  const fumble = d20Roll === YAGS_MECHANICS.fumble;
  const critical = d20Roll === YAGS_MECHANICS.critical;
  
  let level = 'failure';
  if (success) {
    if (margin >= 50) level = 'amazing';
    else if (margin >= 40) level = 'fantastic';
    else if (margin >= 30) level = 'superb';
    else if (margin >= 20) level = 'excellent';
    else if (margin >= 10) level = 'good';
    else level = 'moderate';
  }
  
  return { success, margin, level, fumble, critical };
}

// YAGS attribute check
export function performAttributeCheck(
  attribute: number,
  difficulty: number,
  d20Roll: number = Math.floor(Math.random() * 20) + 1
): {
  success: boolean;
  margin: number;
  level: string;
  fumble: boolean;
  critical: boolean;
} {
  const total = YAGS_MECHANICS.attributeCheck(attribute, d20Roll);
  const margin = total - difficulty;
  const success = total >= difficulty;
  const fumble = d20Roll === YAGS_MECHANICS.fumble;
  const critical = d20Roll === YAGS_MECHANICS.critical;
  
  let level = 'failure';
  if (success) {
    if (margin >= 50) level = 'amazing';
    else if (margin >= 40) level = 'fantastic';
    else if (margin >= 30) level = 'superb';
    else if (margin >= 20) level = 'excellent';
    else if (margin >= 10) level = 'good';
    else level = 'moderate';
  }
  
  return { success, margin, level, fumble, critical };
}

// Generate a unique ID
function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
} 