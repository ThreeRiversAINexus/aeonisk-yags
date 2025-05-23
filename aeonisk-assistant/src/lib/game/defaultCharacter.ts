import type { Character } from '../../types';

export const DEFAULT_CHARACTER: Character = {
  // Core Identity
  name: 'New Character',
  player_name: '',
  campaign: '',
  origin_faction: 'Freeborn',
  concept: 'Adventurer',
  character_level_type: 'Skilled',
  tech_level: 'Aeonisk Standard',
  
  // YAGS Primary Attributes (8)
  attributes: {
    strength: 3,
    health: 3,
    agility: 3,
    dexterity: 3,
    perception: 3,
    intelligence: 3,
    empathy: 3,
    willpower: 3,
  },
  
  // YAGS Secondary Attributes
  secondary_attributes: {
    size: 5,
    soak: 12,
    move: 12, // Size 5 + Str 3 + Agi 3 + 1
  },
  
  // YAGS Talents (start at 2)
  talents: {
    athletics: 2,
    awareness: 2,
    brawl: 2,
    charm: 2,
    guile: 2,
    sleight: 2,
    stealth: 2,
    throw: 2,
  },
  
  // Skills (Knowledges, Standard, Aeonisk-specific)
  skills: {
    // Start with no specialized skills
  },
  
  // Languages
  languages: {
    native_language: 'Common',
    native_level: 4,
    other_languages: [],
  },
  
  // Techniques & Advantages
  techniques: [],
  advantages: [],
  disadvantages: [],
  
  // Aeonisk Specific
  void_score: 0,
  soulcredit: 0,
  
  true_will: {
    declared: false,
    statement: '',
    alignment_bonus_active: false,
  },
  
  bonds: [],
  
  primary_ritual_item: {
    name: 'Personal Focus',
    description: 'A simple object that serves as a ritual focus',
    effects_if_lost: '-2 to Ritual Rolls',
  },
  
  offerings: [
    {
      name: 'Basic Offering',
      description: 'A simple consumable for minor rituals',
    },
  ],
  
  // Status Tracking
  wounds: {
    current_level: 'OK',
    current_penalty: 0,
  },
  stuns: {
    current_level: 'OK',
    current_penalty: 0,
  },
  fatigue: {
    current_level: 'OK',
    current_penalty: 0,
  },
};

/**
 * Creates a character based on origin faction
 */
export function createCharacterByFaction(faction: string): Character {
  const character = { ...DEFAULT_CHARACTER };
  
  switch (faction) {
    case 'Sovereign Nexus':
      character.origin_faction = 'Sovereign Nexus';
      // +1 Willpower or Intelligence
      character.attributes.willpower = 4;
      break;
      
    case 'Astral Commerce Group':
      character.origin_faction = 'Astral Commerce Group';
      // +1 Intelligence or Empathy
      character.attributes.intelligence = 4;
      character.soulcredit = 1; // Start with +1 Soulcredit
      break;
      
    case 'Pantheon Security':
      character.origin_faction = 'Pantheon Security';
      // +1 Strength or Agility
      character.attributes.strength = 4;
      break;
      
    case 'Aether Dynamics':
      character.origin_faction = 'Aether Dynamics';
      // +1 Empathy or Perception
      character.attributes.perception = 4;
      break;
      
    case 'Arcane Genetics':
      character.origin_faction = 'Arcane Genetics';
      // +1 Health or Dexterity
      character.attributes.health = 4;
      break;
      
    case 'Tempest Industries':
      character.origin_faction = 'Tempest Industries';
      // +1 Dexterity or Perception
      character.attributes.dexterity = 4;
      break;
      
    case 'Freeborn':
    default:
      // Freeborn get +1 to any 3 attributes (for simplicity, STR, DEX, INT)
      character.attributes.strength = 4;
      character.attributes.dexterity = 4;
      character.attributes.intelligence = 4;
      break;
  }
  
  // Recalculate move based on new attributes
  character.secondary_attributes.move = 
    character.secondary_attributes.size + 
    character.attributes.strength + 
    character.attributes.agility + 1;
  
  return character;
}
