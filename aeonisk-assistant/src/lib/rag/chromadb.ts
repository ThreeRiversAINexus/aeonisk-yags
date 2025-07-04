// ChromaDB utility for RAG chunks/embeddings storage (SQLite backend)
// This module provides connect, upsert, query, and delete functions for RAG data.
// Uses ChromaDB Node.js client and SQLite for persistence.

import { ChromaClient, Collection } from 'chromadb';
import Database from 'better-sqlite3';

// Path to SQLite DB file (can be configured)
const DB_PATH = './aeonisk-chromadb.sqlite';

// Initialize SQLite DB
const db = new Database(DB_PATH);

// Initialize ChromaDB client
const chroma = new ChromaClient({ db });

// Get or create a collection for RAG chunks
export async function getRagCollection(): Promise<Collection> {
  return await chroma.getOrCreateCollection('rag_chunks');
}

// Upsert a chunk (by id)
export async function upsertRagChunk(id: string, embedding: number[], metadata: any, text: string) {
  const collection = await getRagCollection();
  await collection.upsert({ ids: [id], embeddings: [embedding], metadatas: [metadata], documents: [text] });
}

// Query for similar chunks
export async function queryRagChunks(embedding: number[], topK: number = 5) {
  const collection = await getRagCollection();
  return await collection.query({ queryEmbeddings: [embedding], nResults: topK });
}

// Delete a chunk by id
export async function deleteRagChunk(id: string) {
  const collection = await getRagCollection();
  await collection.delete({ ids: [id] });
}

// List all chunk ids (for migration/cleanup)
export async function listRagChunkIds(): Promise<string[]> {
  const collection = await getRagCollection();
  const results = await collection.get();
  return results.ids as string[];
}

// Clear all RAG chunks (dangerous!)
export async function clearAllRagChunks() {
  const collection = await getRagCollection();
  const ids = await listRagChunkIds();
  if (ids.length > 0) await collection.delete({ ids });
}

// TODO: Add more advanced query/filter logic as needed. 