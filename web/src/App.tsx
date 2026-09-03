import {
  Archive,
  Boxes,
  CalendarClock,
  CircleGauge,
  Coins,
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
  Eye,
  EyeOff,
} from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { Loading } from "./components/Common";
import { useExperienceMode } from "./preferences";

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

function TokenCostPage() {
  return (
    <iframe
      title="Token cost"
      src="/token-report"
      style={{ width: "100%", height: "calc(100vh - 2rem)", border: 0, display: "block" }}
    />
  );
}

const navigation = [
  {
    label: "Review",
    items: [
      { to: "/", label: "Home", icon: CircleGauge, basic: true },
      { to: "/trace", label: "Chat trace", icon: Waypoints, basic: false },
      { to: "/episodes", label: "Episodes", icon: GitCompareArrows, basic: false },
      { to: "/review", label: "Labels & notes", icon: Tags, basic: false },
    ],
  },
  {
    label: "Explore",
    items: [
      { to: "/search", label: "Search", icon: Search, basic: true },
      { to: "/map", label: "Semantic map", icon: Map, basic: false },
      { to: "/sessions", label: "Sessions", icon: Boxes, basic: false },
      { to: "/artifacts", label: "Code evidence", icon: FileCode2, basic: false },
    ],
  },
  {
    label: "Work archive",
    items: [
      { to: "/projects", label: "Projects & categories", icon: FolderKanban, basic: false },
      { to: "/work-trail", label: "Work trail", icon: GitCompareArrows, basic: false },
      { to: "/timesheets", label: "Workload", icon: CalendarClock, basic: true },
      { to: "/archive-status", label: "Archive status", icon: Archive, basic: false },
      { to: "/token-cost", label: "Token cost", icon: Coins, basic: true },
    ],
  },
  {
    label: "System",
    items: [{ to: "/setup", label: "Setup", icon: Settings2, basic: true }],
  },
];

export default function App() {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [experienceMode, setExperienceMode] = useExperienceMode();
  const visibleNavigation = navigation
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => experienceMode === "advanced" || item.basic),
    }))
    .filter((group) => group.items.length > 0);

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
            id="app-navigation-toggle"
            data-action-id="app.navigation.toggle"
            aria-label={navigationOpen ? "Close navigation" : "Open navigation"}
            aria-controls="primary-navigation"
            aria-expanded={navigationOpen}
            onClick={() => setNavigationOpen((open) => !open)}
          >
            {navigationOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <nav id="primary-navigation" aria-label="Primary navigation">
          {visibleNavigation.map((group) => (
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
        <button
          type="button"
          className="nav-mode-toggle"
          id="app-experience-mode-toggle"
          data-action-id="app.experience.toggle"
          onClick={() => setExperienceMode(experienceMode === "basic" ? "advanced" : "basic")}
        >
          {experienceMode === "basic" ? <Eye size={15} /> : <EyeOff size={15} />}
          <span>{experienceMode === "basic" ? "Show advanced tools" : "Use simple navigation"}</span>
        </button>
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
            <Route path="/token-cost" element={<TokenCostPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
