# Unit Normalization Policy

Unit harmonization in this prototype is deterministic and field-context-aware.
It does not use LLM-generated aliases or runtime semantic inference.

## Rationale

Units carry quantitative meaning. Incorrect unit normalization can silently
change the interpretation of numeric values, so this layer is intentionally more
conservative than label, enum, or service-text harmonization.

The implementation separates two concerns:

- Ordinary unit spelling variants follow the practical canonical-name, symbol,
  and alias style used by Pint's default English unit definitions.
- Canonical output units are restricted to the selected prototype fields and
  legacy JSON-LD/export vocabulary.
- Field-bound measurement units and explicit emission `UnitCode` values are
  stored together in `harmonization/unit_registry.py`, but remain separate
  vocabularies.

Pint is not imported at runtime and its full registry is not copied. It is used
only as a practical reference for ordinary English symbols/names such as `gram`,
`centimetre`, `hour`, `minute`, `liter/litre`, and `watt hour`. The active
registry remains a small curated registry for the units needed by the selected
DPP product and emission scopes.

## Alias Scope

Aliases are limited to common symbols, English unit names, British/American
spelling variants, and compact reporting expressions used by the prototype.
For ordinary physical units, the accepted aliases follow the same kind of
canonical-name/symbol/alias structure used by Pint's default English unit
definitions.

Canonical output examples for field-bound legacy measurements:

- `GRM`: `g`, `gram`, `grams`, `grm`
- `CM`: `cm`, `centimeter`, `centimeters`, `centimetre`, `centimetres`
- `HRS`: `h`, `hour`, `hours`, `hr`, `hrs`
- `kWh`: `kilowatt hour`, `kilowatt-hour`, `kilowatt hours`
- `kgCO2e/km`: `kg CO2e/km`, `kg CO2 equivalent per kilometre`

Source-only conversion units are not treated as standalone output units. For
example, `minutes` can be accepted for a mapped `operatingHRS` value and
converted to `HRS`, but `min` is not a legacy output unit by itself.

Explicit emission unit fields are treated as legacy unit-code fields rather than
free unit text:

- `ActivityData.unit` accepts activity source units such as `m`, `km`, `kg`,
  `kWh`, `ltr`, `m3`, `t`, and `unit`; convertible distance input such as `m`
  is aligned to the legacy output value `km` when the quantity is normalized.
- `EmissionFactor.unit` accepts the supported factor units
  `kgCO2e/kWh`, `kgCO2e/kg`, and `kgCO2e/km`.

Ambiguous generic labels such as `u` are not auto-resolved. The literal value
`unit` is accepted only where the legacy unit-code context allows it.

## Runtime Behavior

The unit resolver uses:

1. Exact alias lookup after deterministic key normalization.
2. Conservative fuzzy matching for obvious spelling variants.
3. Field-aware validation against the expected target unit, source-unit family,
   or legacy unit-code vocabulary.

If no safe match is found, the raw unit is preserved and an issue is reported.
The issue includes the expected units for the mapped field where available.

## Exclusions

- No LLM/API notebook is used for unit alias generation.
- No feedback-learning mechanism mutates unit aliases at runtime.
- Generic packaging or informal units such as `box` are not mapped to physical
  units unless they are explicitly modeled in a future domain-specific registry.

Emission units such as `kgCO2e`, `kgCO2e/kWh`, `kgCO2e/kg`, and `kgCO2e/km`
are treated as domain-specific greenhouse-gas reporting units inside the
emission scope.
