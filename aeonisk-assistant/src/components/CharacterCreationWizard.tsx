import React, { useState } from 'react';
import type { Character, CampaignLevel, PriorityPools } from '../types';
import { 
  CAMPAIGN_LEVELS, 
  YAGS_ATTRIBUTES, 
  YAGS_TALENTS,
  AEONISK_SKILLS,
  STANDARD_SKILLS,
  KNOWLEDGE_SKILLS,
  PROFESSIONAL_SKILLS,
  VEHICLE_SKILLS,
  calculatePriorityAllocation,
  createDefaultCharacter,
  validateCharacter,
  getAllAvailableSkills
} from '../lib/game/characterCreation';

interface CharacterCreationWizardProps {
  onComplete: (character: Character) => void;
  onCancel: () => void;
}

type WizardStep = 'concept' | 'faction' | 'campaign' | 'attributes' | 'skills' | 'review';

const AEONISK_FACTIONS = [
  {
    name: 'Sovereign Nexus',
    description: 'Theocratic matriarchy focused on order, ritual, and hierarchy.',
    attributeBonus: ['Willpower', 'Intelligence'],
    trait: 'Ritual Authority: +2 to resist ritual disruption or mental influence',
    startingSkills: ['Astral Arts', 'Religion'],
    soulcredit: 1,
    voidScore: 0,
    bondLimit: 3
  },
  {
    name: 'Astral Commerce Group',
    description: 'Financial entity that tracks and brokers Soulcredit, contracts, and ritual debt.',
    attributeBonus: ['Intelligence', 'Empathy'],
    trait: 'Contract-Bound: Start with +1 Soulcredit or one favorable minor contract',
    startingSkills: ['Corporate Influence', 'Debt Law'],
    soulcredit: 1,
    voidScore: 0,
    bondLimit: 3
  },
  {
    name: 'Pantheon Security',
    description: 'Privatized tactical force emphasizing loyalty and procedure.',
    attributeBonus: ['Strength', 'Agility'],
    trait: 'Tactical Protocol: Once per combat, automatically succeed on an Initiative roll',
    startingSkills: ['Tactics', 'Security Protocols'],
    soulcredit: 0,
    voidScore: 0,
    bondLimit: 3
  },
  {
    name: 'Aether Dynamics',
    description: 'Ecological-spiritual balance focused on leylines, harmony, and symbiosis.',
    attributeBonus: ['Empathy', 'Perception'],
    trait: 'Ley Sense: Can sense presence and mood of nearby ley lines',
    startingSkills: ['Astral Arts', 'Nature'],
    soulcredit: 0,
    voidScore: 0,
    bondLimit: 3
  },
  {
    name: 'Arcane Genetics',
    description: 'Biotech/ritual fusion focused on evolution and coded spirituality.',
    attributeBonus: ['Health', 'Dexterity'],
    trait: 'Bio-Stabilized: +2 to rolls resisting biological Void effects',
    startingSkills: ['Biotech', 'Magick Theory'],
    soulcredit: 0,
    voidScore: 1,
    bondLimit: 3
  },
  {
    name: 'Tempest Industries',
    description: 'Subversive syndicate dealing in stolen tech and forbidden ritual.',
    attributeBonus: ['Dexterity', 'Perception'],
    trait: 'Disruptor: +2 bonus when sabotaging rituals or tech',
    startingSkills: ['Hacking', 'Stealth'],
    soulcredit: -1,
    voidScore: 2,
    bondLimit: 2
  },
  {
    name: 'Freeborn',
    description: 'Outside faction structure. Rare, mistrusted, and feared.',
    attributeBonus: ['Any', 'Any'],
    trait: 'Wild Will: Can only form/maintain 1 Bond',
    startingSkills: ['Survival', 'Stealth'],
    soulcredit: 0,
    voidScore: 0,
    bondLimit: 1
  }
];

