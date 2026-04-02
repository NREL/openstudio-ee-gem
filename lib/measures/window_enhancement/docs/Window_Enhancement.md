# Window Enhancement

## Overview

This measure improves window performance through six retrofit enhancement options while calculating the embodied carbon impact of upgrades using Environmental Product Declaration (EPD) data from the EC3 database. The measure modifies window thermal and optical properties, adjusts space infiltration rates, and provides comprehensive embodied carbon accounting over a specified analysis period.

## Measure Type

ModelMeasure

## Description

Improves window performance through six retrofit enhancement options: (1) frame replacement, (2) glass pane upgrades (single/double/triple pane), (3) caulking/sealant application, (4) glazing film installation (safety, solar control, low-e, etc.), (5) weatherstripping, and (6) secondary glazing for single-pane windows. The measure calculates embodied carbon impact using Environmental Product Declaration (EPD) data from the EC3 database, modifies window thermal and optical properties based on selected enhancements, and adjusts space infiltration rates to reflect improved air sealing.

## Modeler Description

### Functionality

This measure performs three main functions:

#### 1. Infiltration Reduction

- Reduces space infiltration rates by a user-specified percentage (default 50%)
- Simulates improved air sealing from window enhancements
- Applies reduction to all window-containing spaces in selected space type or entire building
- Accounts for both fixed and operable windows

#### 2. Embodied Carbon Calculation

Calculates life-cycle embodied carbon (kg CO2 eq) for six window enhancement options over the analysis period:

**Glass Pane Replacement**
- Single, double, or triple pane configurations
- Customizable optical properties (transmittance, reflectance, emissivity)
- Customizable thermal properties (U-factor, Solar Heat Gain Coefficient)
- User-specified or default glass thickness

**Frame Replacement**
- Vinyl, aluminum, wood, or fiberglass frame materials
- EC3 EPD data for life-cycle assessment

**Glazing Film Application**
- Safety film
- Solar control film
- Anti-graffiti film
- Decorative film
- Low-e film
- Modifies innermost glass pane to simulate combined glass+film optical and thermal performance

**Caulking**
- Acrylic sealants
- Polyurethane sealants
- Applied to window perimeter for air sealing

**Weatherstripping**
- Felt gaskets
- Foam gaskets
- V-strip weatherstripping
- Vinyl gaskets
- Silicone gaskets
- Applies to operable windows only

**Secondary Glazing**
- Additional interior glass pane for single-pane windows
- Improves thermal resistance and noise reduction
- Creates air gap between primary and secondary panes

#### 3. Thermal and Optical Property Updates

The measure modifies window constructions based on selected enhancements:

- **Glass Replacement**: Creates new multi-pane layered constructions with user-specified or default glass properties
- **Film Application**: Modifies the innermost glass pane to simulate combined glass+film performance
- **Secondary Glazing**: Adds additional glass pane with air gap to existing single-pane windows

### EC3 API Integration

The measure:

- Retrieves EPD data from the EC3 database via API
- Calculates statistical GWP values (minimum, maximum, mean, median)
- Removes outliers using the Interquartile Range (IQR) method
- Accounts for product lifetimes and replacement cycles over analysis period
- Supports custom API token for authentication

### Material Quantity Calculation

Material quantities are calculated based on window dimensions:

- **Areas**: Glass panes, glazing film, frame perimeter
- **Lengths**: Weatherstrip for operable windows, caulking perimeter
- **Volumes**: Caulking bead volume for perimeter air sealing
- **Custom Dividers**: Users can override number of horizontal and vertical muntins to calculate accurate glazing areas, or use default values from model

## Inputs and Arguments

### Required Arguments

| Argument | Type | Units | Default | Description |
|----------|------|-------|---------|-------------|
| `ec3_api_key` | String | - | - | EC3 API token for EPD data retrieval |
| `analysis_period` | Integer | years | 30 | Analysis period for embodied carbon calculation |
| `gwp_statistic` | Choice | - | mean | Statistic to use (minimum, maximum, mean, median) |
| `infiltration_reduction_percent` | Double | % | 50 | Infiltration rate reduction from air sealing |
| `space_type_name` | String | - | (entire building) | Space type for infiltration reduction (or apply to all spaces) |

### Cost and RSMeans Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `calculate_costs` | Boolean | true | Enable capital cost calculation and RSMeans lookup |
| `use_custom_costs` | Boolean | false | If true, skip RSMeans and use user-provided unit costs |
| `glass_cost_per_sf` | Double | 0.0 | Custom glass unit cost ($/SF) used when custom costs enabled or RSMeans fails |
| `frame_cost_per_sf` | Double | 0.0 | Custom frame unit cost ($/SF) used when custom costs enabled or RSMeans fails |
| `caulking_cost_per_cy` | Double | 0.0 | Custom caulking unit cost ($/CY) used when custom costs enabled or RSMeans fails |
| `labor_cost_multiplier` | Double | 1.0 | Labor multiplier applied to material cost when using custom costs |
| `use_specific_rsmeans_line_item_ids` | Boolean | false | If true, use exact RSMeans line item IDs below |
| `rsmeans_id_glazing` | String | "" | Optional RSMeans line item ID for glazing |
| `rsmeans_id_frame` | String | "" | Optional RSMeans line item ID for frame |
| `rsmeans_id_caulking` | String | "" | Optional RSMeans line item ID for caulking |
| `rsmeans_id_film` | String | "" | Optional RSMeans line item ID for film |
| `rsmeans_id_weatherstrip` | String | "" | Optional RSMeans line item ID for weatherstrip |
| `rsmeans_id_secondary_glazing` | String | "" | Optional RSMeans line item ID for secondary glazing |

