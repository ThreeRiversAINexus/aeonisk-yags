import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { CampaignDashboard } from '../../components/CampaignDashboard';

beforeEach(() => {
  localStorage.clear();
});

describe('CampaignDashboard', () => {
  it('renders without crashing and shows empty state', () => {
    render(<CampaignDashboard />);
    expect(screen.getByText(/Campaigns/i)).toBeInTheDocument();
    expect(screen.getByText(/No campaigns yet/i)).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByText('Test Campaign')).toBeInTheDocument());
  });

  it('can edit a campaign', async () => {
    // Pre-populate localStorage
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([
      { name: 'Edit Me', description: 'desc', theme: 'Void Corruption', factions: ['Sovereign Nexus'], npcs: [], scenarios: [], dreamlines: [] }
    ]));
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/Edit/i));
    fireEvent.change(screen.getByPlaceholderText(/Enter campaign name/i), { target: { value: 'Edited Campaign' } });
    fireEvent.click(screen.getByText(/Next/i)); // Factions
    fireEvent.click(screen.getByText(/Next/i)); // NPCs
    fireEvent.click(screen.getByText(/Next/i)); // Scenarios
    fireEvent.click(screen.getByText(/Next/i)); // Dreamlines
    fireEvent.click(screen.getByText(/Create Campaign/i));
    await waitFor(() => expect(screen.getByText('Edited Campaign')).toBeInTheDocument());
  });

  it('can delete a campaign', async () => {
    window.confirm = jest.fn(() => true);
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([
      { name: 'Delete Me', description: 'desc', theme: 'Void Corruption', factions: ['Sovereign Nexus'], npcs: [], scenarios: [], dreamlines: [] }
    ]));
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/Delete/i));
    await waitFor(() => expect(screen.queryByText('Delete Me')).not.toBeInTheDocument());
  });

  it('can set a campaign as active', async () => {
    localStorage.setItem('aeoniskCampaigns', JSON.stringify([
      { name: 'Active Me', description: 'desc', theme: 'Void Corruption', factions: ['Sovereign Nexus'], npcs: [], scenarios: [], dreamlines: [] }
    ]));
    window.alert = jest.fn();
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/Set Active/i));
    expect(window.alert).toHaveBeenCalledWith(expect.stringContaining('Active Me'));
    expect(JSON.parse(localStorage.getItem('aeoniskCampaign')!)).toMatchObject({ name: 'Active Me' });
  });

  it('can use AI Suggest Campaign', async () => {
    render(<CampaignDashboard />);
    fireEvent.click(screen.getByText(/AI Suggest Campaign/i));
    // Should open the wizard with AI prefill
    expect(screen.getByDisplayValue('AI Suggested Campaign')).toBeInTheDocument();
  });
}); 