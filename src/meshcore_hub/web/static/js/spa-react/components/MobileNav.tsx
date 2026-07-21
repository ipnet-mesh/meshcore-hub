import { NavLink } from "react-router";

import { useNavItems } from "@/hooks/useNavItems";

export function MobileNav() {
  const items = useNavItems("h-5 w-5");

  return (
    <>
      {items.map((item) => (
        <li key={item.href}>
          <NavLink
            to={item.href}
            end={item.end}
            className={({ isActive }) => (isActive ? "active" : undefined)}
          >
            {item.icon} {item.label}
          </NavLink>
        </li>
      ))}
    </>
  );
}
