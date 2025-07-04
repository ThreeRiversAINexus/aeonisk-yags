import type { 
  Ritual, 
  RitualEffect, 
  RitualConsequence, 
  Character, 
  Bond,
  RitualRecord,
  VoidRecord
} from '../../types';

// Ritual Database
export const RITUALS: Ritual[] = [
  // Intimacy Rituals
  {
    name: 'Bond Formation',
    threshold: 18,
    offering: 'A shared memory or emotion',
    voidRisk: 0.1,
    soulcreditCost: 1,
    category: 'intimacy',
    effects: [
      {
        type: 'narrative',
        description: 'Creates a formal bond between participants',
        magnitude: 1,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'bond_strain',
        description: 'Bond may be unstable if participants are incompatible',
        probability: 0.2,
        severity: 3
      }
    ],
    bondRequirements: [
      {
        type: 'new_bond',
        description: 'Requires willing participants'
      }
    ]
  },
  {
    name: 'Bond Strengthening',
    threshold: 20,
    offering: 'A personal sacrifice or vulnerability',
    voidRisk: 0.05,
    soulcreditCost: 2,
    category: 'intimacy',
    effects: [
      {
        type: 'mechanical',
        description: 'Increases bond strength by 1',
        magnitude: 1,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'soulcredit_loss',
        description: 'May lose additional soulcredit if bond is weak',
        probability: 0.3,
        severity: 2
      }
    ],
    bondRequirements: [
      {
        type: 'existing_bond',
        description: 'Requires an existing bond',
        minimumStrength: 1
      }
    ]
  },
  
  // Astral Rituals
  {
    name: 'Astral Navigation',
    threshold: 22,
    offering: 'A map or navigational tool',
    voidRisk: 0.15,
    soulcreditCost: 1,
    category: 'astral',
    effects: [
      {
        type: 'world',
        description: 'Allows travel through astral currents',
        magnitude: 2,
        duration: 'scene'
      }
    ],
    consequences: [
      {
        type: 'void_gain',
        description: 'Risk of void corruption from astral exposure',
        probability: 0.25,
        severity: 4
      }
    ]
  },
  {
    name: 'Dream Communication',
    threshold: 20,
    offering: 'A personal dream or memory',
    voidRisk: 0.1,
    soulcreditCost: 1,
    category: 'astral',
    effects: [
      {
        type: 'narrative',
        description: 'Allows communication through dreams',
        magnitude: 1,
        duration: 'session'
      }
    ],
    consequences: [
      {
        type: 'narrative_complication',
        description: 'Dreams may become shared or distorted',
        probability: 0.2,
        severity: 2
      }
    ]
  },
  
  // Void Rituals
  {
    name: 'Void Channeling',
    threshold: 25,
    offering: 'A piece of your soul or memory',
    voidRisk: 0.4,
    soulcreditCost: 3,
    category: 'void',
    effects: [
      {
        type: 'mechanical',
        description: 'Gain temporary void powers',
        magnitude: 3,
        duration: 'scene'
      }
    ],
    consequences: [
      {
        type: 'void_gain',
        description: 'High risk of void corruption',
        probability: 0.6,
        severity: 8
      },
      {
        type: 'soulcredit_loss',
        description: 'Significant soulcredit cost',
        probability: 0.8,
        severity: 5
      }
    ]
  },
  {
    name: 'Void Purification',
    threshold: 28,
    offering: 'A pure memory or emotion',
    voidRisk: 0.2,
    soulcreditCost: 4,
    category: 'void',
    effects: [
      {
        type: 'character',
        description: 'Reduces void score by 1',
        magnitude: 1,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'narrative_complication',
        description: 'Purification process is painful and traumatic',
        probability: 0.7,
        severity: 6
      }
    ]
  },
  
  // Faction Rituals
  {
    name: 'Sovereign Recognition',
    threshold: 24,
    offering: 'Proof of service or loyalty',
    voidRisk: 0.05,
    soulcreditCost: 2,
    category: 'faction',
    factionRestrictions: ['Sovereign Nexus'],
    effects: [
      {
        type: 'narrative',
        description: 'Gain recognition and access within Sovereign Nexus',
        magnitude: 2,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'bond_strain',
        description: 'May create obligations to the Sovereign',
        probability: 0.4,
        severity: 4
      }
    ]
  },
  {
    name: 'ArcGen Enhancement',
    threshold: 26,
    offering: 'A sample of your genetic material',
    voidRisk: 0.15,
    soulcreditCost: 3,
    category: 'faction',
    factionRestrictions: ['Arcane Genetics'],
    effects: [
      {
        type: 'character',
        description: 'Gain a physical enhancement',
        magnitude: 2,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'narrative_complication',
        description: 'Enhancement may have unforeseen side effects',
        probability: 0.5,
        severity: 5
      }
    ]
  },
  
  // Transformation Rituals
  {
    name: 'Will Alignment',
    threshold: 30,
    offering: 'Your current purpose or goal',
    voidRisk: 0.1,
    soulcreditCost: 5,
    category: 'transformation',
    effects: [
      {
        type: 'character',
        description: 'Align your will with your true purpose',
        magnitude: 3,
        duration: 'permanent'
      }
    ],
    consequences: [
      {
        type: 'narrative_complication',
        description: 'Alignment may change your personality or goals',
        probability: 0.3,
        severity: 7
      }
    ]
  }
];

