import type { ContentChunk, RetrievalResult } from '../../types';
import { marked } from 'marked';
import { getRagCollection, upsertRagChunk, queryRagChunks, deleteRagChunk, listRagChunkIds } from './chromadb';

interface StoredChunk {
  chunk: ContentChunk;
  embedding?: number[];
}

interface EmbeddingProvider {
  generateEmbedding(text: string): Promise<number[]>;
}

export class AIEnhancedRAG {
  private chunks: Map<string, StoredChunk> = new Map();
  private embeddingProvider: EmbeddingProvider | null = null;
  private initialized = false;
  private migratedToChroma = false;
  
  setEmbeddingProvider(provider: EmbeddingProvider) {
    this.embeddingProvider = provider;
  }

  async initialize() {
    if (this.initialized) return;
    try {
      // Migrate from localStorage to ChromaDB if needed
      if (!this.migratedToChroma) {
        const savedChunks = localStorage.getItem('aeonisk-rag-chunks');
        if (savedChunks) {
          const parsed = JSON.parse(savedChunks);
          for (const [id, data] of Object.entries(parsed)) {
            const stored = data as StoredChunk;
            if (stored.embedding) {
              await upsertRagChunk(id, stored.embedding, stored.chunk.metadata, stored.chunk.text);
            }
          }
          // Remove from localStorage after migration
          localStorage.removeItem('aeonisk-rag-chunks');
        }
        this.migratedToChroma = true;
      }
      // Load from ChromaDB (no need to load all into memory)
      // If no chunks exist, load and index content
      const ids = await listRagChunkIds();
      if (ids.length === 0) {
        console.log('Building content index...');
        await this.loadAndIndexContent();
      }
      // Generate embeddings for chunks that don't have them
      if (this.embeddingProvider) {
        await this.generateMissingEmbeddings();
      }
      this.initialized = true;
    } catch (error) {
      console.error('Failed to initialize RAG system:', error);
      this.initialized = true;
    }
  }

  private async loadAndIndexContent() {
    const contentFiles = [
      { path: '/content/Aeonisk - YAGS Module - v1.2.0.md', source: 'Aeonisk - YAGS Module' },
      { path: '/content/Aeonisk - Lore Book - v1.2.0.md', source: 'Aeonisk - Lore Book' },
      { path: '/content/Aeonisk - Gear & Tech Reference - v1.2.0.md', source: 'Aeonisk - Gear & Tech Reference' },
      { path: '/content/aeonisk_glossary.md', source: 'Aeonisk Glossary' },
      { path: '/content/core.md', source: 'YAGS Core Rules' },
      { path: '/content/character.md', source: 'YAGS Character' },
      { path: '/content/combat.md', source: 'YAGS Combat' },
      { path: '/content/scifitech.md', source: 'YAGS Sci-Fi Tech' },
      { path: '/content/bestiary.md', source: 'YAGS Bestiary' },
      { path: '/content/Aeonisk - Tactical Module - v1.2.0.md', source: 'Aeonisk - Tactical Module' }
    ];
    for (const file of contentFiles) {
      try {
        const response = await fetch(file.path);
        const content = await response.text();
        const chunks = this.chunkContent(content, file.source);
        for (const chunk of chunks) {
          // Only upsert if not already present
          await upsertRagChunk(chunk.id, [], chunk.metadata, chunk.text);
        }
      } catch (error) {
        console.error(`Failed to load ${file.path}:`, error);
      }
    }
  }

  private async generateMissingEmbeddings() {
    if (!this.embeddingProvider) return;
    const ids = await listRagChunkIds();
    for (const id of ids) {
      // Query for chunk
      const collection = await getRagCollection();
      const result = await collection.get({ ids: [id] });
      const embedding = result.embeddings?.[0];
      const text = result.documents?.[0];
      const metadata = result.metadatas?.[0];
      if (!embedding && text) {
        try {
          const newEmbedding = await this.embeddingProvider.generateEmbedding(text);
          await upsertRagChunk(id, newEmbedding, metadata, text);
        } catch (error) {
          console.error(`Failed to generate embedding for ${id}:`, error);
        }
      }
    }
  }

  // Utility to fully flatten arrays of arrays
  private flattenDeep<T>(arr: any): T[] {
    return Array.isArray(arr) ? arr.flat(Infinity).filter((x): x is T => x !== null && x !== undefined) : [];
  }

