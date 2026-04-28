from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents import get_default_skill_registry
from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import normalize_symbol, utcnow
from app.models.position import Position
from app.repositories.position import PositionRepository
from app.repositories.symbol_name_cache import SymbolNameCacheRepository
from app.schemas.position import (
    PositionCreate,
    PositionRead,
    PositionSymbolLookupRead,
    PositionUpdate,
)
from app.services.portfolio_service import PortfolioService
from app.services.quote_provider import QuoteProvider, QuoteProviderError
from app.services.skill_service import SkillService


class PositionService:
    def __init__(self, session: Session, quote_provider: QuoteProvider | None = None) -> None:
        self.session = session
        self.quote_provider = quote_provider
        self.repository = PositionRepository(session)
        self.symbol_name_cache_repository = SymbolNameCacheRepository(session)
        self.portfolio_service = PortfolioService(session)

    def lookup_positions(
        self,
        *,
        skill_references: list[dict[str, object]],
        portfolio_slug: str,
        symbol: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PositionRead]:
        SkillService(self.session, get_default_skill_registry()).require_position_lookup_grant(
            skill_references=skill_references
        )
        portfolio = self.portfolio_service.get_portfolio_model_by_slug_or_none(portfolio_slug)
        if portfolio is None:
            return []

        positions = self.repository.list_for_portfolio(portfolio.id)
        normalized_symbol = normalize_symbol(symbol) if symbol is not None else None
        if normalized_symbol:
            positions = [position for position in positions if position.symbol == normalized_symbol]

        if offset:
            positions = positions[offset:]
        if limit is not None:
            positions = positions[:limit]

        return [PositionRead.model_validate(position) for position in positions]

    def list_positions(self, portfolio_id: int) -> list[PositionRead]:
        self.portfolio_service.get_portfolio_model(portfolio_id)
        positions = self.repository.list_for_portfolio(portfolio_id)
        return [PositionRead.model_validate(position) for position in positions]

    def create_position(self, portfolio_id: int, payload: PositionCreate) -> PositionRead:
        portfolio = self.portfolio_service.get_portfolio_model(portfolio_id)
        if self.repository.get_by_symbol(portfolio_id, payload.symbol) is not None:
            raise business_rule_error(
                "duplicate_symbol",
                "A position for this symbol already exists in the portfolio",
            )

        resolved_name: str | None = payload.name
        if resolved_name is None:
            resolved_name, _ = self._resolve_symbol_name(payload.symbol)
        position = Position(
            portfolio_id=portfolio.id,
            symbol=payload.symbol,
            name=resolved_name,
            quantity=payload.quantity,
            average_cost=payload.average_cost,
            currency=portfolio.base_currency,
            last_source="manual",
        )
        self.repository.add(position)
        self.session.commit()
        self.session.refresh(position)
        return PositionRead.model_validate(position)

    def lookup_symbol(self, portfolio_id: int, symbol: str) -> PositionSymbolLookupRead:
        self.portfolio_service.get_portfolio_model(portfolio_id)
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            return PositionSymbolLookupRead(symbol="", name=None)

        name, cache_updated = self._resolve_symbol_name(normalized_symbol)
        if cache_updated:
            self.session.commit()

        return PositionSymbolLookupRead(symbol=normalized_symbol, name=name)

    def update_position(
        self, portfolio_id: int, position_id: int, payload: PositionUpdate
    ) -> PositionRead:
        position = self.repository.get_for_portfolio(portfolio_id, position_id)
        if position is None:
            raise not_found_error("Position")
        if "name" in payload.model_fields_set:
            position.name = payload.name
        if "quantity" in payload.model_fields_set and payload.quantity is not None:
            quantity = payload.quantity
            position.quantity = quantity
        if "average_cost" in payload.model_fields_set and payload.average_cost is not None:
            average_cost = payload.average_cost
            position.average_cost = average_cost
        position.last_source = "manual"
        self.session.commit()
        self.session.refresh(position)
        return PositionRead.model_validate(position)

    def delete_position(self, portfolio_id: int, position_id: int) -> None:
        position = self.repository.get_for_portfolio(portfolio_id, position_id)
        if position is None:
            raise not_found_error("Position")
        self.repository.delete(position)
        self.session.commit()

    def _resolve_symbol_name(self, symbol: str) -> tuple[str | None, bool]:
        cached = self.symbol_name_cache_repository.get_by_symbol(symbol)
        if cached is not None:
            return cached.name, False

        if self.quote_provider is None:
            return None, False

        try:
            name = self.quote_provider.fetch_symbol_name(symbol)
        except QuoteProviderError:
            return None, False

        if name is None:
            return None, False

        inserted = self.symbol_name_cache_repository.insert_if_missing(
            symbol=symbol,
            name=name,
            fetched_at=utcnow(),
        )
        if inserted:
            return name, True

        cached = self.symbol_name_cache_repository.get_by_symbol(symbol)
        return (cached.name if cached is not None else name), False
