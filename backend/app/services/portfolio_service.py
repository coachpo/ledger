from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.models.portfolio import Portfolio
from app.repositories.portfolio import PortfolioRepository
from app.schemas.portfolio import PortfolioCreate, PortfolioRead, PortfolioUpdate


class PortfolioService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PortfolioRepository(session)

    def list_portfolios(self) -> list[PortfolioRead]:
        portfolios = self.repository.list_all()
        return [self._to_read_model(portfolio) for portfolio in portfolios]

    def get_portfolio(self, portfolio_id: int) -> PortfolioRead:
        portfolio = self.get_portfolio_model(portfolio_id)
        return self._to_read_model(portfolio)

    def get_portfolio_model(self, portfolio_id: int) -> Portfolio:
        portfolio = self.repository.get(portfolio_id)
        if portfolio is None:
            raise not_found_error("Portfolio")
        return portfolio

    def get_portfolio_model_by_slug_or_none(self, slug: str) -> Portfolio | None:
        return self.repository.get_by_slug(slug)

    def create_portfolio(self, payload: PortfolioCreate) -> PortfolioRead:
        if self.repository.get_by_slug(payload.slug) is not None:
            raise business_rule_error(
                "duplicate_portfolio_slug",
                "A portfolio with this slug already exists",
            )
        portfolio = Portfolio(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            base_currency=payload.base_currency,
        )
        self.repository.add(portfolio)
        self.session.commit()
        self.session.refresh(portfolio)
        return self._to_read_model(portfolio)

    def update_portfolio(self, portfolio_id: int, payload: PortfolioUpdate) -> PortfolioRead:
        portfolio = self.get_portfolio_model(portfolio_id)
        if "name" in payload.model_fields_set and payload.name is not None:
            portfolio.name = payload.name
        if "description" in payload.model_fields_set:
            portfolio.description = payload.description
        self.session.commit()
        self.session.refresh(portfolio)
        return self._to_read_model(portfolio)

    def delete_portfolio(self, portfolio_id: int) -> None:
        portfolio = self.get_portfolio_model(portfolio_id)
        self.repository.delete(portfolio)
        self.session.commit()

    def _to_read_model(self, portfolio: Portfolio) -> PortfolioRead:
        return PortfolioRead.model_validate(
            {
                "id": portfolio.id,
                "name": portfolio.name,
                "slug": portfolio.slug,
                "description": portfolio.description,
                "base_currency": portfolio.base_currency,
                "position_count": self.repository.count_positions(portfolio.id),
                "balance_count": self.repository.count_balances(portfolio.id),
                "created_at": portfolio.created_at,
                "updated_at": portfolio.updated_at,
            }
        )
