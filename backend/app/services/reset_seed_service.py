from __future__ import annotations

from app.core.errors import business_rule_error
from app.reset_seed import reset_and_seed_database
from app.schemas.reset_seed import ResetSeedRead


class ResetSeedService:
    def reset_and_seed_starter_data(self) -> ResetSeedRead:
        try:
            summary = reset_and_seed_database()
        except RuntimeError as exc:
            raise business_rule_error("reset_seed_failed", str(exc)) from exc

        return ResetSeedRead.model_validate(summary)
