"""Build the supplied R sources and publish a release only after numerical comparison.

Creates a new output directory; never edits supplied packages or reuses bundled binaries.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".o", ".so", ".dll"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="directory containing PPCI-master and pprRFA-master"
    )
    parser.add_argument("output", type=Path, help="new private release directory")
    args = parser.parse_args()
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker unavailable")
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {}
    with tempfile.TemporaryDirectory(prefix="coastmas-r-build-") as temporary:
        staging = Path(temporary)
        for package in ("PPCI-master", "pprRFA-master"):
            source = args.source / package
            if not (source / "DESCRIPTION").is_file():
                raise ValueError(f"R source package missing: {package}")
            for path in sorted(source.rglob("*")):
                relative = path.relative_to(source)
                if any(part.startswith(".") for part in relative.parts) or path.suffix in EXCLUDED:
                    continue
                if path.is_symlink():
                    raise ValueError(f"source symlinks require explicit review: {relative}")
                if not path.is_file():
                    continue
                content = path.read_bytes()
                name = (Path(package) / relative).as_posix()
                manifest[name] = hashlib.sha256(content).hexdigest()
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        for name in ("Dockerfile", "runner.R"):
            content = (ROOT / "runtime/projection-pursuit" / name).read_bytes()
            manifest[name] = hashlib.sha256(content).hexdigest()
            (staging / name).write_bytes(content)
        serialized = json.dumps(manifest, sort_keys=True, indent=2).encode()
        source_hash = hashlib.sha256(serialized).hexdigest()
        (args.output / "source-manifest.json").write_bytes(serialized)
        with (args.output / "build.log").open("xb") as log:
            subprocess.run(
                [
                    docker,
                    "build",
                    "--label",
                    f"coastmas.source_sha256={source_hash}",
                    "--iidfile",
                    str(staging / "image-id"),
                    str(staging),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=1800,
            )
        image = (staging / "image-id").read_text().strip()
    proof_path = args.output / "release.proof.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_projection_models.py"),
            "--image",
            image,
            "--output",
            str(proof_path),
        ],
        check=True,
        timeout=360,
    )
    proof_bytes = proof_path.read_bytes()
    proof = json.loads(proof_bytes)
    release = {
        "image": image,
        "source_sha256": source_hash,
        "proof_sha256": hashlib.sha256(proof_bytes).hexdigest(),
        "clustering_pair_disagreements": proof["clustering_pair_disagreements"],
        "regression_max_abs_error": proof["regression_max_abs_error"],
    }
    with (args.output / "release.json").open("x") as output:
        json.dump(release, output, indent=2)
    print(json.dumps({"release": str(args.output / "release.json"), "image": image}))


if __name__ == "__main__":
    main()
