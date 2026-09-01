"""LangGraph orchestrator for the portfolio assistant.

This is the reasoning layer: instead of a fixed embed -> retrieve -> answer
pipeline, an LLM agent decides *which* tools to call for each question -
semantic search over prose, or deterministic lookups against the projects/skills
tables - and loops until it can answer. The tools wrap the existing hand-built
services, so the RAG internals stay ours while LangGraph handles orchestration.

Graph shape (the canonical agent loop):

    START -> agent -> (tools_condition) -> tools -> agent -> ... -> END

The `agent` node calls Gemini with the tools bound; `tools_condition` routes to
the `tools` node when the model requests a tool call, otherwise to END.

Conversation memory is durable: the graph is compiled with a Postgres
checkpointer, so each session's messages are persisted in the DB keyed by
`thread_id`. A caller continues a conversation by passing the same session_id.
"""

import logging
from typing import Annotated, TypedDict
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas.query import AskResponse, SourceReference
from app.services import entities
from app.services.generation_errors import GenerationTemporarilyUnavailableError
from app.services.retrieval import retrieve_chunks


logger = logging.getLogger(__name__)
settings = get_settings()

# How many recent messages to send to the model per turn. The full thread is
# still persisted; this only bounds what the model sees (tokens/quota).
MAX_CONTEXT_MESSAGES = 12

SYSTEM_PROMPT = (
    "You are the interactive portfolio assistant for Gaurang Gupta, a Blockchain & AI "
    "Engineer. You answer questions from recruiters and visitors about his experience, "
    "projects, and skills.\n\n"
    "Rules:\n"
    "- Answer ONLY using the tools. Never invent facts, links, dates, or skills.\n"
    "- Use `search_knowledge` for open questions about background, experience, or how a "
    "project works.\n"
    "- Use `get_project` / `list_projects` for project details and GitHub links.\n"
    "- Use `check_skill` / `list_skills` for skills. If `check_skill` returns no evidence, "
    "say clearly that there's no evidence he has that skill - do not guess.\n"
    "- Use the prior conversation to resolve follow-ups ('it', 'that one', 'tell me more').\n"
    "- Refer to Gaurang in the third person.\n"
    "\n"
    "Answer style:\n"
    "- Lead with the direct answer, then a brief supporting detail.\n"
    "- Write short paragraphs; use bullet points only when listing multiple projects or skills.\n"
    "- Keep answers to 2-4 sentences by default; expand only when explicitly asked for more detail.\n"
    "- Plain, professional tone. Always name concrete projects and technologies.\n"
)

_checkpointer = None


