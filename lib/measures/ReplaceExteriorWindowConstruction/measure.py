# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************
import openstudio
import typing
import re
from pint import UnitRegistry

# start the measure
class ReplaceExteriorWindowConstruction(openstudio.measure.ModelMeasure):
  # define the name that a user will see
  def name(self):
    return "Replace Exterior Window Constructions with a Different Construction from the Model."

  # human readable description
  def description(self):
    return "Replace existing windows with different windows to change thermal or lighting performance.  Window technology has improved drastically over the years, and double or triple-pane high performance windows currently on the market can cut down on envelope loads greatly.  Window frames with thermal breaks reduce the considerable energy that can transfer through thermally unbroken frames.  High performance windows typically also come with low-emissivity (low?e) glass to keep radiant heat on the same side of the glass from where the heat originated. This means that during the cooling months a low-e glass would tend to keep radiant heat from the sun on the outside of the window, which would keep the inside of a building cooler. Conversely, during heating months low-e glass helps keep radiant heat from inside the building on the inside, which would keep the inside of a building warmer.  Life cycle cost values may be added for the new window applied by the measure."

  # human readable description of modeling approach
  def modeler_description(self):
    return "Replace fixed and/or operable exterior window constructions with another construction in the model.  Skylights (windows in roofs vs. walls) will not be altered. Windows in surfaces with `Adiabatic` boundary conditions are not specifically assumed to be interior or exterior. As a result constructions used on windows in `Adiabatic` surfaces will not be altered. `Material, installation, demolition, and O and M costs` can be added to the applied window construction. Optionally any prior costs associated with construction can be removed. <br/> <br/> For costs added as part of a design alternatives `Years Until Costs Start?` is typically `0`. For a new construction scenario `Demolition Costs Occur During Initial Construction?` is `false`. For retrofit scenario `Demolition Costs Occur During Initial Construction?` is `true`. `O and M cost and frequency` can be whatever is appropriate for the component."

  # define the arguments that the user will input
  def arguments(self, model: typing.Optional[openstudio.model.Model] = None):
    args = openstudio.measure.OSArgumentVector()

    # make a choice argument for constructions that are appropriate for windows
    construction_handles = openstudio.makeStringVector.new()
    construction_display_names = openstudio.makeStringVector.new()

    # putting space types and names into hash
    construction_args = model.getConstructions(model)
    construction_args_hash = {}
    for construction_arg in construction_args:
      construction_args_hash[construction_arg.name] = construction_arg

    # looping through sorted hash of constructions
    for key, value in sorted(construction_args_hash.items()):
    # Only include if construction is a valid fenestration construction
      if value.isFenestration:
        construction_handles.append(str(value.handle))
        construction_display_names.append(key)

    # make a choice argument for fixed windows
    construction = openstudio.measure.OSArgument.makeChoiceArgument("construction", construction_handles, construction_display_names, True)
    construction.setDisplayName("Pick a Window Construction From the Model to Replace Existing Window Constructions.")
    args.append(construction)

    # make a bool argument for fixed windows
    change_fixed_windows = openstudio.measure.OSArgument.makeBoolArgument("change_fixed_windows", True)
    change_fixed_windows.setDisplayName("Change Fixed Windows?")
    change_fixed_windows.setDefaultValue(True)
    args.append(change_fixed_windows)

    # make a bool argument for operable windows
    change_operable_windows = openstudio.measure.OSArgument.makeBoolArgument("change_operable_windows", True)
    change_operable_windows.setDisplayName("Change Operable Windows?")
    change_operable_windows.setDefaultValue(True)
    args.append(change_operable_windows)

    # make an argument to remove existing costs
    remove_costs = openstudio.measure.OSArgument.makeBoolArgument("remove_costs", True)
    remove_costs.setDisplayName("Remove Existing Costs?")
    remove_costs.setDefaultValue(True)
    args.append(remove_costs)

    # make an argument for material and installation cost
    material_cost_ip = openstudio.measure.OSArgument.makeDoubleArgument("material_cost_ip", True)
    material_cost_ip.setDisplayName("Material and Installation Costs for Construction per Area Used ($/ft^2).")
    material_cost_ip.setDefaultValue(0.0)
    args.append(material_cost_ip)

    # make an argument for demolition cost
    demolition_cost_ip = openstudio.measure.OSArgument.makeDoubleArgument("demolition_cost_ip", True)
    demolition_cost_ip.setDisplayName("Demolition Costs for Construction per Area Used ($/ft^2).")
    demolition_cost_ip.setDefaultValue(0.0)
    args.append(demolition_cost_ip)

    # make an argument for duration in years until costs start
    years_until_costs_start = openstudio.measure.OSArgument.makeIntegerArgument("years_until_costs_start", True)
    years_until_costs_start.setDisplayName("Years Until Costs Start (whole years).")
    years_until_costs_start.setDefaultValue(0)
    args.append(years_until_costs_start)

    # make an argument to determine if demolition costs should be included in initial construction
    demo_cost_initial_const = openstudio.measure.OSArgument.makeBoolArgument("demo_cost_initial_const", True)
    demo_cost_initial_const.setDisplayName("Demolition Costs Occur During Initial Construction?")
    demo_cost_initial_const.setDefaultValue(False)
    args.append(demo_cost_initial_const)

    # make an argument for expected life
    expected_life = openstudio.measure.OSArgument.makeIntegerArgument('expected_life', True)
    expected_life.setDisplayName("Expected Life (whole years).")
    expected_life.setDefaultValue(20)
    args.append(expected_life)

    # make an argument for o&m cost
    om_cost_ip = openstudio.measure.OSArgument.makeDoubleArgument("om_cost_ip", True)
    om_cost_ip.setDisplayName("O & M Costs for Construction per Area Used ($/ft^2).")
    om_cost_ip.setDefaultValue(0.0)
    args.append(om_cost_ip)

    # make an argument for o&m frequency
    om_frequency = openstudio.measure.OSArgument.makeIntegerArgument("om_frequency", True)
    om_frequency.setDisplayName("O & M Frequency (whole years).")
    om_frequency.setDefaultValue(1)
    args.append(om_frequency)

    return args

  # define what happens when the measure is run
  def run(self, model: openstudio.model.Model, runner: openstudio.measure.OSRunner, user_arguments: openstudio.measure.OSArgumentMap):
    """Execute the measure."""
    super().run(model, runner, user_arguments)  # Required

    # use the built-in error checking
    if not runner.validateUserArguments(self.arguments(model), user_arguments):
      return False

    # assign the user inputs to variables
    construction = runner.getOptionalWorkspaceObjectChoiceValue("construction", user_arguments, model)
    change_fixed_windows = runner.getBoolArgumentValue("change_fixed_windows", user_arguments)
    change_operable_windows = runner.getBoolArgumentValue("change_operable_windows", user_arguments)
    remove_costs = runner.getBoolArgumentValue("remove_costs", user_arguments)
    material_cost_ip = runner.getDoubleArgumentValue("material_cost_ip", user_arguments)
    demolition_cost_ip = runner.getDoubleArgumentValue("demolition_cost_ip", user_arguments)
    years_until_costs_start = runner.getIntegerArgumentValue("years_until_costs_start", user_arguments)
    demo_cost_initial_const = runner.getBoolArgumentValue("demo_cost_initial_const", user_arguments)
    expected_life = runner.getIntegerArgumentValue("expected_life", user_arguments)
    om_cost_ip = runner.getDoubleArgumentValue("om_cost_ip", user_arguments)
    om_frequency = runner.getIntegerArgumentValue("om_frequency", user_arguments)

    # check the construction for reasonableness
    if not construction:
      handle = runner.getStringArgumentValue("construction", user_arguments)
      if not handle:
        runner.registerError('No construction was chosen.')
      else:
        runner.registerError(
            f"The selected construction with handle '{handle}' was not found in the model. "
            "It may have been removed by another measure."
        )
      return False
    else:
      if construction.get().to_Construction(): # Assuming get() returns a valid object
        construction = construction.get.to_Construction().get()
      else:
        runner.registerError("Script Error - argument not showing up as construction.")
        return False

    # set flags and counters to use later
    costs_requested = False
    costs_removed = False

    # Later will add hard sized $ cost to this each time I swap a construction surfaces.
    # If demo_cost_initial_const is true then will be applied once in the lifecycle. Future replacements use the demo cost of the new construction.
    demo_costs_of_baseline_objects = 0

    # check costs for reasonableness
    if abs(material_cost_ip) + abs(demolition_cost_ip) + abs(om_cost_ip) == 0:
      runner.registerInfo(f"No costs were requested for {construction.name}.")
    else:
      costs_requested = True

    # check lifecycle arguments for reasonableness
    if years_until_costs_start < 0 or years_until_costs_start > expected_life:
      runner.registerError("Years until costs start should be a non-negative integer less than Expected Life.")

    if expected_life < 1 or expected_life > 100:
      runner.registerError("Choose an integer greater than 0 and less than or equal to 100 for Expected Life.")

    if om_frequency < 1:
      runner.registerError("Choose an integer greater than 0 for O & M Frequency.")

    # short def to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure
    def neat_numbers(number, roundto = 2): # round to 0 or 2
      if roundto == 2:
        number = f"{number:.2f}"
      else:
        number = round(number)
      
      # Regex to add commas
      return re.sub(r'(?<=\d)(?=(\d{3})+(?!\d))', ',', str(number))

    # clone construction to get proper area for measure economics, in case it is used elsewhere in the building
    new_object = construction.clone(model)
    if new_object.to_Construction(): # Assuming it returns a valid object
      construction = new_object.to_Construction().get()

    # remove any component cost line items associated with the construction.
    if construction.lifeCycleCosts() & remove_costs == True:
      runner.registerInfo(f"Removing existing lifecycle cost objects associated with {construction.name}")
      removed_costs = construction.removeLifeCycleCosts()
      costs_removed = bool(removed_costs)

    removed_costs = construction.removeLifeCycleCosts()
    costs_removed = bool(removed_costs)

    # add lifeCycleCost objects if there is a non-zero value in one of the cost arguments
    if costs_requested == True:

      ureg = UnitRegistry()
      # converting doubles to si values from ip
      material_cost_si = (material_cost_ip * ureg("1/ft^2")).to("1/m^2").magnitude
      demolition_cost_si = (demolition_cost_ip * ureg("1/ft^2")).to("1/m^2").magnitude
      om_cost_si = (om_cost_ip * ureg("1/ft^2")).to("1/m^2").magnitude

      # Adding new cost items
      lcc_mat = openstudio.model.LifeCycleCost.createLifeCycleCost(
      f"LCC_Mat-{construction.name}", construction, material_cost_si, 
      "CostPerArea", "Construction", expected_life, years_until_costs_start)

      # If demo_cost_initial_const is true, later will add one-time demo costs using removed baseline objects.
      # Cost will occur at year specified by years_until_costs_start
      lcc_demo = openstudio.model.LifeCycleCost.createLifeCycleCost(
      f"LCC_Demo-{construction.name}", construction, demolition_cost_si, 
      "CostPerArea", "Salvage", expected_life, years_until_costs_start + expected_life)

      lcc_om = openstudio.model.LifeCycleCost.createLifeCycleCost(
      f"LCC_OM-{construction.name}", construction, om_cost_si, 
      "CostPerArea", "Maintenance", om_frequency, 0)

    # loop through sub surfaces
    starting_exterior_windows_constructions = []
    sub_surfaces_to_change = []
    sub_surfaces = model.getSubSurfaces()

    for sub_surface in sub_surfaces:
      if (sub_surface.outsideBoundaryCondition() == "Outdoors") & (sub_surface.subSurfaceType() == "FixedWindow") & (change_fixed_windows == True):
        sub_surfaces_to_change.append(sub_surface)
        sub_surface_const = sub_surface.construction()
        if sub_surface_const != None and sub_surface_const:
          if starting_exterior_windows_constructions:
            starting_exterior_windows_constructions.append(sub_surface_const.get().nameString())
          else:
            starting_exterior_windows_constructions.append(sub_surface_const.get().nameString())

      elif (sub_surface.outsideBoundaryCondition() == 'Outdoors') & (sub_surface.subSurfaceType() == 'OperableWindow') & (change_operable_windows == True):
        sub_surfaces_to_change.append(sub_surface)
        sub_surface_const = sub_surface.construction()
        if sub_surface_const != None and sub_surface_const:
          if starting_exterior_windows_constructions:
            starting_exterior_windows_constructions.append(sub_surface_const.get().nameString())
          else:
            starting_exterior_windows_constructions.append(sub_surface_const.get().nameString())

    # create array of constructions for sub_surfaces to change, before construction is replaced
    constructions_to_change = []
    for sub_surface in sub_surfaces_to_change:
      sub_surface_const = sub_surface.construction()
      if sub_surface_const != None and sub_surface_const:
        constructions_to_change.append(sub_surface_const.get())

    # getting cost of all existing windows before constructions are swapped. This will create demo cost if all windows were removed. Will adjust later for windows left in place
    for construction_to_change in constructions_to_change:
      # loop through lifecycle costs getting total costs under "Salvage" category
      demo_LCCs = construction_to_change.lifeCycleCosts()
      for demo_LCC in demo_LCCs:
        if demo_LCC.category() == 'Salvage':
          demo_costs_of_baseline_objects += demo_LCC.totalCost()

    if (change_fixed_windows == False) & (change_operable_windows == False):
      runner.registerAsNotApplicable("Fixed and operable windows are both set not to change.")
      return True # no need to waste time with the measure if we know it isn't applicable
    elif sub_surfaces_to_change:
      runner.registerAsNotApplicable("There are no appropriate exterior windows to change in the model.")
      return True # no need to waste time with the measure if we know it isn't applicable

    # report initial condition
    # Report initial condition
    runner.registerInitialCondition(
      f"The building had {len(set(starting_exterior_windows_constructions))} window constructions: "
      f"{', '.join(sorted(set(starting_exterior_windows_constructions)))}.")

    # loop through construction sets used in the model
    default_construction_sets = model.getDefaultConstructionSets()
    for default_construction_set in default_construction_sets:
      if default_construction_set.directUseCount() > 0:
        default_sub_surface_const_set = default_construction_set.defaultExteriorSubSurfaceConstructions()
        if default_sub_surface_const_set != None and default_sub_surface_const_set:
          starting_construction = default_sub_surface_const_set.get().fixedWindowConstruction()

          # creating new default construction set
          new_default_construction_set = default_construction_set.clone(model)
          new_default_construction_set = new_default_construction_set.to_DefaultConstructionSet().get()

          # create new sub_surface set
          new_default_sub_surface_const_set = default_sub_surface_const_set.get.clone(model)
          new_default_sub_surface_const_set = new_default_sub_surface_const_set.to_DefaultSubSurfaceConstructions().get()

          if change_fixed_windows == True:
            # assign selected construction sub_surface set
            new_default_sub_surface_const_set.setFixedWindowConstruction(construction)

          if change_operable_windows == True:
            # assign selected construction sub_surface set
            new_default_sub_surface_const_set.setOperableWindowConstruction(construction)

          # link new subset to new set
          new_default_construction_set.setDefaultExteriorSubSurfaceConstructions(new_default_sub_surface_const_set)

          # swap all uses of the old construction set for the new
          construction_set_sources = default_construction_set.sources()
          for construction_set_source in construction_set_sources:
            building_source = construction_set_source.to_Building()
            if building_source != None and building_source:
              building_source = building_source.get()
              building_source.setDefaultConstructionSet(new_default_construction_set)
              continue
            # add SpaceType, BuildingStory, and Space if statements

    # loop through appropriate sub surfaces and change where there is a hard assigned construction
    for sub_surface in sub_surfaces_to_change:
      if sub_surface.isConstructionDefaulted() != None and sub_surface.isConstructionDefaulted():
        sub_surface.setConstruction(construction)

    # loop through lifecycle costs getting total costs under "Salvage" category
    for construction_to_change in constructions_to_change:
      demo_LCCs = construction_to_change.lifeCycleCosts
      for demo_LCC in demo_LCCs:
        if demo_LCC.category == "Salvage":
          demo_costs_of_baseline_objects += demo_LCC.totalCost * -1 # this is to adjust demo cost down for original windows that were not changed

    # loop through lifecycle costs getting total costs under "Construction" or "Salvage" category and add to counter if occurs during year 0
    const_LCCs = construction.lifeCycleCosts()
    yr0_capital_totalCosts = 0
    for const_LCC in const_LCCs:
      if const_LCC.category() == "Construction" or const_LCC.category() == "Salvage":
        if const_LCC.yearsFromStart == 0:
          yr0_capital_totalCosts += const_LCC.totalCost()

    # add one time demo cost of removed windows if appropriate
    if demo_cost_initial_const == True:
      building = model.getBuilding()
      lcc_baseline_demo = openstudio.model.LifeCycleCost.createLifeCycleCost(
      'LCC_baseline_demo', 
      building, 
      demo_costs_of_baseline_objects, 
      'CostPerEach', 
      'Salvage', 
      0, 
      years_until_costs_start
      ).get()  # Using 0 for repeat period since it's a one-time cost.

      runner.registerInfo(
      f"Adding one time cost of ${neat_numbers(lcc_baseline_demo.totalCost, 0)} related to demolition of baseline objects.")

      # if demo occurs on year 0 then add to initial capital cost counter
      if lcc_baseline_demo.yearsFromStart == 0:
        yr0_capital_totalCosts += lcc_baseline_demo.totalCost()

    # ip construction area for reporting
    const_area_ip = openstudio.convert(
      openstudio.Quantity(construction.getNetArea(), openstudio.createUnit('m^2').get()),
      openstudio.createUnit('ft^2').get()).get().value()
    # get names from constructions to change
    const_names = []
    if constructions_to_change != None and constructions_to_change:
      for const_name in sorted(set(constructions_to_change)):
        const_names.append(const_name.name)

    # need to format better. At first I did each do, but seems initial condition only reports the first one.
    runner.registerFinalCondition(
      f"{neat_numbers(const_area_ip, 0)} (ft²) of existing windows of the types: {', '.join(const_names)} were replaced by new {construction.name} windows."
      f"Initial capital costs associated with the new windows are ${neat_numbers(yr0_capital_totalCosts, 0)}.")

    return True

# this allows the measure to be used by the application
ReplaceExteriorWindowConstruction().registerWithApplication()
