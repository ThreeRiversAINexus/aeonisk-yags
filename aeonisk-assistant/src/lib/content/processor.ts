import type { ContentChunk } from '../../types';
import { marked } from 'marked';

export class ContentProcessor {
  /**
   * Process markdown content and extract structured chunks
   */
  static processMarkdown(content: string, source: string): ContentChunk[] {
    const chunks: ContentChunk[] = [];
    const tokens = marked.lexer(content);
    
    let currentSection = '';
    let currentSubsection = '';
    let currentText = '';
    let chunkId = 0;

    for (const token of tokens) {
      if (token.type === 'heading') {
        // Save previous chunk if exists
        if (currentText.trim()) {
          chunks.push(ContentProcessor.createChunk(
            `${source}-${chunkId++}`,
            currentText.trim(),
            source,
            currentSection,
            currentSubsection
          ));
          currentText = '';
        }

        if (token.depth === 2) {
          currentSection = token.text;
          currentSubsection = '';
        } else if (token.depth === 3) {
          currentSubsection = token.text;
        }
      } else if (token.type === 'paragraph' || token.type === 'text' || token.type === 'list') {
        currentText += token.raw + '\n';
        
        // Create chunk at reasonable size
        if (currentText.length > 500) {
          chunks.push(ContentProcessor.createChunk(
            `${source}-${chunkId++}`,
            currentText.trim(),
            source,
            currentSection,
            currentSubsection
          ));
          currentText = '';
        }
      }
    }

    // Don't forget the last chunk
    if (currentText.trim()) {
      chunks.push(ContentProcessor.createChunk(
        `${source}-${chunkId++}`,
        currentText.trim(),
        source,
        currentSection,
        currentSubsection
      ));
    }

    return chunks;
  }

  private static createChunk(
    id: string,
    text: string,
    source: string,
    section: string,
    subsection: string
  ): ContentChunk {
    const type = ContentProcessor.determineType(section, subsection, text);
    const keywords = ContentProcessor.extractKeywords(text, section, subsection);

    return {
      id,
      text,
      metadata: {
        source,
        section,
        type,
        keywords,
        ...(subsection && { subsection })
      }
    };
  }

  private static determineType(
    section: string,
    subsection: string,
    text: string
  ): ContentChunk['metadata']['type'] {
    const combined = `${section} ${subsection} ${text}`.toLowerCase();
    
    if (combined.includes('ritual')) return 'ritual';
    if (combined.includes('faction')) return 'faction';
    if (combined.includes('lore') || combined.includes('history')) return 'lore';
    if (combined.includes('skill') || combined.includes('attribute')) return 'skill';
    if (combined.includes('combat') || combined.includes('attack')) return 'combat';
    if (combined.includes('gear') || combined.includes('equipment')) return 'gear';
    
    return 'rules';
  }

  private static extractKeywords(
    text: string,
    section: string,
    subsection: string
  ): string[] {
    const keywords = new Set<string>();
    
    // Add section/subsection as keywords
    if (section) keywords.add(section.toLowerCase());
    if (subsection) keywords.add(subsection.toLowerCase());
    
    // Extract important terms from text
    const importantTerms = [
      'will', 'bond', 'void', 'ritual', 'astral', 'soulcredit',
      'faction', 'nexus', 'aether', 'tempest', 'pantheon',
      'skill', 'attribute', 'willpower', 'empathy', 'agility',
      'combat', 'damage', 'soak', 'wound', 'stun',
      'yags', 'd20', 'difficulty', 'threshold'
    ];
    
    const textLower = text.toLowerCase();
    for (const term of importantTerms) {
      if (textLower.includes(term)) {
        keywords.add(term);
      }
    }
    
    return Array.from(keywords);
  }

  /**
   * Format content for display in chat
   */
  static formatForChat(chunks: ContentChunk[]): string {
    if (chunks.length === 0) return '';
    
    return chunks
      .map(chunk => {
        const header = chunk.metadata.subsection 
          ? `**${chunk.metadata.section} - ${chunk.metadata.subsection}**`
          : `**${chunk.metadata.section}**`;
        
        return `${header}\n${chunk.text}\n\n*Source: ${chunk.metadata.source}*`;
      })
      .join('\n\n---\n\n');
  }

  /**
   * Extract specific game content (rituals, factions, etc.)
   */
  static extractGameContent(chunks: ContentChunk[]) {
    const rituals = chunks.filter(c => c.metadata.type === 'ritual');
    const factions = chunks.filter(c => c.metadata.type === 'faction');
    const skills = chunks.filter(c => c.metadata.type === 'skill');
    const combat = chunks.filter(c => c.metadata.type === 'combat');
    
    return {
      rituals,
      factions,
      skills,
      combat,
      rules: chunks.filter(c => c.metadata.type === 'rules'),
      lore: chunks.filter(c => c.metadata.type === 'lore'),
      gear: chunks.filter(c => c.metadata.type === 'gear')
    };
  }
}
