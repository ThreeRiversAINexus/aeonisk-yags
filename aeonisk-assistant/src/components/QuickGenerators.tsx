import { useState, useEffect } from 'react';
import { getChatService } from '../lib/chat/service';
import type { Character } from '../types';

interface QuickGeneratorsProps {
  onCharacterGenerated?: (character: Character) => void;
  onCampaignGenerated?: (campaign: any) => void;
}

export function QuickGenerators({ onCharacterGenerated, onCampaignGenerated }: QuickGeneratorsProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationType, setGenerationType] = useState<'character' | 'campaign' | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const chatService = getChatService();

  // Collapse by default on mobile, expanded on desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setCollapsed(true);
      } else {
        setCollapsed(false);
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleGenerateCharacter = async () => {
    if (isGenerating) return;
    
    setIsGenerating(true);
    setGenerationType('character');
    
    try {
      // Generate character with random but reasonable defaults
      const names = ['Zara', 'Kai', 'Luna', 'Raven', 'Phoenix', 'Sage', 'Echo', 'Nova'];
      const concepts = [
        'Curious Investigator',
        'Skilled Negotiator',
        'Mysterious Scholar',
        'Talented Pilot',
        'Astral Researcher',
        'Corporate Liaison',
        'Independent Trader',
        'Ritual Specialist'
      ];
      const factions = [
        'Aether Dynamics',
        'Sovereign Nexus',
        'Astral Commerce Group',
        'Pantheon Security',
        'Arcane Genetics',
        'Tempest Industries',
        'Freeborn'
      ];
      
      const name = names[Math.floor(Math.random() * names.length)];
      const concept = concepts[Math.floor(Math.random() * concepts.length)];
      const faction = factions[Math.floor(Math.random() * factions.length)];
      
      const character = await chatService.generateCharacter(name, concept, faction, 'Skilled');
      
      if (onCharacterGenerated) {
        onCharacterGenerated(character);
      }
    } catch (error) {
      console.error('Character generation failed:', error);
    } finally {
      setIsGenerating(false);
      setGenerationType(null);
    }
  };

  const handleGenerateCampaign = async () => {
    if (isGenerating) return;
    
    const character = chatService.getCharacter();
    if (!character) {
      chatService.sendError(
        'No character found. Please create a character first before generating a campaign.',
        'Character is required for campaign generation',
        'campaign-generation'
      );
      return;
    }
    
    setIsGenerating(true);
    setGenerationType('campaign');
    
    try {
      const campaign = await chatService.generateCampaign(character);
      
      if (onCampaignGenerated) {
        onCampaignGenerated(campaign);
      }
    } catch (error) {
      console.error('Campaign generation failed:', error);
    } finally {
      setIsGenerating(false);
      setGenerationType(null);
    }
  };

  const handleGenerateCharacterAndCampaign = async () => {
    if (isGenerating) return;
    
    setIsGenerating(true);
    setGenerationType('character');
    
    try {
      // First generate character
      const names = ['Zara', 'Kai', 'Luna', 'Raven', 'Phoenix', 'Sage', 'Echo', 'Nova'];
      const concepts = [
        'Curious Investigator',
        'Skilled Negotiator',
        'Mysterious Scholar',
        'Talented Pilot',
        'Astral Researcher',
        'Corporate Liaison',
        'Independent Trader',
        'Ritual Specialist'
      ];
      const factions = [
        'Aether Dynamics',
        'Sovereign Nexus',
        'Astral Commerce Group',
        'Pantheon Security',
        'Arcane Genetics',
        'Tempest Industries',
        'Freeborn'
      ];
      
      const name = names[Math.floor(Math.random() * names.length)];
      const concept = concepts[Math.floor(Math.random() * concepts.length)];
      const faction = factions[Math.floor(Math.random() * factions.length)];
      
      const character = await chatService.generateCharacter(name, concept, faction, 'Skilled');
      
      if (onCharacterGenerated) {
        onCharacterGenerated(character);
      }
      
      // Then generate campaign
      setGenerationType('campaign');
      const campaign = await chatService.generateCampaign(character);
      
      if (onCampaignGenerated) {
        onCampaignGenerated(campaign);
      }
    } catch (error) {
      console.error('Character and campaign generation failed:', error);
    } finally {
      setIsGenerating(false);
      setGenerationType(null);
    }
  };

  return (
    <div className={`bg-gray-800 rounded-lg transition-all duration-300 ${collapsed ? 'p-1' : 'p-4'} shadow-md mb-2`}
         style={{ minHeight: collapsed ? 0 : undefined, overflow: 'hidden' }}>
      <div className="flex items-center justify-between">
        <h3 className={`text-lg font-semibold text-white transition-opacity duration-200 ${collapsed ? 'opacity-0 w-0 overflow-hidden' : 'opacity-100'}`}>Quick Generators</h3>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-xs text-gray-200 transition-colors"
          aria-label={collapsed ? 'Expand Quick Generators' : 'Collapse Quick Generators'}
        >
          {collapsed ? '▼ Show' : '▲ Hide'}
        </button>
      </div>
      {!collapsed && (
        <>
          <p className="text-sm text-gray-300 mt-2 mb-4">
            Generate characters and campaigns instantly. All progress will be shown in the chat.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <button
              onClick={handleGenerateCharacter}
              disabled={isGenerating}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              {isGenerating && generationType === 'character' ? 'Generating...' : '🎭 Generate Character'}
            </button>
            <button
              onClick={handleGenerateCampaign}
              disabled={isGenerating}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              {isGenerating && generationType === 'campaign' ? 'Generating...' : '🌟 Generate Campaign'}
            </button>
            <button
              onClick={handleGenerateCharacterAndCampaign}
              disabled={isGenerating}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-white transition-colors"
            >
              {isGenerating ? 'Generating...' : '🚀 Generate Both'}
            </button>
          </div>
          {isGenerating && (
            <div className="flex items-center gap-2 text-sm text-gray-400 mt-4">
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-500 border-t-transparent"></div>
              <span>
                {generationType === 'character' && 'Creating your character...'}
                {generationType === 'campaign' && 'Designing your campaign...'}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}