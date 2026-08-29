from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.projects import (
    ProjectAccountRead,
    ProjectAccountsAction,
    ProjectAccountsActionResult,
    ProjectAccountsAdd,
    ProjectClaimRead,
    ProjectClaimRequest,
    ProjectCreate,
    ProjectEventRead,
    ProjectLeaseAction,
    ProjectLeaseHeartbeat,
    ProjectRead,
)
from smart_email_manager.db.models import Account, ProjectAccount, ProjectEvent, WorkProject


def _claim_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def _project_or_404(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    lock: bool = False,
) -> WorkProject:
    statement = select(WorkProject).where(WorkProject.id == project_id)
    if lock:
        statement = statement.with_for_update()
    project = await session.scalar(statement)
    if not project:
        raise ApiProblem(
            status=404,
            code="PROJECT_NOT_FOUND",
            title="Project not found",
            detail=f"No project exists with id {project_id}.",
        )
    return project


async def _serialize_project(session: AsyncSession, project: WorkProject) -> ProjectRead:
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(ProjectAccount.status == "to_claim"),
                func.count().filter(ProjectAccount.status == "leased"),
                func.count().filter(ProjectAccount.status == "done"),
                func.count().filter(ProjectAccount.status == "failed"),
            ).where(ProjectAccount.project_id == project.id)
        )
    ).one()
    total, to_claim, leased, done, failed = (int(value or 0) for value in row)
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        default_lease_seconds=project.default_lease_seconds,
        total_count=total,
        to_claim_count=to_claim,
        leased_count=leased,
        done_count=done,
        failed_count=failed,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def create_project(session: AsyncSession, payload: ProjectCreate) -> ProjectRead:
    account_ids = list(dict.fromkeys(payload.account_ids))
    if account_ids:
        existing = set((await session.scalars(select(Account.id).where(Account.id.in_(account_ids)))).all())
        missing = [item for item in account_ids if item not in existing]
        if missing:
            raise ApiProblem(
                status=404,
                code="ACCOUNT_NOT_FOUND",
                title="Account not found",
                detail=f"No account exists with id {missing[0]}.",
            )
    project = WorkProject(
        name=payload.name.strip(),
        description=payload.description.strip(),
        default_lease_seconds=payload.default_lease_seconds,
    )
    session.add(project)
    try:
        await session.flush()
        for account_id in account_ids:
            session.add(ProjectAccount(project_id=project.id, account_id=account_id))
        session.add(
            ProjectEvent(
                project_id=project.id,
                event_type="project.created",
                data={"account_count": len(account_ids)},
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="PROJECT_NAME_CONFLICT",
            title="Project name already exists",
            detail=f"A project already uses {payload.name.strip()}.",
        ) from exc
    await session.refresh(project)
    return await _serialize_project(session, project)


async def list_projects(session: AsyncSession) -> list[ProjectRead]:
    projects = list(
        (await session.scalars(select(WorkProject).order_by(WorkProject.created_at.desc()))).all()
    )
    return [await _serialize_project(session, project) for project in projects]


async def set_project_status(
    session: AsyncSession,
    project_id: uuid.UUID,
    status: str,
) -> ProjectRead:
    project = await _project_or_404(session, project_id, lock=True)
    project.status = status
    session.add(ProjectEvent(project_id=project.id, event_type=f"project.{status}", data={}))
    await session.commit()
    await session.refresh(project)
    return await _serialize_project(session, project)


async def add_project_accounts(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: ProjectAccountsAdd,
) -> ProjectRead:
    project = await _project_or_404(session, project_id, lock=True)
    existing = set(
        (await session.scalars(select(Account.id).where(Account.id.in_(payload.account_ids)))).all()
    )
    if existing != set(payload.account_ids):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail="At least one requested account does not exist.",
        )
    for account_id in existing:
        await session.execute(
            insert(ProjectAccount)
            .values(project_id=project.id, account_id=account_id)
            .on_conflict_do_nothing()
        )
    session.add(
        ProjectEvent(
            project_id=project.id,
            event_type="project.accounts_added",
            data={"requested_count": len(payload.account_ids)},
        )
    )
    await session.commit()
    return await _serialize_project(session, project)


async def mutate_project_accounts(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: ProjectAccountsAction,
) -> ProjectAccountsActionResult:
    project = await _project_or_404(session, project_id, lock=True)
    requested_ids = list(dict.fromkeys(payload.project_account_ids))
    rows = list(
        (
            await session.scalars(
                select(ProjectAccount)
                .where(
                    ProjectAccount.project_id == project.id,
                    ProjectAccount.id.in_(requested_ids),
                )
                .with_for_update()
            )
        ).all()
    )
    updated = 0
    for row in rows:
        if payload.action == "reset_failed" and row.status == "failed":
            row.status = "to_claim"
        elif payload.action == "remove" and row.status not in {"leased", "removed"}:
            row.status = "removed"
        elif payload.action == "restore" and row.status == "removed":
            row.status = "to_claim"
        else:
            continue
        row.lease_owner = None
        row.lease_token_hash = None
        row.lease_expires_at = None
        row.result = {}
        row.error_summary = None
        row.finished_at = None
        updated += 1
    session.add(
        ProjectEvent(
            project_id=project.id,
            event_type=f"accounts.{payload.action}",
            actor="api",
            data={
                "requested_count": len(requested_ids),
                "updated_count": updated,
                "skipped_count": len(requested_ids) - updated,
            },
        )
    )
    await session.commit()
    return ProjectAccountsActionResult(
        requested_count=len(requested_ids),
        updated_count=updated,
        skipped_count=len(requested_ids) - updated,
        project=await _serialize_project(session, project),
    )


