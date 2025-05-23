import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import fetch from 'node-fetch';

// Get __dirname equivalent for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables
dotenv.config({ path: path.join(__dirname, '..', '.env') });

const OPENAI_API_KEY = process.env.VITE_OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  console.error('Error: VITE_OPENAI_API_KEY not found in .env file');
  process.exit(1);
}

// Content files to process
const CONTENT_FILES = [
  'Aeonisk - YAGS Module - v1.2.0.md',
  'Aeonisk - Lore Book - v1.2.0.md',
  'Aeonisk - Gear & Tech Reference - v1.2.0.md',
  'aeonisk_glossary.md',
  'core.md',
  'character.md',
  'combat.md',
  'scifitech.md',
  'bestiary.md',
  'Aeonisk - Tactical Module - v1.2.0.md'
];

const CONTENT_DIR = path.join(__dirname, '..', 'public', 'content');
const OUTPUT_DIR = path.join(__dirname, '..', 'public', 'embeddings');
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'aeonisk-embeddings.json');

// Ensure output directory exists
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// Simple markdown chunking (matches the browser implementation)
function chunkContent(markdown, source) {
  const chunks = [];
  const lines = markdown.split('\n');
  
  let currentSection = '';
  let currentSubsection = '';
  let currentText = '';
  let chunkId = 0;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      // Save previous chunk if exists
      if (currentText.trim()) {
        chunks.push({
          id: `${source.toLowerCase().replace(/\s+/g, '-')}-${chunkId++}`,
          text: currentText.trim(),
          metadata: {
            source,
            section: currentSection,
            type: determineType(currentSection, currentText),
            keywords: extractKeywords(currentSection, currentSubsection, currentText),
            ...(currentSubsection && { subsection: currentSubsection })
          }
        });
        currentText = '';
      }
      currentSection = line.substring(3).trim();
      currentSubsection = '';
    } else if (line.startsWith('### ')) {
      // Save previous chunk if exists
      if (currentText.trim()) {
        chunks.push({
          id: `${source.toLowerCase().replace(/\s+/g, '-')}-${chunkId++}`,
          text: currentText.trim(),
          metadata: {
            source,
            section: currentSection,
            type: determineType(currentSection, currentText),
            keywords: extractKeywords(currentSection, currentSubsection, currentText),
            ...(currentSubsection && { subsection: currentSubsection })
          }
        });
        currentText = '';
      }
      currentSubsection = line.substring(4).trim();
    } else {
      currentText += line + '\n';
      
      // Create chunk at reasonable size
      if (currentText.length > 500) {
        chunks.push({
          id: `${source.toLowerCase().replace(/\s+/g, '-')}-${chunkId++}`,
          text: currentText.trim(),
          metadata: {
            source,
            section: currentSection,
            type: determineType(currentSection, currentText),
            keywords: extractKeywords(currentSection, currentSubsection, currentText),
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
      id: `${source.toLowerCase().replace(/\s+/g, '-')}-${chunkId++}`,
      text: currentText.trim(),
      metadata: {
        source,
        section: currentSection,
        type: determineType(currentSection, currentText),
        keywords: extractKeywords(currentSection, currentSubsection, currentText),
        ...(currentSubsection && { subsection: currentSubsection })
      }
    });
  }

  return chunks;
}

function determineType(section, text) {
  const combined = `${section} ${text}`.toLowerCase();
  
  if (combined.includes('ritual')) return 'ritual';
  if (combined.includes('faction')) return 'faction';
  if (combined.includes('lore') || combined.includes('history')) return 'lore';
  if (combined.includes('skill') || combined.includes('attribute')) return 'skill';
  if (combined.includes('combat') || combined.includes('attack')) return 'combat';
  if (combined.includes('gear') || combined.includes('equipment')) return 'gear';
  
  return 'rules';
}

function extractKeywords(section, subsection, text) {
  const keywords = new Set();
  
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

async function generateEmbedding(text) {
  // Handle text length limit
  const truncatedText = text.substring(0, 8000);
  
  const response = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      input: truncatedText,
      model: 'text-embedding-ada-002'
    })
  });
  
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`OpenAI API error: ${response.status} - ${error}`);
  }
  
  const data = await response.json();
  return data.data[0].embedding;
}

async function main() {
  console.log('Starting embedding generation...');
  
  const allChunks = [];
  
  // Process each content file
  for (const filename of CONTENT_FILES) {
    const filepath = path.join(CONTENT_DIR, filename);
    
    if (!fs.existsSync(filepath)) {
      console.warn(`File not found: ${filepath}`);
      continue;
    }
    
    console.log(`Processing ${filename}...`);
    const content = fs.readFileSync(filepath, 'utf-8');
    const source = filename.replace(/\.md$/, '').replace(/ - v[\d.]+/, '');
    const chunks = chunkContent(content, source);
    
    console.log(`  Created ${chunks.length} chunks`);
    
    // Generate embeddings for each chunk
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      console.log(`  Generating embedding ${i + 1}/${chunks.length}...`);
      
      try {
        chunk.embedding = await generateEmbedding(chunk.text);
        allChunks.push(chunk);
        
        // Rate limiting - OpenAI allows 3000 RPM for embeddings
        await new Promise(resolve => setTimeout(resolve, 20));
      } catch (error) {
        console.error(`  Failed to generate embedding for chunk ${chunk.id}:`, error.message);
      }
    }
  }
  
  console.log(`\nTotal chunks with embeddings: ${allChunks.length}`);
  
  // Save to file
  const output = {
    version: '1.0',
    model: 'text-embedding-ada-002',
    generated: new Date().toISOString(),
    chunks: allChunks
  };
  
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output));
  console.log(`\nEmbeddings saved to: ${OUTPUT_FILE}`);
  
  // Show file size
  const stats = fs.statSync(OUTPUT_FILE);
  console.log(`File size: ${(stats.size / 1024 / 1024).toFixed(2)} MB`);
}

main().catch(console.error);
