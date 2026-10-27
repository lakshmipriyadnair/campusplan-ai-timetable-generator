"""Shared CRUD routes used by the academic-data API."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This change conflicts with existing or referenced academic data.",
        ) from error


def create_crud_router(
    *,
    path: str,
    tag: str,
    model: type[Any],
    create_schema: type[Any],
    update_schema: type[Any],
    read_schema: type[Any],
    references: dict[str, type[Any]] | None = None,
    validate_values: Callable[[Session, dict[str, Any], Any | None], None] | None = None,
    validate_update: Callable[[Any, dict[str, Any]], None] | None = None,
    protect_record: Callable[[Session, Any], None] | None = None,
) -> APIRouter:
    """Build consistent list/get/create/patch/delete routes for one record type."""
    router = APIRouter(prefix=path, tags=[tag])
    reference_models = references or {}

    def find_record(db: Session, record_id: int) -> Any:
        record = db.get(model, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"{tag} record not found.")
        return record

    def check_references(db: Session, values: dict[str, Any]) -> None:
        for field_name, referenced_model in reference_models.items():
            reference_id = values.get(field_name)
            if reference_id is not None and db.get(referenced_model, reference_id) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Referenced record for {field_name} was not found.",
                )

    @router.get("", response_model=list[read_schema], name=f"list_{tag.lower().replace(' ', '_')}")
    def list_records(db: Session = Depends(get_db)) -> list[Any]:
        return list(db.query(model).order_by(model.id).all())

    @router.post(
        "",
        response_model=read_schema,
        status_code=status.HTTP_201_CREATED,
        name=f"create_{tag.lower().replace(' ', '_')}",
    )
    def create_record(payload: create_schema, db: Session = Depends(get_db)) -> Any:
        values = payload.model_dump()
        check_references(db, values)
        if validate_values is not None:
            validate_values(db, values, None)
        record = model(**values)
        db.add(record)
        _commit_or_conflict(db)
        db.refresh(record)
        return record

    @router.get("/{record_id}", response_model=read_schema)
    def get_record(record_id: int, db: Session = Depends(get_db)) -> Any:
        return find_record(db, record_id)

    @router.patch("/{record_id}", response_model=read_schema)
    def update_record(
        record_id: int,
        payload: update_schema,
        db: Session = Depends(get_db),
    ) -> Any:
        record = find_record(db, record_id)
        if protect_record is not None:
            protect_record(db, record)
        values = payload.model_dump(exclude_unset=True)
        check_references(db, values)
        if validate_values is not None:
            validate_values(db, values, record)
        if validate_update is not None:
            validate_update(record, values)
        for field_name, value in values.items():
            setattr(record, field_name, value)
        _commit_or_conflict(db)
        db.refresh(record)
        return record

    @router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_record(record_id: int, db: Session = Depends(get_db)) -> None:
        record = find_record(db, record_id)
        if protect_record is not None:
            protect_record(db, record)
        db.delete(record)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete this {tag.lower()} because other academic records refer to it.",
            ) from error

    return router
