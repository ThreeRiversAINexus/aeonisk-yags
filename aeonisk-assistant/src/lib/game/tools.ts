import type { Character, AIPlayer, Ritual, Session, Dreamline, Tool } from '../../types';
import { characterRegistry } from './characterRegistry';
import {
  createDefaultCharacter, 
  validateCharacter, 
  calculateExperienceCost,
  getAvailableAdvantages,
  getAvailableDisadvantages,
  getAvailableTechniques,
  getAvailableFamiliarities,
  calculatePriorityAllocation,
  getAllAvailableSkills,
  getSkillsByCategory
} from './characterCreation';
import {
  resolveRitual,
  canCastRitual,
  getAvailableRituals,
  getRitualByName,
  calculateVoidInfluence,
  checkVoidSpike
} from './ritualSystem';
import {
  generateAIPersonality,
  generatePlayerGoals,
  generateDecisionStrategy,
  makeAIDecision,
  decideRitualCasting,
  generateNPC,
  generateDreamline,
  runAISession
} from './aiDM';
import {
  exportSessionToDataset,
  exportCharacterToYAML,
  exportSessionToJSONL,
  exportToFineTuneFormat,
  exportAnalysisData,
  validateDatasetEntry,
  generateDatasetMetadata
} from './datasetExport';

/**
 * Roll YAGS dice and calculate successes
 */
export function rollDice(
  diceCount: number,
  targetNumber: number = 15,
  advantage: boolean = false,
  disadvantage: boolean = false
): { result: number; dice: number[]; successes: number } {
  const dice: number[] = [];
  
  // Roll the dice
  for (let i = 0; i < diceCount; i++) {
    dice.push(Math.floor(Math.random() * 20) + 1);
  }
  
  // Sort dice in descending order
  dice.sort((a, b) => b - a);
  
  // Calculate result based on advantage/disadvantage
  let result: number;
  if (advantage && dice.length >= 2) {
    // Take sum of two highest
    result = dice[0] + dice[1];
  } else if (disadvantage && dice.length >= 2) {
    // Take sum of two lowest
    result = dice[dice.length - 1] + dice[dice.length - 2];
  } else {
    // Normal: sum all dice
    result = dice.reduce((sum, die) => sum + die, 0);
  }
  
  // Calculate successes (every 5 points over target)
  const successes = Math.max(0, Math.floor((result - targetNumber) / 5) + 1);
  
  return { result, dice, successes };
}

/**
 * Execute a skill check for a character
 */
export function executeSkillCheck(
  characterName: string,
  skill: string,
  stat: string,
  difficulty: number = 15,
  modifiers: { advantage?: boolean; disadvantage?: boolean; bonus?: number } = {}
): { 
  success: boolean; 
  result: number; 
  dice: number[]; 
  successes: number; 
  description: string;
  characterFound: boolean;
} {
  // Get character from registry
  const character = characterRegistry.getCharacter(characterName);
  
  if (!character) {
    // Fallback if character not found
    const fallbackResult = rollDice(3, difficulty, modifiers.advantage, modifiers.disadvantage);
    return {
      success: fallbackResult.successes > 0,
      result: fallbackResult.result + (modifiers.bonus || 0),
      dice: fallbackResult.dice,
      successes: fallbackResult.successes,
      description: `Rolling 3d20 (fallback - character "${characterName}" not found) vs difficulty ${difficulty}`,
      characterFound: false
    };
  }
  
  // Get attribute value
  const statValue = character.attributes[stat.toLowerCase() as keyof typeof character.attributes] || 3;
  
  // Get skill value - check both talents and skills
  const skillKey = skill.toLowerCase().replace(/\s+/g, '_');
  let skillValue = 0;
  
  // First check if it's a talent
  if (character.talents && skillKey in character.talents) {
    skillValue = character.talents[skillKey as keyof typeof character.talents] || 0;
  }
  // Then check if it's a skill
  else if (character.skills && skillKey in character.skills) {
    skillValue = character.skills[skillKey as keyof typeof character.skills] || 0;
  }
  // Handle special mappings
  else {
    // Map alternative skill names
    const alternativeMap: Record<string, string> = {
      'astralarts': 'astral_arts',
      'astral arts': 'astral_arts',
      'magicktheory': 'magick_theory',
      'magick theory': 'magick_theory'
    };
    
    const mappedName = alternativeMap[skill.toLowerCase()] || skillKey;
    
    // Check talents first, then skills
    if (character.talents && mappedName in character.talents) {
      skillValue = character.talents[mappedName as keyof typeof character.talents] || 0;
    } else if (character.skills && mappedName in character.skills) {
      skillValue = character.skills[mappedName as keyof typeof character.skills] || 0;
    }
  }
  
  // Calculate dice pool
  const dicePool = statValue + skillValue;
  
  // Roll the dice
  const rollResult = rollDice(dicePool, difficulty, modifiers.advantage, modifiers.disadvantage);
  const finalResult = rollResult.result + (modifiers.bonus || 0);
  const finalSuccesses = Math.max(0, Math.floor((finalResult - difficulty) / 5) + 1);
  
  return {
    success: finalSuccesses > 0,
    result: finalResult,
    dice: rollResult.dice,
    successes: finalSuccesses,
    description: `${characterName} rolling ${stat} (${statValue}) + ${skill} (${skillValue}) = ${dicePool}d20 vs difficulty ${difficulty}`,
    characterFound: true
  };
}

