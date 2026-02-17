

###### (Automatically generated documentation)

# Operating Cost Carbon Reporting Measure

## Description
This measure calculates annual emissions and utility costs based on hourly electricity and gas consumption from EnergyPlus simulations. It applies user-specified emission factors and electricity rate structures (on-peak, off-peak, and demand charges) along with gas rates.

## Modeler Description
Reads 'Electricity:Facility' and 'NaturalGas:Facility' hourly output variables from the SQL file. Calculates total emissions using emission factors for electricity and natural gas. Calculates electricity costs using time-of-use rates and demand charges. Calculates natural gas costs using a flat rate. Reports results as measure outputs.

## Measure Type
ReportingMeasure

## Taxonomy
Reporting.QAQC

## Arguments

### State Location
State location for default emission factors and utility rates. Select 'Custom' to use manually entered values.

**Name:** state_location,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false

**Default Value:** US Average

**Choices:**
- US Average
- California
- Texas
- New York
- Florida
- Illinois
- Colorado
- Washington
- Massachusetts
- Pennsylvania
- Custom

### Electricity Emission Factor (kg CO2e/kWh)
Annual average electricity emission factor. US average ~0.42 kg CO2e/kWh. Leave 0 to use state default.

**Name:** electricity_emission_factor,
**Type:** Double,
**Units:** kg CO2e/kWh,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### Natural Gas Emission Factor (kg CO2e/therm)
Natural gas emission factor. US average ~5.3 kg CO2e/therm. Leave 0 to use default.

**Name:** gas_emission_factor,
**Type:** Double,
**Units:** kg CO2e/therm,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### On-Peak Electricity Rate ($/kWh)
Electricity rate during on-peak hours (typically weekdays 12pm-6pm). Leave 0 to use state default.

**Name:** on_peak_rate,
**Type:** Double,
**Units:** $/kWh,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### Off-Peak Electricity Rate ($/kWh)
Electricity rate during off-peak hours (nights and weekends). Leave 0 to use state default.

**Name:** off_peak_rate,
**Type:** Double,
**Units:** $/kWh,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### Monthly Demand Charge ($/kW)
Monthly demand charge based on peak demand. Leave 0 to use state default or skip if not applicable.

**Name:** demand_charge,
**Type:** Double,
**Units:** $/kW,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### Natural Gas Rate ($/therm)
Natural gas cost per therm. Leave 0 to use state default.

**Name:** gas_rate,
**Type:** Double,
**Units:** $/therm,
**Required:** true,
**Model Dependent:** false

**Default Value:** 0.0

### On-Peak Start Hour (0-23)
Hour when on-peak period starts (24-hour format)

**Name:** on_peak_start_hour,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

**Default Value:** 12

### On-Peak End Hour (0-23)
Hour when on-peak period ends (24-hour format)

**Name:** on_peak_end_hour,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

**Default Value:** 18

### Include Weekends in On-Peak
Check if weekends should be considered on-peak

**Name:** weekend_on_peak,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

**Default Value:** false

## Outputs
Annual Electricity Consumption (kWh), Annual Natural Gas Consumption (therms), Annual Electricity Emissions (kg CO2e), Annual Gas Emissions (kg CO2e), Annual Total Emissions (kg CO2e), Annual Total Emissions (metric tons CO2e), On-Peak Electricity Consumption (kWh), Off-Peak Electricity Consumption (kWh), Peak Demand (kW), Annual Electricity Cost ($), Annual Gas Cost ($), Annual Total Utility Cost ($)




