import { useEffect, useCallback } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  useParams,
} from "react-router";
import { useTranslation } from "react-i18next";
import { useAppConfig } from "@/context/AppConfigContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LitBridge } from "@/components/LitBridge";
import { NotFound } from "@/pages/NotFound";
import { Maintenance } from "@/pages/Maintenance";

function useNavActiveState() {
  const location = useLocation();
  const config = useAppConfig();

  useEffect(() => {
    const pathname = location.pathname;
    document.querySelectorAll("[data-nav-link]").forEach((link) => {
      const href = link.getAttribute("href");
      let isActive = false;
      if (href === "/") {
        isActive = pathname === "/";
      } else if (href === "/nodes") {
        isActive = pathname.startsWith("/nodes");
      } else if (href) {
        isActive = pathname === href || pathname.startsWith(href + "/");
      }
      link.classList.toggle("active", isActive);
    });

    const loader = document.getElementById("nav-loading");
    if (loader) loader.classList.add("hidden");

    if (document.activeElement?.closest(".dropdown")) {
      (document.activeElement as HTMLElement).blur();
    }

    window.scrollTo(0, 0);

    const networkName = config.network_name || "MeshCore Network";
    const features = config.features ?? {};
    const t = window.t;
    const compose = (key: string) => `${t(key)} - ${networkName}`;

    const titles: Record<string, string> = { "/": networkName };
    if (features.dashboard !== false) titles["/dashboard"] = compose("entities.dashboard");
    if (features.nodes !== false) titles["/nodes"] = compose("entities.nodes");
    if (features.channels !== false) titles["/channels"] = compose("entities.channels");
    if (features.routes !== false) titles["/routes"] = compose("entities.routes");
    if (features.messages !== false) titles["/messages"] = compose("entities.messages");
    if (features.advertisements !== false) titles["/advertisements"] = compose("entities.advertisements");
    if (features.packets !== false) titles["/packets"] = compose("entities.packets");
    if (features.map !== false) titles["/map"] = compose("entities.map");
    if (features.members !== false) titles["/members"] = compose("entities.members");
    titles["/profile"] = compose("links.profile");

    if (titles[pathname]) {
      document.title = titles[pathname];
    } else if (pathname.startsWith("/nodes/")) {
      document.title = compose("entities.node_detail");
    } else {
      document.title = networkName;
    }
  }, [location.pathname, config]);
}

function ShortLinkRedirect() {
  const { prefix } = useParams();
  return <Navigate to={`/nodes/${prefix}`} replace />;
}

function LitPage({
  loader,
}: {
  loader: () => Promise<{
    render: (
      container: HTMLElement,
      params: Record<string, unknown>,
      router: { navigate: (url: string, replace?: boolean) => void },
    ) => Promise<(() => void) | void>;
  }>;
}) {
  return (
    <ErrorBoundary>
      <LitBridge loader={loader} />
    </ErrorBoundary>
  );
}

function AppRoutes() {
  const config = useAppConfig();
  const features = config.features ?? {};
  const maintenanceMode = config.system_maintenance === true;

  useNavActiveState();

  if (maintenanceMode) {
    return (
      <Routes>
        <Route path="*" element={<Maintenance />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route
        path="/"
        element={
          <LitPage loader={() => import("@legacy/pages/home.js")} />
        }
      />
      {features.dashboard !== false && (
        <Route
          path="/dashboard"
          element={
            <LitPage
              loader={() => import("@legacy/pages/dashboard.js")}
            />
          }
        />
      )}
      {features.nodes !== false && (
        <>
          <Route
            path="/nodes"
            element={
              <LitPage loader={() => import("@legacy/pages/nodes.js")} />
            }
          />
          <Route
            path="/nodes/:publicKey"
            element={
              <LitPage
                loader={() => import("@legacy/pages/node-detail.js")}
              />
            }
          />
          <Route path="/n/:prefix" element={<ShortLinkRedirect />} />
        </>
      )}
      {features.channels !== false && (
        <Route
          path="/channels"
          element={
            <LitPage
              loader={() => import("@legacy/pages/channels.js")}
            />
          }
        />
      )}
      {features.routes !== false && (
        <Route
          path="/routes"
          element={
            <LitPage loader={() => import("@legacy/pages/routes.js")} />
          }
        />
      )}
      {features.messages !== false && (
        <Route
          path="/messages"
          element={
            <LitPage
              loader={() => import("@legacy/pages/messages.js")}
            />
          }
        />
      )}
      {features.advertisements !== false && (
        <Route
          path="/advertisements"
          element={
            <LitPage
              loader={() => import("@legacy/pages/advertisements.js")}
            />
          }
        />
      )}
      {features.packets !== false && (
        <>
          <Route
            path="/packets"
            element={
              <LitPage
                loader={() => import("@legacy/pages/packets.js")}
              />
            }
          />
          <Route
            path="/packets/hash/:hash"
            element={
              <LitPage
                loader={() =>
                  import("@legacy/pages/packet-group-detail.js")
                }
              />
            }
          />
          <Route
            path="/packets/:id"
            element={
              <LitPage
                loader={() =>
                  import("@legacy/pages/packet-detail.js")
                }
              />
            }
          />
        </>
      )}
      {features.map !== false && (
        <Route
          path="/map"
          element={
            <LitPage loader={() => import("@legacy/pages/map.js")} />
          }
        />
      )}
      {features.members !== false && (
        <Route
          path="/members"
          element={
            <LitPage
              loader={() => import("@legacy/pages/members.js")}
            />
          }
        />
      )}
      {features.pages !== false && (
        <Route
          path="/pages/:slug"
          element={
            <LitPage
              loader={() => import("@legacy/pages/custom-page.js")}
            />
          }
        />
      )}
      {config.oidc_enabled && (
        <>
          <Route
            path="/profile"
            element={
              <LitPage
                loader={() => import("@legacy/pages/profile.js")}
              />
            }
          />
          <Route
            path="/profile/:id"
            element={
              <LitPage
                loader={() => import("@legacy/pages/profile.js")}
              />
            }
          />
        </>
      )}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
