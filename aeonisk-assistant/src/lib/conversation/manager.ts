import type { Message, ConversationContext, Character } from '../../types';

export class ConversationManager {
  private messages: Message[] = [];
  private context: ConversationContext | null = null;
  private maxContextMessages = 10;

  addMessage(message: Message) {
    this.messages.push({
      ...message,
      timestamp: message.timestamp || Date.now()
    });
    this.updateContext();
  }

  getMessages(): Message[] {
    return [...this.messages];
  }

  getRecentMessages(count: number = 5): Message[] {
    return this.messages.slice(-count);
  }

  private updateContext() {
    this.context = {
      recentMessages: this.getRecentMessages(this.maxContextMessages),
      gameContext: {
        character: this.extractCharacterContext(),
        scenario: this.extractScenarioContext()
      }
    };
  }

  private extractCharacterContext(): Character | undefined {
    // Look for character information in recent tool calls
    for (let i = this.messages.length - 1; i >= 0; i--) {
      const msg = this.messages[i];
      if (msg.tool_calls) {
        for (const call of msg.tool_calls) {
          const args = JSON.parse(call.function.arguments);
          if (args.character) {
            return args.character;
          }
        }
      }
    }
    return undefined;
  }

  private extractScenarioContext(): string | undefined {
    // Look for scenario/scene information in recent messages
    const recentUserMessages = this.messages
      .filter(m => m.role === 'user')
      .slice(-3);
    
    for (const msg of recentUserMessages) {
      if (msg.content.toLowerCase().includes('scene') || 
          msg.content.toLowerCase().includes('scenario') ||
          msg.content.toLowerCase().includes('situation')) {
        return msg.content;
      }
    }
    
    return undefined;
  }

  getContext(): ConversationContext | null {
    return this.context;
  }

  clearConversation() {
    this.messages = [];
    this.context = null;
  }

  exportConversation(): string {
    return JSON.stringify(this.messages, null, 2);
  }

  importConversation(data: string) {
    try {
      const imported = JSON.parse(data);
      if (Array.isArray(imported)) {
        this.messages = imported;
        this.updateContext();
      }
    } catch (error) {
      console.error('Failed to import conversation:', error);
      throw new Error('Invalid conversation data');
    }
  }

  getConversationSummary(): string {
    const totalMessages = this.messages.length;
    const userMessages = this.messages.filter(m => m.role === 'user').length;
    const assistantMessages = this.messages.filter(m => m.role === 'assistant').length;
    const toolCalls = this.messages.filter(m => m.tool_calls && m.tool_calls.length > 0).length;
    
    return `Conversation Summary:
- Total Messages: ${totalMessages}
- User Messages: ${userMessages}
- Assistant Messages: ${assistantMessages}
- Tool Calls: ${toolCalls}`;
  }

  // Get messages formatted for LLM context
  getMessagesForLLM(systemPrompt?: string): Message[] {
    const messages: Message[] = [];
    
    if (systemPrompt) {
      messages.push({
        role: 'system',
        content: systemPrompt
      });
    }
    
    // Include recent messages, but not too many to avoid context overflow
    const recentMessages = this.getRecentMessages(20);
    messages.push(...recentMessages);
    
    return messages;
  }

  // Extract tool call results from messages
  getToolCallResults(): Array<{ name: string; result: any; timestamp: number }> {
    const results: Array<{ name: string; result: any; timestamp: number }> = [];
    
    for (let i = 0; i < this.messages.length - 1; i++) {
      const msg = this.messages[i];
      if (msg.tool_calls) {
        for (const call of msg.tool_calls) {
          const nextMsg = this.messages[i + 1];
          if (nextMsg && nextMsg.role === 'tool' && nextMsg.tool_call_id === call.id) {
            results.push({
              name: call.function.name,
              result: nextMsg.content,
              timestamp: nextMsg.timestamp || 0
            });
          }
        }
      }
    }
    
    return results;
  }
}
