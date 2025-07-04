import type { 
  Session, 
  Dreamline, 
  DatasetEntry, 
  PlayerRecord, 
  ActionRecord,
  RitualRecord,
  OutcomeRecord,
  MechanicalRecord,
  VoidRecord,
  BondRecord,
  DecisionRecord,
  Character,
  AIPlayer
} from '../../types';

// Dataset Export Functions
export function exportSessionToDataset(session: Session, dreamline: Dreamline): DatasetEntry {
  return {
    session_id: session.id,
    dreamline_id: dreamline.id,
    participants: session.participants.map(p => createPlayerRecord(p)),
    actions: session.actions,
    rituals: session.rituals,
    outcomes: session.outcomes,
    mechanical_data: session.mechanical_data,
    narrative_summary: session.narrative_summary,
    void_progression: session.void_progression,
    bond_changes: session.bond_changes
  };
}

function createPlayerRecord(player: { id: string; name: string; character?: Character }): PlayerRecord {
  return {
    id: player.id,
    name: player.name,
    character: player.character || createDefaultCharacterRecord(),
    personality: createDefaultPersonality(),
    decisions: []
  };
}

function createDefaultCharacterRecord(): Character {
  return {
    name: 'Unknown',
    concept: 'Default character',
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
    skills: {},
    voidScore: 0,
    soulcredit: 0,
    bonds: []
  };
}

function createDefaultPersonality() {
  return {
    riskTolerance: 5,
    bondPreference: 'neutral' as const,
    voidCuriosity: 5,
    factionLoyalty: 5,
    ritualConservatism: 5,
    socialAggressiveness: 5
  };
}

// YAML Export for Character Examples
export function exportCharacterToYAML(character: Character): string {
  const yaml = `name: "${character.name}"
concept: "${character.concept}"
character_level_type: "${character.character_level_type || 'Skilled'}"
origin_faction: "${character.origin_faction || 'Freeborn'}"
tech_level: "${character.tech_level || 'Tech8'}"

attributes:
  Strength: ${character.attributes.Strength}
  Health: ${character.attributes.Health}
  Agility: ${character.attributes.Agility}
  Dexterity: ${character.attributes.Dexterity}
  Perception: ${character.attributes.Perception}
  Intelligence: ${character.attributes.Intelligence}
  Empathy: ${character.attributes.Empathy}
  Willpower: ${character.attributes.Willpower}

secondary_attributes:
  Size: ${character.secondary_attributes?.Size || 5}
  Soak: ${character.secondary_attributes?.Soak || 12}
  Move: ${character.secondary_attributes?.Move || 12}

talents:
${Object.entries(character.talents || {}).map(([skill, level]) => `  ${skill}: ${level}`).join('\n')}

skills:
${Object.entries(character.skills || {}).map(([skill, level]) => `  ${skill}: ${level}`).join('\n')}

knowledges:
${Object.entries(character.knowledges || {}).map(([skill, level]) => `  ${skill}: ${level}`).join('\n')}

languages:
  native_language_name: "${character.languages?.native_language_name || 'Common'}"
  native_language_level: ${character.languages?.native_language_level || 4}
  other_languages:
${(character.languages?.other_languages || []).map(lang => `    - name: "${lang.name}"
      level: ${lang.level}`).join('\n')}

voidScore: ${character.voidScore}
soulcredit: ${character.soulcredit}

bonds:
${(character.bonds || []).map(bond => `  - name: "${bond.name}"
    type: "${bond.type}"
    status: "${bond.status}"
    strength: ${bond.strength || 1}
    partner: "${bond.partner || ''}"`).join('\n')}

trueWill: "${character.trueWill || ''}"

campaignLevel: "${character.campaignLevel || 'Skilled'}"

advantages:
${(character.advantages || []).map(adv => `  - name: "${adv.name}"
    cost: ${adv.cost}
    description: "${adv.description}"
    category: "${adv.category}"`).join('\n')}

disadvantages:
${(character.disadvantages || []).map(dis => `  - name: "${dis.name}"
    cost: ${dis.cost}
    description: "${dis.description}"
    category: "${dis.category}"`).join('\n')}

techniques:
${(character.techniques || []).map(tech => `  - name: "${tech.name}"
    cost: ${tech.cost}
    description: "${tech.description}"
    skill: "${tech.skill}"
    category: "${tech.category}"`).join('\n')}

familiarities:
${(character.familiarities || []).map(fam => `  - name: "${fam.name}"
    cost: ${fam.cost}
    skill: "${fam.skill}"
    description: "${fam.description}"`).join('\n')}

experiencePoints: ${character.experiencePoints || 0}
`;

  return yaml;
}

