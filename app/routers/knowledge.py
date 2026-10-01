import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_current_user
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeEntryCreate,
    KnowledgeEntryPublic,
    KnowledgeSearchResponse,
)
from app.services import knowledge_base

router = APIRouter(tags=["Knowledge"])


@router.post("", response_model=KnowledgeEntryPublic, status_code=status.HTTP_201_CREATED)
def add_knowledge_entry(
    payload: KnowledgeEntryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> KnowledgeEntryPublic:
    entry_id = str(uuid.uuid4())
    try:
        knowledge_base.add_entry(
            entry_id=entry_id,
            title=payload.title,
            content=payload.content,
            destination=payload.destination,
            category=payload.category,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store knowledge entry",
        ) from exc

    return KnowledgeEntryPublic(
        id=entry_id,
        title=payload.title,
        destination=payload.destination,
        category=payload.category,
    )


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    query: Annotated[str, Query(min_length=1)],
    current_user: Annotated[User, Depends(get_current_user)],
    destination: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> KnowledgeSearchResponse:
    try:
        hits = knowledge_base.search(
            query,
            n_results=limit,
            destination_filter=destination,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Knowledge base search failed",
        ) from exc

    return KnowledgeSearchResponse(query=query, results=hits)
