"""Check received originals and the declared deterministic reader, independently."""

import hashlib

from .store import Problem


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024**2):
            digest.update(chunk)
    return digest.hexdigest()


def verify_asset(root, asset, cancelled):
    package = asset["facts"].get("logical_package")
    members = package["members"] + package.get("reader_members", []) if package else [asset]
    if package and not package.get("reader_members"):
        # Earlier packages without adaptation still have a byte-identical primary reader.
        members = members + [asset]
    for member in members:
        path = (root / member["object_key"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise Problem(422, "INPUT_INTEGRITY", "受管文件引用不在当前存储空间")
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024**2):
                    if cancelled.is_set():
                        raise Problem(409, "CANCELLED", "运行已取消")
                    digest.update(chunk)
        except OSError as exc:
            raise Problem(422, "INPUT_INTEGRITY", "受管原件或读取副本已缺失") from exc
        if digest.hexdigest() != member["sha256"]:
            raise Problem(422, "INPUT_INTEGRITY", "受管原件、附件或读取副本与固定哈希不一致")