// JSONL Export for Training Data
export function exportSessionToJSONL(session: Session, dreamline: Dreamline): string {
  const entries: any[] = [];
  
  // Add session overview
  entries.push({
    type: 'session_overview',
    session_id: session.id,
    dreamline_id: dreamline.id,
    theme: dreamline.theme,
    participants: session.participants.map(p => p.name),
    narrative_summary: session.narrative_summary,
    void_influence: dreamline.void_influence,
    timestamp: session.timestamp
  });
  
  // Add actions
  for (const action of session.actions) {
    entries.push({
      type: 'action',
      session_id: session.id,
      actor: action.actor,
      action: action.action,
      target: action.target,
      parameters: action.parameters,
      outcome: action.outcome,
      success: action.success,
      margin: action.margin,
      timestamp: action.timestamp
    });
  }
  
  // Add rituals
  for (const ritual of session.rituals) {
    entries.push({
      type: 'ritual',
      session_id: session.id,
      caster: ritual.caster,
      ritual: ritual.ritual,
      offering: ritual.offering,
      threshold: ritual.threshold,
      roll: ritual.roll,
      success: ritual.success,
      margin: ritual.margin,
      void_gained: ritual.void_gained,
      soulcredit_cost: ritual.soulcredit_cost,
      effects: ritual.effects,
      consequences: ritual.consequences,
      timestamp: ritual.timestamp
    });
  }
  
  // Add outcomes
  for (const outcome of session.outcomes) {
    entries.push({
      type: 'outcome',
      session_id: session.id,
      outcome_type: outcome.type,
      description: outcome.description,
      mechanical_effects: outcome.mechanical_effects,
      narrative_impact: outcome.narrative_impact,
      void_influence: outcome.void_influence
    });
  }
  
  // Add void progression
  for (const voidRecord of session.void_progression) {
    entries.push({
      type: 'void_progression',
      session_id: session.id,
      character: voidRecord.character,
      previous_score: voidRecord.previous_score,
      new_score: voidRecord.new_score,
      source: voidRecord.source,
      ritual: voidRecord.ritual,
      timestamp: voidRecord.timestamp
    });
  }
  
  // Add bond changes
  for (const bondRecord of session.bond_changes) {
    entries.push({
      type: 'bond_change',
      session_id: session.id,
      character: bondRecord.character,
      bond_name: bondRecord.bond_name,
      previous_status: bondRecord.previous_status,
      new_status: bondRecord.new_status,
      strength_change: bondRecord.strength_change,
      reason: bondRecord.reason,
      timestamp: bondRecord.timestamp
    });
  }
  
  return entries.map(entry => JSON.stringify(entry)).join('\n');
}

// Fine-tuning Dataset Export
export function exportToFineTuneFormat(sessions: Session[], dreamlines: Dreamline[]): string {
  const conversations: any[] = [];
  
  for (const session of sessions) {
    const dreamline = dreamlines.find(d => d.id === session.dreamlineId);
    if (!dreamline) continue;
    
    // Create conversation format
    const conversation = {
      messages: [
        {
          role: 'system',
          content: `You are the AI DM for an Aeonisk campaign. The current dreamline theme is "${dreamline.theme}" with void influence level ${dreamline.void_influence}/10. 
          The session involves ${session.participants.map(p => p.name).join(', ')}. 
          Focus on narrative storytelling, ritual consequences, and the spiritual economy of soulcredit and void corruption.`
        },
        {
          role: 'user',
          content: `Generate a scenario description for this session based on the theme "${dreamline.theme}".`
        },
        {
          role: 'assistant',
          content: session.narrative_summary
        }
      ]
    };
    
    // Add action responses
    for (const action of session.actions) {
      conversation.messages.push({
        role: 'user',
        content: `${action.actor} attempts to ${action.action.toLowerCase()}.`
      });
      
      conversation.messages.push({
        role: 'assistant',
        content: `${action.outcome}. ${action.mechanicalEffect ? `Mechanical effects: ${JSON.stringify(action.mechanicalEffect)}` : ''}`
      });
    }
    
    conversations.push(conversation);
  }
  
  return conversations.map(conv => JSON.stringify(conv)).join('\n');
}

