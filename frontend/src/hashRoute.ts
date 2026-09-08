export type AppRoute =
  | { name: "home" }
  | { name: "review"; id?: string }
  | { name: "train"; slug?: string }
  | { name: "studies" };

function hashParts(hash: string): string[] {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const base = String(import.meta.env.BASE_URL ?? "")
    .split("/")
    .filter(Boolean)[0];
  if (base && parts[0] === base) {
    parts.shift();
  }
  return parts;
}

export function parseHash(hash: string): AppRoute {
  const [first, second] = hashParts(hash);
  if (first === "review") {
    return { name: "review", id: second };
  }
  if (first === "train") {
    return { name: "train", slug: second };
  }
  if (first === "studies") {
    return { name: "studies" };
  }
  return { name: "home" };
}

export function toHash(route: AppRoute): string {
  switch (route.name) {
    case "review":
      return route.id ? `#/review/${route.id}` : "#/review";
    case "train":
      return route.slug ? `#/train/${route.slug}` : "#/train";
    case "studies":
      return "#/studies";
    default:
      return "#/";
  }
}

export function navigate(route: AppRoute): void {
  const next = toHash(route);
  if (window.location.hash !== next) {
    window.location.hash = next;
  }
}
