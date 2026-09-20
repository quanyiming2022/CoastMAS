# 结果对象与实体绑定

任务产物保留原始 outputs 和 node_outputs，并新增 result_view。对象 ID 是任务、节点、输出端口和显式管理单元 ID 的 JSON 元组 SHA-256；对象、地理实体、管理单元使用不同标识。对象固定模型版本，用 JSON Pointer 指向原始结果；不复制大型栅格。

绑定只使用场景选中的精确实体版本及其 management_unit_id。相同管理标识对应多个所选实体时拒绝发布，不能猜测。没有对应实体的管理结果保留为 UNBOUND 或 PARTIAL。没有管理语义的通用输出保留对象和原始指针，标记 NOT_APPLICABLE，不伪造空间联系。

海岸统计保留原始各单元指标和明确单位，包括未知 DEM 面积与人口。评价分数按原 unit_ids 和时间行对应，不重排。时间变化输出按管理单元提取变化、年趋势和各期排名，严格验证时间递增、维度与排名范围。完整地图联动仍待实现，不能计作通过。

数据库结果描述增加 result_manifest，保留旧 key/uri/bucket/sha256/size 字段兼容旧接口。清单 ID 与数据库结果 ID 相同，校验和针对实际上传字节。异质输出包的 unit 为 per-output，具体单位来自固定模型输出声明及 result_view.objects[].units；不能把整包解释为无量纲。spatial_extent 暂为 null，不能用研究区冒充实际结果覆盖范围。time_range 是运行场景的时间范围。VALIDATED 表示通过执行契约校验，不代表人工审查或管理批准。

证据：20260920T152815212265Z-result-entity-contract-green 为首批 4 项测试；20260920T153042083544Z-result-view-worker-green 为 16 项相关回归，含真实 Redis/PostgreSQL/S3 产物。20260920T153255788661Z-published-result-manifest-green 为 15 项发布/执行回归；20260920T153505272004Z-management-results-ui-green 为前端测试；20260920T153804904313Z-result-binding-browser 为真实登录→场景选择 U1 实体→工作进程→存储→结果页面/下载，验证部分绑定及固定实体 v1，保留原计算 80000 m²/320 人。截图 result-entity-binding.png。失败记录保留。

相关后端34项回归（20260920T154042079354Z-result-binding-backend-regression）、格式/类型/契约漂移/前端测试/生产构建（20260920T154157535990Z-result-binding-final-checks）通过。全项目最终门禁尚未完成。
