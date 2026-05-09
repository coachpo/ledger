from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from app.models.report import Report
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    model = Report

    def list_all(
        self,
        *,
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Report]:
        statement = select(self.model)

        if ticker is not None:
            statement = statement.where(
                self.model.metadata_.contains({"analysis": {"ticker": ticker}})
            )
        if tag is not None:
            statement = statement.where(self.model.metadata_.contains({"tags": [tag]}))
        if review_type is not None:
            statement = statement.where(
                self.model.metadata_.contains({"analysis": {"reviewType": review_type}})
            )
        if portfolio_slug is not None:
            statement = statement.where(
                self.model.metadata_.contains({"analysis": {"portfolioSlug": portfolio_slug}})
            )
        if source is not None:
            statement = statement.where(self.model.source == source)

        statement = statement.order_by(self.model.created_at.desc(), self.model.id.desc())

        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return self._list(statement)

    def get_by_name(self, name: str) -> Report | None:
        statement = select(self.model).where(self.model.name == name)
        return self._get_by_statement(statement)

    def get_by_slug(self, slug: str) -> Report | None:
        statement = select(self.model).where(self.model.slug == slug)
        return self._get_by_statement(statement)

    def list_agent_memory_by_run_id(self, run_id: int) -> list[Report]:
        statement = (
            select(self.model)
            .where(
                self.model.source == "agent",
                self.model.metadata_.contains(self._agent_memory_metadata_filter(run_id)),
            )
            .order_by(self.model.created_at.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def delete_agent_memory_by_run_ids(self, run_ids: Sequence[int]) -> int:
        deleted_count = 0
        for run_id in run_ids:
            statement = delete(self.model).where(
                self.model.source == "agent",
                self.model.metadata_.contains(self._agent_memory_metadata_filter(run_id)),
            )
            result = self.session.scalars(statement.returning(self.model.id))
            deleted_count += len(result.all())
        return deleted_count

    @staticmethod
    def _agent_memory_metadata_filter(run_id: int) -> dict[str, object]:
        return {
            "analysis": {
                "reviewType": "agent_memory",
                "runId": run_id,
            }
        }
