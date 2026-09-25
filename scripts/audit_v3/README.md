# V3 实现差距诊断复现

只在新的隔离空间运行。产品审计SHA为 `8d8ae10e8a53c3aa63501c0244b7e37739609c13`；审计提交仅增加诊断、证据和报告。真实58013服务未替换。脚本会在58125的合成工程数据中创建账号/项目/资产/运行，不能指向正式环境。凭据、数据库、模型原包均不在Git中。

## 准备与运行

从仓库根目录，按 `next/README.md` 安装 `next/requirements.lock`、`next/requirements-test.lock` 和 `next/web/package-lock.json` 的依赖；需Python3.12、Node及Playwright Chromium。下面为新checkout的完整顺序。初始化拒绝覆盖已存在的审计空间；已有空间应保留，不使用删除数据库绕过保护。证据目录是本次审计专用目录，重跑应在独立checkout中保留原提交证据后生成新的结果。

```sh
npm --prefix next/web run build -- --outDir ../artifacts/audit-rebuild
next/.venv/bin/python scripts/audit_v3/initialize.py --web-root next/artifacts/audit-rebuild
next/.venv/bin/python next/scripts/serve.py --config next/.state/v3-audit-20260925/settings.json --port 58125
```

启动器占用当前终端；在另一个终端运行诊断。访问文件留在 `.state/v3-audit-20260925/settings-access.json`，不可上传。初始化的简单Python模型只是用于核对上传链是否存在，未在API中执行。传入web-root时无需原机器私有设置；省略该参数只读取本机58013配置中的前端路径/运行包目录，不修改它。

```sh
next/.venv/bin/python -m pytest -c next/pyproject.toml next/tests -q --junitxml=.review/evidence/runs/v3-audit-20260925/backend-junit.xml
npm --prefix next/web test -- --run
npm --prefix next/web run lint
(cd next/web && npm exec tsc -- -b)
node scripts/audit_v3/browser.mjs
next/.venv/bin/python scripts/audit_v3/api.py
next/.venv/bin/python scripts/audit_v3/followup.py
node scripts/audit_v3/supplement.mjs
node scripts/audit_v3/final-browser.mjs
next/.venv/bin/python scripts/audit_v3/job.py
next/.venv/bin/python scripts/audit_v3/regression.py --run
next/.venv/bin/python scripts/audit_v3/source_index.py
next/.venv/bin/python scripts/audit_v3/validate.py
```

`regression.py`只生成自己的 `.audit-v3` 临时副本，复用六个现有业务测试；适配旧导航、58125地址及同字节工程夹具，不移除业务断言。修改映射及摘要写入 `test-adaptations-final.json`。Playwright原始套件的其余测试没有借此声称通过。

`api.py`在已知单项下载缺陷处记录FAIL；`followup.py`分别核对worker结果、原值、hash和另一个正确下载入口。它们是诊断探针，不将退出码0当作每个case通过。早期浏览器定位器/权限状态误判保留在原始JSON中；报告仅引用明确标记的纠正证据。`supplement.mjs`有一次带说明的故障注入：修改真实视图保存请求的band=0后交由服务器返回422，未mock成功结果。`final-browser.mjs`的稳定截图不替换加载态原图。

实际审计还记录了构建字节对照、只读数据库隔离核对和日志根因。它们只适用于原审计环境，复现者需对自己的构建重新记录，不继承旧结论。旧Run缺完整Reproduce入口；测试重跑不等于平台已具备Run复现功能。

## 证据范围

- 合成TIFF/坐标及TFW随本目录提供，manifest记录hash；不是data_quan原始观测。
- 后端290、前端72、最终六条浏览器链通过；下载500及未实现业务单独报告。
- 4种桌面截图、原生空间产物、请求/固定版本摘要位于 `.review/evidence/`。
- UI截图含工程测试账号标识；无登录密码、session、csrf、私有原包或数据库。
- `validate.py`检查报告结构、状态、引用、依赖及证据完整性，**不替代业务验收**。
