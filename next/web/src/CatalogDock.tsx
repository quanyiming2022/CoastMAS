import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export function dockBounds(workspaceHeight: number) {
  const max = Math.max(120, Math.floor(workspaceHeight - 264));
  return {
    min: Math.min(220, max),
    max,
    initial: Math.min(
      max,
      Math.max(220, Math.min(420, Math.round(workspaceHeight * 0.35))),
    ),
  };
}

export function CatalogDock({
  open,
  maximized,
  height,
  title,
  onHeight,
  onMaximize,
  onClose,
  children,
}: {
  open: boolean;
  maximized: boolean;
  height?: number;
  title: string;
  onHeight: (height: number) => void;
  onMaximize: () => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const [bounds, setBounds] = useState(dockBounds(800));
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const drag = useRef<{
    pointer: number;
    startY: number;
    startHeight: number;
    current: number;
  } | null>(null);
  const frame = useRef<number | null>(null);
  const current = Math.min(
    bounds.max,
    Math.max(bounds.min, dragHeight ?? height ?? bounds.initial),
  );
  useEffect(() => {
    const parent = root.current?.parentElement;
    if (!parent) return;
    const observer = new ResizeObserver(() =>
      setBounds(dockBounds(parent.getBoundingClientRect().height)),
    );
    observer.observe(parent);
    return () => {
      observer.disconnect();
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, []);
  function end(pointer: number, commit: boolean) {
    if (drag.current?.pointer !== pointer) return;
    const next = drag.current.current;
    drag.current = null;
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    setDragHeight(null);
    if (commit) onHeight(next);
  }
  return (
    <div
      ref={root}
      className="research-drawer catalog-dock"
      hidden={!open}
      style={maximized ? undefined : { height: current }}
      data-dragging={dragHeight !== null}
    >
      <div
        role="separator"
        tabIndex={0}
        aria-label="调整目录高度"
        aria-controls={id}
        aria-orientation="horizontal"
        aria-valuemin={bounds.min}
        aria-valuemax={bounds.max}
        aria-valuenow={current}
        aria-valuetext={`${current}像素${maximized ? "，表格已最大化" : ""}`}
        className="catalog-dock-splitter"
        onPointerDown={(event) => {
          if (maximized || event.button !== 0) return;
          event.preventDefault();
          event.stopPropagation();
          event.currentTarget.focus();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            pointer: event.pointerId,
            startY: event.clientY,
            startHeight: current,
            current,
          };
        }}
        onPointerMove={(event) => {
          const start = drag.current;
          if (!start || start.pointer !== event.pointerId) return;
          event.preventDefault();
          event.stopPropagation();
          start.current = Math.max(
            bounds.min,
            Math.min(
              bounds.max,
              start.startHeight + start.startY - event.clientY,
            ),
          );
          if (frame.current === null)
            frame.current = requestAnimationFrame(() => {
              frame.current = null;
              if (drag.current) setDragHeight(drag.current.current);
            });
        }}
        onPointerUp={(event) => {
          end(event.pointerId, true);
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={(event) => end(event.pointerId, false)}
        onLostPointerCapture={(event) => end(event.pointerId, false)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            onMaximize();
            return;
          }
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
            return;
          }
          if (maximized) return;
          const next =
            event.key === "ArrowUp"
              ? current + 24
              : event.key === "ArrowDown"
                ? current - 24
                : event.key === "Home"
                  ? bounds.min
                  : event.key === "End"
                    ? bounds.max
                    : null;
          if (next !== null) {
            event.preventDefault();
            onHeight(Math.max(bounds.min, Math.min(bounds.max, next)));
          }
        }}
      />
      <div className="drawer-tools">
        <strong>{title}</strong>
        <button type="button" className="secondary" onClick={onMaximize}>
          {maximized ? "恢复面板" : "最大化表格"}
        </button>
        <button type="button" className="secondary" onClick={onClose}>
          关闭目录
        </button>
      </div>
      <div id={id} className="catalog-dock-body">
        {children}
      </div>
    </div>
  );
}
