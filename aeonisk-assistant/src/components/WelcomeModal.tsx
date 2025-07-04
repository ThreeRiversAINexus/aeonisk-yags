import { useState, useRef, useEffect } from 'react';
import type { Character } from '../types';
import { getChatService } from '../lib/chat/service';
import { CharacterCreationWizard } from './CharacterCreationWizard';
import { CampaignPlanningWizard } from './CampaignPlanningWizard';
import YAML from 'yaml';

interface WelcomeModalProps {
  onComplete: (character: Character) => void;
  onClose: () => void;
}

type WelcomeView = 'home' | 'quickstart' | 'character' | 'campaign';

export function WelcomeModal({ onComplete, onClose }: WelcomeModalProps) {
  const [currentView, setCurrentView] = useState<WelcomeView>('home');
  const [showQuickstartOptions, setShowQuickstartOptions] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [campaign, setCampaign] = useState<any>(() => {
    const stored = localStorage.getItem('aeoniskCampaign');
    return stored ? JSON.parse(stored) : null;
  });
  const [character, setCharacter] = useState<Character | null>(null);

  const handleQuickstart = () => {
    setShowQuickstartOptions(true);
  };

  useEffect(() => {
    if (character && campaign) {
      localStorage.setItem('pendingAdventure', 'true');
      localStorage.setItem('pendingAdventureCharacterName', character.name);
    }
  }, [character, campaign]);

  const handleGenerateCharacter = () => {
    const quickstartCharacter: Character = {
      name: 'Quick Explorer',
      concept: 'Curious Investigator - Aether Dynamics member',
      origin_faction: 'Aether Dynamics',
      character_level_type: 'Skilled',
      tech_level: 'Aeonisk Standard',
      attributes: {
        Strength: 3,
        Health: 3,
        Agility: 3,
        Dexterity: 3,
        Perception: 4, // +1 from origin
        Intelligence: 3,
        Empathy: 4, // +1 from origin
        Willpower: 3
      },
      secondary_attributes: {
        Size: 5,
        Move: 12,
        Soak: 12
      },
      skills: {
        Athletics: 2,
        Awareness: 2,
        Brawl: 2,
        Charm: 2,
        Guile: 2,
        Sleight: 2,
        Stealth: 2,
        Throw: 2,
        Investigation: 4,
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
      campaignLevel: 'Skilled',
      priorityPools: {
        attributes: 'Secondary',
        experience: 'Primary',
        advantages: 'Tertiary'
      },
      controller: 'player'
    };
    const chatService = getChatService();
    chatService.setCharacter(quickstartCharacter);
    setCharacter(quickstartCharacter);
    onComplete(quickstartCharacter);
  };

  const handleYAMLUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError(null);
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = YAML.parse(text);
      let character: Character | undefined;
      if (Array.isArray(parsed)) {
        character = parsed[0];
      } else if (parsed.characters && Array.isArray(parsed.characters)) {
        character = parsed.characters[0];
      } else if (parsed.character_name || parsed.name) {
        character = parsed;
      }
      if (!character) throw new Error('No character found in YAML.');
      if (!character.name && (character as any).character_name) {
        character.name = (character as any).character_name;
      }
      if (!(character as any).skills && (character as any).standard_skills) {
        (character as any).skills = (character as any).standard_skills;
      }
      const chatService = getChatService();
      chatService.setCharacter(character);
      setCharacter(character);
      onComplete(character);
    } catch (err: any) {
      setUploadError('Failed to parse YAML: ' + (err.message || err));
    }
  };

  const handleCampaignComplete = (campaignData: any) => {
    setCampaign(campaignData);
    localStorage.setItem('aeoniskCampaign', JSON.stringify(campaignData));
    setCurrentView('home');
  };

  const renderQuickstartOptions = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-center">Quickstart</h2>
      <p className="text-gray-300 text-center">Choose how you want to begin your adventure:</p>
      <div className="grid grid-cols-1 gap-4">
        <label className="p-6 bg-green-900 hover:bg-green-800 rounded-lg transition-colors text-left cursor-pointer">
          <h3 className="text-lg font-semibold mb-2">Upload Character Sheet (YAML)</h3>
          <p className="text-gray-300 mb-2">Use your exported character sheet to start with your own hero.</p>
          <input type="file" accept=".yaml,.yml" className="hidden" onChange={handleYAMLUpload} />
          <span className="inline-block bg-gray-700 text-xs text-white px-2 py-1 rounded">Choose File</span>
        </label>
        <button
          onClick={handleGenerateCharacter}
          className="p-6 bg-blue-900 hover:bg-blue-800 rounded-lg transition-colors text-left"
        >
          <h3 className="text-lg font-semibold mb-2">Generate New Character</h3>
          <p className="text-gray-300">Let the system create a new character for you and drop you into a campaign.</p>
        </button>
      </div>
      {uploadError && <div className="text-red-400 text-sm text-center">{uploadError}</div>}
      <button
        onClick={() => setShowQuickstartOptions(false)}
        className="w-full px-4 py-2 bg-gray-700 rounded hover:bg-gray-600 mt-4"
      >
        Back
      </button>
    </div>
  );

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
          onClick={() => setCurrentView('character')}
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
    return (
      <CharacterCreationWizard
        onComplete={(character) => {
          onComplete(character);
        }}
        onCancel={() => setCurrentView('home')}
      />
    );
  };

  const renderCampaignPlanning = () => (
    <CampaignPlanningWizard
      onComplete={handleCampaignComplete}
      onCancel={() => setCurrentView('home')}
    />
  );

  const renderBeginAdventure = () => (
    <div className="flex flex-col items-center justify-center py-8">
      <button
        className="px-6 py-3 bg-blue-700 hover:bg-blue-800 text-white text-lg rounded-lg shadow-lg transition-colors"
        onClick={() => {
          if (localStorage.getItem('pendingAdventure') === 'true') {
            const chatService = getChatService();
            chatService.chat(
              `You awaken in the heart of Aeonisk Prime, the city of sacred trust and spiritual commerce. The air hums with the energy of talismans and the distant echo of ritual. As ${localStorage.getItem('pendingAdventureCharacterName')}, what do you do first?`,
              { ic: true }
            );
            localStorage.removeItem('pendingAdventure');
            localStorage.removeItem('pendingAdventureCharacterName');
          }
        }}
      >
        Begin Adventure
      </button>
      <p className="mt-4 text-gray-300 text-center">Click to start your campaign with an immersive scene.</p>
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

        {((character && campaign) || localStorage.getItem('pendingAdventure') === 'true')
          ? renderBeginAdventure()
          : showQuickstartOptions
            ? renderQuickstartOptions()
            : currentView === 'home' && renderHome()}
        {currentView === 'character' && renderCharacterCreation()}
        {currentView === 'campaign' && renderCampaignPlanning()}
      </div>
    </div>
  );
}
