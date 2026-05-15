"""
Product Scope definition.

This scope focuses on product usage and physical plausibility. It covers
selected numeric fields from DPPStatic, PartStatic, MaterialInstance, and
DPPInstance.

ProcessStep and service-step subclasses are intentionally excluded.
"""

from __future__ import annotations

from dpp.data_quality.scopes.schemas import CanonicalField, CanonicalRelation, ScopeDefinition


PRODUCT_SCOPE = ScopeDefinition(
    name="product",
    title="Product Usage and Physical Plausibility",
    description=(
        "Selected product, part, material, and usage fields used for label/unit "
        "harmonization and anomaly detection."
    ),
    entities=(
        "DPPStatic",
        "DPPInstance",
        "PartStatic",
        "PartInstance",
        "MaterialStatic",
        "MaterialInstance",
    ),
    fields=(
        # DPPStatic identity/context fields used by optional product profiles.
        CanonicalField(
            entity_type="DPPStatic",
            field_name="name",
            role="analysis_context",
            description="Product model name used to select optional plausibility profiles.",
        ),
        CanonicalField(
            entity_type="DPPStatic",
            field_name="productClass",
            role="analysis_context",
            description="Product class used as broad context for plausibility checks.",
        ),

        # DPPStatic physical fields
        CanonicalField(
            entity_type="DPPStatic",
            field_name="weightGRM",
            role="label_harmonization",
            target_unit="g",
            description="Product-level static weight.",
        ),
        CanonicalField(
            entity_type="DPPStatic",
            field_name="heightCM",
            role="label_harmonization",
            target_unit="cm",
            description="Product-level static height.",
        ),
        CanonicalField(
            entity_type="DPPStatic",
            field_name="widthCM",
            role="label_harmonization",
            target_unit="cm",
            description="Product-level static width.",
        ),
        CanonicalField(
            entity_type="DPPStatic",
            field_name="depthCM",
            role="label_harmonization",
            target_unit="cm",
            description="Product-level static depth.",
        ),

        # PartStatic physical fields
        CanonicalField(
            entity_type="PartStatic",
            field_name="weightGRM",
            role="label_harmonization",
            target_unit="g",
            description="Part-level static weight.",
        ),
        CanonicalField(
            entity_type="PartStatic",
            field_name="heightCM",
            role="label_harmonization",
            target_unit="cm",
            description="Part-level static height.",
        ),
        CanonicalField(
            entity_type="PartStatic",
            field_name="widthCM",
            role="label_harmonization",
            target_unit="cm",
            description="Part-level static width.",
        ),
        CanonicalField(
            entity_type="PartStatic",
            field_name="depthCM",
            role="label_harmonization",
            target_unit="cm",
            description="Part-level static depth.",
        ),

        # MaterialInstance material quality fields
        CanonicalField(
            entity_type="MaterialInstance",
            field_name="weightGRM",
            role="label_harmonization",
            target_unit="g",
            description="Material instance mass.",
        ),
        CanonicalField(
            entity_type="MaterialInstance",
            field_name="percentRecycled",
            role="label_harmonization",
            target_unit="percent",
            description="Recycled-content percentage.",
        ),
        CanonicalField(
            entity_type="MaterialInstance",
            field_name="purityLevel",
            role="label_harmonization",
            target_unit="ratio",
            description="Material purity ratio used for plausibility checks.",
        ),

        # DPPInstance usage counters
        CanonicalField(
            entity_type="DPPInstance",
            field_name="operatingHRS",
            role="label_harmonization",
            target_unit="h",
            description="Product operating hours.",
        ),
        CanonicalField(
            entity_type="DPPInstance",
            field_name="brewingCount",
            role="label_harmonization",
            target_unit="count",
            description="Number of brewing cycles.",
        ),
        CanonicalField(
            entity_type="DPPInstance",
            field_name="cleaningCount",
            role="label_harmonization",
            target_unit="count",
            description="Number of cleaning cycles.",
        ),
        CanonicalField(
            entity_type="DPPInstance",
            field_name="chalkCount",
            role="label_harmonization",
            target_unit="count",
            description="Number of descaling cycles.",
        ),
        CanonicalField(
            entity_type="DPPInstance",
            field_name="coffeeGrindingCount",
            role="label_harmonization",
            target_unit="count",
            description="Number of coffee grinding cycles.",
        ),

        # Context fields used only if present in canonical form.
        CanonicalField(
            entity_type="PartInstance",
            field_name="isModular",
            role="analysis_context",
            description="Optional context for product and part plausibility.",
        ),
        CanonicalField(
            entity_type="PartInstance",
            field_name="hasFailstate",
            role="analysis_context",
            description="Optional condition context; field name follows prototype code.",
        ),
    ),
    relations=(
        CanonicalRelation(
            source_entity_type="DPPInstance",
            relation_name="dppStaticLink",
            target_entity_type="DPPStatic",
            required=True,
            description="Links a product instance to its static DPP definition.",
        ),
        CanonicalRelation(
            source_entity_type="DPPInstance",
            relation_name="partInstanceLink",
            target_entity_type="PartInstance",
            required=False,
            description="Links a product instance to the top-level part instance.",
        ),
        CanonicalRelation(
            source_entity_type="PartInstance",
            relation_name="partStaticLink",
            target_entity_type="PartStatic",
            required=True,
            description="Links a part instance to its static part definition.",
        ),
        CanonicalRelation(
            source_entity_type="PartInstance",
            relation_name="compositeParts",
            target_entity_type="PartInstance",
            is_collection=True,
            description="Preserves recursive child-part structure.",
        ),
        CanonicalRelation(
            source_entity_type="PartInstance",
            relation_name="compositeMaterials",
            target_entity_type="MaterialInstance",
            is_collection=True,
            description="Preserves part-to-material composition structure.",
        ),
        CanonicalRelation(
            source_entity_type="MaterialInstance",
            relation_name="materialStaticLink",
            target_entity_type="MaterialStatic",
            required=True,
            description="Links a material instance to its static material definition.",
        ),
    ),
)
