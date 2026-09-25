import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, actorSchema } from "./api";
import { ErrorNotice } from "./shared";
const settingsSchema = z.object({
  sources: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      kind: z.string(),
      read_only: z.boolean(),
    }),
  ),
  runtime: z.object({
    max_upload_bytes: z.number(),
    chunk_bytes: z.number(),
    preview_size: z.number(),
    display_warp_mib: z.number(),
    free_storage_bytes: z.number(),
    session_hours: z.number(),
    secure_cookies: z.boolean(),
  }),
});
export function Administration({
  project,
  user,
}: {
  project: string;
  user: z.infer<typeof actorSchema>;
}) {
  const settings = useQuery({
    queryKey: ["system-settings"],
    enabled: user.system_admin,
    queryFn: () => api("/system/settings", settingsSchema),
  });
  return (
    <section className="system-settings" aria-label="数据源与系统设置">
      <h1>数据源与系统设置</h1>
      <div className="actions">
        <Link to={"/projects?project=" + project}>
          项目与来源授权
        </Link>
        <Link to={"/management/users?project=" + project}>账号与登录恢复</Link>
        <Link to={"/management/audit?project=" + project}>审计日志</Link>
      </div>
      {!user.system_admin ? (
        <p role="alert">
          全局连接、运行资源和认证设置仅系统管理员可查看；项目设置请进入项目管理。
        </p>
      ) : (
        <>
          <ErrorNotice error={settings.error} />
          {settings.isPending ? <p role="status">正在读取系统设置…</p> : null}
          {settings.data ? (
            <>
              <h2>数据源定义</h2>
              <p>
                以下是当前部署允许的连接。项目授权和资料导入在各自入口完成；连接本身不是已导入资料。
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>连接名称</th>
                      <th>类型</th>
                      <th>源访问</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settings.data.sources.map((source) => (
                      <tr key={source.id}>
                        <td>{source.name}</td>
                        <td>{source.kind}</td>
                        <td>{source.read_only ? "只读" : "可写"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!settings.data.sources.length ? (
                <p>当前部署未配置外部来源。</p>
              ) : null}
              <h2>运行、存储与认证</h2>
              <dl className="settings-values">
                <dt>单文件接入上限</dt>
                <dd>
                  {settings.data.runtime.max_upload_bytes / 1024 ** 3} GiB
                </dd>
                <dt>传输分段</dt>
                <dd>{settings.data.runtime.chunk_bytes / 1024 ** 2} MiB</dd>
                <dt>可用存储</dt>
                <dd>
                  {(
                    settings.data.runtime.free_storage_bytes /
                    1024 ** 3
                  ).toFixed(1)}{" "}
                  GiB
                </dd>
                <dt>预览边长 / 显示重投影预算</dt>
                <dd>
                  {settings.data.runtime.preview_size}像素 /{" "}
                  {settings.data.runtime.display_warp_mib} MiB
                </dd>
                <dt>会话有效期</dt>
                <dd>{settings.data.runtime.session_hours}小时</dd>
                <dt>会话 Cookie</dt>
                <dd>
                  HttpOnly · SameSite=Strict ·{" "}
                  {settings.data.runtime.secure_cookies
                    ? "仅HTTPS"
                    : "本机开发HTTP"}
                </dd>
              </dl>
              <p>当前配置仅供查看。修改连接或运行资源需进入授权维护流程。</p>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
