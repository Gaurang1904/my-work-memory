"""Deterministic queries over the structured entity tables (projects, skills).

This is the factual half of hybrid retrieval. Questions with exact answers -
"give me the GitHub link", "list his ML projects", "does he know Rust?" - are
answered from these tables, not from semantic search, so the answers are exact
and an absent fact returns nothing (enabling an honest "no evidence") rather
than a fuzzy near-miss.

The knowledge base is small (a handful of projects/skills), so filtering is done
in Python for clarity and case-insensitive matching rather than in SQL.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.skill import Skill


logger = logging.getLogger(__name__)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def get_project(db: Session, *, slug: str | None = None, name: str | None = None) -> Project | None:
    """Look up a single project by slug (exact) or name (case-insensitive, then substring)."""
    if slug:
        project = db.execute(select(Project).where(Project.slug == _norm(slug))).scalars().first()
        if project is not None:
            return project

    if name:
        target = _norm(name)
        projects = db.execute(select(Project)).scalars().all()
        for project in projects:
            if _norm(project.name) == target or project.slug == target:
                return project
        for project in projects:  # looser fallback
            if target and (target in _norm(project.name) or _norm(project.name) in target):
                return project

    return None


def list_projects(
    db: Session,
    *,
    category: str | None = None,
    tag: str | None = None,
    tech: str | None = None,
    featured_only: bool = False,
) -> list[Project]:
    """List projects, optionally filtered by category, tag, tech, or featured flag.

    Featured projects come first, then most-recent by start date.
    """
    projects = db.execute(select(Project)).scalars().all()

    def matches(project: Project) -> bool:
        if featured_only and not project.is_featured:
            return False
        if category and _norm(project.category) != _norm(category):
            return False
        if tag and _norm(tag) not in [_norm(t) for t in (project.tags or [])]:
            return False
        if tech and _norm(tech) not in [_norm(t) for t in (project.tech_stack or [])]:
            return False
        return True

    result = [project for project in projects if matches(project)]
    result.sort(key=lambda p: (p.is_featured, p.start_date or date.min), reverse=True)
    return result


def find_skill(db: Session, name: str) -> Skill | None:
    """Find a skill by name: exact (case-insensitive) first, then substring either way.

    Returns None when there is no match - the caller should treat that as an
    honest "no evidence he has this skill" rather than guessing.
    """
    target = _norm(name)
    if not target:
        return None

    skills = db.execute(select(Skill)).scalars().all()
    for skill in skills:
        if _norm(skill.name) == target:
            return skill
    for skill in skills:
        if target in _norm(skill.name) or _norm(skill.name) in target:
            return skill
    return None


def list_skills(db: Session, *, category: str | None = None) -> list[Skill]:
    """List all skills, optionally filtered by category, sorted by name."""
    skills = db.execute(select(Skill)).scalars().all()
    if category:
        skills = [skill for skill in skills if _norm(skill.category) == _norm(category)]
    return sorted(skills, key=lambda s: _norm(s.name))
