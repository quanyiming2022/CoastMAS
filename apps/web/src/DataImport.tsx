import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request, revisionSchema } from "./api";
import { dataContract } from "./data-editor";
import { useWorkspace } from "./workspace";
import {
  DataTable,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
} from "./components";

const listing = z.object({
  sources: z.array(z.string()),
  files: z.array(z.object({ path: z.string(), size_bytes: z.number() })),
  total: z.number(),
});
export default function DataImport() {
  const { projectId } = useWorkspace();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [mode, setMode] = useState("upload");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [path, setPath] = useState("");
  const [offset, setOffset] = useState(0);
  const [name, setName] = useState("");
  const [provenance, setProvenance] = useState("");
  const [license, setLicense] = useState("");
  const [year, setYear] = useState("");
  const files = useQuery({
    queryKey: ["local-import-files", projectId, source, offset],
    enabled: mode === "local",
    queryFn: ({ signal }) =>
      request(
        `/data-assets/local-files?project_id=${encodeURIComponent(projectId)}${source ? `&source=${encodeURIComponent(source)}&offset=${offset}` : ""}`,
        listing,
        { signal },
      ),
  });
  const save = useMutation({
    mutationFn: async () => {
      if (!name.trim() || !provenance.trim() || !license.trim())
        throw new Error(
          "请填写数据名称、来源与使用许可；尚不明确可如实填写待核实。",
        );
      const declaration = {
        name,
        source: provenance,
        license,
        year: year ? Number(year) : null,
      };
      if (
        year &&
        (!Number.isInteger(declaration.year) ||
          declaration.year! < 1 ||
          declaration.year! > 9999)
      )
        throw new Error("年份需为1至9999的整数，未知留空。");
      if (mode === "local") {
        if (!source || !path) throw new Error("请选择已授权目录中的文件。");
        return request(
          "/data-assets/ingest-local",
          revisionSchema.extend({ spec: dataContract }),
          {
            method: "POST",
            body: { project_id: projectId, source, path, declaration },
          },
        );
      }
      if (!file) throw new Error("请选择原始影像文件。");
      if (file.size > 2 * 1024 ** 3) throw new Error("单文件接入上限为2 GiB。");
      const body = new FormData();
      body.append("project_id", projectId);
      body.append("declaration", JSON.stringify(declaration));
      body.append("file", file);
      return request(
        "/data-assets/ingest",
        revisionSchema.extend({ spec: dataContract }),
        { method: "POST", body },
      );
    },
    onSuccess: async (revision) => {
      await cache.invalidateQueries({ queryKey: ["data"] });
      navigate(`/data/${encodeURIComponent(revision.resource_id)}/workspace`);
    },
  });
  return (
    <>
      <Link to="/data">← 返回数据目录</Link>
      <PageTitle
        title="导入真实影像"
        description="保存完整原文件，自动读取坐标、网格、波段和缺测信息，再补充科学变量映射。"
      />
      <ErrorNotice error={save.error ?? files.error} />
      <Panel title="文件接入">
        <p>
          支持GeoTIFF，单文件最多2
          GiB，原始像元不裁剪。导入成功后可以预览、下载和编辑变量；尚未映射或坐标异常的资产不能作为已验证输入执行。
        </p>
        <p>
          <Link to="/data/new">
            CSV、GeoJSON、Shapefile、GeoPackage、NetCDF、JSON或已有完整科学声明：使用声明上传
          </Link>
        </p>
        <form
          className="form-workspace form-shell"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <fieldset
            className="form-section form-stack"
            disabled={save.isPending}
          >
            <legend>来源与原始文件</legend>
            <label>
              接入方式
              <select
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value);
                  setPath("");
                }}
              >
                <option value="upload">浏览器选择文件</option>
                <option value="local">服务器已授权目录</option>
              </select>
            </label>
            {mode === "upload" ? (
              <label>
                原始影像文件
                <input
                  type="file"
                  accept=".tif,.tiff"
                  onChange={(event) => {
                    const selected = event.target.files?.[0] ?? null;
                    setFile(selected);
                    if (selected) setName(selected.name);
                  }}
                />
              </label>
            ) : (
              <>
                <label>
                  已授权来源
                  <select
                    value={source}
                    onChange={(event) => {
                      setSource(event.target.value);
                      setOffset(0);
                      setPath("");
                    }}
                  >
                    <option value="">选择来源</option>
                    {files.data?.sources.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </label>
                {files.isFetching ? <Loading /> : null}
                {files.data && !files.data.sources.length ? (
                  <p>
                    此项目尚未配置本地导入目录。维护人员可按项目配置授权目录，或使用浏览器选择文件。
                  </p>
                ) : null}
                {source && files.data ? (
                  <>
                    <DataTable aria-label="可导入原始文件">
                      <thead>
                        <tr>
                          <th>选择与相对路径</th>
                          <th className="numeric">体积（MiB）</th>
                        </tr>
                      </thead>
                      <tbody>
                        {files.data.files.map((item) => (
                          <tr key={item.path}>
                            <td>
                              <label>
                                <input
                                  type="radio"
                                  name="local-file"
                                  checked={path === item.path}
                                  onChange={() => {
                                    setPath(item.path);
                                    setName(item.path.split("/").at(-1)!);
                                  }}
                                />
                                {item.path}
                              </label>
                            </td>
                            <td className="numeric">
                              {(item.size_bytes / 1024 ** 2).toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </DataTable>
                    {!files.data.files.length ? (
                      <p>该目录没有可导入的GeoTIFF。</p>
                    ) : null}
                    <div className="pagination">
                      <button
                        type="button"
                        disabled={!offset}
                        onClick={() => setOffset(offset - 100)}
                      >
                        上一页文件
                      </button>
                      <span>
                        共{files.data.total}份 · 第{offset / 100 + 1}页
                      </span>
                      <button
                        type="button"
                        disabled={offset + 100 >= files.data.total}
                        onClick={() => setOffset(offset + 100)}
                      >
                        下一页文件
                      </button>
                    </div>
                  </>
                ) : null}
              </>
            )}
            <div className="form-grid">
              <label>
                数据名称
                <input
                  value={name}
                  maxLength={256}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                数据来源
                <input
                  value={provenance}
                  maxLength={256}
                  onChange={(event) => setProvenance(event.target.value)}
                />
              </label>
              <label>
                使用许可
                <input
                  value={license}
                  maxLength={256}
                  onChange={(event) => setLicense(event.target.value)}
                />
              </label>
              <label>
                所属年份（可留空）
                <input
                  type="number"
                  min={1}
                  max={9999}
                  step={1}
                  value={year}
                  onChange={(event) => setYear(event.target.value)}
                />
              </label>
            </div>
            <p>
              年份仅作为用户声明保存，不自动生成全年观测时段；单位和指标含义在资产详情中补充。
            </p>
          </fieldset>
          <button type="submit" disabled={save.isPending}>
            {save.isPending ? "正在导入并核验完整文件…" : "导入为数据资产"}
          </button>
        </form>
      </Panel>
    </>
  );
}
