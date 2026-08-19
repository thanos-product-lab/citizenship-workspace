"""ORM for the requirement catalog: definitions, rule versions, dependency rows.

These three tables are **global reference data**, seeded by migration 0007 at owner
privilege and read (never written) by the app. They carry no case data, so they have
no row-level-security policy; the app role is granted SELECT only. The models exist so
the assessment layer can resolve a requirement key to its `requirement_id` and current
`rule_version_id`, and read a rule's declared dependencies.

The catalog values (titles, groups, guidance citations) live in the migrations, which are
their single source, as do the dependency and composition rows that drive selective
invalidation. `app/requirements/evaluation.py` owns the complementary *evaluator* logic by
key; `tests/assessments/test_catalog.py` asserts the two agree.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class RuleLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class DependencyInputKind(StrEnum):
    """The kinds of versioned input a rule may declare a dependency on (Domain §25.1).
    There is deliberately no requirement-result kind: the composite route rule's
    dependency on other rules' conclusions is rule composition, not an input link."""

    ROUTE_PROFILE = "ROUTE_PROFILE"
    PROPOSED_APPLICATION_DATE = "PROPOSED_APPLICATION_DATE"
    TRAVEL_RECORD = "TRAVEL_RECORD"
    CASE_FACT = "CASE_FACT"
    KNOWLEDGE_RECORD = "KNOWLEDGE_RECORD"
    REFEREE_RECORD = "REFEREE_RECORD"
    EVIDENCE_SUPPORT = "EVIDENCE_SUPPORT"
    GUIDANCE_VERSION = "GUIDANCE_VERSION"


class RequirementDefinition(Base):
    __tablename__ = "requirement_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_key: Mapped[str] = mapped_column(String(60), unique=True)
    route_key: Mapped[str] = mapped_column(String(40))
    group_key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str | None] = mapped_column(Text)
    evaluator_key: Mapped[str] = mapped_column(String(60))
    display_order: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    introduced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirement_definitions.id"))
    semantic_version: Mapped[str] = mapped_column(String(20))
    rule_set: Mapped[str] = mapped_column(String(20))
    evaluator_key: Mapped[str] = mapped_column(String(60))
    # Guidance citations live here as stable source-id strings until Migration 5 adds
    # the GuidanceSection tables and the RuleGuidanceLink FK (ADR-0007).
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_status: Mapped[str] = mapped_column(String(20))
    implementation_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleDependencyDefinition(Base):
    __tablename__ = "rule_dependency_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_versions.id"))
    input_kind: Mapped[str] = mapped_column(String(40))
    input_key: Mapped[str | None] = mapped_column(String(60))
    dependency_scope: Mapped[str] = mapped_column(String(40))
    required: Mapped[bool] = mapped_column(Boolean)


class RuleCompositionEdge(Base):
    """A rule that reads another requirement's *conclusion* rather than a raw input.

    `route.standard_section_6_1` composes the adult and status conclusions. §25.1 has no
    input kind for a result, and adding one would be wrong — a conclusion is not a
    versioned input and has no version to link in `AssessmentInputLink`. So the edge is
    its own relation, versioned with the rule that declares it (§25.3).

    Selective invalidation takes the transitive closure over these edges: if an upstream
    result is stale, its conclusion is no longer known-current, so every rule composing it
    is stale too — regardless of whether recalculation would change anything.
    """

    __tablename__ = "rule_composition_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_versions.id"))
    upstream_requirement_key: Mapped[str] = mapped_column(String(60))
    required: Mapped[bool] = mapped_column(Boolean)


#: The catalog tables: global reference data seeded by migrations, identical for every
#: tenant, never per-case state. Declared here rather than repeated by each consumer, so a
#: new catalog table joins the set by existing. The test suite excludes these from its
#: per-test TRUNCATE — a table missing from this tuple has its seed wiped after the first
#: test, and every read then returns empty in a way that reads as a logic bug.
CATALOG_TABLES: tuple[str, ...] = (
    RequirementDefinition.__tablename__,
    RuleVersion.__tablename__,
    RuleDependencyDefinition.__tablename__,
    RuleCompositionEdge.__tablename__,
)
