import {
  Archive,
  Boxes,
  CalendarClock,
  CircleGauge,
  Database,
  FileCode2,
  FolderKanban,
  GitCompareArrows,
  Map,
  Menu,
  Search,
  Settings2,
  Tags,
  Waypoints,
  X,
} from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { Loading } from "./components/Common";

const ArtifactsPage = lazy(() => import("./pages/ArtifactsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const EpisodesPage = lazy(() => import("./pages/EpisodesPage"));
const ReviewPage = lazy(() => import("./pages/ReviewPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const SetupPage = lazy(() => import("./pages/SetupRoute"));
const SessionsPage = lazy(() => import("./pages/SessionsPage"));
const TracePage = lazy(() => import("./pages/TracePage"));
const WorkArchivePage = lazy(() => import("./pages/WorkArchivePage"));
const MapPage = lazy(() => import("./pages/MapPage"));

const navigation = [
  {
    label: "Review",
    items: [
      { to: "/", label: "Focus", icon: CircleGauge },
      { to: "/trace", label: "Chat trace", icon: Waypoints },
      { to: "/episodes", label: "Episodes", icon: GitCompareArrows },
      { to: "/review", label: "Labels & notes", icon: Tags },
    ],
  },
  {
    label: "Explore",
    items: [
      { to: "/search", label: "Search", icon: Search },
      { to: "/map", label: "Semantic map", icon: Map },
      { to: "/sessions", label: "Sessions", icon: Boxes },
      { to: "/artifacts", label: "Code evidence", icon: FileCode2 },
    ],
  },
  {
    label: "Work archive",
    items: [
      { to: "/projects", label: "Projects & categories", icon: FolderKanban },
      { to: "/work-trail", label: "Work trail", icon: GitCompareArrows },
      { to: "/timesheets", label: "Workload calendar", icon: CalendarClock },
      { to: "/archive-status", label: "Archive status", icon: Archive },
    ],
  },
  {
    label: "System",
    items: [{ to: "/setup", label: "Setup & storage", icon: Settings2 }],
  },
];

export default function App() {
  const [navigationOpen, setNavigationOpen] = useState(false);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${navigationOpen ? "is-open" : ""}`}>
        <div className="sidebar-top">
          <NavLink className="brand" to="/" onClick={() => setNavigationOpen(false)}>
            <div className="brand-mark"><Database size={19} /></div>
            <div>
              <strong>Open Chat Reviewer</strong>
              <span>Self-hosted evidence</span>
            </div>
          </NavLink>
          <button
            type="button"
            className="nav-toggle"
            aria-label={navigationOpen ? "Close navigation" : "Open navigation"}
            aria-controls="primary-navigation"
            aria-expanded={navigationOpen}
            onClick={() => setNavigationOpen((open) => !open)}
          >
            {navigationOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <nav id="primary-navigation" aria-label="Primary navigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} end={to === "/"} onClick={() => setNavigationOpen(false)}>
                  <Icon size={17} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="privacy-note">
          <span className="pulse-dot" />
          Self-hosted archive
          <small>Raw chats stay in your PostgreSQL</small>
        </div>
      </aside>
      <main
        className="main-content"
        aria-hidden={navigationOpen || undefined}
        inert={navigationOpen || undefined}
      >
        <Suspense fallback={<Loading label="Loading workspace" />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/setup" element={<SetupPage />} />
            <Route path="/trace" element={<TracePage />} />
            <Route path="/trace/:sessionId" element={<TracePage />} />
            <Route path="/sessions" element={<SessionsPage />} />
            <Route path="/sessions/:sessionId" element={<SessionsPage />} />
            <Route path="/episodes" element={<EpisodesPage />} />
            <Route path="/episodes/:episodeId" element={<EpisodesPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/projects" element={<WorkArchivePage />} />
            <Route path="/work-trail" element={<WorkArchivePage />} />
            <Route path="/timesheets" element={<WorkArchivePage />} />
            <Route path="/archive-status" element={<WorkArchivePage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
