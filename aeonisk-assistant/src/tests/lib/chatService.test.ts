// @vitest-environment jsdom
// This test file is for Vitest or Jest. If using Vitest, import test globals below.
import { describe, it, expect } from 'vitest';
import { AeoniskChatService } from '../../lib/chat/service';
import YAML from 'yaml';

// Mock UnifiedLLMClient
class MockLLMClient {
  constructor(public response: string) {}
  async chat() {
    return { content: this.response };
  }
  supportsTools() { return false; }
}

describe('AeoniskChatService.generateCampaignProposalFromCharacter', () => {
  function makeService(response: string) {
    const service = new AeoniskChatService();
    // @ts-ignore
    service.llmClient = new MockLLMClient(response);
    return service;
  }

  const character = { name: 'Test', concept: 'Test', attributes: {}, skills: {}, voidScore: 0, soulcredit: 0, bonds: [] };

  it('parses JSON code block', async () => {
    const response = '```json\n{"name":"Test Campaign","theme":"Test","factions":[],"npcs":[],"scenarios":[],"dreamlines":[]}\n```';
    const service = makeService(response);
    const campaign = await service.generateCampaignProposalFromCharacter(character);
    expect(campaign.name).toBe('Test Campaign');
  });

  it('parses YAML code block', async () => {
    const response = '```yaml\nname: Test Campaign\ntheme: Test\nfactions: []\nnpcs: []\nscenarios: []\ndreamlines: []\n```';
    const service = makeService(response);
    const campaign = await service.generateCampaignProposalFromCharacter(character);
    expect(campaign.name).toBe('Test Campaign');
  });

  it('parses plain JSON', async () => {
    const response = '{"name":"Test Campaign","theme":"Test","factions":[],"npcs":[],"scenarios":[],"dreamlines":[]}';
    const service = makeService(response);
    const campaign = await service.generateCampaignProposalFromCharacter(character);
    expect(campaign.name).toBe('Test Campaign');
  });

  it('parses OpenAI tool/function output with properties array', async () => {
    const response = JSON.stringify({
      properties: [
        { name: 'name', value: 'Test Campaign' },
        { name: 'theme', value: 'Test' },
        { name: 'factions', value: [] },
        { name: 'npcs', value: [] },
        { name: 'scenarios', value: [] },
        { name: 'dreamlines', value: [] }
      ]
    });
    const service = makeService(response);
    const campaign = await service.generateCampaignProposalFromCharacter(character);
    expect(campaign.name).toBe('Test Campaign');
  });

  it('throws on invalid input', async () => {
    const response = 'not a campaign';
    const service = makeService(response);
    await expect(service.generateCampaignProposalFromCharacter(character)).rejects.toThrow();
  });
}); 