async def claim_project_account(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: ProjectClaimRequest,
) -> ProjectClaimRead:
    project = await _project_or_404(session, project_id, lock=True)
    if project.status != "active":
        raise ApiProblem(
            status=409,
            code="PROJECT_NOT_ACTIVE",
            title="Project is not active",
            detail="Only active projects can lease work.",
        )
    now = datetime.now(UTC)
    row = await session.scalar(
        select(ProjectAccount)
        .where(
            ProjectAccount.project_id == project.id,
            or_(
                ProjectAccount.status == "to_claim",
                (ProjectAccount.status == "leased") & (ProjectAccount.lease_expires_at < now),
            ),
        )
        .order_by(ProjectAccount.created_at, ProjectAccount.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not row:
        raise ApiProblem(
            status=409,
            code="PROJECT_WORK_UNAVAILABLE",
            title="No project work is available",
            detail="No unclaimed or expired account lease is available.",
        )
    account = await session.get(Account, row.account_id)
    if not account:
        row.status = "removed"
        await session.commit()
        raise ApiProblem(
            status=409,
            code="PROJECT_ACCOUNT_REMOVED",
            title="Project account was removed",
            detail="The selected project account no longer exists.",
        )
    token = f"sem_claim_{secrets.token_urlsafe(32)}"
    lease_seconds = payload.lease_seconds or project.default_lease_seconds
    row.status = "leased"
    row.lease_owner = payload.owner
    row.lease_token_hash = _claim_hash(token)
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.attempt_count += 1
    row.error_summary = None
    session.add(
        ProjectEvent(
            project_id=project.id,
            project_account_id=row.id,
            event_type="account.leased",
            actor=payload.owner,
            data={"lease_seconds": lease_seconds, "attempt_count": row.attempt_count},
        )
    )
    await session.commit()
    return ProjectClaimRead(
        project_account_id=row.id,
        project_id=project.id,
        account_id=account.id,
        email=account.email,
        claim_token=token,
        lease_owner=payload.owner,
        lease_expires_at=row.lease_expires_at,
        attempt_count=row.attempt_count,
    )


async def _leased_row(
    session: AsyncSession,
    project_account_id: uuid.UUID,
    token: str,
) -> ProjectAccount:
    row = await session.get(ProjectAccount, project_account_id, with_for_update=True)
    now = datetime.now(UTC)
    if (
        not row
        or row.status != "leased"
        or not row.lease_token_hash
        or not secrets.compare_digest(row.lease_token_hash, _claim_hash(token))
        or not row.lease_expires_at
        or row.lease_expires_at <= now
    ):
        raise ApiProblem(
            status=409,
            code="PROJECT_LEASE_INVALID",
            title="Project lease is invalid",
            detail="The lease token is invalid, expired or already completed.",
        )
    return row


async def heartbeat_project_lease(
    session: AsyncSession,
    project_account_id: uuid.UUID,
    payload: ProjectLeaseHeartbeat,
) -> ProjectAccountRead:
    row = await _leased_row(session, project_account_id, payload.claim_token.get_secret_value())
    project = await _project_or_404(session, row.project_id)
    seconds = payload.lease_seconds or project.default_lease_seconds
    row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=seconds)
    session.add(
        ProjectEvent(
            project_id=row.project_id,
            project_account_id=row.id,
            event_type="account.heartbeat",
            actor=row.lease_owner,
            data={"lease_seconds": seconds},
        )
    )
    await session.commit()
    return await _project_account_read(session, row)


async def finish_project_lease(
    session: AsyncSession,
    project_account_id: uuid.UUID,
    payload: ProjectLeaseAction,
    *,
    status: str,
) -> ProjectAccountRead:
    row = await _leased_row(session, project_account_id, payload.claim_token.get_secret_value())
    row.status = status
    row.result = payload.result
    row.error_summary = payload.error_summary if status == "failed" else None
    row.finished_at = datetime.now(UTC) if status in {"done", "failed"} else None
    row.lease_token_hash = None
    row.lease_expires_at = None
    actor = row.lease_owner
    row.lease_owner = None
    session.add(
        ProjectEvent(
            project_id=row.project_id,
            project_account_id=row.id,
            event_type=f"account.{status}",
            actor=actor,
            data=payload.result,
        )
    )
    await session.commit()
    return await _project_account_read(session, row)


async def _project_account_read(
    session: AsyncSession,
    row: ProjectAccount,
) -> ProjectAccountRead:
    account = await session.get(Account, row.account_id)
    return ProjectAccountRead(
        id=row.id,
        project_id=row.project_id,
        account_id=row.account_id,
        email=account.email if account else "",
        status=row.status,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        attempt_count=row.attempt_count,
        result=row.result,
        error_summary=row.error_summary,
        finished_at=row.finished_at,
    )


async def list_project_accounts(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int,
) -> list[ProjectAccountRead]:
    await _project_or_404(session, project_id)
    rows = list(
        (
            await session.scalars(
                select(ProjectAccount)
                .where(ProjectAccount.project_id == project_id)
                .order_by(ProjectAccount.created_at)
                .limit(limit)
            )
        ).all()
    )
    return [await _project_account_read(session, row) for row in rows]


async def list_project_events(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    after: int,
    limit: int,
) -> list[ProjectEventRead]:
    await _project_or_404(session, project_id)
    rows = (
        await session.scalars(
            select(ProjectEvent)
            .where(ProjectEvent.project_id == project_id, ProjectEvent.sequence > after)
            .order_by(ProjectEvent.sequence)
            .limit(limit)
        )
    ).all()
    return [ProjectEventRead.model_validate(row) for row in rows]
