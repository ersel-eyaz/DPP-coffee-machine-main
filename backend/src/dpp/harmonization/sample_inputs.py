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
                "unitCode": "cycles",
            },
            "chalkCounter": {
                "@value": 3,
                "unitCode": "count",
            },
            "brewCounter": {
                "@value": 182,
                "unitCode": "times",
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
                "@value": 1.85,
                "unitCode": "kg",
            },
            "mtbfHRS": {
                "@value": 5000,
                "unitCode": "hours",
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
                "@value": 0.92,
                "unitCode": None,
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
                "@value": "2026-04-01 10:00:00",
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
                "unitCode": "kgCO2e",
            },
        },
        {
            "@id": "urn:uuid:activity-001",
            "@type": "dpp:ActivityData",
            "activity_type": {
                "@value": "distance_traveled",
            },
            "quantity": {
                "@value": 85000.0,
                "unitCode": "m",
            },
            "unit": {
                "@value": "meter",
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
