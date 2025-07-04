import React from 'react';
import { useState } from 'react';
import type { Character, NPC, Dreamline } from '../types';

interface CampaignPlanningWizardProps {
  onComplete: (campaign: CampaignData) => void;
  onCancel: () => void;
  prefill?: CampaignData;
}

interface CampaignData {
  name: string;
  description: string;
  theme: string;
  factions: string[];
  npcs: NPC[];
  scenarios: Scenario[];
  dreamlines: Dreamline[];
}

interface Scenario {
  id: string;
  name: string;
  description: string;
  location: string;
  factions: string[];
  objectives: string[];
  complications: string[];
}

type WizardStep = 'overview' | 'factions' | 'npcs' | 'scenarios' | 'dreamlines' | 'review';

const CAMPAIGN_THEMES = [
  {
    name: 'Void Corruption',
    description: 'The void is spreading, corrupting reality and souls.',
    focus: 'Horror, corruption, survival',
    factions: ['Sovereign Nexus', 'Arcane Genetics', 'Tempest Industries']
  },
  {
    name: 'Faction War',
    description: 'Open conflict between major factions over resources and territory.',
    focus: 'Combat, politics, alliances',
    factions: ['Pantheon Security', 'Astral Commerce Group', 'Tempest Industries']
  },
  {
    name: 'Bond Betrayal',
    description: 'Trusted allies become enemies as bonds are broken.',
    focus: 'Drama, betrayal, relationships',
    factions: ['Aether Dynamics', 'Sovereign Nexus', 'Freeborn']
  },
  {
    name: 'Corporate Espionage',
    description: 'Industrial espionage and corporate warfare.',
    focus: 'Stealth, intrigue, technology',
    factions: ['Astral Commerce Group', 'Tempest Industries', 'Arcane Genetics']
  },
  {
    name: 'Ritual Crisis',
    description: 'A major ritual has gone wrong, threatening reality.',
    focus: 'Magic, investigation, urgency',
    factions: ['Sovereign Nexus', 'Aether Dynamics', 'Arcane Genetics']
  }
];

const NPC_TEMPLATES = [
  {
    name: 'Corporate Executive',
    faction: 'Astral Commerce Group',
    role: 'Business Leader',
    description: 'Ambitious and ruthless business leader',
    skills: ['Corporate Influence', 'Leadership', 'Debt Law'],
    personality: 'Calculating, ambitious, profit-driven'
  },
  {
    name: 'Security Officer',
    faction: 'Pantheon Security',
    role: 'Law Enforcement',
    description: 'Dedicated security professional',
    skills: ['Tactics', 'Security Protocols', 'Investigation'],
    personality: 'Loyal, procedural, duty-bound'
  },
  {
    name: 'Void Touched Mystic',
    faction: 'Sovereign Nexus',
    role: 'Religious Leader',
    description: 'Mystic with deep void connection',
    skills: ['Astral Arts', 'Magick Theory', 'Ritual Casting'],
    personality: 'Intense, spiritual, void-obsessed'
  },
  {
    name: 'Tech Specialist',
    faction: 'Arcane Genetics',
    role: 'Scientist',
    description: 'Brilliant but amoral researcher',
    skills: ['Biotech', 'Nanotech', 'Research'],
    personality: 'Curious, amoral, experimental'
  },
  {
    name: 'Street Operative',
    faction: 'Tempest Industries',
    role: 'Criminal',
    description: 'Skilled underworld operator',
    skills: ['Stealth', 'Hacking', 'Smuggling'],
    personality: 'Cautious, opportunistic, survivalist'
  }
];

