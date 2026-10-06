# Dairy plant 3D scene — requirements brief

**Version:** 0.1 · **Date:** 5 October 2026 · **Status:** Draft for delegation

Create an editable, realistic 3D scene of a compact dairy processing plant that receives raw milk, separates it into skim milk and cream, pasteurizes the two streams, and transfers them to cooled storage. A viewer should be able to follow the process and understand what each major piece of equipment does.

## 1. Purpose and working assumptions

The owner confirmed **realistic 3D visualization** as the first delivery. Build a navigable scene for explanation, presentations, and layout discussion. Use the defaults below unless the owner supplies different requirements. These are proposed scene assumptions, not facts about an existing plant.

| Item | Default for this brief |
|---|---|
| Facility | Fictional dairy plant using public references and generic equipment |
| Feed and products | Cow's milk; pasteurized skim milk and pasteurized cream |
| Illustrative capacity | Approximately 5,000 litres of incoming milk per hour |
| Building envelope | Approximately 24 m × 16 m, with 6 m clear internal height |
| Visual style | Clean, believable industrial interior with recognizable dairy equipment |
| Detail level | Equipment, nozzles, pipe routes, supports, instruments, and operator access visible at room and equipment scale |
| Default delivery | Editable source scene, portable OpenUSD export, preview images, and handoff notes |
| Viewer | Use an available desktop 3D viewer or authoring application; a custom app is optional |

This is a conceptual visualization. Dimensions, capacities, and displayed process values are illustrative; construction design, validated food processing, and calibrated simulation require a separate scope.

## 2. Process the scene must communicate

