import type { ContentChunk, RetrievalResult } from '../../types';
import { marked } from 'marked';

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
  
  setEmbeddingProvider(provider: EmbeddingProvider) {
    this.embeddingProvider = provider;
  }

  async initialize() {
    if (this.initialized) return;
    
    try {
      // First try to load pre-computed embeddings
      const precomputedLoaded = await this.loadPrecomputedEmbeddings();
      
      if (!precomputedLoaded) {
        // Fall back to localStorage cache
        const savedChunks = localStorage.getItem('aeonisk-rag-chunks');
        if (savedChunks) {
          const parsed = JSON.parse(savedChunks);
          for (const [id, data] of Object.entries(parsed)) {
            this.chunks.set(id, data as StoredChunk);
          }
        }
        
        // If no chunks exist, load and index content
        if (this.chunks.size === 0) {
          console.log('Building content index...');
          await this.loadAndIndexContent();
        }
        
        // Generate embeddings for chunks that don't have them
        if (this.embeddingProvider) {
          await this.generateMissingEmbeddings();
        }
      }
      
      this.initialized = true;
    } catch (error) {
      console.error('Failed to initialize RAG system:', error);
      // Fallback to basic keyword search
      this.initialized = true;
    }
  }

  private async loadPrecomputedEmbeddings(): Promise<boolean> {
    try {
      console.log('Loading pre-computed embeddings...');
      const response = await fetch('/embeddings/aeonisk-embeddings.json');
      
      if (!response.ok) {
        console.log('Pre-computed embeddings not found, falling back to dynamic generation');
        return false;
      }
      
      const data = await response.json();
      console.log(`Loaded ${data.chunks.length} pre-computed chunks`);
      
      // Load chunks into memory
      for (const chunk of data.chunks) {
        this.chunks.set(chunk.id, {
          chunk: {
            id: chunk.id,
            text: chunk.text,
            metadata: chunk.metadata
          },
          embedding: chunk.embedding
        });
      }
      
      // Save to localStorage for offline use
      this.saveChunks();
      
      return true;
    } catch (error) {
      console.error('Failed to load pre-computed embeddings:', error);
      return false;
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
          this.chunks.set(chunk.id, { chunk });
        }
      } catch (error) {
        console.error(`Failed to load ${file.path}:`, error);
      }
    }
    
    // Save chunks to localStorage
    this.saveChunks();
  }

  private async generateMissingEmbeddings() {
    if (!this.embeddingProvider) return;
    
    let updated = false;
    for (const [id, stored] of this.chunks.entries()) {
      if (!stored.embedding) {
        try {
          stored.embedding = await this.embeddingProvider.generateEmbedding(stored.chunk.text);
          updated = true;
        } catch (error) {
          console.error(`Failed to generate embedding for ${id}:`, error);
        }
      }
    }
    
    if (updated) {
      this.saveChunks();
    }
  }

  private saveChunks() {
    const toSave: Record<string, StoredChunk> = {};
    for (const [id, data] of this.chunks.entries()) {
      toSave[id] = data;
    }
    localStorage.setItem('aeonisk-rag-chunks', JSON.stringify(toSave));
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

  async retrieve(query: string, limit: number = 5): Promise<RetrievalResult> {
    if (!this.initialized) {
      await this.initialize();
    }

    if (!this.embeddingProvider) {
      // Fallback to keyword search
      return this.keywordSearch(query, limit);
    }

    try {
      // Generate embedding for the query
      const queryEmbedding = await this.embeddingProvider.generateEmbedding(query);
      
      // Calculate cosine similarity with all chunks
      const scored: Array<{ chunk: ContentChunk; score: number }> = [];
      
      for (const stored of this.chunks.values()) {
        if (stored.embedding) {
          const similarity = this.cosineSimilarity(queryEmbedding, stored.embedding);
          scored.push({ chunk: stored.chunk, score: similarity });
        }
      }
      
      // Sort by similarity and take top results
      scored.sort((a, b) => b.score - a.score);
      const topResults = scored.slice(0, limit);
      
      return {
        chunks: topResults.map(r => r.chunk),
        relevanceScores: topResults.map(r => r.score)
      };
    } catch (error) {
      console.error('Vector search failed, falling back to keyword search:', error);
      return this.keywordSearch(query, limit);
    }
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    let dotProduct = 0;
    let normA = 0;
    let normB = 0;
    
    for (let i = 0; i < a.length; i++) {
      dotProduct += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }
    
    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
  }

  private keywordSearch(query: string, limit: number): RetrievalResult {
    const queryLower = query.toLowerCase();
    const scored: Array<{ chunk: ContentChunk; score: number }> = [];
    
    for (const stored of this.chunks.values()) {
      const chunk = stored.chunk;
      let score = 0;
      
      // Check text content
      if (chunk.text.toLowerCase().includes(queryLower)) {
        score += 1;
      }
      
      // Check keywords
      const keywordMatches = chunk.metadata.keywords.filter(k => 
        k.includes(queryLower) || queryLower.includes(k)
      ).length;
      score += keywordMatches * 0.5;
      
      // Check section/subsection
      if (chunk.metadata.section.toLowerCase().includes(queryLower)) {
        score += 0.3;
      }
      if (chunk.metadata.subsection?.toLowerCase().includes(queryLower)) {
        score += 0.3;
      }
      
      if (score > 0) {
        scored.push({ chunk, score });
      }
    }
    
    // Sort by score and take top results
    scored.sort((a, b) => b.score - a.score);
    const topResults = scored.slice(0, limit);
    
    return {
      chunks: topResults.map(r => r.chunk),
      relevanceScores: topResults.map(r => r.score)
    };
  }

  async addChunk(chunk: ContentChunk) {
    this.chunks.set(chunk.id, { chunk });
    
    // Generate embedding if embedding provider is available
    if (this.embeddingProvider) {
      try {
        const embedding = await this.embeddingProvider.generateEmbedding(chunk.text);
        const stored = this.chunks.get(chunk.id);
        if (stored) {
          stored.embedding = embedding;
        }
      } catch (error) {
        console.error('Failed to generate embedding for new chunk:', error);
      }
    }
    
    this.saveChunks();
  }

  getChunkCount(): number {
    return this.chunks.size;
  }

  clearIndex() {
    this.chunks.clear();
    localStorage.removeItem('aeonisk-rag-chunks');
  }
}
