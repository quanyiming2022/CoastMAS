"""Local/deployment startup using fixed builtin code and persistent catalog versions."""

import threading
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from coastmas.adapters.storage import S3ArtifactStore, local_storage_settings
from coastmas.configuration import configuration_value
from coastmas.core.contracts import ModelSpec
from coastmas.core.errors import CoastMASError
from coastmas.core.execution import ExecutionRegistry, RegisteredRuntime, model_identity
from coastmas.core.llm import OpenAICompatibleProvider, ProviderSettings
from coastmas.domain.builtin_catalog import BuiltinCatalog
from coastmas.domain.coastal_catalog import coastal_catalog
from coastmas.persistence.auth import hash_password
from coastmas.persistence.database import local_database_url
from coastmas.persistence.schema import AuditLog, Membership, Project, User

DEFAULT_PROJECT_ID = str(uuid5(NAMESPACE_URL, "https://coastmas.local/demonstration-project"))


class BuiltinRuntimeRegistry(ExecutionRegistry):
    """Only fixed code; lifecycle revisions cannot change scientific/runtime fields.

    Each process can resolve saved v1 or later enable/disable revisions without a
    mutable shared Python registry. Arbitrary uploads remain non-executable.
    """

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
        self._catalogs: dict[str, BuiltinCatalog] = {}
        self._lock = threading.Lock()

    def resolve(self, model: ModelSpec) -> RegisteredRuntime:
        # Explicitly registered maintainer handlers retain support for integration use.
        try:
            return super().resolve(model)
        except CoastMASError:
            pass
        parts = model.id.split(":")
        if len(parts) != 3 or parts[0] != "builtin" or not parts[1]:
            raise CoastMASError("MODEL_ERROR", "runtime is not registered")
        project = parts[1]
        with self._lock:
            if project not in self._catalogs:
                self._catalogs[project] = coastal_catalog(project, self.directory)
            catalog = self._catalogs[project]
        expected = next((item for item in catalog.models if item.id == model.id), None)
        mutable = {"version", "enabled", "updated_at"}
        if expected is None or model.model_dump(exclude=mutable) != expected.model_dump(
            exclude=mutable
        ):
            raise CoastMASError(
                "MODEL_ERROR", "runtime scientific contract differs from builtin release"
            )
        runtime = catalog.registry.resolve(expected)
        return RegisteredRuntime(model_identity(model), runtime.adapter, runtime.handler)


def initialize_account(
    session: Session, email: str, password: str, project_id: str
) -> tuple[str, str]:
    """Insert initial owner/project once; never reset passwords or revive deleted access."""
    from uuid import uuid4

    normalized = email.strip().lower()
    if "@" not in normalized or len(normalized) > 320:
        raise CoastMASError("CONFIGURATION_ERROR", "initial administrator email is invalid")
    owner = session.scalar(select(User).where(User.email == normalized))
    if owner is None:
        owner = User(
            id=str(uuid4()),
            email=normalized,
            password_hash=hash_password(password),
            active=True,
            is_admin=True,
        )
        session.add(owner)
        session.flush()
        session.add(
            AuditLog(
                id=str(uuid4()),
                who=owner.id,
                action="INITIALIZE_ADMIN",
                resource=owner.id,
                old_value=None,
                new_value={"email": normalized},
            )
        )
    elif not owner.active or not owner.is_admin:
        raise CoastMASError(
            "CONFIGURATION_ERROR", "existing initial account is inactive or not admin"
        )
    project = session.get(Project, project_id)
    if project is None:
        project = Project(
            id=project_id, name="CoastMAS synthetic demonstrations", owner_id=owner.id
        )
        session.add(project)
        session.flush()
        session.add(Membership(project_id=project_id, user_id=owner.id, role="ADMIN"))
        session.add(
            AuditLog(
                id=str(uuid4()),
                who=owner.id,
                action="CREATE_PROJECT",
                resource=project_id,
                old_value=None,
                new_value={"name": project.name},
            )
        )
    elif project.owner_id != owner.id or session.get(Membership, (project_id, owner.id)) is None:
        raise CoastMASError(
            "CONFIGURATION_ERROR", "existing sample project ownership/access differs"
        )
    session.flush()
    return owner.id, project.id


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sample_directory() -> Path:
    return Path(
        configuration_value("COASTMAS_SAMPLE_DIRECTORY", str(project_root() / "sample-data"))
    )


def database_engine() -> Engine:
    return create_engine(local_database_url(), pool_pre_ping=True)


def object_store() -> S3ArtifactStore:
    return S3ArtifactStore(
        local_storage_settings(), bucket=configuration_value("S3_BUCKET", "coastmas")
    )


def configured_provider() -> OpenAICompatibleProvider | None:
    # Missing credentials do not prevent local deterministic workflows or startup.
    try:
        key = configuration_value("LLM_API_KEY")
        model = configuration_value("LLM_MODEL")
        endpoint = configuration_value("LLM_BASE_URL")
    except RuntimeError:
        return None
    return OpenAICompatibleProvider(
        ProviderSettings(
            base_url=endpoint,
            model=model,
            api_key=SecretStr(key),
            allow_private=configuration_value("LLM_ALLOW_PRIVATE", "false").lower() == "true",
            timeout_seconds=int(configuration_value("LLM_TIMEOUT_SECONDS", "45")),
            max_completion_tokens=int(configuration_value("LLM_MAX_COMPLETION_TOKENS", "4096")),
        )
    )
