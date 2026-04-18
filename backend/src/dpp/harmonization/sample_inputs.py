from __future__ import annotations


EXAMPLE_JSONLD_DOCUMENT = {
    "@context": {
        "schema": "https://schema.org/",
        "dpp": "https://example.org/dpp#",
    },
    "@graph": [
        {
            "@id": "urn:uuid:dpp-instance-001",
            "@type": "dpp:DPPInstance",
            "operatingHours": {
                "@value": 120.0,
                "unitCode": "hours",
            },
            "cleaning_cycles": {
                "@value": 14,
                "unitCode": "count",
            },
            "chalkCounter": {
                "@value": 3,
                "unitCode": "count",
            },
            "hasTopPart": {
                "@id": "urn:uuid:part-instance-root-001",
            },
        },
        {
            "@id": "urn:uuid:part-instance-root-001",
            "@type": "dpp:PartInstance",
            "isModular": False,
            "hasFailstate": True,
            "partStaticLink": {
                "@id": "urn:uuid:part-static-001",
            },
            "compositeMaterials": [
                {
                    "@id": "urn:uuid:material-instance-001",
                }
            ],
        },
        {
            "@id": "urn:uuid:part-static-001",
            "@type": "dpp:PartStatic",
            "weightGRM": {
                "@value": 1850.0,
                "unitCode": "g",
            },
            "mtbfHRS": {
                "@value": 5000,
                "unitCode": "h",
            },
        },
        {
            "@id": "urn:uuid:material-instance-001",
            "@type": "dpp:MaterialInstance",
            "weightGRM": {
                "@value": 220.0,
                "unitCode": "g",
            },
            "percentRecycled": {
                "@value": 35.0,
                "unitCode": "%",
            },
            "purityLevel": {
                "@value": 92.0,
                "unitCode": "%",
            },
            "materialStaticLink": {
                "@id": "urn:uuid:material-static-001",
            },
        },
        {
            "@id": "urn:uuid:material-static-001",
            "@type": "dpp:MaterialStatic",
            "hazardous": False,
            "rareEarth": True,
        },
        {
            "@id": "urn:uuid:process-step-001",
            "@type": "dpp:ProcessStep",
            "beginDate": {
                "@value": "2026-04-01T10:00:00Z",
            },
            "endDate": {
                "@value": "2026-04-01T11:00:00Z",
            },
            "ghgEmissionRecords": [
                {
                    "@id": "urn:uuid:ghg-record-001",
                }
            ],
        },
        {
            "@id": "urn:uuid:ghg-record-001",
            "@type": "dpp:GHGEmissionRecord",
            "scope": {
                "@value": "Scope 3",
            },
            "scope3_category": {
                "@value": "Upstream transportation and distribution",
            },
            "calculation_method": {
                "@value": "activity.quantity * emission_factor.value",
            },
            "provenance": {
                "@value": "supplier_estimate",
            },
            "activity": {
                "@id": "urn:uuid:activity-001",
            },
            "emission_factor": {
                "@id": "urn:uuid:emission-factor-001",
            },
            "emissions_kg_co2e": {
                "@value": 12.5,
                "unitCode": "kg_co2e",
            },
        },
        {
            "@id": "urn:uuid:activity-001",
            "@type": "dpp:ActivityData",
            "activity_type": {
                "@value": "distance_traveled",
            },
            "quantity": {
                "@value": 85.0,
                "unitCode": "km",
            },
            "unit": {
                "@value": "km",
            },
        },
        {
            "@id": "urn:uuid:emission-factor-001",
            "@type": "dpp:EmissionFactor",
            "value": {
                "@value": 0.147,
                "unitCode": "kgCO2e/km",
            },
            "unit": {
                "@value": "kgCO2e/km",
            },
        },
    ],
}