/**
 * Game tools for the AI assistant to use
 */
export const aeoniskTools = {
  // Character Management
  createCharacter: (name: string, concept: string, faction?: string): Character => {
    const character = createDefaultCharacter();
    character.name = name;
    character.concept = concept;
    if (faction) character.origin_faction = faction;
    return character;
  },

  validateCharacter: (character: Character) => {
    return validateCharacter(character);
  },

  calculateExperienceCost: (character: Character) => {
    return calculateExperienceCost(character);
  },

  getAvailableAdvantages: (character: Character) => {
    return getAvailableAdvantages(character);
  },

  getAvailableDisadvantages: (character: Character) => {
    return getAvailableDisadvantages(character);
  },

  getAvailableTechniques: (character: Character) => {
    return getAvailableTechniques(character);
  },

  getAvailableFamiliarities: (character: Character) => {
    return getAvailableFamiliarities(character);
  },

  calculatePriorityAllocation: (campaignLevel: string, priorityPools: any) => {
    return calculatePriorityAllocation(campaignLevel as any, priorityPools);
  },

  // Dice Rolling (existing functionality)
  rollDice: (sides: number, count: number = 1): number[] => {
    const results: number[] = [];
    for (let i = 0; i < count; i++) {
      results.push(Math.floor(Math.random() * sides) + 1);
    }
    return results;
  },

  skillCheck: (character: Character, attribute: string, skill: string, difficulty: number = 20) => {
    const attrValue = character.attributes[attribute] || 3;
    const skillValue = character.skills[skill] || 0;
    const roll = Math.floor(Math.random() * 20) + 1;
    const total = attrValue * skillValue + roll;
    const success = total >= difficulty;
    const margin = success ? total - difficulty : difficulty - total;

    return {
      success,
      margin,
      total,
      roll,
      attribute: attrValue,
      skill: skillValue,
      difficulty,
      character: character.name
    };
  },

  // Ritual System
  castRitual: (ritualName: string, caster: Character, offering: string, participants: Character[] = []) => {
    const ritual = getRitualByName(ritualName);
    if (!ritual) {
      throw new Error(`Ritual "${ritualName}" not found`);
    }

    const validation = canCastRitual(ritual, caster, participants);
    if (!validation.canCast) {
      throw new Error(`Cannot cast ritual: ${validation.reasons.join(', ')}`);
    }

    return resolveRitual(ritual, caster, offering, participants);
  },

  getAvailableRituals: (character: Character) => {
    return getAvailableRituals(character);
  },

  calculateVoidInfluence: (voidScore: number) => {
    return calculateVoidInfluence(voidScore);
  },

  checkVoidSpike: (character: Character, voidGained: number) => {
    return checkVoidSpike(character, voidGained);
  },

  // AI DM System
  generateAIPlayer: (character: Character, faction: string): AIPlayer => {
    const personality = generateAIPersonality(faction);
    const goals = generatePlayerGoals(character, personality);
    const decisionStrategy = generateDecisionStrategy(personality);

    return {
      id: `ai-${Date.now()}`,
      character,
      personality,
      faction,
      goals,
      playStyle: personality.voidCuriosity > 6 ? 'void-seeker' : 
                 personality.bondPreference === 'seeks' ? 'bond-builder' : 'cautious',
      decisionMaking: decisionStrategy
    };
  },

  makeAIDecision: (player: AIPlayer, context: string, options: string[]) => {
    return makeAIDecision(player, context, options);
  },

  decideRitualCasting: (player: AIPlayer, availableRituals: Ritual[], situation: string) => {
    return decideRitualCasting(player, availableRituals, situation);
  },

  generateNPC: (faction: string, role: string) => {
    return generateNPC(faction, role);
  },

  generateDreamline: (theme: string, participants: AIPlayer[], config: any) => {
    return generateDreamline(theme, participants, config);
  },

  runAISession: (dreamline: Dreamline, aiPlayers: AIPlayer[], config: any) => {
    return runAISession(dreamline, aiPlayers, config);
  },

  // Dataset Export
  exportCharacterToYAML: (character: Character) => {
    return exportCharacterToYAML(character);
  },

  exportSessionToDataset: (session: Session, dreamline: Dreamline) => {
    return exportSessionToDataset(session, dreamline);
  },

  exportSessionToJSONL: (session: Session, dreamline: Dreamline) => {
    return exportSessionToJSONL(session, dreamline);
  },

  exportToFineTuneFormat: (sessions: Session[], dreamlines: Dreamline[]) => {
    return exportToFineTuneFormat(sessions, dreamlines);
  },

  exportAnalysisData: (sessions: Session[], dreamlines: Dreamline[]) => {
    return exportAnalysisData(sessions, dreamlines);
  },

  validateDatasetEntry: (entry: any) => {
    return validateDatasetEntry(entry);
  },

  generateDatasetMetadata: (sessions: Session[], dreamlines: Dreamline[]) => {
    return generateDatasetMetadata(sessions, dreamlines);
  },

  // Character Registry Integration
  getCharacter: (name: string) => {
    return characterRegistry.getCharacter(name);
  },

  getAllCharacters: () => {
    return characterRegistry.listAllCharacters();
  },

  addCharacter: (character: Character) => {
    return characterRegistry.addCharacter(character);
  },

  removeCharacter: (name: string) => {
    return characterRegistry.removeCharacter(name);
  },

  exportCharactersToYAML: () => {
    const characters = characterRegistry.listAllCharacters();
    return characters.map((char: Character) => exportCharacterToYAML(char)).join('\n---\n');
  },

  // Skill Management
  getAllAvailableSkills: () => {
    return getAllAvailableSkills();
  },

  getSkillsByCategory: () => {
    return getSkillsByCategory();
  }
};