// Archetype templates (example)
const SKILL_ARCHETYPES: Record<string, Record<string, number>> = {
  Investigator: {
    Investigation: 4,
    Awareness: 3,
    Guile: 2,
    'Astral Arts': 2,
    'Magick Theory': 1,
    'Intimacy Ritual': 1,
    'Corporate Influence': 1,
    'Debt Law': 1,
    Pilot: 2,
    'Area Lore': 1,
    'First Aid': 1,
    Language: 1,
    Computers: 1,
    Technology: 1
  },
  Soldier: {
    Athletics: 3,
    Brawl: 3,
    Stealth: 2,
    Tactics: 2,
    'Security Protocols': 2,
    'First Aid': 1,
    'Awareness': 2,
    'Throw': 2,
    'Pilot': 1,
    'Area Lore': 1
  },
  Technomancer: {
    'Astral Arts': 3,
    'Magick Theory': 3,
    'Void Manipulation': 2,
    'Computers': 3,
    'Technology': 3,
    'Hacking': 2,
    'Awareness': 2,
    'First Aid': 1
  }
};

export function CharacterCreationWizard({ onComplete, onCancel }: CharacterCreationWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>('concept');
  const [character, setCharacter] = useState<Character>(createDefaultCharacter());
  const [selectedFaction, setSelectedFaction] = useState<string>('');
  const [campaignLevel, setCampaignLevel] = useState<CampaignLevel>('Skilled');
  const [priorityPools, setPriorityPools] = useState<PriorityPools>({
    attributes: 'Secondary',
    experience: 'Primary',
    advantages: 'Tertiary'
  });
  const [skillFilter, setSkillFilter] = useState('');
  const [freebornBonuses, setFreebornBonuses] = useState<string[]>([]);
  const [showAutoPick, setShowAutoPick] = useState(false);
  const [autoPickLoading, setAutoPickLoading] = useState(false);
  const [sortSkillsBy, setSortSkillsBy] = useState<'alpha' | 'value'>('alpha');

  const allocation = calculatePriorityAllocation(campaignLevel, priorityPools);
  const [spentPoints, setSpentPoints] = useState({
    attributes: 0,
    experience: 0,
    advantages: 0
  });

  const validation = validateCharacter(
    { ...character, campaignLevel, priorityPools },
    freebornBonuses
  );

  const updateCharacter = (updates: Partial<Character>) => {
    setCharacter(prev => ({ ...prev, ...updates }));
  };

  const handleFactionSelect = (factionName: string) => {
    const faction = AEONISK_FACTIONS.find(f => f.name === factionName);
    if (!faction) return;

    setSelectedFaction(factionName);
    updateCharacter({
      origin_faction: factionName,
      soulcredit: faction.soulcredit,
      voidScore: faction.voidScore
    });

    // Apply faction attribute bonuses
    const newAttributes = { ...character.attributes };
    faction.attributeBonus.forEach(attr => {
      if (attr === 'Any') return; // Handle Freeborn separately
      const attrKey = attr as keyof typeof newAttributes;
      if (newAttributes[attrKey]) {
        newAttributes[attrKey] = Math.min(8, newAttributes[attrKey] + 1);
      }
    });

    updateCharacter({ attributes: newAttributes });
  };

  const handleAttributeChange = (attr: string, value: number) => {
    const currentValue = character.attributes[attr as keyof typeof character.attributes] || 3;
    const baseValue = 3; // All attributes start at 3
    const currentCost = Math.max(0, currentValue - baseValue);
    const newCost = Math.max(0, value - baseValue);
    const costDifference = newCost - currentCost;

    if (spentPoints.attributes + costDifference > allocation.attributes.points) {
      return; // Not enough points
    }

    if (value > allocation.attributes.maxAttribute) {
      return; // Exceeds maximum
    }

    setSpentPoints(prev => ({
      ...prev,
      attributes: prev.attributes + costDifference
    }));

    updateCharacter({
      attributes: {
        ...character.attributes,
        [attr]: value
      }
    });
  };

  const handleSkillChange = (skill: string, value: number) => {
    const currentValue = character.skills[skill] || 0;
    const costDifference = value - currentValue;

    if (spentPoints.experience + costDifference > allocation.experience.points) {
      return; // Not enough points
    }

    if (value > allocation.experience.maxSkill) {
      return; // Exceeds maximum
    }

    setSpentPoints(prev => ({
      ...prev,
      experience: prev.experience + costDifference
    }));

    updateCharacter({
      skills: {
        ...character.skills,
        [skill]: value
      }
    });
  };

  const getFactionAttributeBonuses = (character: Character, freebornBonuses: string[]) => {
    const faction = AEONISK_FACTIONS.find(f => f.name === character.origin_faction);
    if (!faction) return {};
    if (faction.name === 'Freeborn') {
      // Freeborn: user picks two different attributes
      const bonuses: Record<string, number> = {};
      freebornBonuses.forEach(attr => {
        bonuses[attr] = (bonuses[attr] || 0) + 1;
      });
      return bonuses;
    }
    const bonuses: Record<string, number> = {};
    faction.attributeBonus.forEach(attr => {
      if (attr !== 'Any') bonuses[attr] = 1;
    });
    return bonuses;
  };

  const getTotalAttribute = (attr: string) => {
    const base = character.attributes[attr] || 3;
    const bonus = getFactionAttributeBonuses(character, freebornBonuses)[attr] || 0;
    return base + bonus;
  };

  const handleAutoPick = (archetype: string) => {
    setAutoPickLoading(true);
    setTimeout(() => {
      setCharacter(prev => ({
        ...prev,
        skills: {
          ...prev.skills,
          ...SKILL_ARCHETYPES[archetype]
        }
      }));
      setAutoPickLoading(false);
      setShowAutoPick(false);
    }, 500);
  };

  const handleAISuggest = () => {
    setAutoPickLoading(true);
    setTimeout(() => {
      // Placeholder: just pick Investigator for now
      setCharacter(prev => ({
        ...prev,
        skills: {
          ...prev.skills,
          ...SKILL_ARCHETYPES['Investigator']
        }
      }));
      setAutoPickLoading(false);
      setShowAutoPick(false);
    }, 800);
  };

  const renderConceptStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Character Concept</h3>
      <div>
        <label className="block text-sm font-medium mb-2">Name</label>
        <input
          type="text"
          value={character.name}
          onChange={(e) => updateCharacter({ name: e.target.value })}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Enter character name"
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-2">Concept</label>
        <textarea
          value={character.concept}
          onChange={(e) => updateCharacter({ concept: e.target.value })}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Describe your character concept..."
          rows={3}
        />
      </div>
    </div>
  );

  const renderFactionStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Choose Your Faction</h3>
      <div className="grid grid-cols-1 gap-4 max-h-96 overflow-y-auto">
        {AEONISK_FACTIONS.map((faction) => (
          <div
            key={faction.name}
            onClick={() => handleFactionSelect(faction.name)}
            className={`p-4 border rounded-lg cursor-pointer transition-colors ${
              selectedFaction === faction.name
                ? 'border-blue-500 bg-blue-900/20'
                : 'border-gray-600 hover:border-gray-500'
            }`}
          >
            <h4 className="font-semibold text-lg">{faction.name}</h4>
            <p className="text-sm text-gray-300 mb-2">{faction.description}</p>
            <div className="text-xs space-y-1">
              <p><strong>Attribute Bonus:</strong> {faction.attributeBonus.join(', ')}</p>
              <p><strong>Trait:</strong> {faction.trait}</p>
              <p><strong>Starting Skills:</strong> {faction.startingSkills.join(', ')}</p>
              <p><strong>Soulcredit:</strong> {faction.soulcredit}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderCampaignStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Campaign Level & Priority Pools</h3>
      
      <div>
        <label className="block text-sm font-medium mb-2">Campaign Level</label>
        <select
          value={campaignLevel}
          onChange={(e) => setCampaignLevel(e.target.value as CampaignLevel)}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="Mundane">Mundane</option>
          <option value="Skilled">Skilled</option>
          <option value="Exceptional">Exceptional</option>
          <option value="Heroic">Heroic</option>
        </select>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {(['attributes', 'experience', 'advantages'] as const).map((pool) => (
          <div key={pool}>
            <label className="block text-sm font-medium mb-2 capitalize">{pool}</label>
            <select
              value={priorityPools[pool]}
              onChange={(e) => setPriorityPools(prev => ({ ...prev, [pool]: e.target.value as any }))}
              className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="Primary">Primary</option>
              <option value="Secondary">Secondary</option>
              <option value="Tertiary">Tertiary</option>
            </select>
          </div>
        ))}
      </div>

      <div className="bg-gray-700 rounded p-4">
        <h4 className="font-semibold mb-2">Point Allocation</h4>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span>Attributes:</span>
            <span>{spentPoints.attributes}/{allocation.attributes.points} points</span>
          </div>
          <div className="flex justify-between">
            <span>Experience:</span>
            <span>{spentPoints.experience}/{allocation.experience.points} points</span>
          </div>
          <div className="flex justify-between">
            <span>Advantages:</span>
            <span>{spentPoints.advantages}/{allocation.advantages.points} points</span>
          </div>
        </div>
      </div>
    </div>
  );

  const renderAttributesStep = () => {
    const bonuses = getFactionAttributeBonuses(character, freebornBonuses);
    const isFreeborn = character.origin_faction === 'Freeborn';
    const availableAttributes = YAGS_ATTRIBUTES;
    return (
      <div className="space-y-4">
        <h3 className="text-xl font-semibold flex items-center gap-2">
          Attributes
          <span className="text-xs text-blue-300" title="You spend points on base attributes. Faction bonuses (including Freeborn) are added after and do not count against your pool.">
            (Bonuses are highlighted)
          </span>
        </h3>
        {isFreeborn && (
          <div className="bg-yellow-900/20 border border-yellow-500 rounded p-3 mb-2">
            <div className="font-semibold mb-1">Freeborn Bonus</div>
            <div className="text-sm mb-2">Pick <b>two different attributes</b> to receive +1 each. These do <b>not</b> count against your point pool.</div>
            <div className="flex flex-wrap gap-2">
              {availableAttributes.map(attr => (
                <button
                  key={attr}
                  onClick={() => {
                    if (freebornBonuses.includes(attr)) {
                      setFreebornBonuses(freebornBonuses.filter(a => a !== attr));
                    } else if (freebornBonuses.length < 2) {
                      setFreebornBonuses([...freebornBonuses, attr]);
                    }
                  }}
                  className={`px-3 py-1 rounded border ${freebornBonuses.includes(attr) ? 'bg-yellow-500 text-black border-yellow-700' : 'bg-gray-800 border-gray-600 text-gray-200'}`}
                  disabled={freebornBonuses.length >= 2 && !freebornBonuses.includes(attr)}
                >
                  {attr} {freebornBonuses.includes(attr) && '✓'}
                </button>
              ))}
            </div>
            {freebornBonuses.length < 2 && <div className="text-xs text-yellow-300 mt-1">Pick {2 - freebornBonuses.length} more.</div>}
          </div>
        )}
        <div className="bg-gray-700 rounded p-4 mb-4">
          <div className="flex justify-between text-sm">
            <span>Points Spent: {spentPoints.attributes}</span>
            <span>Available: {allocation.attributes.points}</span>
            <span>Max Attribute: {allocation.attributes.maxAttribute}</span>
          </div>
          {spentPoints.attributes > allocation.attributes.points && (
            <div className="text-red-400 text-sm mt-2">
              ⚠️ Exceeding point limit! ({spentPoints.attributes}/{allocation.attributes.points})
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          {YAGS_ATTRIBUTES.map((attr) => {
            const base = character.attributes[attr] || 3;
            const bonus = bonuses[attr] || 0;
            const total = base + bonus;
            // Color logic by value
            let color = '';
            if (total <= 3) color = 'text-white';
            else if (total <= 5) color = 'text-yellow-300';
            else if (total <= 7) color = 'text-orange-400';
            else color = 'text-red-500';
            return (
              <div key={attr} className="flex items-center justify-between p-3 bg-gray-800 rounded">
                <div>
                  <div className="font-medium flex items-center gap-1">{attr}
                    {bonus > 0 && <span className="ml-1 text-xs bg-yellow-400 text-black rounded px-1" title="Faction or Freeborn bonus">+{bonus}</span>}
                  </div>
                  <div className="text-xs text-gray-400">Cost: {Math.max(0, base - 3)} points</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleAttributeChange(attr, base - 1)}
                    disabled={base <= 1}
                    className="w-8 h-8 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50"
                  >
                    -
                  </button>
                  <span className={`w-8 text-center font-bold text-lg ${color}`}>{total}</span>
                  <button
                    onClick={() => handleAttributeChange(attr, base + 1)}
                    disabled={base >= allocation.attributes.maxAttribute}
                    className="w-8 h-8 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50"
                  >
                    +
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderSkillsStep = () => {
    const { aeonisk, standard, knowledge, professional, vehicle } = getAllAvailableSkills();
    
    const filterSkills = (skills: string[]) => {
      if (!skillFilter) return skills;
      return skills.filter(skill => 
        skill.toLowerCase().includes(skillFilter.toLowerCase())
      );
    };
    
    return (
      <div className="space-y-4">
        <h3 className="text-xl font-semibold flex items-center gap-2">
          Skills
          <button
            className="ml-4 px-3 py-1 bg-blue-800 hover:bg-blue-700 rounded text-sm text-white"
            onClick={() => setShowAutoPick(true)}
          >
            Auto-Pick Skills
          </button>
        </h3>
        
        {/* Skill Search */}
        <div>
          <input
            type="text"
            placeholder="Search skills..."
            value={skillFilter}
            onChange={(e) => setSkillFilter(e.target.value)}
            className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="bg-gray-700 rounded p-4 mb-4">
          <div className="flex justify-between text-sm">
            <span>Points Spent: {spentPoints.experience}</span>
            <span>Available: {allocation.experience.points}</span>
            <span>Max Skill: {allocation.experience.maxSkill}</span>
          </div>
          {spentPoints.experience > allocation.experience.points && (
            <div className="text-red-400 text-sm mt-2">
              ⚠️ Exceeding point limit! ({spentPoints.experience}/{allocation.experience.points})
            </div>
          )}
        </div>

        <div className="space-y-6 max-h-[60vh] overflow-y-auto">
          {/* Aeonisk Skills */}
          <div>
            <h4 className="font-semibold mb-2 text-blue-400">Aeonisk Skills</h4>
            <div className="grid grid-cols-2 gap-2">
              {filterSkills(aeonisk).map((skill) => {
                const value = character.skills[skill] || 0;
                return (
                  <div key={skill} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <span className="text-sm">{skill}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleSkillChange(skill, value - 1)}
                        disabled={value <= 0}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm">{value}</span>
                      <button
                        onClick={() => handleSkillChange(skill, value + 1)}
                        disabled={value >= allocation.experience.maxSkill || 
                                 spentPoints.experience + 1 > allocation.experience.points}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Standard Skills */}
          <div>
            <h4 className="font-semibold mb-2">Standard Skills</h4>
            <div className="grid grid-cols-2 gap-2">
              {filterSkills(standard).map((skill) => {
                const value = character.skills[skill] || 0;
                return (
                  <div key={skill} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <span className="text-sm">{skill}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleSkillChange(skill, value - 1)}
                        disabled={value <= 0}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm">{value}</span>
                      <button
                        onClick={() => handleSkillChange(skill, value + 1)}
                        disabled={value >= allocation.experience.maxSkill || 
                                 spentPoints.experience + 1 > allocation.experience.points}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Knowledge Skills */}
          <div>
            <h4 className="font-semibold mb-2 text-green-400">Knowledge Skills</h4>
            <div className="grid grid-cols-2 gap-2">
              {filterSkills(knowledge).map((skill) => {
                const value = character.skills[skill] || 0;
                return (
                  <div key={skill} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <span className="text-sm">{skill}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleSkillChange(skill, value - 1)}
                        disabled={value <= 0}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm">{value}</span>
                      <button
                        onClick={() => handleSkillChange(skill, value + 1)}
                        disabled={value >= allocation.experience.maxSkill || 
                                 spentPoints.experience + 1 > allocation.experience.points}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Professional Skills */}
          <div>
            <h4 className="font-semibold mb-2 text-yellow-400">Professional Skills</h4>
            <div className="grid grid-cols-2 gap-2">
              {filterSkills(professional).map((skill) => {
                const value = character.skills[skill] || 0;
                return (
                  <div key={skill} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <span className="text-sm">{skill}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleSkillChange(skill, value - 1)}
                        disabled={value <= 0}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm">{value}</span>
                      <button
                        onClick={() => handleSkillChange(skill, value + 1)}
                        disabled={value >= allocation.experience.maxSkill || 
                                 spentPoints.experience + 1 > allocation.experience.points}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Vehicle Skills */}
          <div>
            <h4 className="font-semibold mb-2 text-purple-400">Vehicle Skills</h4>
            <div className="grid grid-cols-2 gap-2">
              {filterSkills(vehicle).map((skill) => {
                const value = character.skills[skill] || 0;
                return (
                  <div key={skill} className="flex items-center justify-between p-2 bg-gray-800 rounded">
                    <span className="text-sm">{skill}</span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleSkillChange(skill, value - 1)}
                        disabled={value <= 0}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        -
                      </button>
                      <span className="w-6 text-center text-sm">{value}</span>
                      <button
                        onClick={() => handleSkillChange(skill, value + 1)}
                        disabled={value >= allocation.experience.maxSkill || 
                                 spentPoints.experience + 1 > allocation.experience.points}
                        className="w-6 h-6 bg-gray-600 rounded hover:bg-gray-500 disabled:opacity-50 text-xs"
                      >
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        {showAutoPick && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-gray-900 rounded-lg p-6 w-full max-w-md">
              <h4 className="text-lg font-bold mb-2">Auto-Pick Skills</h4>
              <p className="mb-4 text-gray-300">Choose an archetype or let the AI suggest skills based on your concept and faction.</p>
              <div className="space-y-2 mb-4">
                {Object.keys(SKILL_ARCHETYPES).map(arch => (
                  <button
                    key={arch}
                    className="w-full px-4 py-2 bg-purple-800 hover:bg-purple-700 rounded text-left text-white"
                    onClick={() => handleAutoPick(arch)}
                    disabled={autoPickLoading}
                  >
                    {arch}
                  </button>
                ))}
                <button
                  className="w-full px-4 py-2 bg-green-800 hover:bg-green-700 rounded text-left text-white mt-2"
                  onClick={handleAISuggest}
                  disabled={autoPickLoading}
                >
                  AI Suggest (based on concept/faction)
                </button>
              </div>
              <button
                className="mt-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white w-full"
                onClick={() => setShowAutoPick(false)}
                disabled={autoPickLoading}
              >
                Cancel
              </button>
              {autoPickLoading && <div className="text-center text-blue-300 mt-2">Assigning skills...</div>}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderReviewStep = () => {
    const allocation = calculatePriorityAllocation(campaignLevel, priorityPools);
    const bonuses = getFactionAttributeBonuses(character, freebornBonuses);
    const skillsList = Object.entries(character.skills || {})
      .filter(([_, v]) => v > 0)
      .sort((a, b) =>
        sortSkillsBy === 'alpha'
          ? a[0].localeCompare(b[0])
          : b[1] - a[1] || a[0].localeCompare(b[0])
      );
    return (
      <div className="space-y-4">
        {/* Issues Found - always visible and prominent */}
        <div className={`border-2 rounded p-4 mb-2 ${!validation.valid ? 'border-red-500 bg-red-900/20' : 'border-green-700 bg-green-900/10'}`}
             id="review-issues-box">
          <h4 className={`font-semibold mb-2 ${!validation.valid ? 'text-red-400' : 'text-green-400'}`}>Issues Found:</h4>
          {validation.errors.length === 0 ? (
            <div className="text-green-300">No issues! Ready to create your character.</div>
          ) : (
            <ul className="text-sm text-red-300 space-y-1">
              {validation.errors.map((error, index) => (
                <li key={index}>• {error}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="bg-gray-700 rounded p-4">
          <h4 className="font-semibold mb-2">Attributes (Base (max {allocation.attributes.maxAttribute}) + Bonus = Total)</h4>
          <div className="grid grid-cols-4 gap-2 text-sm">
            <div className="font-bold">Attribute</div>
            <div className="font-bold">Base</div>
            <div className="font-bold">Bonus</div>
            <div className="font-bold">Total</div>
            {YAGS_ATTRIBUTES.map(attr => (
              <React.Fragment key={attr}>
                <div>{attr}</div>
                <div>{character.attributes[attr] || 3}</div>
                <div className="text-yellow-300">{bonuses[attr] || 0}</div>
                <div>{(character.attributes[attr] || 3) + (bonuses[attr] || 0)}</div>
              </React.Fragment>
            ))}
          </div>
        </div>
        {/* Skills Section */}
        <div className="bg-gray-700 rounded p-4">
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-semibold">Skills</h4>
            <button
              className="text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 border border-gray-600"
              onClick={() => setSortSkillsBy(sortSkillsBy === 'alpha' ? 'value' : 'alpha')}
            >
              Sort: {sortSkillsBy === 'alpha' ? 'A-Z' : 'By Value'}
            </button>
          </div>
          {skillsList.length === 0 ? (
            <div className="text-gray-400 text-sm">No skills assigned.</div>
          ) : (
            <div className="grid grid-cols-2 gap-1 text-sm">
              {skillsList.map(([skill, value]) => (
                <div key={skill} className="flex justify-between border-b border-gray-600 py-1">
                  <span>{skill}</span>
                  <span className="font-bold text-blue-200">{value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="bg-gray-700 rounded p-4">
          <h4 className="font-semibold mb-2">Character Summary</h4>
          <div className="space-y-2 text-sm">
            <div><strong>Name:</strong> {character.name}</div>
            <div><strong>Concept:</strong> {character.concept}</div>
            <div><strong>Faction:</strong> {character.origin_faction}</div>
            <div><strong>Campaign Level:</strong> {campaignLevel}</div>
            <div><strong>Void Score:</strong> {character.voidScore}</div>
            <div><strong>Soulcredit:</strong> {character.soulcredit}</div>
          </div>
        </div>
        <div className="bg-gray-700 rounded p-4">
          <h4 className="font-semibold mb-2">Point Summary</h4>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span>Attributes:</span>
              <span>{spentPoints.attributes}/{allocation.attributes.points}</span>
            </div>
            <div className="flex justify-between">
              <span>Experience:</span>
              <span>{spentPoints.experience}/{allocation.experience.points}</span>
            </div>
            <div className="flex justify-between">
              <span>Advantages:</span>
              <span>{spentPoints.advantages}/{allocation.advantages.points}</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 'concept': return renderConceptStep();
      case 'faction': return renderFactionStep();
      case 'campaign': return renderCampaignStep();
      case 'attributes': return renderAttributesStep();
      case 'skills': return renderSkillsStep();
      case 'review': return renderReviewStep();
      default: return null;
    }
  };

  const canProceed = () => {
    switch (currentStep) {
      case 'concept':
        return character.name.trim() && character.concept.trim();
      case 'faction':
        return selectedFaction !== '';
      case 'campaign':
        return true;
      case 'attributes': {
        if (character.origin_faction === 'Freeborn' && freebornBonuses.length < 2) return false;
        return spentPoints.attributes <= allocation.attributes.points;
      }
      case 'skills':
        return spentPoints.experience <= allocation.experience.points;
      case 'review':
        return validation.valid;
      default:
        return false;
    }
  };

  const handleNext = () => {
    if (!canProceed()) return;

    const steps: WizardStep[] = ['concept', 'faction', 'campaign', 'attributes', 'skills', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex < steps.length - 1) {
      setCurrentStep(steps[currentIndex + 1]);
    }
  };

  const handlePrevious = () => {
    const steps: WizardStep[] = ['concept', 'faction', 'campaign', 'attributes', 'skills', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex > 0) {
      setCurrentStep(steps[currentIndex - 1]);
    }
  };

  const handleComplete = () => {
    if (validation.valid) {
      onComplete(character);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold">Character Creation Wizard</h2>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-gray-700 rounded transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="flex justify-between text-sm mb-2">
            {['concept', 'faction', 'campaign', 'attributes', 'skills', 'review'].map((step, index) => (
              <span
                key={step}
                className={`${
                  index <= ['concept', 'faction', 'campaign', 'attributes', 'skills', 'review'].indexOf(currentStep)
                    ? 'text-blue-400'
                    : 'text-gray-500'
                }`}
              >
                {step.charAt(0).toUpperCase() + step.slice(1)}
              </span>
            ))}
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-300"
              style={{
                width: `${((['concept', 'faction', 'campaign', 'attributes', 'skills', 'review'].indexOf(currentStep) + 1) / 6) * 100}%`
              }}
            />
          </div>
        </div>

        {/* Step Content */}
        <div className="mb-6">
          {renderCurrentStep()}
        </div>

        {/* Navigation */}
        <div className="flex justify-between">
          <button
            onClick={handlePrevious}
            disabled={currentStep === 'concept'}
            className="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
            >
              Cancel
            </button>
            
            {currentStep === 'review' ? (
              <button
                onClick={handleComplete}
                disabled={!validation.valid}
                className={`px-4 py-2 rounded ${validation.valid ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-700 border-2 border-red-500 cursor-not-allowed'}`}
                title={!validation.valid ? 'Resolve the issues above to create your character.' : 'Create your character!'}
              >
                Create Character
              </button>
            ) : (
              <button
                onClick={handleNext}
                disabled={!canProceed()}
                className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
} 