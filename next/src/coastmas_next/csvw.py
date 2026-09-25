"""W3C CSVW 2015 packaged-table profile; explicit supported semantics, no URL fetching.

Normative reference: https://www.w3.org/TR/2015/REC-tabular-metadata-20151217/
Original metadata and bytes remain immutable. Unsupported interpretation properties
are reported and prevent task use instead of being silently ignored.
"""

import codecs
import csv
import io
import json
import math
import re
import zipfile
from decimal import Decimal
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from .store import Problem

CONTEXT = "http://www.w3.org/ns/csvw"
VERSION = "W3C-REC-2015-12-17"
MAX_ROWS = 250_000


def fail(code, message):
    raise Problem(422, code, message)


def _json(raw):
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                fail("DUPLICATE_KEY", "CSVW元数据含重复属性")
            output[key] = value
        return output

    return json.loads(
        raw.decode("utf-8-sig"),
        object_pairs_hook=unique,
        parse_constant=lambda _: fail("CSVW_SCHEMA", "元数据不能含非有限JSON数值"),
    )


def _context(value):
    return value == CONTEXT or isinstance(value, list) and CONTEXT in value


def metadata(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(names) != len(set(names)) or len(names) > 1000:
            fail("ARCHIVE_PATH", "压缩包存在重复条目或超出条目预算")
        if any(
            PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts or "\\" in n
            for n in names
        ):
            fail("ARCHIVE_PATH", "压缩包包含越界路径")
        if sum(item.file_size for item in entries) > 2 * 1024**3:
            fail("ARCHIVE_LIMIT", "压缩包解压规模超过预算")
        candidates = []
        for item in entries:
            if item.filename.lower().endswith(".json") and item.file_size <= 1024**2:
                try:
                    value = _json(archive.read(item))
                except (ValueError, UnicodeError):
                    continue
                if isinstance(value, dict) and _context(value.get("@context")):
                    candidates.append((item.filename, value))
        if not candidates:
            return None
        if len(candidates) != 1:
            fail("CSVW_METADATA_AMBIGUOUS", "包内存在多份CSVW描述，请按一个明确的表组组织")
        name, value = candidates[0]
        tables = value.get("tables", [value])
        if not isinstance(tables, list) or not tables or len(tables) > 50:
            fail("CSVW_SCHEMA", "CSVW表组结构无效或超过预算")
        context = value.get("@context")
        unsupported_context = []
        if isinstance(context, list):
            for entry in context:
                if isinstance(entry, dict) and any(key != "@language" for key in entry):
                    unsupported_context.append("@context.base_or_prefix_rules")
        resolved = []
        for table in tables:
            if not isinstance(table, dict):
                fail("CSVW_SCHEMA", "CSVW表描述必须是对象")
            url = table.get("url")
            if not isinstance(url, str):
                fail("CSVW_REFERENCE", "CSVW表必须引用包内实际CSV资料")
            parts = urlsplit(url)
            decoded = unquote(parts.path)
            relative = PurePosixPath(decoded)
            if (
                parts.scheme
                or parts.netloc
                or parts.query
                or parts.fragment
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in decoded
            ):
                fail("CSVW_REFERENCE", "仅可读取包内相对路径；不自动访问网络或外部文件")
            target = str(PurePosixPath(name).parent / relative)
            if target not in names or archive.getinfo(target).file_size > 256 * 1024**2:
                fail("CSVW_REFERENCE", "CSVW引用的表缺失或超过256MiB解析预算")
            schema = table.get("tableSchema", value.get("tableSchema"))
            if not isinstance(schema, dict) or not isinstance(schema.get("columns"), list):
                fail("CSVW_SCHEMA", "CSVW需要实际列描述；外部schema引用尚未接入")
            dialect = table.get("dialect", value.get("dialect", {}))
            if not isinstance(dialect, dict):
                fail("CSVW_SCHEMA", "CSVW方言必须为包内显式对象")
            inherited = {
                key: value[key] for key in ("null", "datatype", "required") if key in value
            }
            inherited.update(
                {key: table[key] for key in ("null", "datatype", "required") if key in table}
            )
            inherited.update(
                {key: schema[key] for key in ("null", "datatype", "required") if key in schema}
            )
            resolved.append(
                {"name": target, "schema": schema, "dialect": dialect, "inherited": inherited}
            )
        if len({table["name"] for table in resolved}) != len(resolved):
            fail("CSVW_SCHEMA", "表组中存在重复表身份")
        return {"document": value, "metadata_path": name, "tables": resolved}


def unsupported(table):
    issues = list(table.get("unsupported_context", []))
    schema = table["schema"]
    if schema.get("foreignKeys"):
        issues.append("foreignKeys")
    for key in table["dialect"]:
        if key not in {
            "delimiter",
            "encoding",
            "quoteChar",
            "doubleQuote",
            "header",
            "headerRowCount",
            "skipRows",
            "lineTerminators",
            "skipBlankRows",
        }:
            issues.append("dialect." + key)
    if table["dialect"].get("headerRowCount", 1) not in {0, 1}:
        issues.append("dialect.headerRowCount")
    for index, column in enumerate(schema["columns"]):
        if not isinstance(column, dict):
            fail("CSVW_SCHEMA", "列描述必须为对象")
        for key in (
            "separator",
            "default",
            "lang",
            "textDirection",
            "virtual",
            "ordered",
            "suppressOutput",
            "aboutUrl",
            "valueUrl",
        ):
            if key in column:
                issues.append(f"columns[{index}].{key}")
        datatype = column.get("datatype", table["inherited"].get("datatype", "string"))
        base = datatype.get("base", "string") if isinstance(datatype, dict) else datatype
        if base not in {
            "string",
            "integer",
            "int",
            "long",
            "double",
            "float",
            "decimal",
            "number",
            "boolean",
        }:
            issues.append(f"columns[{index}].datatype.{base}")
        if isinstance(datatype, dict):
            if set(datatype) - {"base", "format"}:
                issues.append(f"columns[{index}].datatype.constraints")
            fmt = datatype.get("format")
            if fmt is not None and (
                not isinstance(fmt, dict) or set(fmt) - {"decimalChar", "groupChar"}
            ):
                issues.append(f"columns[{index}].datatype.format")
    return issues


def column_names(table):
    columns = table["schema"]["columns"]
    if len(columns) > 512 or any(not isinstance(column, dict) for column in columns):
        fail("CSVW_SCHEMA", "列描述必须为对象且不得超过512列")
    for column in columns:
        datatype = column.get("datatype", table["inherited"].get("datatype", "string"))
        base = datatype.get("base", "string") if isinstance(datatype, dict) else datatype
        if not isinstance(base, str):
            fail("CSVW_SCHEMA", "列数据类型必须为明确名称")
        titles = column.get("titles", column.get("name"))
        title_values = list(titles.values()) if isinstance(titles, dict) else [titles]
        if any(
            not isinstance(v, str)
            and not (isinstance(v, list) and all(isinstance(t, str) for t in v))
            for v in title_values
        ):
            fail("CSVW_SCHEMA", "列标题必须为字符串或语言标题列表")
    names = [column.get("name") for column in columns]
    if (
        not names
        or any(not isinstance(n, str) or not n for n in names)
        or len(set(names)) != len(names)
    ):
        fail("CSVW_SCHEMA", "当前CSVW档案要求唯一、非空的列名称")
    return names


def typed(raw, column, inherited):
    nulls = column.get("null", inherited.get("null", [""]))
    nulls = [nulls] if isinstance(nulls, str) else nulls
    if not isinstance(nulls, list) or any(not isinstance(value, str) for value in nulls):
        fail("CSVW_SCHEMA", "CSVW缺值标记应为字符串或字符串列表")
    if raw in nulls:
        if column.get("required", inherited.get("required", False)):
            fail("CSVW_VALUE", "必填列包含声明的缺值")
        return None
    datatype = column.get("datatype", inherited.get("datatype", "string"))
    base = datatype.get("base", "string") if isinstance(datatype, dict) else datatype
    if base == "string":
        return raw
    value = raw.strip()
    if base == "boolean":
        if value not in {"true", "false", "1", "0"}:
            fail("CSVW_VALUE", "布尔列包含不合法词法值")
        return value in {"true", "1"}
    if isinstance(datatype, dict) and datatype.get("format"):
        fmt = datatype["format"]
        if fmt.get("groupChar"):
            group = fmt["groupChar"]
            decimal = fmt.get("decimalChar", ".")
            integer_part = value.lstrip("+-").split(decimal, 1)[0]
            if group in integer_part and not re.fullmatch(
                r"\d{1,3}(?:" + re.escape(group) + r"\d{3})+", integer_part
            ):
                fail("CSVW_VALUE", "数值分组符不符合声明格式")
            value = value.replace(group, "")
        if fmt.get("decimalChar", ".") != ".":
            value = value.replace(fmt["decimalChar"], ".")
    try:
        if base in {"integer", "int", "long"}:
            if not re.fullmatch(r"[+-]?\d+", value):
                raise ValueError("integer")
            integer = int(value)
            if base == "int" and not -(2**31) <= integer < 2**31:
                raise ValueError("int range")
            if base == "long" and not -(2**63) <= integer < 2**63:
                raise ValueError("long range")
            return integer
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
            raise ValueError("numeric lexical form")
        if base == "decimal":
            if "e" in value.lower():
                raise ValueError("decimal exponent")
            # Retain decimal precision in JSON; numerical methods explicitly use float64.
            return str(Decimal(value))
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("nonfinite")
        return numeric
    except (ValueError, TypeError) as exc:
        raise Problem(
            422, "CSVW_VALUE", "列值不符合声明类型，不自动补值或丢行", {"column": column["name"]}
        ) from exc


def iter_rows(path, table):
    blocked = unsupported(table)
    if blocked:
        raise Problem(
            422,
            "CSVW_SEMANTICS_UNSUPPORTED",
            "该CSVW属性尚未实现，原包保留；相关计算暂不可用",
            {"properties": blocked},
        )
    names = column_names(table)
    dialect = table["dialect"]
    try:
        codecs.lookup(dialect.get("encoding", "utf-8-sig"))
    except (LookupError, TypeError) as exc:
        raise Problem(422, "CSVW_DIALECT", "CSVW声明的编码不可用") from exc
    for column in table["schema"]["columns"]:
        if not isinstance(column.get("required", table["inherited"].get("required", False)), bool):
            fail("CSVW_SCHEMA", "required必须为布尔值")
        datatype = column.get("datatype", table["inherited"].get("datatype", "string"))
        if isinstance(datatype, dict) and isinstance(datatype.get("format"), dict):
            fmt = datatype["format"]
            if any(not isinstance(value, str) or len(value) != 1 for value in fmt.values()):
                fail("CSVW_SCHEMA", "数值分组符和小数符必须为单字符")
            if fmt.get("groupChar") == fmt.get("decimalChar", "."):
                fail("CSVW_SCHEMA", "数值分组符和小数符不能相同")
    delimiter, quote = dialect.get("delimiter", ","), dialect.get("quoteChar", '"')
    if (
        not isinstance(delimiter, str)
        or len(delimiter) != 1
        or quote is not None
        and (not isinstance(quote, str) or len(quote) != 1)
    ):
        fail("CSVW_DIALECT", "分隔符和引号必须为单字符")
    primary = table["schema"].get("primaryKey", [])
    primary = [primary] if isinstance(primary, str) else primary
    if not isinstance(primary, list) or any(key not in names for key in primary):
        fail("CSVW_PRIMARY_KEY", "主键引用了不存在的列")
    skip = dialect.get("skipRows", 0)
    if isinstance(skip, bool) or not isinstance(skip, int) or not 0 <= skip <= MAX_ROWS:
        fail("CSVW_DIALECT", "跳过行数不合法")
    seen = set()
    with zipfile.ZipFile(path) as archive, archive.open(table["name"]) as raw:
        with io.TextIOWrapper(
            raw, encoding=dialect.get("encoding", "utf-8-sig"), newline=""
        ) as stream:
            reader = csv.reader(
                stream,
                delimiter=delimiter,
                quotechar=quote,
                doublequote=dialect.get("doubleQuote", True),
                strict=True,
            )
            for _ in range(skip):
                next(reader, None)
            if dialect.get("headerRowCount", 1 if dialect.get("header", True) else 0) == 1:
                header = next(reader, None)
                if header is None or len(header) != len(names):
                    fail("CSVW_HEADER", "实际表头与列描述数量不一致")
                for actual, column in zip(header, table["schema"]["columns"], strict=True):
                    titles = column.get("titles", column["name"])
                    if isinstance(titles, dict):
                        titles = [
                            t
                            for values in titles.values()
                            for t in (values if isinstance(values, list) else [values])
                        ]
                    titles = [titles] if isinstance(titles, str) else titles
                    if actual.lstrip("\ufeff") not in titles:
                        fail("CSVW_HEADER", "实际表头与CSVW列标题不符")
            count = 0
            for values in reader:
                if not values and dialect.get("skipBlankRows", False):
                    continue
                count += 1
                if count > MAX_ROWS:
                    fail("CSVW_ROW_BUDGET", "CSVW完整校验超过25万行预算，未截断为成功")
                if len(values) != len(names):
                    fail("CSVW_ROW_WIDTH", "数据行列数与CSVW列描述不一致")
                row = {
                    column["name"]: typed(value, column, table["inherited"])
                    for column, value in zip(table["schema"]["columns"], values, strict=True)
                }
                if primary:
                    key = tuple(row[name] for name in primary)
                    if any(value is None or value == "" for value in key) or key in seen:
                        fail("CSVW_PRIMARY_KEY", "CSVW主键缺失或重复")
                    seen.add(key)
                yield row


def facts(path, description):
    layers, issues = [], []
    for table in description["tables"]:
        names = column_names(table)
        blocked = unsupported(table)
        primary = table["schema"].get("primaryKey")
        fields = []
        for name, column in zip(names, table["schema"]["columns"], strict=True):
            datatype = column.get("datatype", table["inherited"].get("datatype", "string"))
            fields.append(
                {
                    "name": name,
                    "data_type": datatype.get("base", "string")
                    if isinstance(datatype, dict)
                    else datatype,
                    "unit": None,
                    "concept": None,
                    "role": "identity" if primary == name or primary == [name] else "feature",
                    "csvw_metadata": column,
                }
            )
        preview, count = [], None
        if blocked:
            issues.append(
                {
                    "code": "CSVW_SEMANTICS_UNSUPPORTED",
                    "blocks": ["observations"],
                    "layer": table["name"],
                    "properties": blocked,
                    "message": "部分CSVW解释规则尚未接入，不能忽略后用于计算",
                }
            )
        else:
            count = 0
            for row in iter_rows(path, table):
                count += 1
                if len(preview) < 20:
                    preview.append(row)
        layers.append(
            {"name": table["name"], "fields": fields, "preview": preview, "row_count": count}
        )
    return {
        "profile": "csvw",
        "standard_version": VERSION,
        "parser_version": "csvw-package-1",
        "observed_period": None,
        "layers": layers,
        "issues": issues,
        "fact_scope": "file_metadata_not_scientific_approval",
        "csvw": description,
        "loss": {"original_bytes": "none", "unsupported_interpretation": bool(issues)},
    }
