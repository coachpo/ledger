from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_template_compiler_service, get_text_template_service
from app.schemas.text_template import (
    PlaceholderTreeRead,
    TextTemplateCompileRead,
    TextTemplateCreate,
    TextTemplateInlineCompile,
    TextTemplateInlineCompileRead,
    TextTemplateRead,
    TextTemplateStoredCompile,
    TextTemplateUpdate,
)
from app.services.template_compiler_service import TemplateCompilerService
from app.services.text_template_service import TextTemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TextTemplateRead])
def list_templates(
    service: Annotated[TextTemplateService, Depends(get_text_template_service)],
) -> list[TextTemplateRead]:
    return service.list_templates()


@router.post("", response_model=TextTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TextTemplateCreate,
    service: Annotated[TextTemplateService, Depends(get_text_template_service)],
) -> TextTemplateRead:
    return service.create_template(payload)


@router.get("/placeholders", response_model=PlaceholderTreeRead)
def get_placeholders(
    compiler_service: Annotated[TemplateCompilerService, Depends(get_template_compiler_service)],
) -> PlaceholderTreeRead:
    tree = compiler_service.get_placeholder_tree()
    return PlaceholderTreeRead.model_validate(tree)


@router.post("/compile", response_model=TextTemplateInlineCompileRead)
def compile_inline(
    payload: TextTemplateInlineCompile,
    compiler_service: Annotated[TemplateCompilerService, Depends(get_template_compiler_service)],
) -> TextTemplateInlineCompileRead:
    compiled = compiler_service.compile(payload.content, inputs=payload.inputs)
    return TextTemplateInlineCompileRead.model_validate({"compiled": compiled})


@router.get("/{template_id:int}", response_model=TextTemplateRead)
def get_template(
    template_id: int,
    service: Annotated[TextTemplateService, Depends(get_text_template_service)],
) -> TextTemplateRead:
    return service.get_template(template_id)


@router.patch("/{template_id:int}", response_model=TextTemplateRead)
def update_template(
    template_id: int,
    payload: TextTemplateUpdate,
    service: Annotated[TextTemplateService, Depends(get_text_template_service)],
) -> TextTemplateRead:
    return service.update_template(template_id, payload)


@router.delete("/{template_id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    service: Annotated[TextTemplateService, Depends(get_text_template_service)],
) -> Response:
    service.delete_template(template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{template_id:int}/compile", response_model=TextTemplateCompileRead)
def compile_template(
    template_id: int,
    template_service: Annotated[TextTemplateService, Depends(get_text_template_service)],
    compiler_service: Annotated[TemplateCompilerService, Depends(get_template_compiler_service)],
) -> TextTemplateCompileRead:
    template = template_service.get_template_model(template_id)
    compiled = compiler_service.compile(template.content)
    return TextTemplateCompileRead.model_validate(
        {
            "id": template.id,
            "name": template.name,
            "compiled": compiled,
        }
    )


@router.post("/{template_id:int}/compile", response_model=TextTemplateCompileRead)
def compile_template_with_inputs(
    template_id: int,
    payload: TextTemplateStoredCompile,
    template_service: Annotated[TextTemplateService, Depends(get_text_template_service)],
    compiler_service: Annotated[TemplateCompilerService, Depends(get_template_compiler_service)],
) -> TextTemplateCompileRead:
    template = template_service.get_template_model(template_id)
    compiled = compiler_service.compile(template.content, inputs=payload.inputs)
    return TextTemplateCompileRead.model_validate(
        {
            "id": template.id,
            "name": template.name,
            "compiled": compiled,
        }
    )
