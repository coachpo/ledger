from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.models.text_template import TextTemplate
from app.repositories.text_template import TextTemplateRepository
from app.schemas.text_template import TextTemplateCreate, TextTemplateRead, TextTemplateUpdate


class TextTemplateService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TextTemplateRepository(session)

    def list_templates(self) -> list[TextTemplateRead]:
        templates = self.repository.list_all()
        return [TextTemplateRead.model_validate(t) for t in templates]

    def get_template(self, template_id: int) -> TextTemplateRead:
        template = self._get_model(template_id)
        return TextTemplateRead.model_validate(template)

    def get_template_model(self, template_id: int) -> TextTemplate:
        return self._get_model(template_id)

    def create_template(self, payload: TextTemplateCreate) -> TextTemplateRead:
        if self.repository.get_by_name(payload.name) is not None:
            raise business_rule_error(
                "duplicate_template_name",
                "A template with this name already exists",
            )
        template = TextTemplate(
            name=payload.name,
            content=payload.content,
        )
        self.repository.add(template)
        self.session.commit()
        self.session.refresh(template)
        return TextTemplateRead.model_validate(template)

    def update_template(self, template_id: int, payload: TextTemplateUpdate) -> TextTemplateRead:
        template = self._get_model(template_id)
        if payload.name is not None and payload.name != template.name:
            duplicate = self.repository.get_by_name(payload.name)
            if duplicate is not None and duplicate.id != template.id:
                raise business_rule_error(
                    "duplicate_template_name",
                    "A template with this name already exists",
                )
            template.name = payload.name
        if payload.content is not None:
            template.content = payload.content
        self.session.commit()
        self.session.refresh(template)
        return TextTemplateRead.model_validate(template)

    def delete_template(self, template_id: int) -> None:
        template = self._get_model(template_id)
        self.repository.delete(template)
        self.session.commit()

    def _get_model(self, template_id: int) -> TextTemplate:
        template = self.repository.get(template_id)
        if template is None:
            raise not_found_error("TextTemplate")
        return template