export function CampaignPlanningWizard({ onComplete, onCancel, prefill }: CampaignPlanningWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>('overview');
  const [campaign, setCampaign] = useState<CampaignData>(() =>
    prefill ? { ...prefill } : {
      name: '',
      description: '',
      theme: '',
      factions: [],
      npcs: [],
      scenarios: [],
      dreamlines: []
    }
  );

  const updateCampaign = (updates: Partial<CampaignData>) => {
    setCampaign(prev => ({ ...prev, ...updates }));
  };

  const addNPC = (template: typeof NPC_TEMPLATES[0]) => {
    const newNPC: NPC = {
      name: template.name,
      faction: template.faction,
      role: template.role,
      description: template.description
    };
    updateCampaign({
      npcs: [...campaign.npcs, newNPC]
    });
  };

  const removeNPC = (index: number) => {
    updateCampaign({
      npcs: campaign.npcs.filter((_, i) => i !== index)
    });
  };

  const addScenario = () => {
    const newScenario: Scenario = {
      id: `scenario-${Date.now()}`,
      name: 'New Scenario',
      description: 'Describe the scenario...',
      location: 'Unknown Location',
      factions: [],
      objectives: [],
      complications: []
    };
    updateCampaign({
      scenarios: [...campaign.scenarios, newScenario]
    });
  };

  const updateScenario = (index: number, updates: Partial<Scenario>) => {
    const newScenarios = [...campaign.scenarios];
    newScenarios[index] = { ...newScenarios[index], ...updates };
    updateCampaign({ scenarios: newScenarios });
  };

  const removeScenario = (index: number) => {
    updateCampaign({
      scenarios: campaign.scenarios.filter((_, i) => i !== index)
    });
  };

  const renderOverviewStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Campaign Overview</h3>
      
      <div>
        <label className="block text-sm font-medium mb-2">Campaign Name</label>
        <input
          type="text"
          value={campaign.name}
          onChange={(e) => updateCampaign({ name: e.target.value })}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Enter campaign name"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Description</label>
        <textarea
          value={campaign.description}
          onChange={(e) => updateCampaign({ description: e.target.value })}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Describe your campaign..."
          rows={4}
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Theme</label>
        <select
          value={campaign.theme}
          onChange={(e) => {
            const theme = CAMPAIGN_THEMES.find(t => t.name === e.target.value);
            updateCampaign({ 
              theme: e.target.value,
              factions: theme?.factions || []
            });
          }}
          className="w-full bg-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Select a theme...</option>
          {CAMPAIGN_THEMES.map((theme) => (
            <option key={theme.name} value={theme.name}>{theme.name}</option>
          ))}
        </select>
      </div>

      {campaign.theme && (
        <div className="bg-gray-700 rounded p-4">
          <h4 className="font-semibold mb-2">Theme Details</h4>
          <div className="text-sm space-y-1">
            <p><strong>Focus:</strong> {CAMPAIGN_THEMES.find(t => t.name === campaign.theme)?.focus}</p>
            <p><strong>Description:</strong> {CAMPAIGN_THEMES.find(t => t.name === campaign.theme)?.description}</p>
            <p><strong>Key Factions:</strong> {CAMPAIGN_THEMES.find(t => t.name === campaign.theme)?.factions.join(', ')}</p>
          </div>
        </div>
      )}
    </div>
  );

  const renderFactionsStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Involved Factions</h3>
      
      <div className="grid grid-cols-2 gap-4">
        {['Sovereign Nexus', 'Astral Commerce Group', 'Pantheon Security', 'Aether Dynamics', 'Arcane Genetics', 'Tempest Industries', 'Freeborn'].map((faction) => (
          <div
            key={faction}
            onClick={() => {
              const newFactions = campaign.factions.includes(faction)
                ? campaign.factions.filter(f => f !== faction)
                : [...campaign.factions, faction];
              updateCampaign({ factions: newFactions });
            }}
            className={`p-4 border rounded-lg cursor-pointer transition-colors ${
              campaign.factions.includes(faction)
                ? 'border-blue-500 bg-blue-900/20'
                : 'border-gray-600 hover:border-gray-500'
            }`}
          >
            <h4 className="font-semibold">{faction}</h4>
          </div>
        ))}
      </div>
    </div>
  );

  const renderNPCsStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">NPCs</h3>
      
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h4 className="font-semibold mb-2">Available Templates</h4>
          <div className="space-y-2">
            {NPC_TEMPLATES.map((template) => (
              <div
                key={template.name}
                onClick={() => addNPC(template)}
                className="p-3 border border-gray-600 rounded cursor-pointer hover:border-gray-500 transition-colors"
              >
                <h5 className="font-medium">{template.name}</h5>
                <p className="text-sm text-gray-400">{template.faction} - {template.role}</p>
                <p className="text-xs text-gray-500">{template.personality}</p>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h4 className="font-semibold mb-2">Campaign NPCs ({campaign.npcs.length})</h4>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {campaign.npcs.map((npc, index) => (
              <div key={index} className="p-3 bg-gray-800 rounded flex justify-between items-start">
                <div>
                  <h5 className="font-medium">{npc.name}</h5>
                  <p className="text-sm text-gray-400">{npc.faction} - {npc.role}</p>
                  <p className="text-xs text-gray-500">{npc.description}</p>
                </div>
                <button
                  onClick={() => removeNPC(index)}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  const renderScenariosStep = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-xl font-semibold">Scenarios</h3>
        <button
          onClick={addScenario}
          className="px-3 py-1 bg-blue-600 rounded hover:bg-blue-700 text-sm"
        >
          Add Scenario
        </button>
      </div>
      
      <div className="space-y-4">
        {campaign.scenarios.map((scenario, index) => (
          <div key={scenario.id} className="bg-gray-800 rounded p-4">
            <div className="flex justify-between items-start mb-3">
              <input
                type="text"
                value={scenario.name}
                onChange={(e) => updateScenario(index, { name: e.target.value })}
                className="text-lg font-semibold bg-transparent border-b border-gray-600 focus:outline-none focus:border-blue-500"
                placeholder="Scenario name"
              />
              <button
                onClick={() => removeScenario(index)}
                className="text-red-400 hover:text-red-300 text-sm"
              >
                Remove
              </button>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Description</label>
                <textarea
                  value={scenario.description}
                  onChange={(e) => updateScenario(index, { description: e.target.value })}
                  className="w-full bg-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                  rows={3}
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium mb-1">Location</label>
                <input
                  type="text"
                  value={scenario.location}
                  onChange={(e) => updateScenario(index, { location: e.target.value })}
                  className="w-full bg-gray-700 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderDreamlinesStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Dreamlines</h3>
      <p className="text-gray-400 text-sm">
        Dreamlines are narrative threads that can emerge from player actions and campaign events.
        They represent potential story developments and consequences.
      </p>
      
      <div className="bg-gray-700 rounded p-4">
        <h4 className="font-semibold mb-2">Potential Dreamlines</h4>
        <div className="space-y-2 text-sm">
          <div className="p-2 bg-gray-800 rounded">
            <strong>Void Corruption:</strong> As characters use void magic, they risk corruption that could spread to others.
          </div>
          <div className="p-2 bg-gray-800 rounded">
            <strong>Faction Betrayal:</strong> Trusted allies may betray the party for their own faction's interests.
          </div>
          <div className="p-2 bg-gray-800 rounded">
            <strong>Ritual Consequences:</strong> Failed or powerful rituals can have unexpected effects on reality.
          </div>
          <div className="p-2 bg-gray-800 rounded">
            <strong>Bond Dynamics:</strong> Relationships between characters and NPCs can evolve in unexpected ways.
          </div>
        </div>
      </div>
    </div>
  );

  const renderReviewStep = () => (
    <div className="space-y-4">
      <h3 className="text-xl font-semibold">Campaign Review</h3>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-4">
          <div className="bg-gray-700 rounded p-4">
            <h4 className="font-semibold mb-2">Campaign Details</h4>
            <div className="text-sm space-y-1">
              <div><strong>Name:</strong> {campaign.name}</div>
              <div><strong>Theme:</strong> {campaign.theme}</div>
              <div><strong>Factions:</strong> {campaign.factions.join(', ')}</div>
              <div><strong>NPCs:</strong> {campaign.npcs.length}</div>
              <div><strong>Scenarios:</strong> {campaign.scenarios.length}</div>
            </div>
          </div>

          <div className="bg-gray-700 rounded p-4">
            <h4 className="font-semibold mb-2">Description</h4>
            <p className="text-sm">{campaign.description}</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-gray-700 rounded p-4">
            <h4 className="font-semibold mb-2">NPCs</h4>
            <div className="space-y-1 text-sm">
              {campaign.npcs.map((npc, index) => (
                <div key={index}>
                  <strong>{npc.name}</strong> ({npc.faction} - {npc.role})
                </div>
              ))}
            </div>
          </div>

          <div className="bg-gray-700 rounded p-4">
            <h4 className="font-semibold mb-2">Scenarios</h4>
            <div className="space-y-1 text-sm">
              {campaign.scenarios.map((scenario, index) => (
                <div key={index}>
                  <strong>{scenario.name}</strong> - {scenario.location}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 'overview': return renderOverviewStep();
      case 'factions': return renderFactionsStep();
      case 'npcs': return renderNPCsStep();
      case 'scenarios': return renderScenariosStep();
      case 'dreamlines': return renderDreamlinesStep();
      case 'review': return renderReviewStep();
      default: return null;
    }
  };

  const canProceed = () => {
    switch (currentStep) {
      case 'overview':
        return campaign.name.trim() && campaign.theme;
      case 'factions':
        return campaign.factions.length > 0;
      case 'npcs':
        return true;
      case 'scenarios':
        return true;
      case 'dreamlines':
        return true;
      case 'review':
        return true;
      default:
        return false;
    }
  };

  const handleNext = () => {
    if (!canProceed()) return;

    const steps: WizardStep[] = ['overview', 'factions', 'npcs', 'scenarios', 'dreamlines', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex < steps.length - 1) {
      setCurrentStep(steps[currentIndex + 1]);
    }
  };

  const handlePrevious = () => {
    const steps: WizardStep[] = ['overview', 'factions', 'npcs', 'scenarios', 'dreamlines', 'review'];
    const currentIndex = steps.indexOf(currentStep);
    if (currentIndex > 0) {
      setCurrentStep(steps[currentIndex - 1]);
    }
  };

  const handleComplete = () => {
    // Persist campaign data to localStorage
    localStorage.setItem('aeoniskCampaign', JSON.stringify(campaign));
    onComplete(campaign);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 w-full max-w-6xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold">Campaign Planning Wizard</h2>
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
            {['overview', 'factions', 'npcs', 'scenarios', 'dreamlines', 'review'].map((step, index) => (
              <span
                key={step}
                className={`${
                  index <= ['overview', 'factions', 'npcs', 'scenarios', 'dreamlines', 'review'].indexOf(currentStep)
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
                width: `${((['overview', 'factions', 'npcs', 'scenarios', 'dreamlines', 'review'].indexOf(currentStep) + 1) / 6) * 100}%`
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
            disabled={currentStep === 'overview'}
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
                disabled={!canProceed()}
                className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Create Campaign
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