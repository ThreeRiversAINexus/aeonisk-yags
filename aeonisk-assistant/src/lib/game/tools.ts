import type { Character, Tool } from '../../types';
import { characterRegistry } from './characterRegistry';

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
  if (skillKey in character.talents) {
    skillValue = character.talents[skillKey as keyof typeof character.talents] || 0;
  }
  // Then check if it's a skill
  else if (skillKey in character.skills) {
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
    if (mappedName in character.talents) {
      skillValue = character.talents[mappedName as keyof typeof character.talents] || 0;
    } else if (mappedName in character.skills) {
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
export const gameTools: Tool[] = [
  {
    type: 'function',
    function: {
      name: 'roll_dice',
      description: 'Roll dice for YAGS system. Returns the result and number of successes.',
      parameters: {
        type: 'object',
        properties: {
          count: {
            type: 'number',
            description: 'Number of d20s to roll'
          },
          target: {
            type: 'number',
            description: 'Target number to beat (default: 15)'
          },
          advantage: {
            type: 'boolean',
            description: 'Roll with advantage (sum two highest dice)'
          },
          disadvantage: {
            type: 'boolean',
            description: 'Roll with disadvantage (sum two lowest dice)'
          }
        },
        required: ['count']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'skill_check',
      description: 'Perform a skill check for a character using their actual stats and skills.',
      parameters: {
        type: 'object',
        properties: {
          character: {
            type: 'string',
            description: 'Name of the character making the check'
          },
          skill: {
            type: 'string',
            description: 'Skill being used (e.g., Athletics, Stealth, Social)'
          },
          stat: {
            type: 'string',
            description: 'Attribute being used (e.g., Strength, Dexterity, Intelligence)'
          },
          difficulty: {
            type: 'number',
            description: 'Difficulty of the check (default: 15)'
          },
          advantage: {
            type: 'boolean',
            description: 'Roll with advantage'
          },
          disadvantage: {
            type: 'boolean',
            description: 'Roll with disadvantage'
          },
          bonus: {
            type: 'number',
            description: 'Additional bonus or penalty to the roll'
          }
        },
        required: ['character', 'skill', 'stat']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'get_character_info',
      description: 'Get information about a character in the registry.',
      parameters: {
        type: 'object',
        properties: {
          name: {
            type: 'string',
            description: 'Name of the character'
          }
        },
        required: ['name']
      }
    }
  }
];

/**
 * Execute a game tool function
 */
export async function executeGameTool(
  toolName: string,
  args: Record<string, any>
): Promise<any> {
  switch (toolName) {
    case 'roll_dice': {
      const result = rollDice(
        args.count,
        args.target || 15,
        args.advantage || false,
        args.disadvantage || false
      );
      return {
        ...result,
        description: `Rolled ${args.count}d20: [${result.dice.join(', ')}] = ${result.result} (${result.successes} ${result.successes === 1 ? 'success' : 'successes'})`
      };
    }
    
    case 'skill_check': {
      const result = executeSkillCheck(
        args.character,
        args.skill,
        args.stat,
        args.difficulty || 15,
        {
          advantage: args.advantage,
          disadvantage: args.disadvantage,
          bonus: args.bonus
        }
      );
      
      return {
        ...result,
        fullDescription: `${result.description}\nRolled: [${result.dice.join(', ')}] = ${result.result} (${result.successes} ${result.successes === 1 ? 'success' : 'successes'})`
      };
    }
    
    case 'get_character_info': {
      const character = characterRegistry.getCharacter(args.name);
      if (!character) {
        return { error: `Character "${args.name}" not found in registry` };
      }
      
      return {
        name: character.name,
        origin_faction: character.origin_faction,
        concept: character.concept,
        attributes: character.attributes,
        talents: character.talents,
        skills: character.skills,
        advantages: character.advantages,
        disadvantages: character.disadvantages,
        void_score: character.void_score,
        soulcredit: character.soulcredit,
        bonds: character.bonds,
        true_will: character.true_will
      };
    }
    
    default:
      throw new Error(`Unknown tool: ${toolName}`);
  }
}
