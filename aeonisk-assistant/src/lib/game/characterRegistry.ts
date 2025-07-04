import type { Character } from '../../types';

/**
 * CharacterRegistry manages all characters in the game session.
 * This includes player characters, NPCs, and AI companions.
 */
export class CharacterRegistry {
  private characters: Map<string, Character>;
  private activePlayerName: string | null;

  constructor() {
    this.characters = new Map();
    this.activePlayerName = null;
  }

  /**
   * Add a character to the registry
   */
  addCharacter(character: Character): void {
    if (!character.name) {
      throw new Error('Character must have a name');
    }
    this.characters.set(character.name, character);
    
    // If this is the first character added, make it the active player
    if (this.characters.size === 1) {
      this.activePlayerName = character.name;
    }
  }

  /**
   * Get a character by name
   */
  getCharacter(name: string): Character | undefined {
    return this.characters.get(name);
  }

  /**
   * Get the active player character
   */
  getActivePlayer(): Character | undefined {
    if (!this.activePlayerName) return undefined;
    return this.characters.get(this.activePlayerName);
  }

  /**
   * Set the active player by name
   */
  setActivePlayer(name: string): void {
    if (!this.characters.has(name)) {
      throw new Error(`Character ${name} not found in registry`);
    }
    this.activePlayerName = name;
  }

  /**
   * Remove a character from the registry
   */
  removeCharacter(name: string): boolean {
    const removed = this.characters.delete(name);
    
    // If we removed the active player, set a new one
    if (removed && this.activePlayerName === name) {
      this.activePlayerName = this.characters.size > 0 
        ? this.characters.keys().next().value ?? null
        : null;
    }
    
    return removed;
  }

  /**
   * List all characters
   */
  listAllCharacters(): Character[] {
    return Array.from(this.characters.values());
  }

  /**
   * Export a character to JSON
   */
  exportCharacter(name: string): string {
    const character = this.characters.get(name);
    if (!character) {
      throw new Error(`Character ${name} not found`);
    }
    return JSON.stringify(character, null, 2);
  }

  /**
   * Export a character to YAML format for dataset contribution
   */
  exportCharacterToYAML(name: string): string {
    const character = this.characters.get(name);
    if (!character) {
      throw new Error(`Character ${name} not found`);
    }

    // Convert to YAML format matching the dataset structure
    const yaml = `- character_name: "${character.name}"
  player_name: "${character.name || ''}"
  campaign: "${character.origin_faction || ''}"
  game_master: ""
  creation_date: "${new Date().toISOString().split('T')[0]}"
  
  character_level_type: "${character.character_level_type || 'Skilled'}"
  point_pool_priority:
    primary: "Experience"
    secondary: "Attributes"
    tertiary: "Advantages"
  
  origin_faction: "${character.origin_faction || 'Freeborn'}"
  tech_level_character: "${character.tech_level || 'Aeonisk Standard'}"
  
  primary_attributes:
    strength: ${character.attributes.strength}
    health: ${character.attributes.health}
    agility: ${character.attributes.agility}
    dexterity: ${character.attributes.dexterity}
    perception: ${character.attributes.perception}
    intelligence: ${character.attributes.intelligence}
    empathy: ${character.attributes.empathy}
    willpower: ${character.attributes.willpower}
  
  secondary_attributes:
    size: ${character.secondary_attributes?.size || 0}
    soak_base: ${character.secondary_attributes?.soak || 0}
    move_base: ${character.secondary_attributes?.move || 0}
  
  talents:
    athletics: ${character.talents.athletics}
    awareness: ${character.talents.awareness}
    brawl: ${character.talents.brawl}
    charm: ${character.talents.charm}
    guile: ${character.talents.guile}
    sleight: ${character.talents.sleight}
    stealth: ${character.talents.stealth}
    throw: ${character.talents.throw}
  
  standard_skills:${Object.entries(character.skills).filter(([k, v]) => v && v > 0).length > 0 ? '\n' + Object.entries(character.skills).filter(([k, v]) => v && v > 0).map(([k, v]) => `    ${k}: ${v}`).join('\n') : ' {}'}
  
  languages:
    native_language_name: "${character.languages.native_language}"
    native_language_level: ${character.languages.native_level}
    other_languages:${character.languages.other_languages && character.languages.other_languages.length > 0 ? '\n' + character.languages.other_languages.map(l => `      - language_name: "${l.name}"\n        level: ${l.level}`).join('\n') : ' []'}
  
  techniques:${character.techniques && character.techniques.length > 0 ? '\n' + character.techniques.map(t => `    - name: "${t.name}"\n      skill_basis: "${t.skill_basis}"\n      cost_level: ${t.cost_level}\n      description: "${t.description}"`).join('\n') : ' []'}
  
  advantages:${character.advantages && character.advantages.length > 0 ? '\n' + character.advantages.map(a => `    - name: "${a.name}"\n      cost_level: ${a.cost || 0}\n      description: "${a.description}"`).join('\n') : ' []'}
  
  disadvantages:${character.disadvantages && character.disadvantages.length > 0 ? '\n' + character.disadvantages.map(d => `    - name: "${d.name}"\n      cost_level: ${d.cost || 0}\n      description: "${d.description}"`).join('\n') : ' []'}
  
  aeonisk_data:
    void_score: ${character.voidScore}
    soulcredit: ${character.soulcredit}
    true_will:
      declared: ${character.trueWill ? true : false}
      statement: "${character.trueWill || ''}"
      alignment_bonus_active: ${character.trueWill ? true : false}
    bonds:${character.bonds.length > 0 ? '\n' + character.bonds.map(b => `      - name: "${b.name}"\n        type: "${b.type}"\n        status: "${b.status}"`).join('\n') : ' []'}
    primary_ritual_item:${character.primary_ritual_item ? `
      name: "${character.primary_ritual_item.name}"
      description: "${character.primary_ritual_item.description}"
      effects_if_lost: "${character.primary_ritual_item.effects_if_lost}"` : ' null'}
    offerings_carried:${character.offerings && character.offerings.length > 0 ? '\n' + character.offerings.map(o => `      - offering_name: "${o.name}"\n        description: "${o.description}"`).join('\n') : ' []'}`;

    return yaml;
  }

