import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatInterface } from '../../components/ChatInterface';
import { getChatService } from '../../lib/chat/service';
import type { Message } from '../../types';

// Mock the chat service
vi.mock('../../lib/chat/service', () => ({
  getChatService: vi.fn()
}));

// Mock other dependencies
vi.mock('../../stores/debugStore', () => ({
  useDebugStore: vi.fn(() => ({
    logs: [],
    tokenCosts: { input: 0, output: 0, cost: 0 }
  }))
}));

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>
}));

vi.mock('remark-gfm', () => ({
  default: () => {}
}));

/**
 * Test the ChatInterface component's handling of progress, error, and result messages
 * This ensures proper UI display and user interaction with generation feedback.
 */
describe('ChatInterface Progress Message Handling', () => {
  let mockChatService: any;
  let mockProgressCallback: (message: Message) => void;

  beforeEach(() => {
    mockChatService = {
      getConversationHistory: vi.fn(() => []),
      onProgressUpdate: vi.fn((callback) => {
        mockProgressCallback = callback;
        return vi.fn(); // unsubscribe function
      }),
      chat: vi.fn().mockResolvedValue({ role: 'assistant', content: 'Response' }),
      clearConversation: vi.fn(),
      exportConversation: vi.fn(),
      rateMessage: vi.fn(),
      getCharacter: vi.fn(() => null)
    };

    (getChatService as any).mockReturnValue(mockChatService);
    
    // Clear localStorage
    localStorage.clear();
  });

  describe('Message Type Display', () => {
    it('should display progress messages with correct styling and icons', async () => {
      render(<ChatInterface />);

      // Simulate progress message
      const progressMessage: Message = {
        role: 'progress',
        content: 'Generating character...',
        progressType: 'character-generation',
        progressStatus: 'in-progress',
        timestamp: Date.now()
      };

      // Send progress update
      mockProgressCallback(progressMessage);

      await waitFor(() => {
        expect(screen.getByText(/Generating character/)).toBeInTheDocument();
      });

      // Check for progress-specific styling
      const messageElement = screen.getByText(/Generating character/).closest('div');
      expect(messageElement).toHaveClass('bg-blue-900/30', 'text-blue-200', 'border-blue-500');

      // Check for progress type display
      expect(screen.getByText(/character generation/i)).toBeInTheDocument();
      expect(screen.getByText(/in-progress/i)).toBeInTheDocument();
    });

    it('should display error messages with correct styling and content', async () => {
      render(<ChatInterface />);

      const errorMessage: Message = {
        role: 'error',
        content: 'Generation failed due to network issue',
        errorDetails: 'Connection timeout after 30 seconds',
        progressType: 'character-generation',
        timestamp: Date.now()
      };

      mockProgressCallback(errorMessage);

      await waitFor(() => {
        expect(screen.getByText(/Generation failed due to network issue/)).toBeInTheDocument();
      });

      // Check for error-specific styling
      const messageElement = screen.getByText(/Generation failed/).closest('div');
      expect(messageElement).toHaveClass('bg-red-900/30', 'text-red-200', 'border-red-500');

      // Check for error header
      expect(screen.getByText('Error')).toBeInTheDocument();
    });

    it('should display result messages with action buttons', async () => {
      render(<ChatInterface />);

      const characterData = {
        name: 'Test Hero',
        concept: 'Brave Warrior',
        faction: 'Aether Dynamics'
      };

      const resultMessage: Message = {
        role: 'result',
        content: 'Character created successfully!',
        resultData: characterData,
        progressType: 'character-generation',
        timestamp: Date.now()
      };

      mockProgressCallback(resultMessage);

      await waitFor(() => {
        expect(screen.getByText(/Character created successfully!/)).toBeInTheDocument();
      });

      // Check for result-specific styling
      const messageElement = screen.getByText(/Character created successfully/).closest('div');
      expect(messageElement).toHaveClass('bg-green-900/30', 'text-green-200', 'border-green-500');

      // Check for action button
      expect(screen.getByText('View Character')).toBeInTheDocument();
    });

    it('should display campaign result with Begin Adventure button', async () => {
      render(<ChatInterface />);

      const campaignData = {
        name: 'Test Campaign',
        theme: 'Void Corruption',
        description: 'A dangerous adventure'
      };

      const resultMessage: Message = {
        role: 'result',
        content: 'Campaign created successfully!',
        resultData: campaignData,
        progressType: 'campaign-generation',
        timestamp: Date.now()
      };

      mockProgressCallback(resultMessage);

      await waitFor(() => {
        expect(screen.getByText(/Campaign created successfully!/)).toBeInTheDocument();
      });

      // Check for campaign-specific action button
      const beginButton = screen.getByText('Begin Adventure');
      expect(beginButton).toBeInTheDocument();
    });
  });

  describe('Progress Status Icons', () => {
    it('should show correct icons for different progress statuses', async () => {
      render(<ChatInterface />);

      const testCases = [
        { status: 'started', expectedIcon: '🚀' },
        { status: 'in-progress', expectedIcon: '⚙️' },
        { status: 'completed', expectedIcon: '✅' },
        { status: 'failed', expectedIcon: '❌' }
      ];

      for (const { status, expectedIcon } of testCases) {
        const message: Message = {
          role: 'progress',
          content: `Process ${status}`,
          progressType: 'character-generation',
          progressStatus: status as any,
          timestamp: Date.now()
        };

        mockProgressCallback(message);

        await waitFor(() => {
          expect(screen.getByText(expectedIcon)).toBeInTheDocument();
        });
      }
    });

    it('should show correct icon for error messages', async () => {
      render(<ChatInterface />);

      const errorMessage: Message = {
        role: 'error',
        content: 'Something went wrong',
        timestamp: Date.now()
      };

      mockProgressCallback(errorMessage);

      await waitFor(() => {
        expect(screen.getByText('❌')).toBeInTheDocument();
      });
    });

    it('should show correct icon for result messages', async () => {
      render(<ChatInterface />);

      const resultMessage: Message = {
        role: 'result',
        content: 'Success!',
        resultData: {},
        progressType: 'general',
        timestamp: Date.now()
      };

      mockProgressCallback(resultMessage);

      await waitFor(() => {
        expect(screen.getByText('🎉')).toBeInTheDocument();
      });
    });
  });

  describe('Action Button Interactions', () => {
    it('should handle View Character button click', async () => {
      render(<ChatInterface />);

      const resultMessage: Message = {
        role: 'result',
        content: 'Character ready!',
        resultData: { name: 'Hero' },
        progressType: 'character-generation',
        timestamp: Date.now()
      };

      mockProgressCallback(resultMessage);

      await waitFor(() => {
        const viewButton = screen.getByText('View Character');
        expect(viewButton).toBeInTheDocument();
      });

      // Click the button - should log character details (mocked)
      const consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      
      fireEvent.click(screen.getByText('View Character'));
      
      expect(consoleLogSpy).toHaveBeenCalledWith('Character details:', { name: 'Hero' });
      
      consoleLogSpy.mockRestore();
    });

    it('should handle Begin Adventure button click', async () => {
      render(<ChatInterface />);

      const resultMessage: Message = {
        role: 'result',
        content: 'Campaign ready!',
        resultData: { name: 'Epic Quest' },
        progressType: 'campaign-generation',
        timestamp: Date.now()
      };

      mockProgressCallback(resultMessage);

      await waitFor(() => {
        const beginButton = screen.getByText('Begin Adventure');
        expect(beginButton).toBeInTheDocument();
      });

      // Click the button - should set pending adventure
      fireEvent.click(screen.getByText('Begin Adventure'));
      
      expect(localStorage.getItem('pendingAdventure')).toBe('true');
    });
  });

  describe('Message Ordering and Duplication', () => {
    it('should prevent duplicate messages based on timestamp and content', async () => {
      render(<ChatInterface />);

      const message: Message = {
        role: 'progress',
        content: 'Unique message',
        progressType: 'general',
        progressStatus: 'started',
        timestamp: 12345
      };

      // Send the same message twice
      mockProgressCallback(message);
      mockProgressCallback(message);

      await waitFor(() => {
        const elements = screen.getAllByText(/Unique message/);
        expect(elements).toHaveLength(1);
      });
    });

    it('should display messages in chronological order', async () => {
      render(<ChatInterface />);

      const messages: Message[] = [
        {
          role: 'progress',
          content: 'First message',
          progressType: 'general',
          progressStatus: 'started',
          timestamp: 1000
        },
        {
          role: 'progress',
          content: 'Second message',
          progressType: 'general',
          progressStatus: 'in-progress',
          timestamp: 2000
        },
        {
          role: 'result',
          content: 'Third message',
          resultData: {},
          progressType: 'general',
          timestamp: 3000
        }
      ];

      // Send messages in order
      for (const message of messages) {
        mockProgressCallback(message);
      }

      await waitFor(() => {
        const messageElements = screen.getAllByText(/message/);
        expect(messageElements).toHaveLength(3);
        
        // Check order (first message should appear first in DOM)
        expect(messageElements[0]).toHaveTextContent('First message');
        expect(messageElements[1]).toHaveTextContent('Second message');
        expect(messageElements[2]).toHaveTextContent('Third message');
      });
    });
  });

  describe('Integration with Conversation History', () => {
    it('should load existing progress messages on mount', () => {
      const existingMessages: Message[] = [
        {
          role: 'progress',
          content: 'Previous progress',
          progressType: 'character-generation',
          progressStatus: 'completed',
          timestamp: Date.now()
        },
        {
          role: 'result',
          content: 'Previous result',
          resultData: { name: 'Previous Character' },
          progressType: 'character-generation',
          timestamp: Date.now()
        }
      ];

      mockChatService.getConversationHistory.mockReturnValue(existingMessages);

      render(<ChatInterface />);

      expect(screen.getByText('Previous progress')).toBeInTheDocument();
      expect(screen.getByText('Previous result')).toBeInTheDocument();
      expect(screen.getByText('View Character')).toBeInTheDocument();
    });

    it('should handle mixed message types correctly', () => {
      const mixedMessages: Message[] = [
        {
          role: 'user',
          content: 'Generate a character',
          ic: false
        },
        {
          role: 'progress',
          content: 'Starting generation...',
          progressType: 'character-generation',
          progressStatus: 'started',
          timestamp: Date.now()
        },
        {
          role: 'assistant',
          content: 'I will help you create a character.'
        },
        {
          role: 'result',
          content: 'Character completed!',
          resultData: { name: 'New Hero' },
          progressType: 'character-generation',
          timestamp: Date.now()
        }
      ];

      mockChatService.getConversationHistory.mockReturnValue(mixedMessages);

      render(<ChatInterface />);

      // All message types should be displayed
      expect(screen.getByText('Generate a character')).toBeInTheDocument();
      expect(screen.getByText('Starting generation...')).toBeInTheDocument();
      expect(screen.getByText('I will help you create a character.')).toBeInTheDocument();
      expect(screen.getByText('Character completed!')).toBeInTheDocument();
    });
  });

  describe('Responsive Design and Accessibility', () => {
    it('should apply correct maximum width to progress messages', async () => {
      render(<ChatInterface />);

      const message: Message = {
        role: 'progress',
        content: 'Long progress message that should be constrained to maximum width',
        progressType: 'general',
        progressStatus: 'in-progress',
        timestamp: Date.now()
      };

      mockProgressCallback(message);

      await waitFor(() => {
        const messageContainer = screen.getByText(/Long progress message/).closest('div');
        expect(messageContainer).toHaveClass('max-w-[80%]');
      });
    });

    it('should have proper ARIA labels for progress status', async () => {
      render(<ChatInterface />);

      const message: Message = {
        role: 'progress',
        content: 'Process status',
        progressType: 'character-generation',
        progressStatus: 'in-progress',
        timestamp: Date.now()
      };

      mockProgressCallback(message);

      await waitFor(() => {
        // Check that progress type and status are clearly indicated
        expect(screen.getByText('character generation')).toBeInTheDocument();
        expect(screen.getByText('(in-progress)')).toBeInTheDocument();
      });
    });
  });
});