// Tool definitions for AI integration
export const toolDefinitions: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'createCharacter',
      description: 'Create a new character with basic information',
      parameters: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Character name' },
          concept: { type: 'string', description: 'Character concept' },
          faction: { type: 'string', description: 'Character faction', enum: ['Sovereign Nexus', 'Tempest Industries', 'Arcane Genetics', 'Astral Commerce Group', 'Resonance Communes', 'Freeborn'] }
        },
        required: ['name', 'concept']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'validateCharacter',
      description: 'Validate a character against creation rules',
      parameters: {
        type: 'object',
        properties: {
          character: { type: 'object', description: 'Character object to validate' }
        },
        required: ['character']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'skillCheck',
      description: 'Perform a YAGS skill check',
      parameters: {
        type: 'object',
        properties: {
          characterName: { type: 'string', description: 'Name of the character' },
          attribute: { type: 'string', description: 'Attribute to use', enum: ['Strength', 'Health', 'Agility', 'Dexterity', 'Perception', 'Intelligence', 'Empathy', 'Willpower'] },
          skill: { type: 'string', description: 'Skill to use' },
          difficulty: { type: 'number', description: 'Difficulty target number', default: 20 }
        },
        required: ['characterName', 'attribute', 'skill']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'castRitual',
      description: 'Cast a ritual using Aeonisk ritual system',
      parameters: {
        type: 'object',
        properties: {
          ritualName: { type: 'string', description: 'Name of the ritual to cast' },
          casterName: { type: 'string', description: 'Name of the character casting the ritual' },
          offering: { type: 'string', description: 'Offering for the ritual' },
          participantNames: { type: 'array', items: { type: 'string' }, description: 'Names of ritual participants' }
        },
        required: ['ritualName', 'casterName', 'offering']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'getAvailableRituals',
      description: 'Get list of rituals available to a character',
      parameters: {
        type: 'object',
        properties: {
          characterName: { type: 'string', description: 'Name of the character' }
        },
        required: ['characterName']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'generateAIPlayer',
      description: 'Generate an AI player with personality and goals',
      parameters: {
        type: 'object',
        properties: {
          characterName: { type: 'string', description: 'Name of the character to convert to AI player' },
          faction: { type: 'string', description: 'Faction for the AI player' }
        },
        required: ['characterName', 'faction']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'runAISession',
      description: 'Run an AI-only session with multiple AI players',
      parameters: {
        type: 'object',
        properties: {
          dreamlineId: { type: 'string', description: 'ID of the dreamline to run' },
          aiPlayerIds: { type: 'array', items: { type: 'string' }, description: 'IDs of AI players to include' },
          config: { type: 'object', description: 'Session configuration' }
        },
        required: ['dreamlineId', 'aiPlayerIds']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'exportSessionData',
      description: 'Export session data in various formats',
      parameters: {
        type: 'object',
        properties: {
          sessionId: { type: 'string', description: 'ID of the session to export' },
          format: { type: 'string', description: 'Export format', enum: ['yaml', 'jsonl', 'finetune', 'analysis'] }
        },
        required: ['sessionId', 'format']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'getAllAvailableSkills',
      description: 'Get all available skills organized by category',
      parameters: {
        type: 'object',
        properties: {},
        required: []
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'getSkillsByCategory',
      description: 'Get skills organized by thematic categories for easier selection',
      parameters: {
        type: 'object',
        properties: {},
        required: []
      }
    }
  }
];

// Tool execution function
export function executeTool(toolName: string, parameters: any): any {
  switch (toolName) {
    case 'createCharacter':
      return aeoniskTools.createCharacter(parameters.name, parameters.concept, parameters.faction);
    
    case 'validateCharacter':
      return aeoniskTools.validateCharacter(parameters.character);
    
    case 'skillCheck':
      const character = aeoniskTools.getCharacter(parameters.characterName);
      if (!character) throw new Error(`Character ${parameters.characterName} not found`);
      return aeoniskTools.skillCheck(character, parameters.attribute, parameters.skill, parameters.difficulty);
    
    case 'castRitual':
      const caster = aeoniskTools.getCharacter(parameters.casterName);
      if (!caster) throw new Error(`Character ${parameters.casterName} not found`);
      const participants = (parameters.participantNames || []).map((name: string) => aeoniskTools.getCharacter(name)).filter(Boolean);
      return aeoniskTools.castRitual(parameters.ritualName, caster, parameters.offering, participants);
    
    case 'getAvailableRituals':
      const char = aeoniskTools.getCharacter(parameters.characterName);
      if (!char) throw new Error(`Character ${parameters.characterName} not found`);
      return aeoniskTools.getAvailableRituals(char);
    
    case 'generateAIPlayer':
      const baseChar = aeoniskTools.getCharacter(parameters.characterName);
      if (!baseChar) throw new Error(`Character ${parameters.characterName} not found`);
      return aeoniskTools.generateAIPlayer(baseChar, parameters.faction);
    
    case 'runAISession':
      // This would require more complex session management
      throw new Error('runAISession not yet implemented in tool execution');
    
    case 'exportSessionData':
      // This would require session storage
      throw new Error('exportSessionData not yet implemented in tool execution');
    
    case 'getAllAvailableSkills':
      return aeoniskTools.getAllAvailableSkills();
    
    case 'getSkillsByCategory':
      return aeoniskTools.getSkillsByCategory();
    
    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
}
