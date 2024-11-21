

###### (Automatically generated documentation)

# Replace Exterior Window Constructions with a Different Construction from the Model.

## Description
Replace existing windows with different windows to change thermal or lighting performance.  Window technology has improved drastically over the years, and double or triple-pane high performance windows currently on the market can cut down on envelope loads greatly.  Window frames with thermal breaks reduce the considerable energy that can transfer through thermally unbroken frames.  High performance windows typically also come with low-emissivity (low?e) glass to keep radiant heat on the same side of the glass from where the heat originated. This means that during the cooling months a low-e glass would tend to keep radiant heat from the sun on the outside of the window, which would keep the inside of a building cooler. Conversely, during heating months low-e glass helps keep radiant heat from inside the building on the inside, which would keep the inside of a building warmer.  Life cycle cost values may be added for the new window applied by the measure.

## Modeler Description
Replace fixed and/or operable exterior window constructions with another construction in the model.  Skylights (windows in roofs vs. walls) will not be altered. Windows in surfaces with `Adiabatic` boundary conditions are not specifically assumed to be interior or exterior. As a result constructions used on windows in `Adiabatic` surfaces will not be altered. `Material, installation, demolition, and O and M costs` can be added to the applied window construction. Optionally any prior costs associated with construction can be removed. <br/> <br/> For costs added as part of a design alternatives `Years Until Costs Start?` is typically `0`. For a new construction scenario `Demolition Costs Occur During Initial Construction?` is `false`. For retrofit scenario `Demolition Costs Occur During Initial Construction?` is `true`. `O and M cost and frequency` can be whatever is appropriate for the component.

## Measure Type
ModelMeasure

## Taxonomy


## Arguments


### Pick a Window Construction From the Model to Replace Existing Window Constructions.

**Name:** construction,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Change Fixed Windows?

**Name:** change_fixed_windows,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Change Operable Windows?

**Name:** change_operable_windows,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Remove Existing Costs?

**Name:** remove_costs,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Material and Installation Costs for Construction per Area Used ($/ft^2).

**Name:** material_cost_ip,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Demolition Costs for Construction per Area Used ($/ft^2).

**Name:** demolition_cost_ip,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Years Until Costs Start (whole years).

**Name:** years_until_costs_start,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Demolition Costs Occur During Initial Construction?

**Name:** demo_cost_initial_const,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Expected Life (whole years).

**Name:** expected_life,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### O & M Costs for Construction per Area Used ($/ft^2).

**Name:** om_cost_ip,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### O & M Frequency (whole years).

**Name:** om_frequency,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false