// Analysis Export
export function exportAnalysisData(sessions: Session[], dreamlines: Dreamline[]): {
  ritualAnalysis: any[];
  voidProgression: any[];
  bondDynamics: any[];
  playerBehavior: any[];
} {
  const ritualAnalysis: any[] = [];
  const voidProgression: any[] = [];
  const bondDynamics: any[] = [];
  const playerBehavior: any[] = [];
  
  for (const session of sessions) {
    // Analyze rituals
    for (const ritual of session.rituals) {
      ritualAnalysis.push({
        ritual_name: ritual.ritual,
        success_rate: ritual.success ? 1 : 0,
        margin: ritual.margin,
        void_gained: ritual.void_gained,
        soulcredit_cost: ritual.soulcredit_cost,
        session_id: session.id,
        dreamline_theme: dreamlines.find(d => d.id === session.dreamlineId)?.theme
      });
    }
    
    // Analyze void progression
    for (const voidRecord of session.void_progression) {
      voidProgression.push({
        character: voidRecord.character,
        void_change: voidRecord.new_score - voidRecord.previous_score,
        source: voidRecord.source,
        session_id: session.id,
        dreamline_theme: dreamlines.find(d => d.id === session.dreamlineId)?.theme
      });
    }
    
    // Analyze bond dynamics
    for (const bondRecord of session.bond_changes) {
      bondDynamics.push({
        character: bondRecord.character,
        bond_name: bondRecord.bond_name,
        status_change: `${bondRecord.previous_status} -> ${bondRecord.new_status}`,
        strength_change: bondRecord.strength_change || 0,
        reason: bondRecord.reason,
        session_id: session.id,
        dreamline_theme: dreamlines.find(d => d.id === session.dreamlineId)?.theme
      });
    }
    
    // Analyze player behavior
    const actionCounts: Record<string, number> = {};
    for (const action of session.actions) {
      actionCounts[action.actor] = (actionCounts[action.actor] || 0) + 1;
    }
    
    for (const [actor, count] of Object.entries(actionCounts)) {
      playerBehavior.push({
        player: actor,
        action_count: count,
        session_id: session.id,
        dreamline_theme: dreamlines.find(d => d.id === session.dreamlineId)?.theme
      });
    }
  }
  
  return {
    ritualAnalysis,
    voidProgression,
    bondDynamics,
    playerBehavior
  };
}

// Batch Export Functions
export function exportMultipleSessions(
  sessions: Session[],
  dreamlines: Dreamline[],
  format: 'yaml' | 'jsonl' | 'finetune' | 'analysis'
): string {
  switch (format) {
    case 'yaml':
      return sessions.map(session => {
        const dreamline = dreamlines.find(d => d.id === session.dreamlineId);
        return exportSessionToDataset(session, dreamline!);
      }).map(entry => JSON.stringify(entry, null, 2)).join('\n---\n');
    
    case 'jsonl':
      return sessions.map(session => {
        const dreamline = dreamlines.find(d => d.id === session.dreamlineId);
        return exportSessionToJSONL(session, dreamline!);
      }).join('\n');
    
    case 'finetune':
      return exportToFineTuneFormat(sessions, dreamlines);
    
    case 'analysis':
      const analysis = exportAnalysisData(sessions, dreamlines);
      return JSON.stringify(analysis, null, 2);
    
    default:
      throw new Error(`Unknown export format: ${format}`);
  }
}

// Validation Functions
export function validateDatasetEntry(entry: DatasetEntry): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (!entry.session_id) errors.push('Missing session_id');
  if (!entry.dreamline_id) errors.push('Missing dreamline_id');
  if (!entry.participants || entry.participants.length === 0) errors.push('No participants');
  if (!entry.narrative_summary) errors.push('Missing narrative summary');
  
  // Validate participants
  for (const participant of entry.participants) {
    if (!participant.name) errors.push('Participant missing name');
    if (!participant.character) errors.push('Participant missing character data');
  }
  
  // Validate actions
  for (const action of entry.actions) {
    if (!action.actor) errors.push('Action missing actor');
    if (!action.action) errors.push('Action missing action description');
    if (!action.timestamp) errors.push('Action missing timestamp');
  }
  
  return {
    valid: errors.length === 0,
    errors
  };
}

// Utility Functions
export function generateDatasetMetadata(
  sessions: Session[],
  dreamlines: Dreamline[]
): {
  total_sessions: number;
  total_dreamlines: number;
  date_range: { start: Date; end: Date };
  themes: string[];
  participants: string[];
  ritual_count: number;
  void_events: number;
  bond_events: number;
} {
  const allTimestamps = sessions.map(s => s.timestamp);
  const startDate = new Date(Math.min(...allTimestamps.map(t => t.getTime())));
  const endDate = new Date(Math.max(...allTimestamps.map(t => t.getTime())));
  
  const themes = [...new Set(dreamlines.map(d => d.theme))];
  const participants = [...new Set(sessions.flatMap(s => s.participants.map(p => p.name)))];
  
  const ritualCount = sessions.reduce((sum, s) => sum + s.rituals.length, 0);
  const voidEvents = sessions.reduce((sum, s) => sum + s.void_progression.length, 0);
  const bondEvents = sessions.reduce((sum, s) => sum + s.bond_changes.length, 0);
  
  return {
    total_sessions: sessions.length,
    total_dreamlines: dreamlines.length,
    date_range: { start: startDate, end: endDate },
    themes,
    participants,
    ritual_count: ritualCount,
    void_events: voidEvents,
    bond_events: bondEvents
  };
} 