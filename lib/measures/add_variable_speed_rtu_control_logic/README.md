

###### (Automatically generated documentation)

# Add Variable Speed RTU Control Logic

## Description
This measure adds control logic for a variable-speed RTU to the model. The control logic is responsible for staging the fan in response to the amount of heating/cooling required. It is meant to be paired specifically with the Create Variable Speed RTU OpenStudio measure. Users enter the fan flow rate fractions for up to nine different stages: ventilation, up to four cooling stages, and up to four heating stages. The measure examines the amount of heating/cooling required at each time step, identifies which heating/cooling stage is required to supply that amount of heating/cooling, and modifies the fan flow accordingly. This measure allows users to identify the impact of different fan flow control strategies.

## Modeler Description
This measure inserts EMS code for each airloop found to contain an AirLoopHVAC:UnitarySystem object. It is meant to be paired specifically with the Create Variable Speed RTU OpenStudio measure.

Users can select the fan mass flow fractions for up to nine stages (ventilation, two or four cooling, and two or four heating). The default control logic is as follows:
When the unit is ventilating (heating and cooling coil energy is zero), the fan flow rate is set to 40% of nominal.
When the unit is in heating (gas heating coil), the fan flow rate is set to 100% of nominal (not changeable).
When the unit is in staged heating/cooling, as indicated by the current heating/cooling coil energy rate divided by the nominal heating/cooling coil size, the fan flow rate is set to either 50/100% (two-stage compressor), or 40/50/75/100% (four-stage compressor).

When applied to staged coils, the measure assumes that all stages are of equal capacity. That is, for two-speed coils, that the compressors are split 50/50, and that in four-stage units, that each of the four compressors represents 25% of the total capacity.

The measure is set up so that a separate block of EMS code is inserted for each applicable airloop (i.e., the EMS text is not hard-coded).

## Measure Type
EnergyPlusMeasure

## Taxonomy


## Arguments


### Fan speed fraction during ventilation mode.

**Name:** vent_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage one DX cooling.

**Name:** stage_one_cooling_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage two DX cooling.

**Name:** stage_two_cooling_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage three DX cooling. Not used for two-speed systems.

**Name:** stage_three_cooling_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage four DX cooling. Not used for two-speed systems.

**Name:** stage_four_cooling_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage one DX heating.

**Name:** stage_one_heating_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage two DX heating.

**Name:** stage_two_heating_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage three DX heating. Not used for two-speed systems.

**Name:** stage_three_heating_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false

### Fan speed fraction during stage four DX heating. Not used for two-speed systems.

**Name:** stage_four_heating_fan_speed,
**Type:** Double,
**Units:** ,
**Required:** false,
**Model Dependent:** false




