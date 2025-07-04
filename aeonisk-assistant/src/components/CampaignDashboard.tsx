import React from 'react';
import { useState, useEffect } from 'react';
import { CampaignPlanningWizard } from './CampaignPlanningWizard';
import { AeoniskChatService } from '../lib/chat/service';
import { ToastContainer, useToast } from './Toast';

interface CampaignData {
  name: string;
  description: string;
  theme: string;
  factions: string[];
  npcs: any[];
  scenarios: any[];
  dreamlines: any[];
}

interface ConfirmationDialog {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

interface AISuggestionState {
  isLoading: boolean;
  suggestion: CampaignData | null;
  error: string | null;
}

const CAMPAIGN_THEMES = [
  'Void Corruption',
  'Faction War',
  'Bond Betrayal',
  'Corporate Espionage',
  'Ritual Crisis'
];

export function CampaignDashboard() {
  const [campaigns, setCampaigns] = useState<CampaignData[]>([]);
  const [showWizard, setShowWizard] = useState(false);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [prefill, setPrefill] = useState<CampaignData | undefined>(undefined);
  const [selectedCampaign, setSelectedCampaign] = useState<CampaignData | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterTheme, setFilterTheme] = useState('All Themes');
  const { toasts, showToast, removeToast } = useToast();
  const [confirmDialog, setConfirmDialog] = useState<ConfirmationDialog>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
    onCancel: () => {}
  });
  const [aiSuggestion, setAISuggestion] = useState<AISuggestionState>({
    isLoading: false,
    suggestion: null,
    error: null
  });
  const [chatService] = useState(() => new AeoniskChatService());

  useEffect(() => {
    const stored = localStorage.getItem('aeoniskCampaigns');
    if (stored) {
      setCampaigns(JSON.parse(stored));
    }
  }, []);

  const saveCampaigns = (newCampaigns: CampaignData[]) => {
    setCampaigns(newCampaigns);
    localStorage.setItem('aeoniskCampaigns', JSON.stringify(newCampaigns));
  };

  const showConfirmation = (title: string, message: string, onConfirm: () => void) => {
    setConfirmDialog({
      isOpen: true,
      title,
      message,
      onConfirm: () => {
        onConfirm();
        setConfirmDialog(prev => ({ ...prev, isOpen: false }));
      },
      onCancel: () => setConfirmDialog(prev => ({ ...prev, isOpen: false }))
    });
  };

  const handleCreate = () => {
    setPrefill(undefined);
    setEditIndex(null);
    setShowWizard(true);
  };

  const handleEdit = (idx: number) => {
    setPrefill(campaigns[idx]);
    setEditIndex(idx);
    setShowWizard(true);
  };

  const handleDelete = (idx: number) => {
    const campaign = campaigns[idx];
    showConfirmation(
      'Delete Campaign',
      `Are you sure you want to delete "${campaign.name}"? This action cannot be undone.`,
      () => {
        const newCampaigns = campaigns.filter((_, i) => i !== idx);
        saveCampaigns(newCampaigns);
        showToast('Campaign deleted successfully');
      }
    );
  };

  const handleDuplicate = (idx: number) => {
    const original = campaigns[idx];
    const duplicate = {
      ...original,
      name: `${original.name} (Copy)`,
      npcs: [...original.npcs],
      scenarios: [...original.scenarios],
      dreamlines: [...original.dreamlines],
      factions: [...original.factions]
    };
    
    const newCampaigns = [...campaigns, duplicate];
    saveCampaigns(newCampaigns);
    showToast('Campaign duplicated successfully');
  };

  const handleSetActive = (idx: number) => {
    const campaign = campaigns[idx];
    localStorage.setItem('aeoniskCampaign', JSON.stringify(campaign));
    showToast(`"${campaign.name}" set as active campaign`);
  };

  const handleViewDetails = (idx: number) => {
    setSelectedCampaign(campaigns[idx]);
    setShowDetails(true);
  };

  const handleWizardComplete = (campaign: CampaignData) => {
    let newCampaigns;
    if (editIndex !== null) {
      newCampaigns = [...campaigns];
      newCampaigns[editIndex] = campaign;
      showToast('Campaign updated successfully');
    } else {
      newCampaigns = [...campaigns, campaign];
      showToast('Campaign created successfully');
    }
    saveCampaigns(newCampaigns);
    setShowWizard(false);
    setEditIndex(null);
    setPrefill(undefined);
    setAISuggestion({ isLoading: false, suggestion: null, error: null });
  };

  const handleAISuggest = async () => {
    setAISuggestion({ isLoading: true, suggestion: null, error: null });
    
    try {
      // Get current character for context
      const character = chatService.getCharacter();
      
      let aiCampaign: CampaignData;
      
      if (character) {
        // Generate AI suggestion based on character
        aiCampaign = await chatService.generateCampaignProposalFromCharacter(character);
      } else {
        // Generate a generic AI suggestion
        aiCampaign = await chatService.generateCampaignProposalFromCharacter({
          name: 'Unknown',
          concept: 'Mysterious wanderer',
          voidScore: 0,
          soulcredit: 10,
          bonds: [],
          attributes: {},
          skills: {}
        });
      }
      
      setAISuggestion({ isLoading: false, suggestion: aiCampaign, error: null });
      setPrefill(aiCampaign);
      setEditIndex(null);
      setShowWizard(true);
      showToast('AI campaign suggestion generated');
    } catch (error) {
      console.error('AI suggestion error:', error);
      setAISuggestion({ 
        isLoading: false, 
        suggestion: null, 
        error: error instanceof Error ? error.message : 'Failed to generate AI suggestion'
      });
      showToast('Failed to generate AI suggestion', 'error');
    }
  };

  // Filter campaigns based on search and theme
  const filteredCampaigns = campaigns.filter(campaign => {
    const matchesSearch = campaign.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         campaign.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesTheme = filterTheme === 'All Themes' || campaign.theme === filterTheme;
    return matchesSearch && matchesTheme;
  });

  // Responsive grid classes
  const getGridClasses = () => {
    if (typeof window !== 'undefined' && window.innerWidth <= 768) {
      return 'grid-cols-1';
    }
    return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3';
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <h2 className="text-2xl font-bold">Campaign Dashboard</h2>
        <div className="flex flex-col md:flex-row gap-2 w-full md:w-auto">
          <button
            className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
            onClick={handleCreate}
          >
            New Campaign
          </button>
          <button
            className="px-4 py-2 bg-purple-600 rounded hover:bg-purple-700 transition-colors relative"
            onClick={handleAISuggest}
            disabled={aiSuggestion.isLoading}
          >
            {aiSuggestion.isLoading ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                Generating AI suggestion...
              </div>
            ) : (
              'AI Suggest Campaign'
            )}
          </button>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search campaigns..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-gray-700 rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="w-full md:w-48">
          <select
            value={filterTheme}
            onChange={(e) => setFilterTheme(e.target.value)}
            className="w-full bg-gray-700 rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="All Themes">All Themes</option>
            {CAMPAIGN_THEMES.map(theme => (
              <option key={theme} value={theme}>{theme}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Campaign Grid */}
      <div className={`grid ${getGridClasses()} gap-4`} data-testid="campaign-grid">
        {filteredCampaigns.length === 0 && searchTerm === '' && filterTheme === 'All Themes' && (
          <div className="col-span-full text-center text-gray-400 py-12">
            <div className="text-6xl mb-4">🎭</div>
            <h3 className="text-xl font-semibold mb-2">No campaigns yet</h3>
            <p>Click "New Campaign" to create your first campaign or use "AI Suggest Campaign" for inspiration.</p>
          </div>
        )}
        
        {filteredCampaigns.length === 0 && (searchTerm !== '' || filterTheme !== 'All Themes') && (
          <div className="col-span-full text-center text-gray-400 py-12">
            <div className="text-6xl mb-4">🔍</div>
            <h3 className="text-xl font-semibold mb-2">No campaigns match your search</h3>
            <p>Try adjusting your search terms or filters.</p>
          </div>
        )}
        
        {filteredCampaigns.map((campaign, idx) => {
          const originalIndex = campaigns.indexOf(campaign);
          return (
            <div
              key={`${campaign.name}-${idx}`}
              className="bg-gray-800 rounded-lg p-4 border border-gray-700 hover:border-gray-600 transition-colors cursor-pointer"
              onClick={() => handleViewDetails(originalIndex)}
            >
              <div className="flex justify-between items-start mb-3">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-white hover:text-blue-400 transition-colors">
                    {campaign.name}
                  </h3>
                  <div className="text-sm text-gray-400">{campaign.theme}</div>
                </div>
                <div className="flex gap-1 ml-2">
                  <button
                    className="px-2 py-1 text-xs bg-blue-600 rounded hover:bg-blue-700 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEdit(originalIndex);
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="px-2 py-1 text-xs bg-green-600 rounded hover:bg-green-700 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDuplicate(originalIndex);
                    }}
                  >
                    Duplicate
                  </button>
                  <button
                    className="px-2 py-1 text-xs bg-purple-600 rounded hover:bg-purple-700 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSetActive(originalIndex);
                    }}
                  >
                    Set Active
                  </button>
                  <button
                    className="px-2 py-1 text-xs bg-red-600 rounded hover:bg-red-700 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(originalIndex);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
              
              <div className="text-sm text-gray-300 mb-3 line-clamp-2">
                {campaign.description}
              </div>
              
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
                <div>
                  <span className="font-medium">Factions:</span> {campaign.factions.length}
                </div>
                <div>
                  <span className="font-medium">NPCs:</span> {campaign.npcs.length}
                </div>
                <div>
                  <span className="font-medium">Scenarios:</span> {campaign.scenarios.length}
                </div>
                <div>
                  <span className="font-medium">Dreamlines:</span> {campaign.dreamlines.length}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Campaign Details Modal */}
      {showDetails && selectedCampaign && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold">Campaign Details</h2>
                <button
                  onClick={() => setShowDetails(false)}
                  className="p-2 hover:bg-gray-700 rounded transition-colors"
                  aria-label="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Overview</h3>
                    <div className="bg-gray-800 rounded p-4 space-y-2">
                      <div><strong>Name:</strong> {selectedCampaign.name}</div>
                      <div><strong>Theme:</strong> {selectedCampaign.theme}</div>
                      <div><strong>Description:</strong> {selectedCampaign.description}</div>
                    </div>
                  </div>
                  
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Factions</h3>
                    <div className="bg-gray-800 rounded p-4">
                      {selectedCampaign.factions.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {selectedCampaign.factions.map((faction, idx) => (
                            <span key={idx} className="px-2 py-1 bg-blue-600 rounded text-sm">
                              {faction}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <div className="text-gray-400">No factions defined</div>
                      )}
                    </div>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">NPCs</h3>
                    <div className="bg-gray-800 rounded p-4 max-h-48 overflow-y-auto">
                      {selectedCampaign.npcs.length > 0 ? (
                        <div className="space-y-2">
                          {selectedCampaign.npcs.map((npc, idx) => (
                            <div key={idx} className="border-b border-gray-700 pb-2 last:border-b-0">
                              <div className="font-medium">{npc.name}</div>
                              <div className="text-sm text-gray-400">
                                {npc.faction} - {npc.role}
                              </div>
                              <div className="text-sm text-gray-500">{npc.description}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-gray-400">No NPCs defined</div>
                      )}
                    </div>
                  </div>
                  
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Scenarios</h3>
                    <div className="bg-gray-800 rounded p-4 max-h-48 overflow-y-auto">
                      {selectedCampaign.scenarios.length > 0 ? (
                        <div className="space-y-2">
                          {selectedCampaign.scenarios.map((scenario, idx) => (
                            <div key={idx} className="border-b border-gray-700 pb-2 last:border-b-0">
                              <div className="font-medium">{scenario.name}</div>
                              <div className="text-sm text-gray-400">{scenario.location}</div>
                              <div className="text-sm text-gray-500">{scenario.description}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-gray-400">No scenarios defined</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="mt-6 flex gap-2">
                <button
                  onClick={() => {
                    const idx = campaigns.indexOf(selectedCampaign);
                    setShowDetails(false);
                    handleEdit(idx);
                  }}
                  className="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700 transition-colors"
                >
                  Edit Campaign
                </button>
                <button
                  onClick={() => {
                    const idx = campaigns.indexOf(selectedCampaign);
                    setShowDetails(false);
                    handleDuplicate(idx);
                  }}
                  className="px-4 py-2 bg-green-600 rounded hover:bg-green-700 transition-colors"
                >
                  Duplicate Campaign
                </button>
                <button
                  onClick={() => {
                    const idx = campaigns.indexOf(selectedCampaign);
                    handleSetActive(idx);
                    setShowDetails(false);
                  }}
                  className="px-4 py-2 bg-purple-600 rounded hover:bg-purple-700 transition-colors"
                >
                  Set as Active
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Campaign Planning Wizard */}
      {showWizard && (
        <CampaignPlanningWizard
          onComplete={handleWizardComplete}
          onCancel={() => {
            setShowWizard(false);
            setEditIndex(null);
            setPrefill(undefined);
            setAISuggestion({ isLoading: false, suggestion: null, error: null });
          }}
          prefill={prefill}
        />
      )}

      {/* Confirmation Dialog */}
      {confirmDialog.isOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-lg max-w-md w-full p-6">
            <h3 className="text-lg font-semibold mb-4">{confirmDialog.title}</h3>
            <p className="text-gray-300 mb-6">{confirmDialog.message}</p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={confirmDialog.onCancel}
                className="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className="px-4 py-2 bg-red-600 rounded hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </div>
  );
} 