// ChromaDB utility for RAG chunks/embeddings storage (HTTP client for browser)
// This module provides connect, upsert, query, and delete functions for RAG data.
// Uses HTTP requests to communicate with the custom RAG backend service.

// Configuration
const RAG_BACKEND_URL = 'http://localhost:4000'; // RAG backend URL
const RAG_COLLECTION_NAME = 'rag_chunks';

// Types
export interface RagChunk {
  id: string;
  embedding: number[];
  metadata: any;
  text: string;
}

export interface QueryResult {
  ids: string[][];
  embeddings: number[][][];
  metadatas: any[][];
  documents: string[][];
  distances?: number[][];
}

// HTTP client for RAG backend operations
class RagBackendClient {
  private baseUrl: string;

  constructor(baseUrl: string = RAG_BACKEND_URL) {
    this.baseUrl = baseUrl;
  }

  async makeRequest(endpoint: string, method: string = 'GET', data?: any): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const options: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('RAG backend request failed:', error);
      throw error;
    }
  }

  async upsert(id: string, embedding: number[], metadata: any, text: string): Promise<void> {
    await this.makeRequest('/upsert', 'POST', {
      id,
      embedding,
      metadata,
      text
    });
  }

  async query(embedding: number[], topK: number = 5): Promise<QueryResult> {
    return await this.makeRequest('/query', 'POST', {
      embedding,
      topK
    });
  }

  async delete(id: string): Promise<void> {
    await this.makeRequest('/delete', 'POST', { id });
  }

  async clear(): Promise<void> {
    await this.makeRequest('/clear', 'POST');
  }

  async checkHealth(): Promise<boolean> {
    try {
      const response = await this.makeRequest('/health', 'GET');
      return response.status === 'ok';
    } catch (error) {
      return false;
    }
  }
}

// Initialize RAG backend client
const ragClient = new RagBackendClient();

// Get or create a collection for RAG chunks (collection is implicit in backend)
export async function getRagCollection(): Promise<{ name: string }> {
  return { name: RAG_COLLECTION_NAME };
}

// Upsert a chunk (by id)
export async function upsertRagChunk(id: string, embedding: number[], metadata: any, text: string): Promise<void> {
  await ragClient.upsert(id, embedding, metadata, text);
}

// Query for similar chunks
export async function queryRagChunks(embedding: number[], topK: number = 5): Promise<QueryResult> {
  return await ragClient.query(embedding, topK);
}

// Delete a chunk by id
export async function deleteRagChunk(id: string): Promise<void> {
  await ragClient.delete(id);
}

// List all chunk ids (not implemented in backend - would need to be added)
export async function listRagChunkIds(): Promise<string[]> {
  // This functionality would need to be implemented in the backend
  // For now, return empty array
  console.warn('listRagChunkIds not implemented in backend');
  return [];
}

// Clear all RAG chunks
export async function clearAllRagChunks(): Promise<void> {
  await ragClient.clear();
}

// Test connection to RAG backend
export async function testRagConnection(): Promise<boolean> {
  return await ragClient.checkHealth();
} 