import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { request, resourceSchema } from "./api";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading } from "./components";
import type { VersionReference } from "./generated/contracts";
import { toggleReference } from "./scene-editor";
export default function ReferencePicker({
  endpoint,
  title,
  selected,
  onChange,
}: {
  endpoint: string;
  title: string;
  selected: VersionReference[];
  onChange: (references: VersionReference[]) => void;
}) {
  const { projectId } = useWorkspace();
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: ["scene-picker", projectId, endpoint, page],
    queryFn: ({ signal }) =>
      request(
        `/${endpoint}?project_id=${encodeURIComponent(projectId)}&limit=50&offset=${page * 50}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  return (
    <fieldset>
      <legend>选择{title}的精确版本</legend>
      <ErrorNotice error={query.error} />
      {query.isPending ? <Loading /> : null}
      <div className="resource-checklist">
        {query.data
          ?.filter((item) => item.enabled)
          .map((item) => (
            <label className="checkbox-label" key={item.id}>
              <input
                type="checkbox"
                checked={selected.some(
                  (reference) =>
                    reference.id === item.id &&
                    reference.version === item.version,
                )}
                onChange={(event) =>
                  onChange(
                    toggleReference(
                      selected,
                      { id: item.id, version: item.version },
                      event.target.checked,
                    ),
                  )
                }
              />
              {item.name} · v{item.version}
            </label>
          ))}
      </div>
      <div className="pagination">
        <button
          className="secondary"
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
        >
          上一页{title}
        </button>
        <span>第 {page + 1} 页</span>
        <button
          className="secondary"
          disabled={(query.data?.length ?? 0) < 50}
          onClick={() => setPage((current) => current + 1)}
        >
          下一页{title}
        </button>
      </div>
      <details>
        <summary>
          已选{title}版本：{selected.length}
        </summary>
        <ul>
          {selected.map((reference) => (
            <li key={reference.id}>
              {reference.id} · v{reference.version}
              <button
                className="secondary"
                onClick={() =>
                  onChange(toggleReference(selected, reference, false))
                }
              >
                移除此{title}版本
              </button>
            </li>
          ))}
        </ul>
      </details>
    </fieldset>
  );
}
