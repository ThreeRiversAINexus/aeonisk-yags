import { useState } from 'react';
import type { Character } from '../types';

interface WelcomeModalProps {
  onComplete: (character: Character) => void;
  onClose: () => void;
}

type WelcomeView = 'home' | 'quickstart' | 'character' | 'campaign';
type CharacterStep = 'concept' | 'origin' | 'attributes' | 'skills' | 'equipment' | 'review';

const ORIGINS = [
  { 
    name: 'Sovereign Nexus', 
    attributes: ['willpower', 'intelligence'],
    trait: 'Indoctrinated: +2 to resist ritual disruption or mental influence',
    description: 'Theocratic matriarchy. Order, ritual, hierarchy.'
  },
  { 
    name: 'Astral Commerce Group', 
    attributes: ['intelligence', 'empathy'],
    trait: 'Contract-Bound: Start with +1 Soulcredit or one favorable minor contract',
    description: 'Financial entity. Tracks/brokers Soulcredit, contracts, ritual debt.'
  },
  { 
    name: 'Pantheon Security', 
    attributes: ['strength', 'agility'],
    trait: 'Tactical Protocol: Once per combat, automatically succeed on an Initiative roll',
    description: 'Privatized tactical force. Loyalty, procedure.'
  },
  { 
    name: 'Aether Dynamics', 
    attributes: ['empathy', 'perception'],
    trait: 'Ley Sense: Can sense presence and mood of nearby ley lines',
    description: 'Ecological-spiritual balance. Leylines, harmony, symbiosis.'
  },
  { 
    name: 'Arcane Genetics', 
    attributes: ['health', 'dexterity'],
    trait: 'Bio-Stabilized: +2 to rolls resisting biological Void effects',
    description: 'Biotech/ritual fusion. Evolution, coded spirituality.'
  },
  { 
    name: 'Tempest Industries', 
    attributes: ['dexterity', 'perception'],
    trait: 'Disruptor: +2 bonus when sabotaging rituals or tech',
    description: 'Subversive syndicate. Stolen tech, forbidden ritual.'
  },
  { 
    name: 'Freeborn', 
    attributes: ['any', 'any', 'any'],
    trait: 'Wild Will: Can only form/maintain 1 Bond',
    description: 'Outside faction structure. Rare, mistrusted/feared.'
  }
];

const AEONISK_SKILLS = [
  { name: 'astral_arts', display: 'Astral Arts', attribute: 'willpower' },
  { name: 'magick_theory', display: 'Magick Theory', attribute: 'intelligence' },
  { name: 'intimacy_ritual', display: 'Intimacy Ritual', attribute: 'empathy' },
  { name: 'corporate_influence', display: 'Corporate Influence', attribute: 'empathy' },
  { name: 'debt_law', display: 'Debt Law', attribute: 'intelligence' },
  { name: 'pilot', display: 'Pilot', attribute: 'agility' },
  { name: 'drone_operation', display: 'Drone Operation', attribute: 'intelligence' }
];