### Glass Enhancement Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_glass_pane_replacement` | Boolean | false | Enable glass pane replacement |
| `glass_pane_type` | Choice | double | Single, double, or triple pane configuration |
| `glass_transmittance` | Double | 0.84 | Visible transmittance (0.0-1.0) |
| `glass_solar_absorptance` | Double | 0.07 | Solar absorptance (0.0-1.0) |
| `glass_emissivity` | Double | 0.84 | Thermal emissivity (0.0-1.0) |
| `glass_thickness` | Double | 0.003 | Glass thickness (m) |
| `user_num_panes` | Integer | -1 | Custom glazing area panes (-1 uses model) |

### Frame Enhancement Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_frame_replacement` | Boolean | false | Enable frame replacement |
| `frame_material` | Choice | wood_window_frame | Frame material type |

### Caulking Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_caulking` | Boolean | false | Enable caulking/sealant application |
| `caulking_type` | Choice | acrylic | Acrylic or polyurethane sealant |

### Film Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_film_application` | Boolean | false | Enable glazing film installation |
| `film_type` | Choice | safety_film | Film type (safety, solar control, anti-graffiti, decorative, low-e) |

### Weatherstripping Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_weatherstripping` | Boolean | false | Enable weatherstripping (operable windows only) |
| `weatherstrip_type` | Choice | silicone_gasket | Gasket or weatherstrip type |

### Secondary Glazing Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `perform_secondary_glazing` | Boolean | false | Add secondary glazing to single-pane windows |

## Workflow

1. **Initialization**: Retrieves all exterior windows from the model
2. **Space Analysis**: Identifies spaces by type and calculates infiltration reductions
3. **Enhancement Selection**: User selects which enhancements to apply
4. **Construction Modification**: Modifies window constructions based on selected enhancements
5. **EPD Lookup**: Fetches embodied carbon data from EC3 database for each selected material
6. **Quantity Calculation**: Computes volumes and masses for added materials
7. **Embodied Carbon Calculation**: Accounts for analysis period and product replacement cycles
8. **Property Storage**: Records results in window constructions and spaces for reporting
9. **Reporting**: Provides summary of windows processed, renovations applied, and total embodied carbon

## Outputs

Results stored as additional properties include:

**Window Construction Properties:**
- Material quantities (volumes, areas, lengths, masses)
- Embodied carbon metrics (total GWP in kg CO2 eq)
- GWP statistics (minimum, maximum, mean, median)
- Renovation details (enhancement type, properties modified)

**Space Properties:**
- Infiltration reduction percentage
- Number of window-containing spaces
- Total window area

**Summary Report:**
- Infiltration reduction summary
- Windows processed by type
- Renovations applied
- Total embodied carbon for all enhancements

**RSMeans Outputs (Facility AdditionalProperties):**
- `window_enhancement_retrofit_materials_json`
- `window_enhancement_rsmeans_results_json`
   - Includes matched line items, costs, and `match_type` (`exact_id_match` or `closest_match`)

## Important Notes

- **EC3 API Key Required**: Users must obtain an EC3 API key from the EC3 website (https://www.ec3.build)
- **Multiple Enhancements**: Users can select multiple enhancement options simultaneously
- **Custom Dividers**: Use `user_num_panes` to override model's muntin count for accurate glazing area calculations; -1 uses model values
- **Weatherstripping**: Only applies to operable windows; skipped for fixed windows
- **Secondary Glazing**: Requires single-pane layered constructions (not simple glazing systems); skipped if glass replacement also selected to avoid conflicts
- **Film Application**: Requires layered constructions with StandardGlazing materials for successful property modification
- **Outlier Removal**: GWP values are automatically cleaned using IQR method before statistics calculation
- **Replacement Cycles**: Measure accounts for product lifetime and assumes full replacement at end of product life
- **Infiltration Reduction**: Applied uniformly to all spaces or selected space type; does not differentiate by window size or orientation

## Requirements

- OpenStudio 3.0+
- Python 3.7+
- EC3 API key and internet connectivity
- Supporting Python libraries: openstudio, numpy, requests

## Related Measures

- **IncreaseInsulationRValueForExteriorWalls**: Complimentary wall insulation improvements
- **IncreaseInsulationRValueForRoofs**: Roof insulation enhancements
- **ReplaceExteriorWindowConstruction**: Alternative approach for window replacement with custom constructions from model

## Example Workflows

### Scenario 1: Upgrade to High-Performance Double-Pane Windows with Low-E Film

1. Enable glass pane replacement with double-pane configuration
2. Enable low-e film application
3. Set 30-year analysis period
4. Measure will:
   - Replace existing single-pane constructions with double-pane
   - Apply low-e film to innermost pane
   - Calculate embodied carbon for both glass and film
   - Reduce infiltration by 50%
   - Store results for downstream reporting

### Scenario 2: Comprehensive Window Retrofit with Multiple Enhancements

1. Enable glass pane replacement (double-pane)
2. Enable frame replacement (wood)
3. Enable weatherstripping (silicone gasket)
4. Enable caulking (polyurethane)
5. Measure will:
   - Apply all four enhancements to operable windows
   - Calculate cumulative embodied carbon
   - Reduce infiltration by 50%
   - Account for material replacement cycles over 30 years

### Scenario 3: Secondary Glazing for Historic Single-Pane Windows

1. Enable secondary glazing only
2. Disable other enhancements
3. Measure will:
   - Add interior glass panes to single-pane windows
   - Preserve original exterior appearance
   - Calculate embodied carbon for additional glass and air gaps
   - Improve thermal resistance without visible modification