  // Retrieval using ChromaDB
  async retrieve(query: string, limit: number = 5): Promise<RetrievalResult> {
    if (!this.embeddingProvider) throw new Error('No embedding provider set');
    const queryEmbedding = await this.embeddingProvider.generateEmbedding(query);
    const results = await queryRagChunks(queryEmbedding, limit);
    const chunks: ContentChunk[] = [];
    // Fully flatten and filter arrays for correct types
    const ids = this.flattenDeep<string>(results.ids).filter((id): id is string => typeof id === 'string');
    const documents = this.flattenDeep<string>(results.documents).filter((doc): doc is string => typeof doc === 'string');
    const metadatas = this.flattenDeep<ContentChunk['metadata']>(results.metadatas).filter((meta): meta is ContentChunk['metadata'] => !!meta && typeof meta === 'object');
    for (let i = 0; i < Math.min(ids.length, documents.length, metadatas.length); i++) {
      if (ids[i] && documents[i] && metadatas[i]) {
        chunks.push({
          id: ids[i],
          text: documents[i],
          metadata: metadatas[i]
        });
      }
    }
    // ChromaDB may not return similarity scores; use dummy values for now
    const relevanceScores = chunks.map(() => 1);
    return { chunks, relevanceScores };
  }

  // Add a new chunk to ChromaDB
  async addChunk(chunk: ContentChunk) {
    await upsertRagChunk(chunk.id, [], chunk.metadata, chunk.text);
  }

  // Get the number of chunks in ChromaDB
  async getChunkCount(): Promise<number> {
    const ids = await listRagChunkIds();
    return ids.length;
  }

  // Clear all RAG data from ChromaDB
  async clearIndex() {
    await (await getRagCollection()).delete({ ids: await listRagChunkIds() });
  }

  private chunkContent(markdown: string, source: string): ContentChunk[] {
    const chunks: ContentChunk[] = [];
    const tokens = marked.lexer(markdown);
    
    let currentSection = '';
    let currentSubsection = '';
    let currentText = '';
    let chunkId = 0;

    for (const token of tokens) {
      if (token.type === 'heading') {
        // Save current chunk if exists
        if (currentText.trim()) {
          chunks.push({
            id: `${source.replace(/\s+/g, '-').toLowerCase()}-${chunkId++}`,
            text: currentText.trim(),
            metadata: {
              source,
              section: currentSection,
              type: this.determineType(currentSection, currentText),
              keywords: this.extractKeywords(currentSection, currentSubsection, currentText),
              ...(currentSubsection && { subsection: currentSubsection })
            }
          });
          currentText = '';
        }

        if (token.depth === 2) {
          currentSection = token.text;
          currentSubsection = '';
        } else if (token.depth === 3) {
          currentSubsection = token.text;
        }
      } else if (token.type === 'paragraph' || token.type === 'text') {
        currentText += token.raw + '\n';
        
        // Create chunk at reasonable size
        if (currentText.length > 500) {
          chunks.push({
            id: `${source.replace(/\s+/g, '-').toLowerCase()}-${chunkId++}`,
            text: currentText.trim(),
            metadata: {
              source,
              section: currentSection,
              type: this.determineType(currentSection, currentText),
              keywords: this.extractKeywords(currentSection, currentSubsection, currentText),
              ...(currentSubsection && { subsection: currentSubsection })
            }
          });
          currentText = '';
        }
      }
    }

    // Don't forget the last chunk
    if (currentText.trim()) {
      chunks.push({
        id: `${source.replace(/\s+/g, '-').toLowerCase()}-${chunkId++}`,
        text: currentText.trim(),
        metadata: {
          source,
          section: currentSection,
          type: this.determineType(currentSection, currentText),
          keywords: this.extractKeywords(currentSection, currentSubsection, currentText),
          ...(currentSubsection && { subsection: currentSubsection })
        }
      });
    }

    return chunks;
  }

  private determineType(section: string, text: string): ContentChunk['metadata']['type'] {
    const combined = `${section} ${text}`.toLowerCase();
    
    if (combined.includes('ritual')) return 'ritual';
    if (combined.includes('faction')) return 'faction';
    if (combined.includes('lore') || combined.includes('history')) return 'lore';
    if (combined.includes('skill') || combined.includes('attribute')) return 'skill';
    if (combined.includes('combat') || combined.includes('attack')) return 'combat';
    if (combined.includes('gear') || combined.includes('equipment')) return 'gear';
    
    return 'rules';
  }

  private extractKeywords(section: string, subsection: string, text: string): string[] {
    const keywords = new Set<string>();
    
    // Add section/subsection as keywords
    if (section) keywords.add(section.toLowerCase());
    if (subsection) keywords.add(subsection.toLowerCase());
    
    // Extract important Aeonisk terms
    const importantTerms = [
      'will', 'bond', 'void', 'ritual', 'astral', 'soulcredit',
      'sovereign nexus', 'astral commerce', 'pantheon security',
      'aether dynamics', 'arcane genetics', 'tempest industries',
      'freeborn', 'true will', 'willpower', 'empathy', 'agility',
      'yags', 'skill', 'attribute', 'd20'
    ];
    
    const textLower = text.toLowerCase();
    for (const term of importantTerms) {
      if (textLower.includes(term)) {
        keywords.add(term);
      }
    }
    
    return Array.from(keywords);
  }
}
