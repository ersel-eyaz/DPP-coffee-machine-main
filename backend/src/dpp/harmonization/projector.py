from __future__ import annotations

"""
Headless projection of harmonized intermediate results to the original models.

Design intent
-------------
This projector is intentionally conservative:

1. Harmonized scope stays narrow.
   We only trust and project the fields that already exist in the
   harmonized intermediate result.

2. Projection compatibility is handled here.
   If the original model requires additional technical fields
   (for example identifier formatting or a required backup link),
   this file fills them in explicitly and documents that decision.

3. Out-of-scope semantics are not invented here.
   We do not pretend to harmonize fields that were not harmonized.
   We only add minimal technical values when the original model needs them
   to instantiate successfully.

This keeps the harmonization layer semantically scoped while still allowing
controlled experiments with projection to the original prototype models.
"""

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from dpp.harmonization.schemas import HarmonizationResult, ScopedEntityType
from dpp.models.dpp import DPPInstance, DPPStatic
from dpp.models.part import PartInstance, PartStatic
from dpp.models.material import MaterialInstance, MaterialStatic
from dpp.models.processstep import ProcessStep
from dpp.models.ghg import GHGEmissionRecord, ActivityData
from dpp.models.location import Place


@dataclass(slots=True)
class ProjectionIssue:
    """One non-fatal projection problem or technical fill-in note."""

    severity: str
    message: str
    entity_id: str | None = None
    entity_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProjectionReport:
    """Small report so projection behavior stays transparent."""

    projected_count: int = 0
    skipped_count: int = 0
    technical_fill_count: int = 0
    issues: list[ProjectionIssue] = field(default_factory=list)


