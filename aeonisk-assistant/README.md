# Aeonisk AI Assistant

A mobile-first Progressive Web App (PWA) that provides conversational AI assistance for the Aeonisk YAGS tabletop RPG. Features intelligent rule retrieval, dice rolling, and conversation export for fine-tuning.

## Features

- 🤖 **Multi-Provider LLM Support**: OpenAI, Anthropic, Google, Groq, Together AI, and custom endpoints
- 📚 **AI-Enhanced RAG**: Intelligent retrieval of game rules and lore using AI-powered intent analysis
- 🎲 **Integrated Dice Rolling**: Natural language dice rolls with YAGS mechanics
- 📱 **Mobile-First PWA**: Installable on phones, works offline
- 💾 **Conversation Export**: Multiple formats (JSONL, fine-tuning, Assistants API, ShareGPT)
- 🎭 **Character Management**: Track character stats, Void Score, and Soulcredit
- ⭐ **Message Rating**: Rate responses to build high-quality fine-tuning datasets

## Setup

1. **Install dependencies:**
   ```bash
   cd aeonisk-assistant
   npm install
   ```

2. **Copy game content:**
   Create a `public/content` directory and copy your markdown files:
   ```bash
   mkdir -p public/content
   cp ../content/*.md public/content/
   cp ../datasets/aeonisk_glossary.md public/content/
   ```

3. **Update content loader:**
   Edit `src/lib/chat/service.ts` and update the `loadContentFiles()` method to fetch your actual content files:
   ```typescript
   private async loadContentFiles(): Promise<{ [filename: string]: string }> {
     const contentFiles: { [filename: string]: string } = {};
     const files = [
       'Aeonisk - YAGS Module - v1.2.0.md',
       'Aeonisk - Lore Book - v1.2.0.md',
       'Aeonisk - Gear & Tech Reference - v1.2.0.md',
       'Aeonisk - Tactical Module - v1.2.0.md',
       'aeonisk_glossary.md'
     ];
     
     for (const file of files) {
       try {
         const response = await fetch(`/content/${file}`);
         if (response.ok) {
           contentFiles[file] = await response.text();
         }
       } catch (error) {
         console.error(`Failed to load ${file}:`, error);
       }
     }
     
     return contentFiles;
   }
   ```

4. **Start the development server:**
   ```bash
   npm run dev
   ```

5. **Build for production:**
   ```bash
   npm run build
   npm run preview
   ```

## Usage

### Initial Setup

1. Open the app and click the settings icon
2. Select your preferred LLM provider
3. Enter your API key
4. For custom/local models, enter the base URL (e.g., `http://localhost:11434/v1` for Ollama)
5. Save the configuration

### Chat Interface

- Ask questions about rules, lore, or game mechanics
- Request dice rolls: "Roll a Willpower + Astral Arts check with difficulty 18"
- Describe character actions: "I want to perform a ritual to cleanse the void"
- The AI will automatically retrieve relevant rules and offer to roll dice when appropriate

### Character Management

1. Click the character icon to open the character panel
2. Click "Edit Character" to modify stats
3. The character's attributes and skills are used for dice rolls
4. Void Score and Soulcredit are tracked and updated based on actions

### Exporting Conversations

1. Click "Export" in the chat interface
2. Choose your format:
   - **JSONL**: Standard OpenAI format
   - **Fine-tuning**: Only highly-rated exchanges
   - **Assistants API**: OpenAI Assistants thread format
   - **ShareGPT**: Compatible with ShareGPT tools

### Rating Messages

- Use 👍 for good responses
- Use 👎 for bad responses  
- Use ✏️ to mark for editing
- Highly-rated messages are prioritized in fine-tuning exports

## Architecture

- **Frontend**: React + TypeScript + Tailwind CSS
- **RAG System**: AI-powered intent analysis + Fuse.js search + IndexedDB storage
- **LLM Integration**: Unified adapter pattern for multiple providers
- **Game Mechanics**: Function calling for dice rolls and rituals
- **PWA**: Service worker for offline support

## Customization

### Adding New LLM Providers

Edit `src/lib/llm/adapters.ts` to add new providers:

```typescript
export class MyProviderAdapter implements LLMAdapter {
  // Implement the LLMAdapter interface
}
```

### Modifying Game Tools

Edit `src/lib/game/tools.ts` to add or modify game-specific functions.

### Customizing RAG Behavior

Edit `src/lib/rag/index.ts` to adjust:
- Intent analysis prompts
- Retrieval strategies
- Chunk ranking algorithms

## Fine-Tuning Workflow

1. Use the app to have conversations about the game
2. Rate messages (👍/👎/✏️) as you go
3. Export using "Fine-tuning Format" to get only high-quality exchanges
4. Use the exported JSONL file to fine-tune GPT-3.5 or GPT-4
5. Deploy your fine-tuned model by adding it as a custom endpoint

## License

Distributed under the GPL v2 license, same as the YAGS system.
