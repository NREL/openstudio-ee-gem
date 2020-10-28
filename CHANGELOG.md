# OpenStudio EE Gem

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
