// src/content/fieldHelp.js
export const FIELD_HELP = {
  // Header data
  "dates.declaration": "Date of the manufacturer’s product declaration.",
  "dates.published": "Publication date of the product data set.",
  "status.overall": "Count of parts reported OK relative to all parts in the product tree.",

  // Section titles
  "general.title": "General product information (identifiers, economic operators).",
  "specs.title": "Technical characteristics such as dimensions, weight (mass), and TARIC code.",
  "images.title": "Product images provided by the manufacturer.",

  // General information
  "general.gtin": "Global Trade Item Number (GTIN) — unique product identifier.",
  "general.gs1": "GS1 Digital Link — HTTP identifier per the GS1 standard pointing to structured product information.",
  "org.responsible": "Responsible economic operator under EU law.",
  "org.manufacturer": "Manufacturer of the product.",
  "org.importer": "Importer placing the product on the market.",

  // Specs
  "specs.heightCM": "Product height in the unpacked state (centimetres, cm).",
  "specs.widthCM": "Product width in the unpacked state (centimetres, cm).",
  "specs.depthCM": "Product depth in the unpacked state (centimetres, cm).",
  "specs.weightGRM": "Total product weight (grams, g).",
  "specs.taricCode": "EU TARIC code for customs classification.",

  // Guarantee / Warranty
  "guarantee.validUntil": "Validity end date of the guarantee/warranty.",
  "guarantee.description": "Text description of guarantee terms and conditions.",

  // Usage counters
  "counters.operatingHRS": "Cumulative operating hours recorded.",
  "counters.cleaning": "Number of recorded cleaning cycles.",
  "counters.chalk": "Number of recorded descaling events.",
  "counters.brewing": "Number of recorded brewing cycles.",
  "counters.grinding": "Number of recorded grinding cycles.",

  // Materials
  "materials.title": "Overview of the product’s material composition.",
  "materials.distribution": "Mass distribution by material type.",
  "materials.recycled": "Share (%) of recycled content across all materials (mass-based).",
  "materials.rare": "Mass fraction of rare-earth elements in total product mass.",
  "materials.perMaterial": "Per-material mass and share of recycled content.",

  // Documents & Compliance
  "compliance.title": "Conformity certificates (e.g., CE, Ecodesign).",
  "cert.ce": "EU CE Declaration of Conformity.",
  "cert.ecodesign": "Ecodesign compliance declaration.",
  "documents.title": "Additional technical documentation.",
  "doc.dataSheet": "Technical datasheet with key parameters.",
  "doc.installation": "Installation and operating instructions.",
  "doc.repair": "Repair and service manual.",
  "doc.disassembly": "Disassembly instructions.",
  "doc.recycling": "Recycling and end-of-life guidance.",

  // Returning places
  "returning.title": "Take-back locations for repair, return, or recycling.",
  "returning.item": "Location for return, service, or recycling (GLN — Global Location Number).",

  // Backup
  "backup.title": "External backup link (e.g., data provisioning endpoint).",

  // Parts
  "parts.title": "Structured product parts tree.",
  "parts.totalInTree": "Total count of parts (including sub-assemblies).",
  "parts.statusOverall": "Overall parts status (OK vs. fault state).",

  // Journey / Process
  "journey.title": "Graphical representation of production, transport, and secondary steps.",
  "process.title": "Number of identified process steps by category.",
  "process.total": "Sum of all process steps.",
  "process.production": "Production (manufacturing) steps.",
  "process.transport": "Transport and logistics steps.",
  "process.secondary": "Secondary value steps (e.g., service, refurbishment).",

  // GHG
  "ghg.header": "Greenhouse-gas emissions based on life-cycle data.",
  "ghg.total": "Total greenhouse-gas emissions across Scopes 1, 2, and 3.",
  "ghg.scopes":
    "Breakdown by scopes: Scope 1 (direct), Scope 2 (purchased energy), Scope 3 (value-chain upstream/downstream).",
  "ghg.byCategory": "Totals per category (e.g., purchased goods, transport).",

  // Transport distance
  "transport.header": "Aggregated transport distances derived from process steps.",
  "transport.total": "Total transport distance across all steps.",
  "transport.parts": "Transport distance from parts-related steps.",
  "transport.materials": "Transport distance from materials-related steps.",
  //DPPLinks
  "dpplinks.header": "Links to DPP resources of subparts.",
  //PartTree.jsx
  "materials.totalWeight": "Total product weight in grams (g).",
  "purity.avg": "Average purity across recorded batches (0–100%).",
  "parts.subparts": "Sub-assemblies/parts directly belonging to this part.",

  // --- ServiceView additions ---
  "service.header": "Service & maintenance overview and actions.",
  "service.dates": "Key dates and warranty/qualification info for servicing.",
  "dates.productAge": "Days since product declaration date.",
  "qualification.required": "Required skill level or certification for performing repairs.",

  "mtbf.title": "MTBF = Mean Time Between Failures — reliability indicator.",
  "mtbf.expected": "Expected mean time between failures.",

  "tools.maintenance": "Recommended tools for service procedures.",
  "spares.common": "Commonly replaced parts for this product.",

  "history.service": "All recorded service steps with costs and notes.",
  "history.totalCost": "Sum of costs across all listed steps.",

  "diag.probNote": "Probabilities are derived from historical service data.",
  "diag.avgCost": "Average repair cost for this diagnosis.",
  "diag.avgOccur": "Average time from declaration until occurrence.",

  "parts.failing": "Parts currently reported in a failstate.",
  "parts.detached": "Parts that were removed during service over the product’s lifetime.",

  "modal.stepType": "Choose the type of service step to register.",
  "modal.processedAt": "Facility/location where the step was performed.",
  "modal.part": "Target part instance for this service step.",
  "modal.cost": "Optional handling/processing cost.",
  "modal.beginDate": "Local date/time converted to ISO when saved.",
  "modal.newPartStatic": "Select the static definition for the new/replacement part.",
  "modal.serial": "Optional serial number for the new part.",
  "modal.batch": "Optional batch number for traceability.",
  "modal.diagnose": "Short description of the diagnosed issue.",
  "modal.symptoms": "Comma or semicolon separated list of observed symptoms.",

  //--- End-of-life ---
  "eol.header": "Overview for take-back, recycling and end-of-life handling.",
  "eol.compliance": "End-of-life handling information and compliance identifiers.",

  "weee.number": "National WEEE registration identifier for producer responsibility.",

  "counters.title": "Recorded usage metrics from the device.",

  "materials.virgin": "Share of virgin (non-recycled) content.",
  "materials.rareParts": "Materials flagged as rare-earth and the parts where they occur (with grams).",
  "materials.hazardous": "Materials flagged as hazardous; shows affected parts and warnings.",

  "recycling.beginDate": "Timestamp stored on the RecyclingStep.",
  "recycling.reason": "Short explanation saved as RecyclingStep.reason.",
  "recycling.diagnose": "Optional diagnostic note for the end-of-life step.",

  //--- PartTreeService ---
  "part.failstate": "Current failstate flag on this part instance.",
  "part.modular": "Whether this part is modular and can be replaced independently.",
  "service.summary.subtree": "Aggregated service metrics for this node and all its subparts (subtree).",
  "service.cost.total": "Total service cost recorded for this subtree.",
  "service.counts.repair": "Number of repair steps affecting this subtree.",
  "service.counts.replace": "Number of replacement steps affecting this subtree.",
  "service.counts.cleaning": "Number of cleaning steps affecting this subtree.",
  "service.counts.remanufacturing": "Number of remanufacturing steps affecting this subtree.",
  "service.counts.refurbishment": "Number of refurbishment steps affecting this subtree.",
  "node.toggleFail": "Toggle the failstate of this part instance.",

  //-- Subpart tree visualizer
  "componenttree.title":
    "Visualisation of the subpart composition of the product. Click on a node to expand or collapse it.",
};
