from fastapi import APIRouter

from skillproof import taxonomy
from skillproof.schemas import SkillTagOut

router = APIRouter(tags=["taxonomy"])


@router.get("/skills", response_model=list[SkillTagOut])
def list_skills() -> list[SkillTagOut]:
    return [SkillTagOut(name=s.name, category=s.category, description=s.description) for s in taxonomy.list_skills()]
