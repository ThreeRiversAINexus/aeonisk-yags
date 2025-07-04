import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { CampaignDashboard } from '../../components/CampaignDashboard';

beforeEach(() => {
  localStorage.clear();
});

describe('CampaignDashboard', () => {
  const mockCampaign = {
    name: 'Test Campaign',
    description: 'A test campaign for unit testing',
    theme: 'Void Corruption',
    factions: ['Sovereign Nexus', 'Astral Commerce Group'],
    npcs: [
      { name: 'Commander Vex', faction: 'Sovereign Nexus', role: 'Military Leader', description: 'Stern military commander' }
    ],
    scenarios: [
      { id: 'scenario-1', name: 'First Contact', description: 'Initial scenario', location: 'Nexus Station', factions: ['Sovereign Nexus'], objectives: ['Establish contact'], complications: ['Void corruption'] }
    ],
    dreamlines: []
  };

  it('renders without crashing and shows empty state', () => {
    render(<CampaignDashboard />);
    expect(screen.getByText(/Campaigns/i)).toBeInTheDocument();
    expect(screen.getByText(/No campaigns yet/i)).toBeInTheDocument();
  });

  it('displays search and filter controls', () => {
    render(<CampaignDashboard />);
    expect(screen.getByPlaceholderText(/Search campaigns/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue(/All Themes/i)).toBeInTheDocument();
  });

  it('can create a new campaign', async () => {
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/New Campaign/i));
    
    // Fill out the wizard (overview step)
    fireEvent.change(screen.getByPlaceholderText(/Enter campaign name/i), { target: { value: 'Test Campaign' } });
    fireEvent.change(screen.getByPlaceholderText(/Describe your campaign/i), { target: { value: 'A test campaign.' } });
    fireEvent.change(screen.getByDisplayValue(''), { target: { value: 'Void Corruption' } });
    fireEvent.click(screen.getByText(/Next/i));
    
    // Factions step
    fireEvent.click(screen.getByText('Sovereign Nexus'));
    fireEvent.click(screen.getByText(/Next/i));
    
    // NPCs step
    fireEvent.click(screen.getByText(/Next/i));
    
    // Scenarios step
    fireEvent.click(screen.getByText(/Next/i));
    
    // Dreamlines step
    fireEvent.click(screen.getByText(/Next/i));
    
    // Review step
    fireEvent.click(screen.getByText(/Create Campaign/i));
    
    await waitFor(() => {
      expect(screen.getByText('Test Campaign')).toBeInTheDocument();
    });
  });

  it('can edit a campaign', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText(/Edit/i));
    fireEvent.change(screen.getByPlaceholderText(/Enter campaign name/i), { target: { value: 'Edited Campaign' } });
    fireEvent.click(screen.getByText(/Next/i)); // Factions
    fireEvent.click(screen.getByText(/Next/i)); // NPCs
    fireEvent.click(screen.getByText(/Next/i)); // Scenarios
    fireEvent.click(screen.getByText(/Next/i)); // Dreamlines
    fireEvent.click(screen.getByText(/Create Campaign/i));
    
    await waitFor(() => {
      expect(screen.getByText('Edited Campaign')).toBeInTheDocument();
    });
  });

  it('can delete a campaign with confirmation', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText(/Delete/i));
    
    // For now, test the basic delete functionality
    // TODO: Add confirmation dialog tests after implementing modal
    await waitFor(() => {
      expect(screen.queryByText('Test Campaign')).not.toBeInTheDocument();
    });
  });

  it('can duplicate a campaign', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText(/Duplicate/i));
    
    await waitFor(() => {
      expect(screen.getByText('Test Campaign (Copy)')).toBeInTheDocument();
    });
  });

  it('can set a campaign as active', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText(/Set Active/i));
    
    expect(JSON.parse(localStorage.getItem('aeoniskCampaign')!)).toMatchObject({ name: 'Test Campaign' });
  });

  it('can view campaign details', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText('Test Campaign'));
    
    await waitFor(() => {
      expect(screen.getByText(/Campaign Details/i)).toBeInTheDocument();
      expect(screen.getByText('A test campaign for unit testing')).toBeInTheDocument();
      expect(screen.getByText('Commander Vex')).toBeInTheDocument();
      expect(screen.getByText('First Contact')).toBeInTheDocument();
    });
  });

  it('can close campaign details modal', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.click(screen.getByText('Test Campaign'));
    
    await waitFor(() => {
      expect(screen.getByText(/Campaign Details/i)).toBeInTheDocument();
    });
    
    fireEvent.click(screen.getByLabelText(/Close/i));
    
    await waitFor(() => {
      expect(screen.queryByText(/Campaign Details/i)).not.toBeInTheDocument();
    });
  });

  it('can search campaigns', async () => {
    const campaigns = [
      { ...mockCampaign, name: 'Void Campaign' },
      { ...mockCampaign, name: 'Corporate Campaign', theme: 'Corporate Espionage' }
    ];
    localStorage.setItem('aeoniskCampaigns', JSON.stringify(campaigns));
    render(<CampaignDashboard />);
    
    fireEvent.change(screen.getByPlaceholderText(/Search campaigns/i), { target: { value: 'void' } });
    
    await waitFor(() => {
      expect(screen.getByText('Void Campaign')).toBeInTheDocument();
      expect(screen.queryByText('Corporate Campaign')).not.toBeInTheDocument();
    });
  });

  it('can filter campaigns by theme', async () => {
    const campaigns = [
      { ...mockCampaign, name: 'Void Campaign', theme: 'Void Corruption' },
      { ...mockCampaign, name: 'Corporate Campaign', theme: 'Corporate Espionage' }
    ];
    localStorage.setItem('aeoniskCampaigns', JSON.stringify(campaigns));
    render(<CampaignDashboard />);
    
    fireEvent.change(screen.getByDisplayValue(/All Themes/i), { target: { value: 'Corporate Espionage' } });
    
    await waitFor(() => {
      expect(screen.getByText('Corporate Campaign')).toBeInTheDocument();
      expect(screen.queryByText('Void Campaign')).not.toBeInTheDocument();
    });
  });

  it('handles empty search results', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    fireEvent.change(screen.getByPlaceholderText(/Search campaigns/i), { target: { value: 'nonexistent' } });
    
    await waitFor(() => {
      expect(screen.getByText(/No campaigns match your search/i)).toBeInTheDocument();
    });
  });

  it('is mobile-friendly', () => {
    // Mock mobile viewport
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 375 });
    
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([mockCampaign]));
    render(<CampaignDashboard />);
    
    // Should render campaign cards in single column
    const campaignGrid = screen.getByTestId('campaign-grid');
    expect(campaignGrid).toHaveClass('grid-cols-1');
  });

  // TODO: Add AI integration tests after implementing enhanced AI features
  // This will require proper mocking of the AeoniskChatService
  it('can use AI Suggest Campaign', async () => {
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/AI Suggest Campaign/i));
    
    // Should open the wizard - exact behavior depends on implementation
    await waitFor(() => {
      expect(screen.getByText(/Campaign Planning Wizard/i)).toBeInTheDocument();
    });
  });
}); 