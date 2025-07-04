import { useState } from 'react';
import type { Character } from '../types';
import { getChatService } from '../lib/chat/service';
import { CharacterCreationWizard } from './CharacterCreationWizard';

interface WelcomeModalProps {
  onComplete: (character: Character) => void;
  onClose: () => void;
}

type WelcomeView = 'home' | 'quickstart' | 'character' | 'campaign';




export function WelcomeModal({ onComplete, onClose }: WelcomeModalProps) {
  const [currentView, setCurrentView] = useState<WelcomeView>('home');



  const handleQuickstart = () => {
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
        // YAGS Talents at 2
        Athletics: 2,
        Awareness: 2,
        Brawl: 2,
        Charm: 2,
        Guile: 2,
        Sleight: 2,
        Stealth: 2,
        Throw: 2,
        // Professional skills
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
      voidScore: 0, // Aether Dynamics starts at 0
      soulcredit: 0, // Aether Dynamics starts at 0
      bonds: [],
      campaignLevel: 'Skilled',
      priorityPools: {
        attributes: 'Secondary',
        experience: 'Primary',
        advantages: 'Tertiary'
      },
      controller: 'player'
    };
    
    // Set the character in the chat service
    const chatService = getChatService();
    chatService.setCharacter(quickstartCharacter);
    
    onComplete(quickstartCharacter);
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