class HeadlessProjector:
    """
    Convert harmonized entities into original model instances.

    Important distinction:
    - Harmonized fields come from the intermediate result and are trusted as such.
    - Technical fill-ins are added only when the original model requires them
      for construction or graph integrity.
    """

    def __init__(self, result: HarmonizationResult):
        self.result = result
        self.projected_entities: Dict[str, Any] = {}
        self.report = ProjectionReport()
        self._relation_index = self._build_relation_index()

    def run(self) -> List[Any]:
        """
        Main entry point.

        Strategy:
        1. Create model instances for all known entities.
        2. Use relation-aware construction for entities that need required links.
        3. Wire remaining relations after instantiation.
        """
        for entity_id, entity in self.result.entities.items():
            model_instance = self._create_model_instance(entity)
            if model_instance is None:
                self.report.skipped_count += 1
                continue

            self.projected_entities[entity_id] = model_instance
            self.report.projected_count += 1

        self._wire_relations()
        return list(self.projected_entities.values())

    def _create_model_instance(self, entity: Any) -> Any | None:
        entity_type = entity.entity_type
        fields = self._extract_field_payload(entity)

        try:
            if entity_type == ScopedEntityType.DPP_INSTANCE:
                return self._create_dpp_instance(entity.entity_id, fields)

            if entity_type == ScopedEntityType.DPP_STATIC:
                return self._safe_construct(
                    DPPStatic,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id},
                )

            if entity_type == ScopedEntityType.PART_INSTANCE:
                return self._safe_construct(
                    PartInstance,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.PART_STATIC:
                return self._safe_construct(
                    PartStatic,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.MATERIAL_INSTANCE:
                return self._safe_construct(
                    MaterialInstance,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.MATERIAL_STATIC:
                return self._safe_construct(
                    MaterialStatic,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.PROCESS_STEP:
                return self._safe_construct(
                    ProcessStep,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.GHG_EMISSION_RECORD:
                return self._safe_construct(
                    GHGEmissionRecord,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.ACTIVITY_DATA:
                return self._safe_construct(
                    ActivityData,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id, **fields},
                )

            if entity_type == ScopedEntityType.PLACE:
                return self._safe_construct(
                    Place,
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    kwargs={"id": entity.entity_id},
                )

            self.report.issues.append(
                ProjectionIssue(
                    severity="info",
                    message="Entity type is currently not projected.",
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                )
            )
            return None

        except Exception as exc:
            self.report.issues.append(
                ProjectionIssue(
                    severity="error",
                    message="Unexpected projection failure.",
                    entity_id=entity.entity_id,
                    entity_type=entity_type.value,
                    details={"exception": repr(exc)},
                )
            )
            return None

    def _create_dpp_instance(self, entity_id: str, fields: dict[str, Any]) -> Any | None:
        """
        Create DPPInstance with explicit technical fill-ins.

        Why this is special:
        - The original model currently validates `id` as a 34-digit SGTIN-like string.
        - The original model requires `dppStaticLink`.
        - The original model requires `backupLink`.

        These are projection-compatibility requirements, not evidence that the
        harmonization scope itself should be expanded.
        """
        dpp_static_link = self._get_single_related_object_id(
            entity_id=entity_id,
            relation_type_value="dpp_instance_to_static",
        )
        if dpp_static_link is None:
            self.report.issues.append(
                ProjectionIssue(
                    severity="warning",
                    message="DPPInstance projection skipped because required relation dpp_instance_to_static is missing.",
                    entity_id=entity_id,
                    entity_type=ScopedEntityType.DPP_INSTANCE.value,
                )
            )
            return None

        projected_id = self._coerce_to_34_digit_identifier(entity_id)
        backup_link = self._build_placeholder_backup_link(entity_id)

        kwargs = {
            "id": projected_id,
            "dppStaticLink": dpp_static_link,
            "backupLink": backup_link,
            **fields,
        }

        if projected_id != entity_id:
            self._note_technical_fill(
                message="Replaced non-conforming harmonized DPP id with a deterministic 34-digit projection identifier.",
                entity_id=entity_id,
                entity_type=ScopedEntityType.DPP_INSTANCE.value,
                details={"original_id": entity_id, "projected_id": projected_id},
            )

        self._note_technical_fill(
            message="Filled required DPP backupLink with a deterministic projection placeholder.",
            entity_id=entity_id,
            entity_type=ScopedEntityType.DPP_INSTANCE.value,
            details={"backupLink": backup_link},
        )

        return self._safe_construct(
            DPPInstance,
            entity_id=entity_id,
            entity_type=ScopedEntityType.DPP_INSTANCE.value,
            kwargs=kwargs,
        )

    def _safe_construct(
        self,
        cls: type,
        entity_id: str,
        entity_type: str,
        kwargs: dict[str, Any],
    ) -> Any | None:
        try:
            return cls(**kwargs)
        except ValidationError as exc:
            self.report.issues.append(
                ProjectionIssue(
                    severity="warning",
                    message="Projection skipped because original model validation failed.",
                    entity_id=entity_id,
                    entity_type=entity_type,
                    details={
                        "class_name": cls.__name__,
                        "validation_errors": exc.errors(),
                        "attempted_kwargs_keys": sorted(kwargs.keys()),
                    },
                )
            )
            return None

    def _extract_field_payload(self, entity: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for canonical_name, field in entity.fields.items():
            target_name = canonical_name.split(".")[-1]
            payload[target_name] = field.normalized_value
        return payload

    def _wire_relations(self) -> None:
        for relation in self.result.relations:
            subject = self.projected_entities.get(relation.subject_entity_id)
            obj = self.projected_entities.get(relation.object_entity_id)

            if subject is None or obj is None:
                continue

            relation_type = relation.relation_type.value

            if relation_type == "dpp_instance_to_part":
                self._set_attr_if_present(subject, "hasTopPart", getattr(obj, "id", obj))

            elif relation_type == "part_instance_to_static":
                self._set_attr_if_present(subject, "describedBy", getattr(obj, "id", obj))
                self._set_attr_if_present(subject, "partStaticLink", getattr(obj, "id", obj))

            elif relation_type == "part_instance_to_part":
                self._append_relation(subject, "contains", obj)
                self._append_relation(subject, "composes", obj)

            elif relation_type == "part_instance_to_material":
                self._append_relation(subject, "hasCompositeMaterials", obj)
                self._append_relation(subject, "compositeMaterials", obj)

            elif relation_type == "material_instance_to_static":
                self._set_attr_if_present(subject, "describedBy", getattr(obj, "id", obj))
                self._set_attr_if_present(subject, "materialStaticLink", getattr(obj, "id", obj))

            elif relation_type == "process_step_to_place":
                self._set_attr_if_present(subject, "processedAt", getattr(obj, "id", obj))

            elif relation_type == "process_step_to_ghg_record":
                self._append_relation(subject, "ghgEmissionRecords", obj)
                self._append_relation(subject, "logs", obj)

            elif relation_type == "ghg_record_to_activity":
                self._set_attr_if_present(subject, "activity", obj)
                self._set_attr_if_present(subject, "describesActivity", obj)

            elif relation_type == "ghg_record_to_emission_factor":
                self._set_attr_if_present(subject, "emissionFactor", obj)
                self._set_attr_if_present(subject, "hasFactor", obj)

    def _append_relation(self, subject: Any, attr_name: str, obj: Any) -> None:
        if not hasattr(subject, attr_name):
            return
        current = getattr(subject, attr_name)
        if current is None:
            try:
                setattr(subject, attr_name, [obj])
            except Exception:
                return
            return
        if isinstance(current, list):
            current.append(obj)

    def _set_attr_if_present(self, subject: Any, attr_name: str, value: Any) -> None:
        if hasattr(subject, attr_name):
            try:
                setattr(subject, attr_name, value)
            except Exception:
                pass

    def _build_relation_index(self) -> dict[tuple[str, str], list[str]]:
        index: dict[tuple[str, str], list[str]] = {}
        for relation in self.result.relations:
            key = (relation.subject_entity_id, relation.relation_type.value)
            index.setdefault(key, []).append(relation.object_entity_id)
        return index

    def _get_single_related_object_id(
        self,
        entity_id: str,
        relation_type_value: str,
    ) -> Optional[str]:
        values = self._relation_index.get((entity_id, relation_type_value), [])
        if not values:
            return None
        return values[0]

    def _coerce_to_34_digit_identifier(self, raw_id: str) -> str:
        digits_only = "".join(ch for ch in raw_id if ch.isdigit())
        if len(digits_only) == 34:
            return digits_only

        digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
        numeric = "".join(str(int(ch, 16) % 10) for ch in digest)
        return numeric[:34]

    def _build_placeholder_backup_link(self, entity_id: str) -> str:
        safe_tail = hashlib.sha1(entity_id.encode("utf-8")).hexdigest()[:16]
        return f"https://projection-placeholder.local/dpp/{safe_tail}"

    def _note_technical_fill(
        self,
        message: str,
        entity_id: str,
        entity_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.report.technical_fill_count += 1
        self.report.issues.append(
            ProjectionIssue(
                severity="info",
                message=message,
                entity_id=entity_id,
                entity_type=entity_type,
                details=details or {},
            )
        )
