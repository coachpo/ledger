from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.core.errors import ApiError, not_found_error
from app.core.formatting import utcnow
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.repositories.report import ReportRepository
from app.schemas.report import ReportMetadata, ReportRead, ReportUpdate
from app.services.capability_service import CapabilityService

_MAX_NAME_LENGTH = 200
_DATETIME_SUFFIX_LENGTH = 16
_DEFAULT_EXTERNAL_REPORT_BASENAME = "external_report"


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ReportRepository(session)

    def list_reports(
        self,
        *,
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        return self._list_report_reads(
            ticker=ticker,
            tag=tag,
            review_type=review_type,
            portfolio_slug=portfolio_slug,
            source=source,
            limit=limit,
            offset=offset,
        )

    def lookup_reports(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        CapabilityService(self.session, get_default_tool_catalog()).require_report_lookup_grant(
            capability_references=capability_references
        )
        return self._list_report_reads(
            ticker=ticker,
            tag=tag,
            review_type=review_type,
            portfolio_slug=portfolio_slug,
            source=source,
            limit=limit,
            offset=offset,
        )

    def get_report(self, report_id: int) -> ReportRead:
        report = self._get_model(report_id)
        return ReportRead.model_validate(report)

    def get_report_model(self, report_id: int) -> Report:
        return self._get_model(report_id)

    def get_report_by_slug(self, slug: str) -> ReportRead:
        report = self._get_model_by_slug(slug)
        return ReportRead.model_validate(report)

    def get_report_model_by_slug(self, slug: str) -> Report:
        return self._get_model_by_slug(slug)

    def create_from_template(
        self,
        template: TextTemplate,
        compiled_content: str,
        metadata: ReportMetadata | dict[str, Any] | None = None,
    ) -> ReportRead:
        name = self._generate_unique_name(template.name)
        return self._create_report_record(
            name=name,
            slug=name,
            source="compiled",
            content=compiled_content,
            metadata=metadata,
        )

    def create_from_upload(
        self,
        *,
        content: str,
        slug: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReportRead:
        normalized_slug = self._normalize_name(slug)
        if not normalized_slug:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_slug",
                message="Slug must contain at least one alphanumeric character",
            )
        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")

        if self.repository.get_by_slug(normalized_slug) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="slug_conflict",
                message=f'A report with slug "{normalized_slug}" already exists',
            )

        validated_metadata = ReportMetadata.model_validate(metadata or {})

        report_name = name if name else normalized_slug
        if len(report_name) > _MAX_NAME_LENGTH:
            report_name = report_name[:_MAX_NAME_LENGTH]

        if self.repository.get_by_name(report_name) is not None:
            report_name = self._generate_unique_name(report_name)

        return self._create_report_record(
            name=report_name,
            slug=normalized_slug,
            source="uploaded",
            content=content,
            metadata=validated_metadata,
        )

    def create_external_report(
        self,
        *,
        content: str,
        name: str | None = None,
        slug: str | None = None,
        metadata: ReportMetadata | dict[str, Any] | None = None,
    ) -> ReportRead:
        report_name = self._resolve_external_report_name(name)

        if slug is not None:
            normalized_slug = self._normalize_slug(slug)
            if self.repository.get_by_slug(normalized_slug) is not None:
                raise ApiError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="slug_conflict",
                    message=f'A report with slug "{normalized_slug}" already exists',
                )
        else:
            normalized_slug = self._generate_unique_slug(report_name)

        return self._create_report_record(
            name=report_name,
            slug=normalized_slug,
            source="external",
            content=content,
            metadata=metadata,
        )

    def update_report_by_slug(self, slug: str, payload: ReportUpdate) -> ReportRead:
        report = self._get_model_by_slug(slug)
        if payload.content is not None:
            report.content = payload.content
        self.session.commit()
        self.session.refresh(report)
        return ReportRead.model_validate(report)

    def delete_report_by_slug(self, slug: str) -> None:
        report = self._get_model_by_slug(slug)
        self.repository.delete(report)
        self.session.commit()

    def update_report(self, report_id: int, payload: ReportUpdate) -> ReportRead:
        report = self._get_model(report_id)
        if payload.content is not None:
            report.content = payload.content
        self.session.commit()
        self.session.refresh(report)
        return ReportRead.model_validate(report)

    def delete_report(self, report_id: int) -> None:
        report = self._get_model(report_id)
        self.repository.delete(report)
        self.session.commit()

    def _list_report_reads(
        self,
        *,
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        reports = self.repository.list_all(
            ticker=self._normalize_ticker_filter(ticker),
            tag=self._normalize_optional_filter(tag),
            review_type=self._normalize_optional_filter(review_type),
            portfolio_slug=self._normalize_optional_filter(portfolio_slug),
            source=source,
            limit=limit,
            offset=offset,
        )
        return [ReportRead.model_validate(report) for report in reports]

    def _get_model(self, report_id: int) -> Report:
        report = self.repository.get(report_id)
        if report is None:
            raise not_found_error("Report")
        return report

    def _get_model_by_slug(self, slug: str) -> Report:
        report = self.repository.get_by_slug(slug)
        if report is None:
            raise not_found_error("Report")
        return report

    def _generate_unique_name(self, template_name: str) -> str:
        normalized = self._normalize_name(template_name)
        now = utcnow()
        datetime_suffix = now.strftime("_%Y%m%d_%H%M%S")

        max_prefix_length = _MAX_NAME_LENGTH - _DATETIME_SUFFIX_LENGTH
        if len(normalized) > max_prefix_length:
            normalized = normalized[:max_prefix_length].rstrip("_")

        base_name = f"{normalized}{datetime_suffix}"

        if self.repository.get_by_name(base_name) is None:
            return base_name

        counter = 2
        while True:
            candidate = f"{base_name}_{counter}"
            if len(candidate) > _MAX_NAME_LENGTH:
                trim = len(candidate) - _MAX_NAME_LENGTH
                normalized_trimmed = normalized[: len(normalized) - trim].rstrip("_")
                candidate = f"{normalized_trimmed}{datetime_suffix}_{counter}"
            if self.repository.get_by_name(candidate) is None:
                return candidate
            counter += 1

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        lowered = normalized.lower()
        replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
        collapsed = re.sub(r"_+", "_", replaced)
        return collapsed.strip("_")

    def _create_report_record(
        self,
        *,
        name: str,
        slug: str,
        source: str,
        content: str,
        metadata: ReportMetadata | dict[str, Any] | None = None,
    ) -> ReportRead:
        validated_metadata = self._validate_metadata(metadata)
        report = Report(
            name=name,
            slug=slug,
            source=source,
            content=content,
            metadata_=self._serialize_metadata(validated_metadata),
        )
        self.repository.add(report)
        self.session.commit()
        self.session.refresh(report)
        return ReportRead.model_validate(report)

    def _validate_metadata(
        self, metadata: ReportMetadata | dict[str, Any] | None
    ) -> ReportMetadata:
        if isinstance(metadata, ReportMetadata):
            return metadata
        return ReportMetadata.model_validate(metadata or {})

    def _serialize_metadata(self, metadata: ReportMetadata) -> dict[str, Any]:
        payload = metadata.model_dump(by_alias=True)
        analysis = metadata.analysis
        if analysis is None:
            payload.pop("analysis", None)
        else:
            payload["analysis"] = analysis.model_dump(by_alias=True, exclude_none=True)
        return payload

    def _resolve_external_report_name(self, name: str | None) -> str:
        if name is None:
            return self._generate_unique_name(_DEFAULT_EXTERNAL_REPORT_BASENAME)

        report_name = name.strip()
        if not report_name:
            return self._generate_unique_name(_DEFAULT_EXTERNAL_REPORT_BASENAME)

        if len(report_name) > _MAX_NAME_LENGTH:
            report_name = report_name[:_MAX_NAME_LENGTH]

        if self.repository.get_by_name(report_name) is not None:
            report_name = self._generate_unique_name(report_name)

        return report_name

    def _generate_unique_slug(self, base_value: str) -> str:
        normalized_slug = self._normalize_name(base_value)
        if not normalized_slug:
            normalized_slug = _DEFAULT_EXTERNAL_REPORT_BASENAME

        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")

        if self.repository.get_by_slug(normalized_slug) is None:
            return normalized_slug

        counter = 2
        while True:
            suffix = f"_{counter}"
            max_base_length = _MAX_NAME_LENGTH - len(suffix)
            trimmed_base = normalized_slug[:max_base_length].rstrip("_")
            if not trimmed_base:
                trimmed_base = "report"
            candidate = f"{trimmed_base}{suffix}"
            if self.repository.get_by_slug(candidate) is None:
                return candidate
            counter += 1

    def _normalize_slug(self, value: str) -> str:
        normalized_slug = self._normalize_name(value)
        if not normalized_slug:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_slug",
                message="Slug must contain at least one alphanumeric character",
            )
        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")
        return normalized_slug

    @staticmethod
    def _normalize_optional_filter(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    def _normalize_ticker_filter(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_filter(value)
        if normalized is None:
            return None
        return normalized.upper()
