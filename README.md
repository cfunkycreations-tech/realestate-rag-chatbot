# HomeIQ — AI Real Estate Assistant 🏠

A full-featured AI-powered real estate chatbot built for a boutique Austin, TX real estate agency. Users can search listings, compare properties, and get neighborhood insights — all through a natural language chat interface.

## Features

- **RAG Architecture** — Retrieval-Augmented Generation retrieves relevant property listings based on each query before sending to the LLM, grounding responses in real inventory
- **GPT-4o-mini powered** — Fast, cost-efficient responses via OpenAI Chat Completions API
- **Smart Listing Retrieval** — Keyword + intent-based semantic search across price, bedrooms, neighborhoods, and features
- **Live Property Sidebar** — Matched listings update dynamically as conversation evolves
- **Suggested Prompts** — Guided entry points for common buyer questions
- **Responsive Design** — Mobile-friendly chat, desktop sidebar for listings
- **Dark luxury UI** — Built with React 19, TypeScript, Tailwind CSS, Vite

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React 19, TypeScript, Vite |
| Styling | Tailwind CSS |
| AI | OpenAI GPT-4o-mini (Chat Completions API) |
| RAG | In-memory keyword/intent retrieval (swap for Pinecone in production) |
| Icons | Lucide React |

## Architecture

```
User Query
    │
    ▼
RAG Retrieval Layer
(listings.ts — scores properties by relevance to query)
    │
    ▼
Context Injection
(relevant listings injected into system prompt)
    │
    ▼
OpenAI GPT-4o-mini
    │
    ▼
Grounded Response
```

In production, the RAG layer would use:
- OpenAI `text-embedding-3-small` to embed listings and queries
- Pinecone (or pgvector) as the vector store
- Cosine similarity search for retrieval

## Getting Started

### Prerequisites
- Node.js v18+
- OpenAI API key

### Installation

```bash
git clone https://github.com/cfunkycreations-tech/realestate-rag-chatbot
cd realestate-rag-chatbot
npm install
```

Create a `.env` file:
```bash
cp .env.example .env
# Add your OpenAI API key
```

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

## Customization

**Add listings:** Edit `src/services/listings.ts` — add properties to the `LISTINGS` array.

**Swap AI provider:** Replace `src/services/openai.ts` with any OpenAI-compatible API (Anthropic, Gemini, etc.).

**Production RAG:** Replace the keyword retrieval in `retrieveRelevantListings()` with embedding-based vector search via Pinecone.

## License

MIT

---

Built by [CFunk Creations LLC](mailto:cfunkycreations@gmail.com) — Austin, TX