// Ritual Resolution Functions
export function resolveRitual(
  ritual: Ritual,
  caster: Character,
  offering: string,
  participants: Character[] = []
): {
  success: boolean;
  margin: number;
  effects: RitualEffect[];
  consequences: RitualConsequence[];
  voidGained: number;
  soulcreditCost: number;
  record: RitualRecord;
} {
  // Calculate ritual roll
  const willpower = caster.attributes.Willpower || 3;
  const astralArts = caster.skills['Astral Arts'] || 0;
  const roll = Math.floor(Math.random() * 20) + 1;
  const total = willpower * astralArts + roll;
  
  const success = total >= ritual.threshold;
  const margin = success ? total - ritual.threshold : ritual.threshold - total;
  
  // Determine effects based on success margin
  const effects: RitualEffect[] = [];
  if (success) {
    for (const effect of ritual.effects) {
      const magnitude = Math.max(1, Math.floor(margin / 5) + effect.magnitude);
      effects.push({
        ...effect,
        magnitude
      });
    }
  }
  
  // Determine consequences
  const consequences: RitualConsequence[] = [];
  let voidGained = 0;
  let soulcreditCost = ritual.soulcreditCost;
  
  // Check for void gain
  if (Math.random() < ritual.voidRisk) {
    voidGained = 1;
    consequences.push({
      type: 'void_gain',
      description: 'Void corruption from ritual casting',
      probability: ritual.voidRisk,
      severity: 5
    });
  }
  
  // Check for additional consequences
  for (const consequence of ritual.consequences) {
    if (Math.random() < consequence.probability) {
      consequences.push(consequence);
      
      if (consequence.type === 'void_gain') {
        voidGained += Math.floor(consequence.severity / 2);
      } else if (consequence.type === 'soulcredit_loss') {
        soulcreditCost += Math.floor(consequence.severity / 2);
      }
    }
  }
  
  // Create ritual record
  const record: RitualRecord = {
    caster: caster.name,
    ritual: ritual.name,
    offering,
    threshold: ritual.threshold,
    roll: total,
    success,
    margin,
    void_gained: voidGained,
    soulcredit_cost: soulcreditCost,
    effects,
    consequences,
    timestamp: new Date()
  };
  
  return {
    success,
    margin,
    effects,
    consequences,
    voidGained,
    soulcreditCost,
    record
  };
}

