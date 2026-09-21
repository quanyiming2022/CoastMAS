import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, LogOut, Menu, X } from "lucide-react";
import {
  activeEntry,
  groups,
  initialGroups,
  navigation,
  NAV_STORAGE_KEY,
} from "./navigation";

const mediaQuery = "(max-width: 720px)";
function subscribe(callback: () => void) {
  const query = window.matchMedia(mediaQuery);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}
function isMobile() {
  return window.matchMedia(mediaQuery).matches;
}
export default function Sidebar({
  email,
  isAdmin,
  onLogout,
  logoutPending,
}: {
  email: string;
  isAdmin: boolean;
  onLogout: () => void;
  logoutPending: boolean;
}) {
  const location = useLocation();
  const current = activeEntry(location.pathname);
  const [state, setState] = useState(() => ({
    path: location.pathname,
    expanded: initialGroups(location.pathname),
  }));
  // Derive on a real pathname transition only; toggles never affect the page subtree.
  if (state.path !== location.pathname)
    setState({
      path: location.pathname,
      expanded: current?.group
        ? { ...state.expanded, [current.group]: true }
        : state.expanded,
    });
  useEffect(() => {
    try {
      localStorage.setItem(NAV_STORAGE_KEY, JSON.stringify(state.expanded));
    } catch {
      /* The menu remains usable when storage is unavailable. */
    }
  }, [state.expanded]);
  const mobile = useSyncExternalStore(subscribe, isMobile, () => false);
  const navigationRegion = useRef<HTMLElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => dialog.current?.close();
  useEffect(() => {
    dialog.current?.close();
  }, [location.key]);
  useEffect(() => {
    const region = navigationRegion.current;
    const active = region?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!region || !active || active.closest("[hidden]")) return;
    const bounds = region.getBoundingClientRect();
    const item = active.getBoundingClientRect();
    if (item.bottom > bounds.bottom)
      region.scrollTop += item.bottom - bounds.bottom;
    else if (item.top < bounds.top) region.scrollTop -= bounds.top - item.top;
  }, [location.pathname, mobile, state.expanded]);
  const visible = navigation.filter(
    (item) => item.permission !== "admin" || isAdmin,
  );
  const link = (item: (typeof navigation)[number]) => (
    <Link
      key={item.id}
      to={item.path}
      className="nav-item"
      aria-current={current?.id === item.id ? "page" : undefined}
      onClick={close}
    >
      <item.icon size={18} aria-hidden="true" />
      <span>{item.label}</span>
    </Link>
  );
  const content = (
    <>
      <div className="sidebar-brand">
        <Link className="brand" to="/dashboard" onClick={close}>
          <span className="brand-mark" aria-hidden="true">
            ≈
          </span>
          <span>
            CoastMAS<small>海岸带科研协同平台</small>
          </span>
        </Link>
        {mobile && (
          <button
            type="button"
            className="nav-close"
            aria-label="关闭导航"
            onClick={close}
          >
            <X size={18} />
          </button>
        )}
      </div>
      <nav
        ref={navigationRegion}
        className="sidebar-navigation"
        aria-label="主导航"
      >
        {groups.map((group) => {
          const entries = visible.filter((item) => item.group === group.id);
          if (!entries.length) return null;
          return (
            <div className="nav-group" key={group.id}>
              <button
                type="button"
                className="nav-group-toggle"
                aria-expanded={state.expanded[group.id]}
                aria-controls={`nav-${group.id}`}
                onClick={() =>
                  setState((previous) => ({
                    ...previous,
                    expanded: {
                      ...previous.expanded,
                      [group.id]: !previous.expanded[group.id],
                    },
                  }))
                }
              >
                <span>{group.label}</span>
                <ChevronDown size={16} aria-hidden="true" />
              </button>
              <ul id={`nav-${group.id}`} hidden={!state.expanded[group.id]}>
                {entries.map((item) => (
                  <li key={item.id}>{link(item)}</li>
                ))}
              </ul>
            </div>
          );
        })}
        <ul className="nav-independent">
          {visible
            .filter(
              (item) => item.group === null && item.permission !== "admin",
            )
            .map((item) => (
              <li key={item.id}>{link(item)}</li>
            ))}
        </ul>
      </nav>
      <footer className="sidebar-foot">
        {visible.filter((item) => item.permission === "admin").map(link)}
        <small className="sidebar-account" title={email}>
          {email}
        </small>
        <button
          type="button"
          className="secondary sidebar-logout"
          onClick={onLogout}
          disabled={logoutPending}
        >
          <LogOut size={18} aria-hidden="true" />
          退出登录
        </button>
      </footer>
    </>
  );
  if (!mobile) return <aside className="sidebar">{content}</aside>;
  return (
    <>
      <header className="mobile-navigation-bar">
        <span>CoastMAS</span>
        <button
          ref={trigger}
          type="button"
          className="secondary"
          aria-label="打开导航"
          aria-haspopup="dialog"
          onClick={() => dialog.current?.showModal()}
        >
          <Menu size={18} aria-hidden="true" />
          导航
        </button>
      </header>
      <dialog
        ref={dialog}
        className="nav-drawer"
        aria-label="CoastMAS 导航"
        onClose={() => trigger.current?.focus()}
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <aside className="sidebar">{content}</aside>
      </dialog>
    </>
  );
}
