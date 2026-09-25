import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { z } from "zod";
import {
  DataTable,
  Details,
  ErrorNotice,
  PageTitle,
  Panel,
} from "./components";

const raster = z
  .object({
    path: z.string(),
    size_bytes: z.number().nonnegative(),
    sha256: z.string(),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    bands: z.number().int().positive(),
    dtype: z.string(),
    crs: z.string().nullable(),
    grid_id: z.string(),
    unit: z.string().nullable(),
    declared_unit: z.string().optional(),
    observed_period: z.null(),
    statistics_scope: z.enum(["full", "sample"]),
    valid_cells: z.number().nullable(),
    nodata_cells: z.number().nullable(),
    sample_cells: z.number(),
    sample_valid_cells: z.number(),
    minimum: z.number().nullable(),
    maximum: z.number().nullable(),
    value_counts: z
      .array(
        z.object({ value: z.number(), count: z.number().int().nonnegative() }),
      )
      .max(256),
    issues: z.array(z.string()),
  })
  .passthrough();
const reportSchema = z
  .object({
    kind: z.literal("coastmas_business_intake"),
    version: z.literal(1),
    generated_at: z.string(),
    source_name: z.string(),
    scientific_execution_ready: z.literal(false),
    r_runtime_available: z.boolean(),
    file_count: z.number().int().nonnegative(),
    user_declarations: z
      .object({
        year: z.number(),
        source: z.string(),
        use_restriction: z.string(),
        units: z.record(z.string(), z.string()),
      })
      .optional(),
    rasters: z.array(raster).max(10000),
    models: z
      .array(
        z
          .object({
            path: z.string(),
            name: z.string(),
            version: z.string().nullable(),
            method: z.string(),
            license: z.string().nullable(),
            execution_status: z.literal("NOT_EXECUTABLE"),
            issues: z.array(z.string()),
          })
          .passthrough(),
      )
      .max(1000),
    errors: z.array(z.object({ path: z.string(), error_type: z.string() })),
    skipped_symlinks: z.array(z.string()),
  })
  .passthrough();
