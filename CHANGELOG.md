# OpenStudio(R) EE Gem

## Version 0.12.0
* Support for OpenStudio 3.10 (upgrade to standards gem 0.8.2, extension gem 0.9.1)
* todo add log after finalize bug fixes for this release

## Version 0.11.1
* Update additional dependencies for OpenStudio 3.9

## Version 0.11.0
* Support for OpenStudio 3.9 (upgrade to standards gem 0.7.0, extension gem 0.8.1)

## Version 0.10.0
* Support for OpenStudio 3.8 (upgrade to standards gem 0.6.0, extension gem 0.8.0)
* Support Ruby 3.2.2

## Version 0.9.0
* Support for OpenStudio 3.7 (upgrade to standards gem 0.5.0, extension gem 0.7.0)
* Fix fuel type for GLHEProExportLoadsforGroundHeatExchangerSizing
* Relax UH for test for test in nzehvac measure

## Version 0.8.0
* Support for OpenStudio 3.6 (upgrade to standards gem 0.4.0, extension gem 0.6.1)

## Version 0.7.0
* Support for OpenStudio 3.5 (upgrade to standards gem 0.3.0, extension gem 0.6.0)

## Version 0.6.0
* Support for OpenStudio 3.4 (upgrade to standards gem 0.2.16, no extension gem upgrade)

## Version 0.5.0
* Support for OpenStudio 3.3 (upgrade to extension gem 0.5.1 and standards gem 0.2.15)
* Fixed [#9]( https://github.com/NREL/openstudio-ee-gem/issues/9 ), nze_hvac is failing in 3.1
* Fixed [#32]( https://github.com/NREL/openstudio-ee-gem/pull/32 ), adding compatibility matrix and contribution policy

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
