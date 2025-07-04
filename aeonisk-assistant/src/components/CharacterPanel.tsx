import { useState, useEffect } from 'react';
import { getChatService } from '../lib/chat/service';
import type { Character } from '../types';
import { characterRegistry } from '../lib/game/characterRegistry';

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
  bonds: [],
  inventory: []
};

export function CharacterPanel({ onClose }: CharacterPanelProps) {
  const chatService = getChatService();
  const [character, setCharacter] = useState<Character>(() => {
    // Try to load from localStorage first
    const savedCharacter = localStorage.getItem('character');
    if (savedCharacter) {
      try {
        return JSON.parse(savedCharacter);
      } catch (e) {
        console.error('Failed to parse saved character:', e);
      }
    }
    return chatService.getCharacter() || DEFAULT_CHARACTER;
  });
  const [editMode, setEditMode] = useState(false);

  // Listen for character updates from the AI
  useEffect(() => {
    const checkForUpdates = () => {
      const currentCharacter = chatService.getCharacter();
      if (currentCharacter && JSON.stringify(currentCharacter) !== JSON.stringify(character)) {
        setCharacter(currentCharacter);
      }
    };

    // Check for updates every second
    const interval = setInterval(checkForUpdates, 1000);
    return () => clearInterval(interval);
  }, [character]);

  const handleSave = () => {
    chatService.setCharacter(character);
    localStorage.setItem('character', JSON.stringify(character));
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

  // Inventory/Talisman Actions
  const handleAttune = (itemId: string) => {
    characterRegistry.attuneTalisman(character.name, itemId);
    setCharacter(characterRegistry.getCharacter(character.name) as Character);
  };
  const handleSpend = (itemId: string) => {
    const amt = parseInt(prompt('Spend how much energy from this talisman?') || '0', 10);
    if (!isNaN(amt) && amt > 0) {
      characterRegistry.spendTalismanCharge(character.name, itemId, amt);
      setCharacter(characterRegistry.getCharacter(character.name) as Character);
    }
  };
  const handleRecharge = (itemId: string) => {
    const amt = parseInt(prompt('Recharge how much energy to this talisman?') || '0', 10);
    if (!isNaN(amt) && amt > 0) {
      characterRegistry.rechargeTalisman(character.name, itemId, amt);
      setCharacter(characterRegistry.getCharacter(character.name) as Character);
    }
  };
  const handleEquip = (itemId: string) => {
    characterRegistry.equipItem(character.name, itemId);
    setCharacter(characterRegistry.getCharacter(character.name) as Character);
  };
  const handleUnequip = (itemId: string) => {
    characterRegistry.unequipItem(character.name, itemId);
    setCharacter(characterRegistry.getCharacter(character.name) as Character);
  };
  const handleRemove = (itemId: string) => {
    if (window.confirm('Remove this item?')) {
      characterRegistry.removeItemFromInventory(character.name, itemId);
      setCharacter(characterRegistry.getCharacter(character.name) as Character);
    }
  };
  const handleAddItem = () => {
    const name = prompt('Item name?');
    if (!name) return;
    const type = prompt('Item type? (talisman, weapon, gear, offering, etc.)') || 'gear';
    let item: any = { id: Math.random().toString(36).slice(2), name, type };
    if (type === 'talisman') {
      item.element = prompt('Element? (Grain, Drip, Spark, Breath, Hollow, Seed)') || 'Spark';
      item.current_charge = parseInt(prompt('Current charge?') || '1', 10);
      item.max_charge = parseInt(prompt('Max charge?') || '1', 10);
      item.size = prompt('Size? (Single, Band, Sigil, Core, Vault)') || 'Single';
      item.attuned = window.confirm('Is this talisman attuned?');
    } else {
      item.quantity = parseInt(prompt('Quantity?') || '1', 10);
      item.equipped = window.confirm('Is this item equipped?');
    }
    item.notes = prompt('Notes?') || '';
    characterRegistry.addItemToInventory(character.name, item);
    setCharacter(characterRegistry.getCharacter(character.name) as Character);
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
            {Object.entries(character.attributes || {}).map(([attr, value]) => (
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
            {Object.entries(character.skills || {}).map(([skill, value]) => (
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

        {/* Faction */}
        {character.origin_faction && (
          <div>
            <h3 className="text-sm font-medium mb-2">Faction</h3>
            <div className="bg-gray-700 rounded px-3 py-2">
              <span className="text-sm font-medium text-blue-400">{character.origin_faction}</span>
            </div>
          </div>
        )}

        {/* Spiritual Status */}
        <div>
          <h3 className="text-sm font-medium mb-2">Spiritual Status</h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm">Void Score:</span>
              <span className={`font-medium ${character.voidScore >= 5 ? 'text-red-400' : character.voidScore >= 3 ? 'text-yellow-400' : 'text-gray-300'}`}>
                {character.voidScore}/10
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Soulcredit:</span>
              <span className={`font-medium ${
                character.soulcredit >= 6 ? 'text-purple-400' :
                character.soulcredit >= 1 ? 'text-green-400' : 
                character.soulcredit >= -5 ? 'text-yellow-400' :
                character.soulcredit >= -9 ? 'text-orange-400' :
                'text-red-400'
              }`}>
                {character.soulcredit > 0 ? '+' : ''}{character.soulcredit}/10
              </span>
            </div>
            {character.trueWill && (
              <div className="flex items-center justify-between">
                <span className="text-sm">True Will:</span>
                <span className="text-sm text-blue-400 italic">{character.trueWill}</span>
              </div>
            )}
          </div>
        </div>

        {/* Bonds */}
        <div>
          <h3 className="text-sm font-medium mb-2">Bonds</h3>
          {(character.bonds || []).length === 0 ? (
            <p className="text-xs text-gray-400">No bonds formed</p>
          ) : (
            <div className="space-y-1">
              {(character.bonds || []).map((bond, idx) => (
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

        {/* Advantages */}
        <div>
          <h3 className="text-sm font-medium mb-2">Advantages</h3>
          {(character.advantages || []).length === 0 ? (
            <p className="text-xs text-gray-400">No advantages</p>
          ) : (
            <ul className="list-disc ml-4 text-xs text-green-300">
              {(character.advantages || []).map((adv, idx) => (
                <li key={idx}>{adv.name} ({adv.category}) - {adv.description}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium mb-2">Disadvantages</h3>
          {(character.disadvantages || []).length === 0 ? (
            <p className="text-xs text-gray-400">No disadvantages</p>
          ) : (
            <ul className="list-disc ml-4 text-xs text-red-300">
              {(character.disadvantages || []).map((dis, idx) => (
                <li key={idx}>{dis.name} ({dis.category}) - {dis.description}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium mb-2">Techniques</h3>
          {(character.techniques || []).length === 0 ? (
            <p className="text-xs text-gray-400">No techniques</p>
          ) : (
            <ul className="list-disc ml-4 text-xs text-blue-300">
              {(character.techniques || []).map((tech, idx) => (
                <li key={idx}>{tech.name} ({tech.skill}) - {tech.description}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium mb-2">Familiarities</h3>
          {(character.familiarities || []).length === 0 ? (
            <p className="text-xs text-gray-400">No familiarities</p>
          ) : (
            <ul className="list-disc ml-4 text-xs text-yellow-300">
              {(character.familiarities || []).map((fam, idx) => (
                <li key={idx}>{fam.name} ({fam.skill}) - {fam.description}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium mb-2">Other Languages</h3>
          {((character.languages?.other_languages) || []).length === 0 ? (
            <p className="text-xs text-gray-400">None</p>
          ) : (
            <ul className="list-disc ml-4 text-xs text-purple-300">
              {((character.languages?.other_languages) || []).map((lang, idx) => (
                <li key={idx}>{lang.name} (Level {lang.level})</li>
              ))}
            </ul>
          )}
        </div>

        {/* Inventory */}
        <div>
          <h3 className="text-sm font-medium mb-2">Inventory</h3>
          {((character.inventory || []).length === 0) ? (
            editMode ? (
              <div className="mt-2">
                <button className="w-full px-3 py-2 bg-purple-800 rounded text-white text-xs" onClick={async () => {
                  const request = prompt('Describe the item you want to request from the AI DM:');
                  if (request) {
                    // Send request to AI DM (as chat message)
                    await chatService.chat(`Player requests item: ${request}`);
                    alert('Your request has been sent to the AI DM. Await a narrative response.');
                  }
                }}>Request Item</button>
              </div>
            ) : (
              <p className="text-xs text-gray-400">No items in inventory</p>
            )
          ) : (
            <div className="space-y-2">
              {/* Group talismans first */}
              {(character.inventory || []).filter(item => item.type === 'talisman').length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-blue-300 mb-1">Talismans</h4>
                  <div className="space-y-1">
                    {(character.inventory || []).filter(item => item.type === 'talisman').map((item, idx) => {
                      const talisman = item as any; // TalismanItem
                      return (
                        <div key={talisman.id || idx} className="bg-gray-700 rounded p-2 flex flex-col gap-1">
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-blue-200">{talisman.name}</span>
                            <span className="text-xs text-gray-400">{talisman.size} / {talisman.element}</span>
                          </div>
                          <div className="flex flex-wrap gap-2 text-xs">
                            <span>Charge: {talisman.current_charge}/{talisman.max_charge}</span>
                            <span>Attuned: {talisman.attuned ? 'Yes' : 'No'}</span>
                            {talisman.notes && <span className="italic text-gray-400">{talisman.notes}</span>}
                          </div>
                          {editMode && (
                            <div className="flex gap-2 mt-1">
                              <button className="px-2 py-1 bg-green-700 rounded text-xs text-white" onClick={() => handleAttune(talisman.id)}>Attune</button>
                              <button className="px-2 py-1 bg-yellow-700 rounded text-xs text-white" onClick={() => handleSpend(talisman.id)}>Spend</button>
                              <button className="px-2 py-1 bg-blue-700 rounded text-xs text-white" onClick={() => handleRecharge(talisman.id)}>Recharge</button>
                              <button className="px-2 py-1 bg-gray-600 rounded text-xs text-white" onClick={() => talisman.equipped ? handleUnequip(talisman.id) : handleEquip(talisman.id)}>{talisman.equipped ? 'Unequip' : 'Equip'}</button>
                              <button className="px-2 py-1 bg-red-700 rounded text-xs text-white" onClick={() => handleRemove(talisman.id)}>Remove</button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {/* Other items */}
              {(character.inventory || []).filter(item => item.type !== 'talisman').length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-300 mb-1">Other Items</h4>
                  <div className="space-y-1">
                    {(character.inventory || []).filter(item => item.type !== 'talisman').map((item, idx) => (
                      <div key={item.id || idx} className="bg-gray-700 rounded p-2 flex flex-col gap-1">
                        <div className="flex justify-between items-center">
                          <span className="font-bold text-gray-200">{item.name}</span>
                          <span className="text-xs text-gray-400">{item.type}</span>
                        </div>
                        <div className="flex flex-wrap gap-2 text-xs">
                          <span>Qty: {item.quantity || 1}</span>
                          <span>Equipped: {item.equipped ? 'Yes' : 'No'}</span>
                          {item.notes && <span className="italic text-gray-400">{item.notes}</span>}
                        </div>
                        {editMode && (
                          <div className="flex gap-2 mt-1">
                            <button className="px-2 py-1 bg-gray-600 rounded text-xs text-white" onClick={() => item.equipped ? handleUnequip(item.id) : handleEquip(item.id)}>{item.equipped ? 'Unequip' : 'Equip'}</button>
                            <button className="px-2 py-1 bg-red-700 rounded text-xs text-white" onClick={() => handleRemove(item.id)}>Remove</button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {editMode && (
                <div className="mt-2">
                  <button className="w-full px-3 py-2 bg-purple-800 rounded text-white text-xs" onClick={async () => {
                    const request = prompt('Describe the item you want to request from the AI DM:');
                    if (request) {
                      // Send request to AI DM (as chat message)
                      await chatService.chat(`Player requests item: ${request}`);
                      alert('Your request has been sent to the AI DM. Await a narrative response.');
                    }
                  }}>Request Item</button>
                </div>
              )}
            </div>
          )}
        </div>

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
      {/* YAML Export Button */}
      {!editMode && (
        <button
          className="w-full mt-4 px-4 py-2 bg-green-700 rounded hover:bg-green-800 text-white text-sm"
          onClick={() => {
            const yaml = characterRegistry.exportCharacterToYAML(character.name);
            const blob = new Blob([yaml], { type: 'text/yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${character.name.replace(/\s+/g, '_').toLowerCase()}-aeonisk.yaml`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          Export as YAML
        </button>
      )}
    </div>
  );
}
