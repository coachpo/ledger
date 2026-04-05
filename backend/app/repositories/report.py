from __future__ import annotations

from sqlalchemy import select

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

    def list_for_backtest_tag(self, tag: str) -> list[Report]:
        statement = (
            select(self.model)
            .where(self.model.metadata_.contains({"tags": [tag]}))
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)

    def delete_for_backtest_tag(self, tag: str) -> None:
        for report in self.list_for_backtest_tag(tag):
            self.delete(report)