// Ritual Validation Functions
export function canCastRitual(ritual: Ritual, caster: Character, participants: Character[] = []): {
  canCast: boolean;
  reasons: string[];
} {
  const reasons: string[] = [];
  
  // Check faction restrictions
  if (ritual.factionRestrictions && ritual.factionRestrictions.length > 0) {
    const casterFaction = caster.origin_faction;
    if (!casterFaction || !ritual.factionRestrictions.includes(casterFaction)) {
      reasons.push(`Ritual restricted to factions: ${ritual.factionRestrictions.join(', ')}`);
    }
  }
  
  // Check bond requirements
  if (ritual.bondRequirements) {
    for (const requirement of ritual.bondRequirements) {
      if (requirement.type === 'existing_bond') {
        const hasBond = caster.bonds.some(bond => bond.status === 'Active');
        if (!hasBond) {
          reasons.push('Ritual requires an existing bond');
        }
      } else if (requirement.type === 'bond_strength' && requirement.minimumStrength) {
        const strongBond = caster.bonds.some(bond => 
          bond.status === 'Active' && (bond.strength || 0) >= requirement.minimumStrength
        );
        if (!strongBond) {
          reasons.push(`Ritual requires a bond with strength ${requirement.minimumStrength}+`);
        }
      }
    }
  }
  
  // Check soulcredit
  if (caster.soulcredit < ritual.soulcreditCost) {
    reasons.push(`Insufficient soulcredit (${caster.soulcredit}/${ritual.soulcreditCost})`);
  }
  
  // Check void score (some rituals may be restricted)
  if (caster.voidScore >= 8) {
    reasons.push('Void corruption too high for ritual casting');
  }
  
  return {
    canCast: reasons.length === 0,
    reasons
  };
}

// Ritual Effect Application
export function applyRitualEffects(
  ritual: Ritual,
  effects: RitualEffect[],
  caster: Character,
  participants: Character[] = []
): {
  updatedCaster: Character;
  updatedParticipants: Character[];
  voidRecords: VoidRecord[];
} {
  const updatedCaster = { ...caster };
  const updatedParticipants = participants.map(p => ({ ...p }));
  const voidRecords: VoidRecord[] = [];
  
  for (const effect of effects) {
    switch (effect.type) {
      case 'character':
        if (effect.description.includes('void score')) {
          const previousVoid = updatedCaster.voidScore;
          updatedCaster.voidScore = Math.max(0, Math.min(10, previousVoid - effect.magnitude));
          voidRecords.push({
            character: updatedCaster.name,
            previous_score: previousVoid,
            new_score: updatedCaster.voidScore,
            source: ritual.name,
            ritual: ritual.name,
            timestamp: new Date()
          });
        }
        break;
        
      case 'narrative':
        // Narrative effects are handled by the GM/AI
        break;
        
      case 'mechanical':
        // Mechanical effects are applied to character stats
        break;
        
      case 'world':
        // World effects are handled by the GM/AI
        break;
    }
  }
  
  return {
    updatedCaster,
    updatedParticipants,
    voidRecords
  };
}

// Ritual Discovery and Learning
export function getAvailableRituals(character: Character): Ritual[] {
  return RITUALS.filter(ritual => {
    const validation = canCastRitual(ritual, character);
    return validation.canCast;
  });
}

export function getRitualByCategory(category: Ritual['category']): Ritual[] {
  return RITUALS.filter(ritual => ritual.category === category);
}

export function getRitualByName(name: string): Ritual | undefined {
  return RITUALS.find(ritual => ritual.name === name);
}

// Void Management
export function calculateVoidInfluence(voidScore: number): {
  passiveEffects: string[];
  voidSpikeThreshold: number;
} {
  const passiveEffects: string[] = [];
  let voidSpikeThreshold = 10;
  
  if (voidScore >= 5) {
    passiveEffects.push('Reality begins to warp around you');
    voidSpikeThreshold = 8;
  }
  
  if (voidScore >= 7) {
    passiveEffects.push('Others can sense your corruption');
    voidSpikeThreshold = 6;
  }
  
  if (voidScore >= 9) {
    passiveEffects.push('Void entities may be drawn to you');
    voidSpikeThreshold = 4;
  }
  
  return {
    passiveEffects,
    voidSpikeThreshold
  };
}

export function checkVoidSpike(character: Character, voidGained: number): {
  spikeOccurs: boolean;
  spikeEffects: string[];
} {
  const { voidSpikeThreshold } = calculateVoidInfluence(character.voidScore);
  
  if (voidGained >= voidSpikeThreshold) {
    return {
      spikeOccurs: true,
      spikeEffects: [
        'Reality distortion intensifies',
        'Void entities may manifest',
        'Other characters may be affected',
        'Ritual consequences are amplified'
      ]
    };
  }
  
  return {
    spikeOccurs: false,
    spikeEffects: []
  };
} 