def _get_checkpointer():
    """Lazily create a durable Postgres checkpointer (one per process).

    LangGraph persists each conversation thread's messages in Postgres, keyed by
    thread_id, so the server remembers a session across requests and restarts.
    """
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        conninfo = settings.database_url.replace("+psycopg", "")
        pool = ConnectionPool(
            conninfo=conninfo,
            max_size=5,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        pool.open()
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()  # creates the checkpoint tables if missing (idempotent)
        _checkpointer = checkpointer
        logger.info("Initialized Postgres conversation checkpointer")
    return _checkpointer


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _windowed(messages: list) -> list:
    """Keep the most recent messages, starting on a human turn so we never send a
    tool result without its preceding tool call."""
    window = messages[-MAX_CONTEXT_MESSAGES:]
    while window and not isinstance(window[0], HumanMessage):
        window = window[1:]
    return window


def _build_tools(db: Session, sources_sink: list[SourceReference]):
    """Build the tool set, closed over the request's DB session.

    `search_knowledge` appends the passages it used to `sources_sink` so the API
    response can carry real citations for grounded prose claims.
    """

    @tool
    def search_knowledge(query: str) -> str:
        """Search Gaurang's documents (profile, resumes, project write-ups) for prose
        relevant to the query. Use for background, experience, and explanations."""
        results = retrieve_chunks(db, query, None, settings.retrieval_top_k)
        if not results:
            return "No relevant passages found."
        blocks = []
        for chunk, doc, _distance in results:
            sources_sink.append(
                SourceReference(
                    document=doc.title,
                    document_id=str(doc.id),
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    excerpt=chunk.chunk_text[:240],
                )
            )
            blocks.append(f"[{doc.title}] {chunk.chunk_text}")
        return "\n\n".join(blocks)

    @tool
    def get_project(name: str) -> str:
        """Get details for a single project by name or slug (summary, tech stack,
        GitHub link, category, dates)."""
        project = entities.get_project(db, name=name)
        if project is None:
            return f"No project found matching '{name}'."
        lines = [
            f"Name: {project.name}",
            f"Summary: {project.summary}",
            f"Category: {project.category or 'n/a'}",
            f"Tech: {', '.join(project.tech_stack or []) or 'n/a'}",
            f"GitHub: {project.github_url or 'not provided'}",
        ]
        if project.description:
            lines.append(f"Details: {project.description}")
        return "\n".join(lines)

    @tool
    def list_projects(category: str = "", tag: str = "", tech: str = "", featured_only: bool = False) -> str:
        """List Gaurang's projects, optionally filtered by category, tag, tech, or
        featured flag. Use for questions like 'show his blockchain projects'."""
        projects = entities.list_projects(
            db,
            category=category or None,
            tag=tag or None,
            tech=tech or None,
            featured_only=featured_only,
        )
        if not projects:
            return "No matching projects found."
        return "\n".join(
            f"- {p.name} ({p.category or 'n/a'}): {p.summary} [{p.github_url or 'no link'}]"
            for p in projects
        )

    @tool
    def check_skill(name: str) -> str:
        """Check whether Gaurang has a specific skill (e.g. 'Solidity', 'Deep Learning').
        Returns evidence, or states there is none."""
        skill = entities.find_skill(db, name)
        if skill is None:
            return f"No evidence in Gaurang's profile that he has the skill '{name}'."
        parts = [f"Yes - {skill.name}"]
        if skill.category:
            parts.append(f"category: {skill.category}")
        if skill.proficiency:
            parts.append(f"proficiency: {skill.proficiency}")
        if skill.related_project_slugs:
            parts.append(f"used in: {', '.join(skill.related_project_slugs)}")
        if skill.notes:
            parts.append(f"note: {skill.notes}")
        return "; ".join(parts)

    @tool
    def list_skills(category: str = "") -> str:
        """List Gaurang's skills, optionally filtered by category (e.g. 'Blockchain',
        'Backend', 'Machine Learning')."""
        skills = entities.list_skills(db, category=category or None)
        if not skills:
            return "No matching skills found."
        return ", ".join(s.name for s in skills)

    return [search_knowledge, get_project, list_projects, check_skill, list_skills]


def _build_model():
    """Chat model for the agent. Any provider works as long as it supports tool
    calling; the prompt, tools, graph, and memory are provider-independent."""
    if settings.llm_provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
            temperature=0.2,
        )
    return ChatGoogleGenerativeAI(
        model=settings.gemini_chat_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
    )


def _build_graph(db: Session, sources_sink: list[SourceReference]):
    tools = _build_tools(db, sources_sink)
    model = _build_model().bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        # System prompt is injected per call (not persisted); the thread stores
        # only the real conversation. Trim to a recent window to bound tokens.
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + _windowed(state["messages"])
        return {"messages": [model.invoke(messages)]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=_get_checkpointer())


def _extract_text(content) -> str:
    """Pull plain text out of a message's content.

    Gemini 2.5 via langchain sometimes returns content as a list of blocks
    (e.g. text parts plus thought-signature metadata) rather than a plain
    string. Join the text parts and drop the rest.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "429" in message or "RESOURCE_EXHAUSTED" in message or "QUOTA" in message


def _is_unavailable_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "503" in message or "UNAVAILABLE" in message or "HIGH DEMAND" in message


def answer_with_agent(
    db: Session,
    question: str,
    session_id: str | None = None,
) -> AskResponse:
    if not settings.gemini_api_key.strip():
        raise RuntimeError("GEMINI_API_KEY is missing.")

    session_id = session_id or str(uuid4())
    sources_sink: list[SourceReference] = []
    graph = _build_graph(db, sources_sink)
    config = {"configurable": {"thread_id": session_id}}

    logger.info("Running agent for question=%r session=%s", question, session_id)
    try:
        result = graph.invoke({"messages": [HumanMessage(content=question)]}, config=config)
    except Exception as exc:
        if _is_quota_error(exc):
            logger.warning("Agent generation quota exhausted")
            raise GenerationTemporarilyUnavailableError(
                "Gemini quota hit right now. Wait a minute and try again, "
                "or switch to paid quota / another model."
            ) from exc
        if _is_unavailable_error(exc):
            logger.warning("Agent generation temporarily unavailable")
            raise GenerationTemporarilyUnavailableError(
                "The answer model is temporarily busy. Please try again in a minute."
            ) from exc
        raise

    final = result["messages"][-1]
    answer = _extract_text(final.content)

    # Deduplicate sources by (document, chunk_index), preserving order.
    seen: set[tuple[str, int]] = set()
    sources: list[SourceReference] = []
    for source in sources_sink:
        key = (source.document, source.chunk_index)
        if key not in seen:
            seen.add(key)
            sources.append(source)

    logger.info("Agent produced answer with %s cited sources", len(sources))
    return AskResponse(answer=answer.strip(), sources=sources, session_id=session_id)
