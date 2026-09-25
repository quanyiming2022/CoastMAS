"""Download complete received logical members with their integrity manifest."""

import json
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZIP_STORED, ZipFile

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .store import Problem


def package_download(settings, asset):
    package = asset["facts"]["logical_package"]
    with tempfile.NamedTemporaryFile(
        prefix="coastmas-package-", suffix=".zip", dir=settings.storage_root, delete=False
    ) as stream:
        target = Path(stream.name)
    try:
        with ZipFile(target, "w", compression=ZIP_STORED, allowZip64=True) as archive:
            for member in package["members"]:
                relative = PurePosixPath(member["path"])
                source = (settings.storage_root / member["object_key"]).resolve(strict=True)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not source.is_relative_to(settings.storage_root)
                ):
                    raise Problem(422, "PACKAGE_PATH", "资料成员路径无效，未导出其他文件。")
                archive.write(source, str(relative))
            archive.writestr(
                "coastmas-integrity-manifest.json",
                json.dumps(
                    {
                        "asset_id": asset["id"],
                        "asset_revision": asset["revision"],
                        "primary": package["primary"],
                        "logical_sha256": package["sha256"],
                        "members": [
                            {k: v for k, v in m.items() if k != "object_key"}
                            for m in package["members"]
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        return FileResponse(
            target,
            media_type="application/zip",
            filename=asset["name"] + ".zip",
            background=BackgroundTask(target.unlink, missing_ok=True),
        )
    except BaseException:
        target.unlink(missing_ok=True)
        raise
