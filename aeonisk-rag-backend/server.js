const express = require('express');
const cors = require('cors');
const { ChromaClient } = require('chromadb');
const Database = require('better-sqlite3');

const app = express();
app.use(cors());
app.use(express.json());

const db = new Database('./aeonisk-chromadb.sqlite');
const chroma = new ChromaClient({ db });

async function getRagCollection() {
  return await chroma.getOrCreateCollection('rag_chunks');
}

app.post('/upsert', async (req, res) => {
  const { id, embedding, metadata, text } = req.body;
  const collection = await getRagCollection();
  await collection.upsert({ ids: [id], embeddings: [embedding], metadatas: [metadata], documents: [text] });
  res.json({ success: true });
});

app.post('/query', async (req, res) => {
  const { embedding, topK } = req.body;
  const collection = await getRagCollection();
  const results = await collection.query({ queryEmbeddings: [embedding], nResults: topK || 5 });
  res.json(results);
});

app.post('/delete', async (req, res) => {
  const { id } = req.body;
  const collection = await getRagCollection();
  await collection.delete({ ids: [id] });
  res.json({ success: true });
});

app.post('/clear', async (req, res) => {
  const collection = await getRagCollection();
  const results = await collection.get();
  if (results.ids.length > 0) await collection.delete({ ids: results.ids });
  res.json({ success: true });
});

app.get('/health', (req, res) => res.json({ status: 'ok' }));

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => console.log(`ChromaDB RAG backend running on port ${PORT}`)); 