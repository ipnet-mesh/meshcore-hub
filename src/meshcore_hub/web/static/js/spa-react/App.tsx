import { useEffect, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  useParams,
} from "react-router";
import { createQueryClient } from "@/utils/queryClient";
import { useAppConfig } from "@/context/AppConfigContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Navbar } from "@/components/Navbar";
import { Announcements } from "@/components/Announcements";
import { Footer } from "@/components/Footer";
import { HomePage } from "@/pages/Home";
import { DashboardPage } from "@/pages/Dashboard";
import { Nodes } from "@/pages/Nodes";
import { NodeDetailPage } from "@/pages/NodeDetail";
import { Channels } from "@/pages/Channels";
import { RoutesPage } from "@/pages/Routes";
import { Messages } from "@/pages/Messages";
import { Advertisements } from "@/pages/Advertisements";
import { Packets } from "@/pages/Packets";
import { PacketDetail } from "@/pages/PacketDetail";
import { PacketGroupDetail } from "@/pages/PacketGroupDetail";
import { MapPage } from "@/pages/MapPage";
import { Members } from "@/pages/Members";
import { CustomPagePage } from "@/pages/CustomPage";
import { Profile } from "@/pages/Profile";
import { NotFound } from "@/pages/NotFound";
import { Maintenance } from "@/pages/Maintenance";

function useNavActiveState() {
  const location = useLocation();
  const config = useAppConfig();

  useEffect(() => {
    const pathname = location.pathname;

    if (document.activeElement?.closest(".dropdown")) {
      (document.activeElement as HTMLElement).blur();
    }

    if (!location.hash) {
      window.scrollTo(0, 0);
    }

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
  }, [location.pathname, location.hash, config]);
}

function ShortLinkRedirect() {
  const { prefix } = useParams();
  return <Navigate to={`/nodes/${prefix}`} replace />;
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
          <ErrorBoundary>
            <HomePage />
          </ErrorBoundary>
        }
      />
      {features.dashboard !== false && (
        <Route
          path="/dashboard"
          element={
            <ErrorBoundary>
              <DashboardPage />
            </ErrorBoundary>
          }
        />
      )}
      {features.nodes !== false && (
        <>
          <Route
            path="/nodes"
            element={
              <ErrorBoundary>
                <Nodes />
              </ErrorBoundary>
            }
          />
          <Route
            path="/nodes/:publicKey"
            element={
              <ErrorBoundary>
                <NodeDetailPage />
              </ErrorBoundary>
            }
          />
          <Route path="/n/:prefix" element={<ShortLinkRedirect />} />
        </>
      )}
      {features.channels !== false && (
        <Route
          path="/channels"
          element={
            <ErrorBoundary>
              <Channels />
            </ErrorBoundary>
          }
        />
      )}
      {features.routes !== false && (
        <Route
          path="/routes"
          element={
            <ErrorBoundary>
              <RoutesPage />
            </ErrorBoundary>
          }
        />
      )}
      {features.messages !== false && (
        <Route
          path="/messages"
          element={
            <ErrorBoundary>
              <Messages />
            </ErrorBoundary>
          }
        />
      )}
      {features.advertisements !== false && (
        <Route
          path="/advertisements"
          element={
            <ErrorBoundary>
              <Advertisements />
            </ErrorBoundary>
          }
        />
      )}
      {features.packets !== false && (
        <>
          <Route
            path="/packets"
            element={
              <ErrorBoundary>
                <Packets />
              </ErrorBoundary>
            }
          />
          <Route
            path="/packets/hash/:hash"
            element={
              <ErrorBoundary>
                <PacketGroupDetail />
              </ErrorBoundary>
            }
          />
          <Route
            path="/packets/:id"
            element={
              <ErrorBoundary>
                <PacketDetail />
              </ErrorBoundary>
            }
          />
        </>
      )}
      {features.map !== false && (
        <Route
          path="/map"
          element={
            <ErrorBoundary>
              <MapPage />
            </ErrorBoundary>
          }
        />
      )}
      {features.members !== false && (
        <Route
          path="/members"
          element={
            <ErrorBoundary>
              <Members />
            </ErrorBoundary>
          }
        />
      )}
      {features.pages !== false && (
        <Route
          path="/pages/:slug"
          element={
            <ErrorBoundary>
              <CustomPagePage />
            </ErrorBoundary>
          }
        />
      )}
      {config.oidc_enabled && (
        <>
          <Route
            path="/profile"
            element={
              <ErrorBoundary>
                <Profile />
              </ErrorBoundary>
            }
          />
          <Route
            path="/profile/:id"
            element={
              <ErrorBoundary>
                <Profile />
              </ErrorBoundary>
            }
          />
        </>
      )}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

function Shell() {
  return (
    <>
      <Navbar />
      <Announcements />
      <main className="container mx-auto px-4 py-6 flex-1">
        <AppRoutes />
      </main>
      <Footer />
    </>
  );
}

export function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
