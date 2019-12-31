

###### (Automatically generated documentation)

# Fan Assist Night Ventilation

## Description
This measure is meant to roughly model the impact of fan assisted night ventilation. The user needs to have a ventilation schedule in the model, operable windows where natural ventilation is desired, and air walls or interior operable windows in walls and floors to define the path of air through the building. The user specified flow rate is proportionally split up based on the area of exterior operable windows. The size of interior air walls and windows doesn't matter.

## Modeler Description
It's up to the modeler to choose a flow rate that is approriate for the fenestration and interior openings within the building. Each zone with operable windows will get a zone ventilation object. The measure will first look for a celing opening to find a connection for zone a zone mixing object. If a ceiling isn't found, then it looks for a wall. Don't provide more than one ceiling paths or more than one wall path. The end result is zone ventilation object followed by a path of zone mixing objects. The fan consumption is modeled in the zone ventilation object, but no heat is brought in from the fan. There is no zone ventilation object at the end of the path of zones. In addition to schedule, the zone ventilation is controlled by a minimum outdoor temperature.

The measure was developed for use in un-conditioned models. Has not been tested in conjunction with mechanical systems.

To address an issue in OpenStudio zones with ZoneVentilation, this measure adds an exhaust fan added as well, but the CFM value for the exhaust fan is set to 0.0

## Measure Type
ModelMeasure

## Taxonomy


## Arguments


### Exhaust Flow Rate

**Name:** design_flow_rate,
**Type:** Double,
**Units:** cfm,
**Required:** true,
**Model Dependent:** false

### Fan Pressure Rise

**Name:** fan_pressure_rise,
**Type:** Double,
**Units:** Pa,
**Required:** true,
**Model Dependent:** false

### Fan Total Efficiency

**Name:** efficiency,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Choose a Ventilation Schedule.

**Name:** ventilation_schedule,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Minimum Outdoor Temperature

**Name:** min_outdoor_temp,
**Type:** Double,
**Units:** F,
**Required:** true,
**Model Dependent:** false




