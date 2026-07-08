from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.extensions.signaldeck_finance.config import get_finance_workspace_settings
from app.extensions.signaldeck_finance.provider_factories import create_quote_provider
from app.extensions.signaldeck_finance.service_gate import (
    MARKET_DATA_SERVICE_SURFACE,
    REPORT_SERVICE_SURFACE,
    TEMPLATE_COMPILER_SURFACE,
    TEXT_TEMPLATE_SERVICE_SURFACE,
)
from app.services.quote_provider import QuoteProvider

if TYPE_CHECKING:
    from app.extensions.signaldeck_finance.services.market_data_service import MarketDataService
    from app.extensions.signaldeck_finance.services.report_service import ReportService
    from app.extensions.signaldeck_finance.services.template_compiler_service import (
        TemplateCompilerService,
    )
    from app.extensions.signaldeck_finance.services.text_template_service import TextTemplateService

FinanceSharedServiceClassification = Literal[
    "move-now",
    "wrapped-by-finance-factory",
]


@dataclass(frozen=True, slots=True)
class FinanceSharedServiceOwnership:
    service_name: str
    module_path: str
    classification: FinanceSharedServiceClassification
    surface: str
    rationale: str


_FINANCE_OWNED_SERVICE_RATIONALE = (
    "Finance behavior lives in extension-owned service implementations; "
    "construction is supplied through finance-owned factories and every direct entrypoint "
    "blocks when the extension is disabled."
)

FINANCE_SHARED_SERVICE_OWNERSHIP_MAP: tuple[FinanceSharedServiceOwnership, ...] = (
    FinanceSharedServiceOwnership(
        "MarketDataService",
        "app.extensions.signaldeck_finance.services.market_data_service",
        "move-now",
        MARKET_DATA_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TextTemplateService",
        "app.extensions.signaldeck_finance.services.text_template_service",
        "move-now",
        TEXT_TEMPLATE_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "ReportService",
        "app.extensions.signaldeck_finance.services.report_service",
        "move-now",
        REPORT_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TemplateCompilerService",
        "app.extensions.signaldeck_finance.services.template_compiler_service",
        "move-now",
        TEMPLATE_COMPILER_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
)


def get_finance_workspace_session() -> Iterator[Session]:
    yield from get_db_session()


def get_quote_provider() -> QuoteProvider:
    return create_quote_provider()


def get_market_data_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> MarketDataService:
    from app.extensions.signaldeck_finance.services.market_data_service import MarketDataService

    settings = get_finance_workspace_settings()
    return MarketDataService(
        session=session,
        quote_provider=quote_provider,
        quote_stale_after_minutes=settings.quote_stale_after_minutes,
    )


def get_text_template_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> TextTemplateService:
    from app.extensions.signaldeck_finance.services.text_template_service import TextTemplateService

    return TextTemplateService(session)


def get_report_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> ReportService:
    from app.extensions.signaldeck_finance.services.report_service import ReportService

    return ReportService(session)


def get_template_compiler_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> TemplateCompilerService:
    from app.extensions.signaldeck_finance.services.template_compiler_service import (
        TemplateCompilerService,
    )

    return TemplateCompilerService(session)


if TYPE_CHECKING:
    MarketDataServiceDependency = Annotated[
        MarketDataService,
        Depends(get_market_data_service),
    ]
    TextTemplateServiceDependency = Annotated[
        TextTemplateService,
        Depends(get_text_template_service),
    ]
    ReportServiceDependency = Annotated[
        ReportService,
        Depends(get_report_service),
    ]
    TemplateCompilerServiceDependency = Annotated[
        TemplateCompilerService,
        Depends(get_template_compiler_service),
    ]
else:
    MarketDataServiceDependency = Annotated[
        object,
        Depends(get_market_data_service),
    ]
    TextTemplateServiceDependency = Annotated[
        object,
        Depends(get_text_template_service),
    ]
    ReportServiceDependency = Annotated[
        object,
        Depends(get_report_service),
    ]
    TemplateCompilerServiceDependency = Annotated[
        object,
        Depends(get_template_compiler_service),
    ]


__all__ = [
    "FINANCE_SHARED_SERVICE_OWNERSHIP_MAP",
    "FinanceSharedServiceClassification",
    "FinanceSharedServiceOwnership",
    "MarketDataServiceDependency",
    "ReportServiceDependency",
    "TemplateCompilerServiceDependency",
    "TextTemplateServiceDependency",
    "get_finance_workspace_session",
    "get_market_data_service",
    "get_quote_provider",
    "get_report_service",
    "get_template_compiler_service",
    "get_text_template_service",
]
