from pydantic import BaseModel, Field


class KnowledgeEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    destination: str = Field(default="", max_length=255)
    category: str = Field(default="", max_length=100)


class KnowledgeEntryPublic(BaseModel):
    id: str
    title: str
    destination: str
    category: str


class KnowledgeSearchResult(BaseModel):
    id: str
    title: str
    content: str
    destination: str
    category: str
    distance: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResult]