Use **cream separation** as the equipment/process term. In the selected arrangement, milk is warmed before the separator and final heat treatment follows separation. Cream separation and milk pasteurization belong to one connected process; they are not two unrelated demonstrations. This is based on the warm-separation arrangement described in the [Tetra Pak separator reference](https://dairyprocessinghandbook.tetrapak.com/chapter/centrifugal-separators-and-milk-standardization).

```text
Raw milk reception → Raw milk tanks → Balance tank / feed pump
                                           ↓
                                  Preheating section
                                           ↓
                                     Cream separator
                                      /           \
                              Skim milk           Cream
                                  ↓                 ↓
                            Milk heating       Cream buffer
                                  ↓                 ↓
                             Holding tube      Cream heating
                                  ↓                 ↓
                          Temperature check     Holding tube
                          / diversion valve          ↓
                                  ↓          Temperature check
                         Heat recovery /      / diversion valve
                              cooling                ↓
                                  ↓               Cooling
                          Skim milk tank             ↓
                            / outlet            Cream tank
                                                  / outlet
```

The milk preheating, final heating, heat recovery, and cooling sections may share one plate heat exchanger assembly. Label its separate functions. Show the raw and treated product passages as separate circuits; heat recovery must not look like direct mixing. Include a clearly traceable return route from the milk diversion valve to the balance tank. Give the cream line its own depicted return route to its buffer. Holding tubes and diversion arrangements should follow the principles in the [process-line reference](https://dairyprocessinghandbook.tetrapak.com/chapter/designing-process-line).

For explanatory labels, use approximately 60–65 °C at separation, 35–40% fat for the cream stream, and a low-fat skim stream. Milk heat treatment can be labeled “illustrative HTST: 72–75 °C, 15–20 seconds,” followed by cooling to approximately 4 °C. Label the cream skid as a separate cream-specific heat treatment and cooling process; do not simply copy the milk settings. Exact cream conditions are outside this scene brief. See the [milk and cream processing reference](https://dairyprocessinghandbook.tetrapak.com/chapter/pasteurized-and-esl-dairy-products).

The baseline produces skim milk. Adding cream back to make standardized drinking milk is an optional extension. Omit homogenization from the baseline to keep this process easy to follow.

## 3. Required equipment and visible details

Use the tags below consistently in the scene, labels, and asset list. Capacities are scene assumptions. Detailed equipment geometry may be adapted from public references, with its source recorded.

| Tag | Equipment / quantity | Required visible detail |
|---|---|---|
| REC-101 | One milk reception station | Unloading connection, capped hose connection, strainer/filter, transfer pump, and flow meter. A tanker vehicle is optional. |
| TK-101 / TK-102 | Two raw milk tanks, nominally 5,000 L each | Vertical insulated stainless vessels, manways, inlet/outlet connections, temperature and level instruments, and plausible access provisions. |
| BT-101 / P-101 | One balance tank and feed pump | Small vessel upstream of the milk processing skid, level instrument, pump motor, isolation valves, and connecting pipework. |
| HX-101 | One milk plate heat exchanger skid | Recognizable plate pack and frame, labeled thermal sections, utility connections, and distinguishable product ports. Reserve about 5 m × 3 m for the overall milk skid. |
| SEP-101 | One centrifugal cream separator | Disc-stack separator housing, motor/base, one feed and two distinguishable product outlets. Reserve about 2 m × 2 m. |
| HT-101 / DV-101 | One milk holding section and diversion assembly | Holding tube, temperature instrument, valve, forward path, and return path. These are separately named parts of the milk skid. |
| TK-201 | One cream buffer, nominally 500 L | Closed vessel upstream of cream heat treatment, with inlet/outlet and level indication. |
| HX-201 / HT-201 / DV-201 | One cream treatment skid | Heat exchanger, holding section, temperature instrument, diversion route, pump, and cooling connections. Reserve about 3 m × 2 m. |
| TK-301 | One cooled skim milk tank, nominally 5,000 L | Insulated vessel, product inlet/outlet, level and temperature instruments, and outlet labeled “to downstream filling.” |
| TK-302 | One cooled cream tank, nominally 1,000 L | Visibly smaller vessel, labeled cream inlet/outlet, level and temperature instruments, and outlet labeled “to downstream use / filling.” |
| CIP-401 | One clean-in-place station | Three illustrative vessels labeled water, alkaline solution, and acid solution; pump, valve manifold, supply and return headers. Reserve about 4 m × 3 m. |
| UTL-501 / CP-601 | Utility connections and control panel | Hot-water and chilled-water supply/return headers, compressed-air connection, electrical cabinet, emergency-stop button, and local operator screen. |

Include additional pumps, valves, elbows, reducers, clamps, pipe supports, and cable trays where the layout needs them. Product pipes must meet equipment nozzles rather than disappear into a housing. Give unused connections caps or explicit boundary labels.

## 4. Layout and spatial requirements

Arrange the room so an overview reads from raw milk reception on one side, through separation and heat treatment in the middle, to finished product storage on the opposite side. Keep the cream branch alongside the milk branch so the split is easy to see. Place CIP and utilities along a service wall, leaving access to the processing equipment.

Use these modeling targets, which are layout assumptions rather than certified clearances:

- A continuous main operator aisle at least 1.2 m wide.
- Approximately 1 m of visible service space at equipment access faces; allow extra space where plates, motors, or separator parts would be removed.
- At least 2.2 m head clearance wherever pipes cross a walking route.
- Equipment and tank heights that fit the building, including overhead connections.
- Doors, drains, support legs, and stairs or platforms placed without obvious clashes.

Provide a removable roof and hideable walls for overview viewing. Include a simple hygiene entry, washable wall surfaces, floor drains, and marked walking routes. Treat raw milk, treated product, utilities, and cleaning circuits as separately identifiable routes. Pipe crossings are not junctions unless a connection is intentionally modeled.

## 5. Appearance and process readability

Use brushed stainless steel for equipment and sanitary pipework, restrained painted finishes for motors and cabinets, and a clean epoxy-style floor. Vary roughness enough to distinguish surfaces; avoid making every object mirror polished. Include readable equipment tags, valve handles, instrument faces, and pipe identification bands.

Keep product pipes visually metallic in the normal view. Provide a separate explanation view or display layer using directional arrows and labels: raw milk, skim milk, cream, hot water, chilled water, and CIP. Colors are an explanatory convention for this scene, not an asserted plant standard. Use labels as well as color.

The separator must be recognizable by its shape and connected outlets. The pasteurizer must visibly include a plate heat exchanger and holding section. Final delivery should have more detail than generic cylinders and boxes. Internals such as separator discs may be shown in an optional cutaway; keep normal equipment housings closed.

## 6. Viewer behavior and optional extensions

**Required:** orbit, pan, and zoom; a whole-plant overview; saved views of reception, milk treatment, the separator, cream treatment, and product storage; and a way to show/hide building surfaces and process labels. Native application controls are acceptable. A viewer should be able to trace either product route without opening the modeling hierarchy.

**Optional walkthrough:** a 60–90 second camera tour with moving flow markers, stage captions, and a close-up of the separator split. Mark time compression and illustrative readings clearly.

**Optional interactive demonstration:** start/pause/reset, selected equipment information, and illustrative production, temperature-diversion, and cleaning states. In a diversion demonstration, the affected product must follow its return route and stop entering its finished-product tank. Cleaning and product movement must not be shown simultaneously in the same circuit.

Physical fluid simulation, heat-transfer calculation, rotating separator physics, validated PLC logic, live sensor integration, filling machines, packaging lines, full utility plants, and robot navigation are outside the baseline. Scope those separately if needed.

## 7. Deliverables

| Deliverable | Required contents |
|---|---|
| Editable source | Native scene/project; generation scripts and parameters if used; materials and referenced assets |
| Portable 3D scene | OpenUSD entry file with packaged dependencies and relative asset paths; a GLB preview is optional |
| Preview set | At least six images at 1920 × 1080 or higher: overview, labeled top view, milk skid, separator connections, cream line, and CIP/utilities |
| Asset and connection list | CSV, JSON, or Markdown recording each tag, name, function, approximate dimensions, and each principal pipe's origin, destination, and service |
| Handoff notes | Application/version, opening steps, units, axes, navigation, assumptions, reference/asset attribution, licenses, and known omissions |
| Review evidence | Completed acceptance checklist with image or scene-view references |

Use metres for scale. For OpenUSD, author Z-up and set the stage's units explicitly. Keep equipment, pipes, structure, annotations, lights, and cameras in separate named groups. Individual tagged equipment must remain selectable and movable. Do not deliver the entire plant as one merged mesh. Validate the export by reopening it independently of the authoring session.

## 8. Acceptance checklist

- [ ] All equipment tags in Section 3 exist and match the asset list.
- [ ] A reviewer can trace raw milk to the separator and both outlet streams to their own treatment and storage equipment.
- [ ] Forward and diversion routes are visible; raw milk does not bypass treatment into finished-product storage.
- [ ] Principal pipes connect to visible ports, and utilities are distinguishable from product circuits.
- [ ] The building, equipment, and clearances meet the declared scene dimensions, with no obvious intersections or floating assets.
- [ ] The plate pack, holding section, and separator are recognizable in close-up.
- [ ] Overview and detail views have usable lighting and legible labels.
- [ ] Scene groups and individual equipment remain editable, with consistent tags and scale.
- [ ] The delivered export opens with no missing geometry, materials, or textures on the documented viewer/version.
- [ ] Navigation works on the builder's declared test machine; report the machine, viewer, and any visible performance limitations.
- [ ] Preview images, references, assumptions, and known omissions are included.
- [ ] Any optional animation follows the same connections as the static scene and identifies illustrative behavior.

## 9. Suggested work sequence

Start with a simple layout and the complete process connections. Save an overview and top view so the layout can be reviewed before detailed modeling. Next refine the separator, pasteurization skids, tanks, and connected pipework. Add materials, labels, and viewing controls, then package the export and complete the acceptance checklist. Deliver the baseline before adding optional behavior.

The recipient should record their chosen authoring tool and viewer, whether optional animation is included, and an estimated effort before detailed production. No deadline or target hardware has been specified. Use the stated defaults for a first layout; request owner input only when a missing decision materially changes scope or compatibility.

## 10. Message to send with this brief

> Please build the dairy plant 3D scene described in the attached requirements brief. Use its default assumptions for a first layout and record any changes. Deliver a realistic, editable scene with connected equipment, separate skim milk and cream paths, useful overview/detail views, and a portable OpenUSD package. Save a layout checkpoint before detailed modeling. Prioritize process clarity, recognizable equipment, and clean handoff files. Treat animation and simulation as optional additions. Include evidence against the acceptance checklist and call out any requirement you could not meet.

*Public references checked 5 October 2026: Tetra Pak Dairy Processing Handbook, [centrifugal separators and milk standardization](https://dairyprocessinghandbook.tetrapak.com/chapter/centrifugal-separators-and-milk-standardization), [designing a process line](https://dairyprocessinghandbook.tetrapak.com/chapter/designing-process-line), and [pasteurized and ESL dairy products](https://dairyprocessinghandbook.tetrapak.com/chapter/pasteurized-and-esl-dairy-products). These references inform the process concept; the proposed layout and scene dimensions are original assumptions.*
