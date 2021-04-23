# OpenStudio EE Gem

## Version 0.4.0

* Support Ruby ~> 2.7
* Support for OpenStudio 3.2 (upgrade to extension gem 0.4.2 and standards gem 0.2.13)

## Version 0.3.2

* Bump openstudio-extension-gem version to 0.3.2 to support updated workflow-gem

## Version 0.3.1

* Adds the following to lib/measures:
    * IncreaseInsulationRValueForExteriorWallsByPercentage
    * IncreaseInsulationRValueForRoofsByPercentage

## Version 0.3.0

* Support for OpenStudio 3.1
    * Update OpenStudio Standards to 0.2.12
    * Update OpenStudio Extension gem to 0.3.1

## Version 0.2.1

* Update openstudio-extension to 0.2.5
* Adds the following to lib/measures:
    * ImproveFanTotalEfficiencyByPercentage
    * ReplaceFanTotalEfficiency
    * add_apszhp_to_each_zone
    * add_energy_recovery_ventilator
    * improve_simple_glazing_by_percentage
    * reduce_water_use_by_percentage
    * replace_hvac_with_gshp_and_doas
    * replace_simple_glazing
    * set_boiler_thermal_efficiency
    * set_water_heater_efficiency_heat_lossand_peak_water_flow_rate
    * tenant_star_internal_loads
    * vr_fwith_doas

## Version 0.2.0

* Support for OpenStudio 3.0
    * Upgrade Bundler to 2.1.x
    * Restrict to Ruby ~> 2.5.0   
    * Removed simplecov forked dependency 
* Upgraded openstudio-extension to 0.2.2
    * Updated measure tester to 0.2.0 (removes need for github gem in downstream projects)
* Upgraded openstudio-standards to 0.2.11
* Exclude measure tests from being released with the gem (reduces the size of the installed gem significantly)

## Version 0.1.0

* Initial release of the energy efficiency measures gem.
