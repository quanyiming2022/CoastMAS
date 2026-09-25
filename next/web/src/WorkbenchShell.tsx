import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import {
  PanelLeftOpen,
  PanelLeftClose,
  LogOut,
  X,
  Menu,
  Waves,
  UserRound,
  ChevronDown,
} from "lucide-react";
import { V3Navigation } from "./V3Navigation";

export function WorkbenchShell({
  children,
  projectControl,
  onHeaderHost,
  project,
  email,
  canManage,
  systemAdmin = canManage,
  onSignOut,
  taskPurpose = null,
}: {
  children: ReactNode;
  projectControl: ReactNode;
  onHeaderHost?: (host: HTMLDivElement | null) => void;
  project: string;
  email: string;
  canManage: boolean;
  systemAdmin?: boolean;
  onSignOut: () => Promise<void>;
  taskPurpose?: string | null;
}) {
  const [expanded, setExpanded] = useState(() => {
    try {
      return (
        localStorage.getItem("coastmas.desktop.navigation.expanded") !== "false"
      );
    } catch {
      return true;
    }
  });
  const [failure, setFailure] = useState("");
  const accountId = useId();
  const [accountOpen, setAccountOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null),
    trigger = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => {
    if (dialog.current?.open) dialog.current.close();
  }, [location.pathname, location.search]);
  const navigation = <V3Navigation project={project} canManage={canManage} systemAdmin={systemAdmin} taskPurpose={taskPurpose}/>;
  async function signOut() {
    try {
      setFailure("");
      await onSignOut();
    } catch {
      setFailure("退出失败，请重试。当前内容仍保留。");
    }
  }
  return (
    <div className="professional-shell" data-expanded={expanded}>
      <aside className="workspace-rail" aria-label="工作台导航">
        <div className="workspace-brand" title="CoastMAS 海岸带科研协同平台">
          <Waves size={26} aria-hidden="true" />
          <span>
            CoastMAS<small>海岸带科研协同平台</small>
          </span>
        </div>
        {navigation}
        <button
          className="rail-toggle"
          type="button"
          aria-label={expanded ? "收起导航" : "展开导航"}
          aria-expanded={expanded}
          onClick={() => {
            const next = !expanded;
            setExpanded(next);
            try {
              localStorage.setItem(
                "coastmas.desktop.navigation.expanded",
                String(next),
              );
            } catch {
              /* Optional UI preference; navigation remains usable. */
            }
          }}
        >
          {expanded ? (
            <PanelLeftClose size={20} />
          ) : (
            <PanelLeftOpen size={20} />
          )}
          <span>{expanded ? "收起导航" : "展开导航"}</span>
        </button>
      </aside>
      <div className="workspace-main">
        <header className="workspace-topbar">
          <button
            ref={trigger}
            type="button"
            className="mobile-menu secondary"
            aria-label="打开导航"
            onClick={() => dialog.current?.showModal()}
          >
            <Menu size={19} />
          </button>
          <div className="workspace-project">{projectControl}</div>
          <div className="workspace-research-header" ref={onHeaderHost} />
          <button
            type="button"
            className="secondary account-trigger"
            popoverTarget={accountId}
            aria-label="账号菜单"
            aria-haspopup="dialog"
            aria-expanded={accountOpen}
          >
            <UserRound size={18} aria-hidden="true" />
            <span>账号</span>
            <ChevronDown size={14} aria-hidden="true" />
          </button>
          <div
            id={accountId}
            popover="auto"
            role="dialog"
            aria-label="账号详情"
            className="account-popover"
            onToggle={(event) =>
              setAccountOpen(event.currentTarget.matches(":popover-open"))
            }
          >
            <p tabIndex={0}>{email}</p>
            <button
              type="button"
              className="secondary signout"
              onClick={() => void signOut()}
            >
              <LogOut size={16} aria-hidden="true" />
              退出登录
            </button>
          </div>
        </header>
        {failure ? (
          <p role="alert" className="error">
            {failure}
          </p>
        ) : null}
        <main className="workspace-content">{children}</main>
      </div>
      <dialog
        ref={dialog}
        className="workspace-mobile-nav"
        aria-label="移动导航"
        onClose={() => trigger.current?.focus()}
      >
        <div className="section-heading">
          <strong>CoastMAS</strong>
          <button
            type="button"
            className="secondary"
            aria-label="关闭导航"
            onClick={() => dialog.current?.close()}
          >
            <X size={18} />
          </button>
        </div>
        {navigation}
      </dialog>
    </div>
  );
}
