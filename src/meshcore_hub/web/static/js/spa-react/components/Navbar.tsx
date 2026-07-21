import { NavLink } from "react-router";

import { useAppConfig } from "@/context/AppConfigContext";
import { useNavItems } from "@/hooks/useNavItems";
import { AuthSection } from "@/components/AuthSection";
import { MobileNav } from "@/components/MobileNav";
import { ThemeToggle } from "@/components/ThemeToggle";

export function Navbar() {
  const config = useAppConfig();
  const items = useNavItems("h-4 w-4");
  const logoClass = `theme-logo${
    config.logo_invert_light ? " theme-logo--invert-light" : ""
  } h-6 w-6 mr-2`;

  return (
    <div className="navbar bg-base-100 shadow-lg">
      <div className="navbar-start">
        <NavLink to="/" end className="btn btn-ghost text-xl">
          <img src={config.logo_url} alt={config.network_name} className={logoClass} />
          {config.network_name}
        </NavLink>
      </div>
      <div className="navbar-center hidden lg:flex">
        <ul className="menu menu-horizontal px-1">
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
        </ul>
      </div>
      <div className="navbar-end gap-1 pr-2">
        <ThemeToggle />
        {config.oidc_enabled && !config.system_maintenance && <AuthSection />}
        <div className="dropdown dropdown-end lg:hidden">
          <div tabIndex={0} role="button" className="btn btn-ghost">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </div>
          <ul
            tabIndex={0}
            className="dropdown-content menu z-50 p-2 shadow bg-base-100 rounded-box w-56 mt-3"
          >
            <MobileNav />
          </ul>
        </div>
      </div>
    </div>
  );
}
