export interface Property {
  id: string;
  address: string;
  neighborhood: string;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number;
  type: string;
  yearBuilt: number;
  features: string[];
  description: string;
  status: 'available' | 'pending' | 'sold';
}

export const LISTINGS: Property[] = [
  {
    id: 'prop-001',
    address: '2847 South Congress Ave, Austin TX 78704',
    neighborhood: 'South Congress / SoCo',
    price: 685000,
    bedrooms: 3,
    bathrooms: 2,
    sqft: 1820,
    type: 'Bungalow',
    yearBuilt: 1962,
    features: ['Renovated kitchen', 'Original hardwood floors', 'Large backyard', 'Walking distance to South Congress shops', 'No HOA'],
    description: 'Charming mid-century bungalow in the heart of SoCo. Fully renovated kitchen with quartz countertops and stainless appliances. Original hardwood floors throughout. Private backyard with mature oak trees. Steps from some of Austin\'s best restaurants and boutiques.',
    status: 'available'
  },
  {
    id: 'prop-002',
    address: '504 West 38th St Unit 12, Austin TX 78705',
    neighborhood: 'Hyde Park',
    price: 420000,
    bedrooms: 2,
    bathrooms: 2,
    sqft: 1100,
    type: 'Condo',
    yearBuilt: 2018,
    features: ['Rooftop deck', 'Smart home system', 'EV charging', 'Pool', 'Dog friendly', 'UT shuttle stop nearby'],
    description: 'Modern condo in historic Hyde Park with stunning downtown views from private rooftop deck. Smart home system controls lighting, thermostat, and security. Building amenities include resort-style pool and EV charging. Walk to local coffee shops, Guadalupe, and the UT campus.',
    status: 'available'
  },
  {
    id: 'prop-003',
    address: '1203 Barton Hills Dr, Austin TX 78704',
    neighborhood: 'Barton Hills',
    price: 1250000,
    bedrooms: 4,
    bathrooms: 3,
    sqft: 2900,
    type: 'Single Family',
    yearBuilt: 2021,
    features: ['Pool', 'Home office', 'Chef kitchen', 'Primary suite with spa bath', 'Solar panels', '3-car garage', 'Greenbelt access'],
    description: 'Newly built luxury home backing to Barton Creek Greenbelt. Chef\'s kitchen with Wolf range, Sub-Zero fridge, and waterfall island. Primary suite with heated floors and rainfall shower. Solar panels with battery backup. Private pool with spa. Direct trail access from backyard.',
    status: 'available'
  },
  {
    id: 'prop-004',
    address: '78 East 2nd St Unit 901, Austin TX 78701',
    neighborhood: 'Downtown / East Cesar Chavez',
    price: 895000,
    bedrooms: 2,
    bathrooms: 2,
    sqft: 1350,
    type: 'High-Rise Condo',
    yearBuilt: 2020,
    features: ['Floor-to-ceiling windows', 'City skyline views', 'Concierge', 'Gym', 'Co-working lounge', 'Walking distance to 6th St'],
    description: 'Stunning 9th floor unit with panoramic Austin skyline views. Floor-to-ceiling windows flood the open floor plan with natural light. Building features 24-hour concierge, state-of-the-art fitness center, and co-working lounge. Walk to Lady Bird Lake, restaurants, and nightlife.',
    status: 'available'
  },
  {
    id: 'prop-005',
    address: '3312 Webberville Rd, Austin TX 78702',
    neighborhood: 'East Austin',
    price: 575000,
    bedrooms: 3,
    bathrooms: 2,
    sqft: 1650,
    type: 'Craftsman',
    yearBuilt: 1948,
    features: ['Historic charm', 'Updated plumbing and electrical', 'Covered porch', 'Detached studio/ADU', 'Alley access', 'Near Mueller'],
    description: 'Classic East Austin craftsman with original character and modern updates. Fully updated plumbing, electrical, and HVAC. Detached studio with AC — perfect for a home office, gym, or rental income. Wide covered front porch perfect for Austin evenings. Minutes from Mueller, Franklin BBQ, and the vibrant East 6th corridor.',
    status: 'available'
  },
  {
    id: 'prop-006',
    address: '9204 Balcones Club Dr, Austin TX 78750',
    neighborhood: 'Northwest Hills',
    price: 799000,
    bedrooms: 5,
    bathrooms: 4,
    sqft: 3400,
    type: 'Single Family',
    yearBuilt: 1989,
    features: ['Pool', 'Game room', 'Three-car garage', 'Top-rated AISD schools', 'Cul-de-sac', 'Updated master bath'],
    description: 'Spacious family home in sought-after Northwest Hills. Five bedrooms including a flexible game room perfect for a media room or playroom. Three-car garage. Sparkling pool with waterfall feature. In the attendance zone for some of Austin\'s highest-rated AISD schools. Quiet cul-de-sac street.',
    status: 'pending'
  },
];

// ── RAG: Build a simple in-memory vector context from listings ──
// In production this would use OpenAI embeddings + Pinecone.
// For the demo, we do keyword-based semantic retrieval.

export function retrieveRelevantListings(query: string, topK = 3): Property[] {
  const q = query.toLowerCase();

  const scored = LISTINGS.map(p => {
    let score = 0;
    const text = [
      p.address, p.neighborhood, p.type, p.description,
      ...p.features, String(p.price), String(p.bedrooms), String(p.bathrooms), String(p.sqft)
    ].join(' ').toLowerCase();

    // Price signals
    if (q.includes('cheap') || q.includes('affordable') || q.includes('budget')) {
      score += p.price < 600000 ? 3 : -1;
    }
    if (q.includes('luxury') || q.includes('high-end') || q.includes('upscale')) {
      score += p.price > 800000 ? 3 : -1;
    }

    // Bedroom signals
    const bedroomMatch = q.match(/(\d)\s*bed/);
    if (bedroomMatch) {
      score += p.bedrooms === parseInt(bedroomMatch[1]) ? 4 : 0;
    }

    // Feature keywords
    const keywords = ['pool', 'downtown', 'condo', 'bungalow', 'yard', 'school', 'office',
      'modern', 'historic', 'east austin', 'south congress', 'soco', 'barton', 'hyde park',
      'northwest', 'garage', 'solar', 'adu', 'studio', 'views', 'greenbelt'];
    for (const kw of keywords) {
      if (q.includes(kw) && text.includes(kw)) score += 2;
    }

    // General text overlap
    const queryWords = q.split(/\s+/).filter(w => w.length > 3);
    for (const word of queryWords) {
      if (text.includes(word)) score += 1;
    }

    return { property: p, score };
  });

  return scored
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)
    .map(s => s.property);
}

export function buildRAGContext(properties: Property[]): string {
  if (properties.length === 0) return 'No specific listings matched. Use your general knowledge of Austin real estate to answer.';

  return properties.map(p => `
LISTING: ${p.address}
Neighborhood: ${p.neighborhood}
Price: $${p.price.toLocaleString()}
Type: ${p.type} | ${p.bedrooms}bd / ${p.bathrooms}ba | ${p.sqft.toLocaleString()} sqft | Built ${p.yearBuilt}
Status: ${p.status}
Features: ${p.features.join(', ')}
Description: ${p.description}
`).join('\n---\n');
}
