

###### (Automatically generated documentation)

# NZEHVAC

## Description
This measure replaces the existing HVAC system if any with the user selected HVAC system.  The user can select how to partition the system, applying it to the whole building, a system per building type, a system per building story, or automatically partition based on residential/non-residential occupany types and space loads.

## Modeler Description
HVAC system creation logic uses [openstudio-standards](https://github.com/NREL/openstudio-standards) and efficiency values are defined in the openstudio-standards Standards spreadsheet under the *NREL ZNE Ready 2017* template.

## Measure Type
ModelMeasure

## Taxonomy


## Arguments


### Remove existing HVAC?

**Name:** remove_existing_hvac,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### HVAC System Type:
Details on HVAC system type in measure documentation.
**Name:** hvac_system_type,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### DOAS capable of demand control ventilation?
If a DOAS system, this will make air terminals variable air volume instead of constant volume.
**Name:** doas_dcv,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### HVAC System Partition:
Automatic Partition will separate the HVAC system by residential/non-residential and if loads and schedules are substantially different.
**Name:** hvac_system_partition,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false




