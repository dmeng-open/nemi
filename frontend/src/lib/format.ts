const LABELS: Record<string, string> = {
  technology: "Technology",
  workshops: "Workshops",
  live_music: "Live music",
  food: "Food",
  comedy: "Comedy",
  arts: "Art",
  film: "Film",
  outdoors: "Outdoors",
  nightlife: "Nightlife",
  japanese: "Japanese",
  italian: "Italian",
  thai: "Thai",
  indian: "Indian",
  korean: "Korean",
  mexican: "Mexican",
  canadian: "Canadian",
  cafe: "Cafe",
  cocktail_bar: "Cocktail bar",
};

export function labelFor(token: string) {
  if (LABELS[token]) return LABELS[token];
  const text = token.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatDay(iso: string | null, timeZone: string) {
  if (!iso) return "Time to be set";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    timeZone,
  }).format(new Date(iso));
}

export function formatClock(iso: string | null, timeZone: string) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

export function formatRange(
  start: string | null,
  end: string | null,
  timeZone: string,
) {
  if (!start || !end) return "A time that fits your evening";
  return `${formatClock(start, timeZone)} – ${formatClock(end, timeZone)}`;
}

const PLACE_PRICE_BANDS: Record<number, number> = {
  0: 0,
  1: 15,
  2: 35,
  3: 70,
  4: 120,
};

function isRankingBand(
  price: number | null,
  priceLevel: number | null,
  travelTimeIsEstimate: boolean,
) {
  if (priceLevel == null) return false;
  if (travelTimeIsEstimate || price == null) return true;
  return PLACE_PRICE_BANDS[priceLevel] === price;
}

export function formatPrice(
  price: number | null,
  priceLevel: number | null,
  travelTimeIsEstimate = false,
) {
  if (isRankingBand(price, priceLevel, travelTimeIsEstimate)) {
    if (priceLevel === 0 || price === 0) return "Free";
    if (priceLevel) return "$".repeat(priceLevel);
    return "Price varies";
  }
  if (price === 0) return "Free";
  const dollars = price == null ? null : `$${Math.round(price)}`;
  const level = priceLevel ? "$".repeat(priceLevel) : null;
  if (level && dollars) return `${level} · about ${dollars}`;
  return dollars ?? level ?? "Price varies";
}

export function formatTravel(minutes: number | null, distanceKm: number | null) {
  const parts: string[] = [];
  if (minutes != null) parts.push(`${minutes} min away`);
  if (distanceKm != null) parts.push(`${distanceKm.toFixed(1)} km`);
  return parts.join(" · ");
}

export function matchPercent(score: number) {
  return `${Math.round(score * 100)}%`;
}