const issues: Record<string, string> = {
  YEAR_ONLY_DECLARED: "已声明 2022 等所属年份；精确统计时段仍需核实",
  UNIT_USER_DECLARED: "单位来自用户声明，文件内未独立核实",
  UNIT_DECLARATION_DIFFERS_FROM_FILE: "用户单位与文件单位不同，需明确换算关系",
  GEOGRAPHIC_BOUNDS_INVALID:
    "经纬度坐标超出合法范围，需核实原始 CRS；禁止自动改标签",
  CRS_MISSING: "缺少坐标参考系",
  UNIT_UNDECLARED: "文件未声明数值单位",
  PERIOD_UNDECLARED: "观测或统计时期待确认",
  SOURCE_LICENSE_UNCONFIRMED: "来源与使用许可待确认",
  VARIABLE_MEANING_UNCONFIRMED: "变量业务含义待确认",
  CLASS_LABELS_UNCONFIRMED: "离散值的类别含义待确认",
  EXCEEDS_WEB_UPLOAD_LIMIT: "超过当前网页 64 MiB 上传上限",
  EXCEEDS_CURRENT_EXECUTION_GRID_LIMIT:
    "超过当前内存执行网格上限，需分块执行方案",
  MULTIBAND_MAPPING_REQUIRED: "多波段须明确变量映射；当前统计仅第 1 波段",
  WGS84_TRANSFORM_UNAVAILABLE: "无法可靠转换显示范围到 WGS84",
  RUNTIME_NOT_APPROVED: "尚未批准运行适配器",
  INPUT_BINDING_UNCONFIRMED: "输入及参数绑定待确认",
  BUSINESS_VALIDATION_REQUIRED: "尚无业务基准验证",
};
function issueText(code: string) {
  return issues[code] ?? code;
}
const methods: Record<string, string> = {
  projection_pursuit_clustering: "投影寻踪聚类",
  projection_pursuit_regression: "投影寻踪回归",
};
export default function BusinessIntake() {
  const [report, setReport] = useState<z.infer<typeof reportSchema> | null>(
    null,
  );
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const requestId = useRef(0);
  async function read(file: File | undefined) {
    const id = ++requestId.current;
    setReport(null);
    setError(null);
    setPage(0);
    setSearch("");
    if (!file) {
      setPending(false);
      return;
    }
    setPending(true);
    try {
      if (file.size > 4 * 1024 * 1024)
        throw new Error("检查报告不得超过 4 MiB。");
      const parsed = reportSchema.safeParse(JSON.parse(await file.text()));
      if (!parsed.success)
        throw new Error(
          "不是支持的 CoastMAS 业务资料检查报告，请使用检查工具生成。",
        );
      if (requestId.current === id) setReport(parsed.data);
    } catch (cause) {
      if (requestId.current === id)
        setError(cause instanceof Error ? cause : new Error("报告读取失败"));
    } finally {
      if (requestId.current === id) setPending(false);
    }
  }
  const filtered =
    report?.rasters.filter((row) =>
      row.path.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
    ) ?? [];
  return (
    <>
      <Link to="/data">← 返回数据目录</Link>
      <PageTitle
        title="业务资料检查"
        description="核对本机真实栅格和模型的接入条件，保留原始数据与科学含义。"
      />
      <Panel title="读取检查报告">
        <p>
          选择维护人员生成的 JSON
          报告。文件只在当前浏览器读取，不上传原始资料。检查报告不等于数据已导入、已批准模型或科学验证通过。
        </p>
        <label>
          选择业务资料检查报告
          <input
            type="file"
            accept=".json,application/json"
            onChange={(event) => void read(event.target.files?.[0])}
          />
        </label>
        {pending ? <p role="status">正在读取报告…</p> : null}
        <ErrorNotice error={error} />
      </Panel>
      {report ? (
        <>
          <Panel title="来源与接入状态">
            <p>
              {report.source_name} · {report.generated_at} · 文件{" "}
              {report.file_count} 份 · 栅格 {report.rasters.length} 份 · 模型包{" "}
              {report.models.length} 个
            </p>
            <p>
              科学运行条件尚未确认。R 运行环境：
              {report.r_runtime_available
                ? "发现 Rscript，尚未验证依赖"
                : "未发现 Rscript"}
              。不同网格不能直接按像元相加；日期、单位、类别方向和权重均不能从文件名猜测。
            </p>
            {report.errors.length ? (
              <Details
                title="读取失败文件（不计为通过）"
                value={report.errors}
              />
            ) : null}
            {report.skipped_symlinks.length ? (
              <Details
                title="未跟随的符号链接"
                value={report.skipped_symlinks}
              />
            ) : null}
          </Panel>
          {report.user_declarations ? (
            <Panel title="用户补充声明">
              <p>
                数据年份：{report.user_declarations.year}
                （不等于连续全年观测覆盖）
              </p>
              <p>
                来源：{report.user_declarations.source}；使用限制：
                {report.user_declarations.use_restriction}
              </p>
              <p>
                来源网址、具体许可条款及指标字典仍需补充。声明与文件测量分别保留。
              </p>
            </Panel>
          ) : null}
          <Panel title="真实栅格与待补条件">
            <label>
              筛选全部栅格
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(0);
                }}
              />
            </label>
            <p>
              统计针对文件存储值，尚未应用
              scale/offset；完整参数在原始检查项中。类别数量是像元数，不是面积。样本最小／最大值不是全图极值。
            </p>
            <DataTable aria-label="业务栅格检查">
              <thead>
                <tr>
                  <th>文件</th>
                  <th>网格与坐标</th>
                  <th>统计范围</th>
                  <th>值与类别数量</th>
                  <th>待处理条件</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(page * 20, (page + 1) * 20).map((row) => (
                  <tr key={row.path}>
                    <td>
                      {row.path}
                      <small className="resource-id">
                        {(row.size_bytes / 1024 ** 2).toFixed(2)} MiB
                      </small>
                    </td>
                    <td>
                      {row.width} × {row.height} · {row.bands} 波段
                      <p>
                        {row.crs?.startsWith("EPSG:")
                          ? row.crs
                          : row.crs
                            ? "自定义投影（展开查看）"
                            : "未声明 CRS"}
                      </p>
                      <small>网格 {row.grid_id.slice(0, 12)}</small>
                    </td>
                    <td>
                      {row.statistics_scope === "full"
                        ? `全图第1波段：有效 ${row.valid_cells}，缺测/无效 ${row.nodata_cells}`
                        : `第1波段采样：有效 ${row.sample_valid_cells}/${row.sample_cells}；全图数量未知`}
                    </td>
                    <td>
                      {row.minimum ?? "未知"} 至 {row.maximum ?? "未知"}
                      <p>
                        {row.value_counts
                          .map((item) => `${item.value} × ${item.count}`)
                          .join("；")}
                      </p>
                      <p>文件单位：{row.unit ?? "未声明"}</p>
                      {row.declared_unit ? (
                        <p>用户声明单位：{row.declared_unit}</p>
                      ) : null}
                    </td>
                    <td>
                      <ul>
                        {row.issues.map((code) => (
                          <li key={code}>{issueText(code)}</li>
                        ))}
                      </ul>
                      <Details title="原始检查项与指纹" value={row} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
            {!filtered.length ? <p>当前筛选无栅格。</p> : null}
            <div className="pagination">
              <button
                type="button"
                className="secondary"
                disabled={!page}
                onClick={() => setPage(page - 1)}
              >
                上一页栅格
              </button>
              <span>
                共 {filtered.length} 份 · 第 {page + 1} 页
              </span>
              <button
                type="button"
                className="secondary"
                disabled={(page + 1) * 20 >= filtered.length}
                onClick={() => setPage(page + 1)}
              >
                下一页栅格
              </button>
            </div>
          </Panel>
          <Panel title="已有模型的真实用途">
            <DataTable aria-label="业务模型检查">
              <thead>
                <tr>
                  <th>模型／版本</th>
                  <th>方法与许可</th>
                  <th>接入条件</th>
                </tr>
              </thead>
              <tbody>
                {report.models.map((model) => (
                  <tr key={model.path}>
                    <td>
                      {model.name} · {model.version ?? "未知版本"}
                      <small className="resource-id">{model.path}</small>
                    </td>
                    <td>
                      {methods[model.method] ?? "未分类方法"}
                      <p>{model.license ?? "许可未声明"}</p>
                    </td>
                    <td>
                      不可执行
                      <ul>
                        {model.issues.map((code) => (
                          <li key={code}>{issueText(code)}</li>
                        ))}
                      </ul>
                      <Details title="模型声明与指纹" value={model} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
            {!report.models.length ? <p>未发现 R 模型包声明。</p> : null}
            <p>
              聚类用于分组，回归需要响应变量及训练／验证资料；二者都不能直接替代综合评价权重或政策优化目标。未执行模型代码或附带示例。
            </p>
          </Panel>
        </>
      ) : null}
    </>
  );
}
