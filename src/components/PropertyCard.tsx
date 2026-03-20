import { Bed, Bath, Square, MapPin, Tag } from 'lucide-react';
import type { Property } from '../services/listings';

interface Props {
  property: Property;
}

export function PropertyCard({ property }: Props) {
  const statusColors: Record<string, string> = {
    available: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    pending: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    sold: 'bg-red-500/20 text-red-300 border-red-500/30',
  };

  return (
    <div className="property-card rounded-2xl p-4 mb-3 border border-white/10 bg-white/5 backdrop-blur-sm hover:bg-white/8 transition-all">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-1 text-stone-400 text-xs mb-1">
            <MapPin size={11} />
            <span>{property.neighborhood}</span>
          </div>
          <p className="text-white font-medium text-sm leading-snug">{property.address}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${statusColors[property.status]} capitalize ml-2 shrink-0`}>
          {property.status}
        </span>
      </div>

      <div className="text-amber-300 font-semibold text-lg mb-3">
        ${property.price.toLocaleString()}
      </div>

      <div className="flex gap-4 text-stone-400 text-xs mb-3">
        <span className="flex items-center gap-1"><Bed size={11} />{property.bedrooms} bd</span>
        <span className="flex items-center gap-1"><Bath size={11} />{property.bathrooms} ba</span>
        <span className="flex items-center gap-1"><Square size={11} />{property.sqft.toLocaleString()} sqft</span>
        <span className="flex items-center gap-1"><Tag size={11} />{property.type}</span>
      </div>

      <div className="flex flex-wrap gap-1">
        {property.features.slice(0, 4).map(f => (
          <span key={f} className="text-xs bg-white/8 text-stone-300 px-2 py-0.5 rounded-full border border-white/10">
            {f}
          </span>
        ))}
        {property.features.length > 4 && (
          <span className="text-xs text-stone-500">+{property.features.length - 4} more</span>
        )}
      </div>
    </div>
  );
}
