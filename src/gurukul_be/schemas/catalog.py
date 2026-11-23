from pydantic import BaseModel


class TeacherResponse(BaseModel):
    id: str
    display_name: str
    description: str
    min_grade: int
    max_grade: int
    supported_languages: list[str]
    capabilities: list[str]


class SubjectResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    teacher: TeacherResponse


class TeacherSummary(BaseModel):
    id: str
    subject_id: str
    display_name: str


class SubjectSummary(BaseModel):
    id: str
    name: str
