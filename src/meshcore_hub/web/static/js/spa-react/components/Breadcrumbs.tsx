import type { ReactNode } from "react";
import { Link } from "react-router";

export interface Crumb {
  label: ReactNode;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <div className="breadcrumbs text-sm mb-4">
        <ul>
          {items.map((item, index) => {
            const isLast = index === items.length - 1;
            return (
              <li key={index} aria-current={isLast ? "page" : undefined}>
                {item.to && !isLast ? (
                  <Link to={item.to}>{item.label}</Link>
                ) : (
                  item.label
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
