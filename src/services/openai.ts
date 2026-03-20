import { retrieveRelevantListings, buildRAGContext } from './listings';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

const SYSTEM_PROMPT = `You are HomeIQ, a knowledgeable and friendly AI real estate assistant for a boutique Austin, Texas real estate agency. You help prospective buyers and renters find their perfect home.

Your personality:
- Warm and conversational, never robotic
- Knowledgeable about Austin neighborhoods, lifestyle, and market trends
- Proactive: ask follow-up questions to better understand what someone needs
- Honest: if a listing doesn't perfectly match, say so and explain what does
- Brief but complete: answer questions clearly without unnecessary fluff

What you can help with:
- Searching available listings based on budget, bedrooms, neighborhood, and features
- Comparing properties
- Explaining Austin neighborhoods and lifestyle
- General home buying / renting advice
- Scheduling showings (tell users to call 512-555-0100 or email hello@homeiq.co)

CONTEXT — Relevant Listings from our database:
{RAG_CONTEXT}

Use the listing context above to answer questions. Always reference specific properties by address when relevant. If a user asks about something not in the listings, say you don't currently have that exact match but suggest the closest alternative or offer to alert them when something comes in.`;

export async function sendMessage(
  userMessage: string,
  history: Message[]
): Promise<string> {
  const apiKey = import.meta.env.VITE_OPENAI_API_KEY;
  if (!apiKey) throw new Error('Missing VITE_OPENAI_API_KEY in .env');

  // RAG: retrieve relevant listings for this query
  const relevant = retrieveRelevantListings(userMessage);
  const ragContext = buildRAGContext(relevant);
  const systemPrompt = SYSTEM_PROMPT.replace('{RAG_CONTEXT}', ragContext);

  const messages = [
    { role: 'system', content: systemPrompt },
    ...history.slice(-10).map(m => ({ role: m.role, content: m.content })),
    { role: 'user', content: userMessage },
  ];

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages,
      temperature: 0.7,
      max_tokens: 600,
    }),
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error?.message || 'OpenAI API error');
  }

  const data = await response.json();
  return data.choices[0].message.content;
}
