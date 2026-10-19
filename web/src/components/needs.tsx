import Link from "next/link";

import type { Setup } from "@/lib/api";

type Item = Setup["items"][number];

/** The set-up items among `keys` that have nothing in them yet. */
export function missing(setup: Setup, keys: string[]): Item[] {
  return keys
    .map((key) => setup.items.find((i) => i.key === key))
    .filter((i): i is Item => i !== undefined && i.status === "missing");
}

export function has(setup: Setup, key: string): boolean {
  const item = setup.items.find((i) => i.key === key);
  return item !== undefined && item.status !== "missing";
}

/** What a page cannot work out yet, and where each missing piece comes in. */
export function Needs({ items, purpose }: { items: Item[]; purpose: string }) {
  if (items.length === 0) return null;
  return (
    <div className="notice needs">
      <p>{`${purpose}, Lekhara needs:`}</p>
      <ul>
        {items.map((i) => (
          <li key={i.key}>
            {`${i.title}. `}
            <Link href={i.href} className="link-action">
              {i.action}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
