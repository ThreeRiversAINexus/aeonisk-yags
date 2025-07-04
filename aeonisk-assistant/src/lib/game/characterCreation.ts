import type { 
  Character, 
  CampaignLevel, 
  PriorityPools, 
  PriorityAllocation, 
  Advantage, 
  Disadvantage, 
  Technique,
  Familiarity,
  Language
} from '../../types';

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

// Aeonisk-Specific Skills
export const AEONISK_SKILLS = [
  'Astral Arts', 'Magick Theory', 'Intimacy Ritual', 
  'Corporate Influence', 'Debt Law', 'Pilot', 'Drone Operation'
];

// Standard Skills (modern setting)
export const STANDARD_SKILLS = [
  'Academics', 'Area Lore', 'Art', 'Athletics', 'Awareness', 'Brawl',
  'Charm', 'Computers', 'Craft', 'Drive', 'First Aid', 'Guile',
  'Guns', 'Intimidation', 'Investigation', 'Language', 'Leadership',
  'Medicine', 'Melee', 'Navigation', 'Outdoors', 'Perception',
  'Persuasion', 'Pilot', 'Profession', 'Religion', 'Science',
  'Sleight', 'Stealth', 'Survival', 'Swimming', 'Teaching',
  'Technology', 'Trade', 'Throw', 'Tracking'
];

// Knowledge Skills
export const KNOWLEDGE_SKILLS = [
  'Anthropology', 'Archaeology', 'Architecture', 'Art History',
  'Astronomy', 'Biology', 'Chemistry', 'Economics', 'Engineering',
  'Geography', 'Geology', 'History', 'Law', 'Linguistics',
  'Mathematics', 'Meteorology', 'Military Science', 'Music',
  'Philosophy', 'Physics', 'Political Science', 'Psychology',
  'Sociology', 'Theology', 'Zoology'
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
    skills: {},
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

export function validateCharacter(character: Character): { valid: boolean; errors: string[] } {
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
  
  for (const [attr, value] of Object.entries(character.attributes)) {
    if (value > allocation.attributes.maxAttribute) {
      errors.push(`${attr} cannot exceed ${allocation.attributes.maxAttribute}`);
    }
    if (value < 1) {
      errors.push(`${attr} cannot be less than 1`);
    }
  }
  
  // Check skills are within bounds
  for (const [skill, value] of Object.entries(character.skills)) {
    if (value > allocation.experience.maxSkill) {
      errors.push(`${skill} cannot exceed ${allocation.experience.maxSkill}`);
    }
    if (value < 0) {
      errors.push(`${skill} cannot be negative`);
    }
  }
  
  // Check advantages/disadvantages balance
  const advantageCost = character.advantages?.reduce((sum, adv) => sum + adv.cost, 0) || 0;
  const disadvantagePoints = character.disadvantages?.reduce((sum, dis) => sum + Math.abs(dis.cost), 0) || 0;
  const totalAdvantagePoints = allocation.advantages.points + disadvantagePoints;
  
  if (advantageCost > totalAdvantagePoints) {
    errors.push(`Advantage cost (${advantageCost}) exceeds available points (${totalAdvantagePoints})`);
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