export function WelcomeModal({ onComplete, onClose }: WelcomeModalProps) {
  const [currentView, setCurrentView] = useState<WelcomeView>('home');
  const [characterStep, setCharacterStep] = useState<CharacterStep>('concept');
  const [character, setCharacter] = useState<Partial<Character>>({
    name: '',
    concept: '',
    origin_faction: '',
    character_level_type: 'Skilled',
    tech_level: 'Aeonisk Standard',
    // YAGS human defaults
    attributes: {
      strength: 3,
      health: 3,
      agility: 3,
      dexterity: 3,
      perception: 3,
      intelligence: 3,
      empathy: 3,
      willpower: 3
    },
    secondary_attributes: {
      size: 5,
      move: 12, // 5 + 3 + 3 + 1
      soak: 12,
      void: 0,
      soulcredit: 0
    },
    // Talents start at 2
    skills: {
      athletics: 2,
      awareness: 2,
      brawl: 2,
      charm: 2,
      guile: 2,
      sleight: 2,
      stealth: 2,
      throw: 2
    },
    talents: {},
    languages: {
      native_language_name: 'Low Arcanum',
      native_language_level: 4,
      other_languages: []
    },
    voidScore: 0,
    soulcredit: 0,
    bonds: [],
    controller: 'player'
  });

  const handleQuickstart = () => {
    const quickstartCharacter: Character = {
      name: 'Quick Explorer',
      concept: 'Curious Investigator',
      origin_faction: 'Aether Dynamics',
      character_level_type: 'Skilled',
      tech_level: 'Aeonisk Standard',
      attributes: {
        strength: 3,
        health: 3,
        agility: 3,
        dexterity: 3,
        perception: 4, // +1 from origin
        intelligence: 3,
        empathy: 3,
        willpower: 3
      },
      secondary_attributes: {
        size: 5,
        move: 12,
        soak: 12,
        void: 0,
        soulcredit: 0
      },
      skills: {
        // Talents at 2
        athletics: 2,
        awareness: 2,
        brawl: 2,
        charm: 2,
        guile: 2,
        sleight: 2,
        stealth: 2,
        throw: 2,
        // Professional skills
        investigation: 4,
        astral_arts: 2,
        research: 3,
        pilot: 2
      },
      talents: {},
      languages: {
        native_language_name: 'Low Arcanum',
        native_language_level: 4,
        other_languages: [
          { name: 'High Arcanum', level: 2 }
        ]
      },
      voidScore: 0,
      soulcredit: 0,
      bonds: [],
      trueWill: undefined,
      controller: 'player'
    };
    onComplete(quickstartCharacter);
  };

  const selectOrigin = (originName: string) => {
    const origin = ORIGINS.find(o => o.name === originName);
    if (origin) {
      setCharacter(prev => ({
        ...prev,
        origin_faction: originName
      }));
    }
  };

  const applyOriginBonus = () => {
    const origin = ORIGINS.find(o => o.name === character.origin_faction);
    if (!origin || !character.attributes) return;

    // For Freeborn, we'll let them choose 3 attributes to boost later
    if (origin.name === 'Freeborn') {
      return;
    }

    // For now, apply bonus to first listed attribute
    const attrToBoost = origin.attributes[0];
    setCharacter(prev => ({
      ...prev,
      attributes: {
        ...prev.attributes!,
        [attrToBoost]: Math.min(8, (prev.attributes![attrToBoost] || 3) + 1)
      }
    }));
  };

  const updateAttribute = (attr: string, value: number) => {
    setCharacter(prev => {
      const newAttributes = {
        ...prev.attributes!,
        [attr]: value
      };
      
      // Recalculate Move
      const newMove = (prev.secondary_attributes?.size || 5) + 
                      newAttributes.strength + 
                      newAttributes.agility + 1;
      
      return {
        ...prev,
        attributes: newAttributes,
        secondary_attributes: {
          ...prev.secondary_attributes!,
          move: newMove
        }
      };
    });
  };

  const updateSkill = (skill: string, value: number) => {
    setCharacter(prev => ({
      ...prev,
      skills: {
        ...prev.skills!,
        [skill]: value
      }
    }));
  };

  const renderHome = () => (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-center">Welcome to Aeonisk</h2>
      <p className="text-gray-300 text-center italic">
        "Will is Power. Bond is Law. Void is Real."
      </p>
      
      <div className="grid grid-cols-1 gap-4">
        <button
          onClick={handleQuickstart}
          className="p-6 bg-blue-900 hover:bg-blue-800 rounded-lg transition-colors text-left"
        >
          <h3 className="text-xl font-semibold mb-2">Quickstart</h3>
          <p className="text-gray-300">Jump right in with a pre-made character ready for adventure</p>
        </button>
        
        <button
          onClick={() => {
            setCurrentView('character');
            setCharacterStep('concept');
          }}
          className="p-6 bg-purple-900 hover:bg-purple-800 rounded-lg transition-colors text-left"
        >
          <h3 className="text-xl font-semibold mb-2">Create Character</h3>
          <p className="text-gray-300">Build your wielder of Will from scratch</p>
        </button>
        
        <button
          onClick={() => setCurrentView('campaign')}
          className="p-6 bg-green-900 hover:bg-green-800 rounded-lg transition-colors text-left"
        >
          <h3 className="text-xl font-semibold mb-2">Plan Campaign</h3>
          <p className="text-gray-300">Set up your world of sacred trust and spiritual economy</p>
        </button>
      </div>
    </div>
  );

  const renderCharacterCreation = () => {
    switch (characterStep) {
      case 'concept':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Character Concept</h3>
            <p className="text-gray-300">Who are you in this world of Will and Void?</p>
            
            <div>
              <label className="block text-sm font-medium mb-1">Name</label>
              <input
                type="text"
                value={character.name || ''}
                onChange={(e) => setCharacter(prev => ({ ...prev, name: e.target.value }))}
                className="w-full p-2 bg-gray-800 rounded border border-gray-700 focus:border-blue-500"
                placeholder="Enter character name"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-1">Concept</label>
              <input
                type="text"
                value={character.concept || ''}
                onChange={(e) => setCharacter(prev => ({ ...prev, concept: e.target.value }))}
                className="w-full p-2 bg-gray-800 rounded border border-gray-700 focus:border-blue-500"
                placeholder="e.g., Curious Investigator, Void-touched Mystic"
              />
            </div>

            <button
              onClick={() => setCharacterStep('origin')}
              disabled={!character.name || !character.concept}
              className="w-full px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed"
            >
              Choose Origin
            </button>
          </div>
        );

      case 'origin':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Choose Your Origin</h3>
            <p className="text-gray-300">Your faction grants an attribute bonus and special trait</p>
            
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {ORIGINS.map(origin => (
                <button
                  key={origin.name}
                  onClick={() => selectOrigin(origin.name)}
                  className={`w-full p-4 text-left rounded-lg border transition-colors ${
                    character.origin_faction === origin.name
                      ? 'border-blue-500 bg-blue-900/50'
                      : 'border-gray-700 hover:border-gray-600 bg-gray-800'
                  }`}
                >
                  <h4 className="font-semibold">{origin.name}</h4>
                  <p className="text-sm text-gray-400 mt-1">{origin.description}</p>
                  <p className="text-sm text-blue-400 mt-2">
                    +1 to {origin.attributes.join(' or ')}
                  </p>
                  <p className="text-sm text-green-400 mt-1">{origin.trait}</p>
                </button>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setCharacterStep('concept')}
                className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
              >
                Back
              </button>
              <button
                onClick={() => {
                  applyOriginBonus();
                  setCharacterStep('attributes');
                }}
                disabled={!character.origin_faction}
                className="flex-1 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed"
              >
                Assign Attributes
              </button>
            </div>
          </div>
        );

      case 'attributes':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Assign Attributes</h3>
            <p className="text-gray-300">Distribute points (human average is 3)</p>
            
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(character.attributes || {}).map(([attr, value]) => (
                <div key={attr} className="flex items-center gap-2">
                  <label className="flex-1 capitalize">{attr}:</label>
                  <input
                    type="number"
                    min="2"
                    max="5"
                    value={value}
                    onChange={(e) => updateAttribute(attr, parseInt(e.target.value) || 3)}
                    className="w-16 p-1 bg-gray-800 rounded border border-gray-700"
                  />
                </div>
              ))}
            </div>

            <div className="text-sm text-gray-400">
              <p>Move: {character.secondary_attributes?.move}</p>
              <p>Soak: {character.secondary_attributes?.soak}</p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setCharacterStep('origin')}
                className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
              >
                Back
              </button>
              <button
                onClick={() => setCharacterStep('skills')}
                className="flex-1 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700"
              >
                Choose Skills
              </button>
            </div>
          </div>
        );

      case 'skills':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Choose Skills</h3>
            <p className="text-gray-300">Talents start at 2. Professional level is 4+</p>
            
            <div className="space-y-2 max-h-96 overflow-y-auto">
              <h4 className="font-semibold text-blue-400">Aeonisk Skills</h4>
              {AEONISK_SKILLS.map(skill => (
                <div key={skill.name} className="flex items-center gap-2">
                  <label className="flex-1">{skill.display}</label>
                  <input
                    type="number"
                    min="0"
                    max="6"
                    value={character.skills?.[skill.name] || 0}
                    onChange={(e) => updateSkill(skill.name, parseInt(e.target.value) || 0)}
                    className="w-16 p-1 bg-gray-800 rounded border border-gray-700"
                  />
                  <span className="text-xs text-gray-500">({skill.attribute})</span>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setCharacterStep('attributes')}
                className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
              >
                Back
              </button>
              <button
                onClick={() => setCharacterStep('equipment')}
                className="flex-1 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700"
              >
                Equipment
              </button>
            </div>
          </div>
        );

      case 'equipment':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Ritual Kit & Equipment</h3>
            <p className="text-gray-300">Every wielder of Will needs their tools</p>
            
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium mb-1">Primary Ritual Item</label>
                <p className="text-xs text-gray-400 mb-2">A sacred, non-consumable item. If lost: -2 to Ritual Rolls</p>
                <input
                  type="text"
                  placeholder="e.g., Obsidian pendant, Bone athame, Crystal focus"
                  className="w-full p-2 bg-gray-800 rounded border border-gray-700"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Starting Offerings (1-3)</label>
                <p className="text-xs text-gray-400 mb-2">Consumable items for rituals</p>
                <textarea
                  placeholder="e.g., Vial of blessed salt, Written confession, Knotted hair"
                  className="w-full p-2 bg-gray-800 rounded border border-gray-700 h-20"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Starting Currency</label>
                <p className="text-xs text-gray-400">You begin with basic elemental talismans</p>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <div className="text-sm">
                    <span className="text-yellow-400">Spark:</span> 10 units
                  </div>
                  <div className="text-sm">
                    <span className="text-blue-400">Drip:</span> 10 units
                  </div>
                  <div className="text-sm">
                    <span className="text-green-400">Grain:</span> 10 units
                  </div>
                  <div className="text-sm">
                    <span className="text-gray-400">Breath:</span> 10 units
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setCharacterStep('skills')}
                className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
              >
                Back
              </button>
              <button
                onClick={() => setCharacterStep('review')}
                className="flex-1 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700"
              >
                Review Character
              </button>
            </div>
          </div>
        );

      case 'review':
        return (
          <div className="space-y-4">
            <h3 className="text-xl font-bold">Review Your Character</h3>
            
            <div className="space-y-2 text-sm">
              <p><span className="text-gray-400">Name:</span> {character.name}</p>
              <p><span className="text-gray-400">Concept:</span> {character.concept}</p>
              <p><span className="text-gray-400">Origin:</span> {character.origin_faction}</p>
              
              <div className="mt-3">
                <p className="text-gray-400 mb-1">Attributes:</p>
                <div className="grid grid-cols-2 gap-1 ml-4">
                  {Object.entries(character.attributes || {}).map(([attr, value]) => (
                    <p key={attr} className="capitalize">
                      {attr}: {value}
                    </p>
                  ))}
                </div>
              </div>

              <div className="mt-3">
                <p className="text-gray-400 mb-1">Notable Skills:</p>
                <div className="ml-4">
                  {Object.entries(character.skills || {})
                    .filter(([_, value]) => value > 2)
                    .map(([skill, value]) => (
                      <p key={skill} className="capitalize">
                        {skill.replace(/_/g, ' ')}: {value}
                      </p>
                    ))}
                </div>
              </div>

              <div className="mt-3 text-blue-400">
                <p>Void Score: 0</p>
                <p>Soulcredit: 0</p>
                <p>Bonds: None (formed through play)</p>
                <p>True Will: Undefined (discovered through play)</p>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setCharacterStep('equipment')}
                className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
              >
                Back
              </button>
              <button
                onClick={() => onComplete(character as Character)}
                className="flex-1 px-4 py-2 bg-green-600 rounded hover:bg-green-700"
              >
                Begin Journey
              </button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  const renderCampaignPlanning = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-bold">Campaign Planning</h3>
      <p className="text-gray-300">Set the stage for your Aeonisk story</p>
      
      <div className="space-y-3">
        <div>
          <h4 className="font-semibold mb-2">Campaign Level</h4>
          <select className="w-full p-2 bg-gray-800 rounded border border-gray-700">
            <option value="mundane">Mundane - Normal people, abnormal situations</option>
            <option value="skilled" selected>Skilled - Trained professionals (Default)</option>
            <option value="exceptional">Exceptional - Well above average</option>
            <option value="heroic">Heroic - Hollywood action heroes</option>
          </select>
        </div>

        <div>
          <h4 className="font-semibold mb-2">Primary Themes</h4>
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <input type="checkbox" className="rounded" defaultChecked />
              <span>Sacred trust and betrayal</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="rounded" defaultChecked />
              <span>Power bought with spirit, not coin</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="rounded" defaultChecked />
              <span>The slow erosion of self under Void</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="rounded" />
              <span>Faction politics and intrigue</span>
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="rounded" />
              <span>Exploration of True Will</span>
            </label>
          </div>
        </div>

        <div>
          <h4 className="font-semibold mb-2">Starting Location</h4>
          <select className="w-full p-2 bg-gray-800 rounded border border-gray-700">
            <option>Aeonisk Prime - Heart of the Nexus</option>
            <option>Arcadia Station - Trade hub</option>
            <option>Elysium - Frontier colony</option>
            <option>Nimbus - Contested space</option>
            <option>Custom Location</option>
          </select>
        </div>

        <div>
          <h4 className="font-semibold mb-2">Campaign Notes</h4>
          <textarea
            className="w-full p-2 bg-gray-800 rounded border border-gray-700 h-24"
            placeholder="Add any specific notes about your campaign..."
          />
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setCurrentView('home')}
          className="flex-1 px-4 py-2 bg-gray-700 rounded hover:bg-gray-600"
        >
          Back
        </button>
        <button
          onClick={onClose}
          className="flex-1 px-4 py-2 bg-green-600 rounded hover:bg-green-700"
        >
          Save Campaign Settings
        </button>
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-gray-900 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">
            {currentView === 'character' ? 'Character Creation' : 
             currentView === 'campaign' ? 'Campaign Planning' : 
             'Welcome to Aeonisk'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            ✕
          </button>
        </div>

        {currentView === 'home' && renderHome()}
        {currentView === 'character' && renderCharacterCreation()}
        {currentView === 'campaign' && renderCampaignPlanning()}
      </div>
    </div>
  );
}