  /**
   * Import a character from JSON
   */
  importCharacter(data: string): Character {
    try {
      const character = JSON.parse(data) as Character;
      
      // Validate required fields
      if (!character.name || !character.attributes || !character.talents) {
        throw new Error('Invalid character data: missing required fields');
      }
      
      // Ensure all required attributes are present
      const requiredAttributes = ['strength', 'health', 'agility', 'dexterity', 'perception', 'intelligence', 'empathy', 'willpower'];
      for (const attr of requiredAttributes) {
        if (!(attr in character.attributes)) {
          throw new Error(`Invalid character data: missing attribute ${attr}`);
        }
      }
      
      // Ensure all required talents are present
      const requiredTalents = ['athletics', 'awareness', 'brawl', 'charm', 'guile', 'sleight', 'stealth', 'throw'];
      for (const talent of requiredTalents) {
        if (!(talent in character.talents)) {
          throw new Error(`Invalid character data: missing talent ${talent}`);
        }
      }
      
      // Set defaults for optional fields
      character.advantages = character.advantages || [];
      character.disadvantages = character.disadvantages || [];
      character.skills = character.skills || {};
      character.secondary_attributes = character.secondary_attributes || {
        size: 5,
        soak: 12,
        move: character.attributes.strength + character.attributes.agility + 6
      };
      character.languages = character.languages || {
        native_language: 'Common',
        native_level: 4
      };
      character.bonds = character.bonds || [];
      
      this.addCharacter(character);
      return character;
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error('Invalid JSON format');
      }
      throw error;
    }
  }

  /**
   * Clear all characters from the registry
   */
  clear(): void {
    this.characters.clear();
    this.activePlayerName = null;
  }

  /**
   * Get the number of characters in the registry
   */
  size(): number {
    return this.characters.size;
  }

  /**
   * Check if a character exists in the registry
   */
  hasCharacter(name: string): boolean {
    return this.characters.has(name);
  }

  /**
   * Get all character names
   */
  getCharacterNames(): string[] {
    return Array.from(this.characters.keys());
  }

}

// Singleton instance
export const characterRegistry = new CharacterRegistry();

// Function to get the singleton instance (for compatibility)
export function getCharacterRegistry(): CharacterRegistry {
  return characterRegistry;
}
