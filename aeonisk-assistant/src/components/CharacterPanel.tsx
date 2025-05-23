import { useState } from 'react';
import { getChatService } from '../lib/chat/service';
import type { Character } from '../types';

interface CharacterPanelProps {
  onClose: () => void;
}

const DEFAULT_CHARACTER: Character = {
  name: 'New Character',
  concept: 'Adventurer',
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
  skills: {
    'Astral Arts': 0,
    'Athletics': 2,
    'Awareness': 2,
    'Brawl': 2,
    'Charm': 2,
    'Guile': 2,
    'Sleight': 2,
    'Stealth': 2,
    'Throw': 2
  },
  voidScore: 0,
  soulcredit: 0,
  bonds: []
};

export function CharacterPanel({ onClose }: CharacterPanelProps) {
  const chatService = getChatService();
  const [character, setCharacter] = useState<Character>(
    chatService.getCharacter() || DEFAULT_CHARACTER
  );
  const [editMode, setEditMode] = useState(false);

  const handleSave = () => {
    chatService.setCharacter(character);
    setEditMode(false);
  };

  const handleAttributeChange = (attr: string, value: string) => {
    const numValue = parseInt(value) || 0;
    setCharacter(prev => ({
      ...prev,
      attributes: {
        ...prev.attributes,
        [attr]: Math.max(1, Math.min(5, numValue))
      }
    }));
  };

  const handleSkillChange = (skill: string, value: string) => {
    const numValue = parseInt(value) || 0;
    setCharacter(prev => ({
      ...prev,
      skills: {
        ...prev.skills,
        [skill]: Math.max(0, Math.min(7, numValue))
      }
    }));
  };

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 p-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Character</h2>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-700 rounded transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="space-y-4">
        {/* Basic Info */}
        <div>
          <label className="block text-sm font-medium mb-1">Name</label>
          <input
            type="text"
            value={character.name}
            onChange={(e) => setCharacter(prev => ({ ...prev, name: e.target.value }))}
            disabled={!editMode}
            className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Concept</label>
          <input
            type="text"
            value={character.concept}
            onChange={(e) => setCharacter(prev => ({ ...prev, concept: e.target.value }))}
            disabled={!editMode}
            className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
        </div>

        {/* Attributes */}
        <div>
          <h3 className="text-sm font-medium mb-2">Attributes (1-5)</h3>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(character.attributes).map(([attr, value]) => (
              <div key={attr} className="flex items-center gap-2">
                <label className="text-xs flex-1">{attr}:</label>
                <input
                  type="number"
                  value={value}
                  onChange={(e) => handleAttributeChange(attr, e.target.value)}
                  disabled={!editMode}
                  min="1"
                  max="5"
                  className="w-12 bg-gray-700 rounded px-2 py-1 text-center focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Skills */}
        <div>
          <h3 className="text-sm font-medium mb-2">Skills (0-7)</h3>
          <div className="space-y-1">
            {Object.entries(character.skills).map(([skill, value]) => (
              <div key={skill} className="flex items-center gap-2">
                <label className="text-xs flex-1">{skill}:</label>
                <input
                  type="number"
                  value={value}
                  onChange={(e) => handleSkillChange(skill, e.target.value)}
                  disabled={!editMode}
                  min="0"
                  max="7"
                  className="w-12 bg-gray-700 rounded px-2 py-1 text-center focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Spiritual Status */}
        <div>
          <h3 className="text-sm font-medium mb-2">Spiritual Status</h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm">Void Score:</span>
              <span className={`font-medium ${character.voidScore >= 5 ? 'text-red-400' : 'text-gray-300'}`}>
                {character.voidScore}/10
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Soulcredit:</span>
              <span className={`font-medium ${
                character.soulcredit > 0 ? 'text-green-400' : 
                character.soulcredit < 0 ? 'text-red-400' : 
                'text-gray-300'
              }`}>
                {character.soulcredit > 0 ? '+' : ''}{character.soulcredit}
              </span>
            </div>
          </div>
        </div>

        {/* Bonds */}
        <div>
          <h3 className="text-sm font-medium mb-2">Bonds</h3>
          {character.bonds.length === 0 ? (
            <p className="text-xs text-gray-400">No bonds formed</p>
          ) : (
            <div className="space-y-1">
              {character.bonds.map((bond, idx) => (
                <div key={idx} className="text-sm">
                  {bond.name} ({bond.type}) - {bond.status}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* True Will */}
        {character.trueWill && (
          <div>
            <h3 className="text-sm font-medium mb-1">True Will</h3>
            <p className="text-sm text-gray-300">{character.trueWill}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          {editMode ? (
            <>
              <button
                onClick={handleSave}
                className="flex-1 px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setCharacter(chatService.getCharacter() || DEFAULT_CHARACTER);
                  setEditMode(false);
                }}
                className="flex-1 px-4 py-2 bg-gray-600 rounded hover:bg-gray-700 transition-colors"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={() => setEditMode(true)}
              className="w-full px-4 py-2 bg-gray-600 rounded hover:bg-gray-700 transition-colors"
            >
              Edit Character
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
