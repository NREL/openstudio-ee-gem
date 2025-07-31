# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see
  def name
    return 'Increase R-value of Insulation for Exterior Walls to a Specific Value'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make an argument insulation R-value
    r_value = open_studio::Measure::os_argument.make_double_argument('r_value', true)
    r_value.set_display_name('Insulation R-value (ft^2*h*R/Btu).')
    r_value.set_default_value(13.0)
    args << r_value

    # make bool argument to allow both increase and decrease in R value
    allow_reduction = open_studio::Measure::os_argument.make_bool_argument('allow_reduction', true)
    allow_reduction.set_display_name('Allow both increase and decrease in R-value to reach requested target?')
    allow_reduction.set_default_value(false)
    args << allow_reduction

    # make an argument for material and installation cost
    material_cost_increase_ip = open_studio::Measure::os_argument.make_double_argument('material_cost_increase_ip', true)
    material_cost_increase_ip.set_display_name('Increase in Material and Installation Costs for Construction per Area Used ($/ft^2).')
    material_cost_increase_ip.set_default_value(0.0)
    args << material_cost_increase_ip

    # make an argument for demolition cost
    one_time_retrofit_cost_ip = open_studio::Measure::os_argument.make_double_argument('one_time_retrofit_cost_ip', true)
    one_time_retrofit_cost_ip.set_display_name('One Time Retrofit Cost to Add Insulation to Construction ($/ft^2).')
    one_time_retrofit_cost_ip.set_default_value(0.0)
    args << one_time_retrofit_cost_ip

    # make an argument for duration in years until costs start
    years_until_retrofit_cost = open_studio::Measure::os_argument.make_integer_argument('years_until_retrofit_cost', true)
    years_until_retrofit_cost.set_display_name('Year to Incur One Time Retrofit Cost (whole years).')
    years_until_retrofit_cost.set_default_value(0)
    args << years_until_retrofit_cost

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # use the built-in error checking
    if !runner.validate_user_arguments(arguments(model), user_arguments)
      return false
    end

    # assign the user inputs to variables
    r_value = runner.get_double_argument_value('r_value', user_arguments)
    allow_reduction = runner.get_bool_argument_value('allow_reduction', user_arguments)
    material_cost_increase_ip = runner.get_double_argument_value('material_cost_increase_ip', user_arguments)
    one_time_retrofit_cost_ip = runner.get_double_argument_value('one_time_retrofit_cost_ip', user_arguments)
    years_until_retrofit_cost = runner.get_integer_argument_value('years_until_retrofit_cost', user_arguments)

    # set limit for minimum insulation. This is used to limit input and for inferring insulation layer in construction.
    min_expected_r_value_ip = 1 # ip units

    # check the R-value for reasonableness
    if (r_value < 0) || (r_value > 500)
      runner.register_error("The requested wall insulation R-value of #{r_value} ft^2*h*R/Btu was above the measure limit.")
      return false
    elsif r_value > 40
      runner.register_warning("The requested wall insulation R-value of #{r_value} ft^2*h*R/Btu is abnormally high.")
    elsif r_value < min_expected_r_value_ip
      runner.register_warning("The requested wall insulation R-value of #{r_value} ft^2*h*R/Btu is abnormally low.")
    end

    # check lifecycle arguments for reasonableness
    if (years_until_retrofit_cost < 0) && (years_until_retrofit_cost > 100)
      runner.register_error('Year to incur one time retrofit cost should be a non-negative integer less than or equal to 100.')
    end

    # short def to make numbers pretty (converts 4125001.25641 to 4,125,001.26 or 4,125,001). The definition be called through this measure
    # round to 0 or 2)
    neat_numbers = lambda do |number, roundto = 2|
      number.to_s.reverse.gsub(/([0-9]{3}(?=([0-9])))/, '\\1,').reverse
    end

    # helper to make it easier to do unit conversions on the fly
    unit_helper = lambda do |number, from_unit_string, to_unit_string|
      initial_string << "#{exterior_surface_construction.name} (R-#{format '%.1f', initial_conductance_ip})"
    end
    runner.register_initial_condition("The building had #{initial_string.size} exterior wall constructions: #{initial_string.sort.join(', ')}.")

    # hashes to track constructions and materials made by the measure, to avoid duplicates
    constructions_hash_old_new = {}
    constructions_hash_new_old = {} # used to get net_area of new construction and then cost objects of construction it replaced
    materials_hash = {}

    # array and counter for new constructions that are made, used for reporting final condition
    final_constructions_array = []

    # loop through all constructions and materials used on exterior walls, edit and clone
    exterior_surface_constructions.each do |exterior_surface_construction|
      construction_layers = exterior_surface_construction.layers
      max_thermal_resistance_material = ''
      max_thermal_resistance_material_index = ''
      materials_in_construction = construction_layers.map.with_index do |layer, i|
        { 'name' => layer.name.to_s,
          'index' => i,
          'nomass' => !layer.to_massless_opaque_material.empty?,
          'r_value' => layer.to_opaque_material.get.thermal_resistance,
          'mat' => layer }
      end

      no_mass_materials = materials_in_construction.select { |mat| mat['nomass'] == true }
      # measure will select the no mass material with the highest r-value as the insulation layer
      # if no mass materials are present, the measure will select the material with the highest r-value per inch
      if no_mass_materials.empty?
        thermal_resistance_per_thickness_values = materials_in_construction.map { |mat| mat['r_value'] / mat['mat'].thickness }
        target_index = thermal_resistance_per_thickness_values.index(thermal_resistance_per_thickness_values.max)
        max_mat_hash = materials_in_construction.select { |mat| mat['index'] == target_index }
        thermal_resistance_values = materials_in_construction.map { |mat| mat['r_value'] }
      else
        thermal_resistance_values = no_mass_materials.map { |mat| mat['r_value'] }
        max_mat_hash = no_mass_materials.select { |mat| mat['r_value'] >= thermal_resistance_values.max }
      end
      max_thermal_resistance_material = max_mat_hash[0]['mat']
      max_thermal_resistance_material_index = max_mat_hash[0]['index']
      max_thermal_resistance = max_thermal_resistance_material.to_opaque_material.get.thermal_resistance

      if max_thermal_resistance <= unit_helper(min_expected_r_value_ip, 'ft^2*h*R/Btu', 'm^2*K/W')
        runner.register_warning("Construction '#{exterior_surface_construction.name}' does not appear to have an insulation layer and was not altered.")
      elsif (max_thermal_resistance >= r_value_si) && !allow_reduction
        runner.register_info("The insulation layer of construction #{exterior_surface_construction.name} exceeds the requested R-Value. It was not altered.")
      else
        # clone the construction
        final_construction = exterior_surface_construction.clone(model)
        final_construction = final_construction.to_construction.get
        final_construction.set_name("#{exterior_surface_construction.name} adj ext wall insulation")
        final_constructions_array << final_construction

        # loop through lifecycle costs getting total costs under "Construction" or "Salvage" category and add to counter if occurs during year 0
        const_lc_cs = final_construction.life_cycle_costs
        cost_added = false
        const_lcc_cat_const = false
        updated_cost_si = 0
        const_lc_cs.each do |const_lcc|
          if (const_lcc.category == 'Construction') && (material_cost_increase_si != 0)
            const_lcc_cat_const = true # need this test to add proper lcc if it didn't exist to start with
            # if multiple lcc objects associated with construction only adjust the cost of one of them.
            if cost_added
              runner.register_info("More than one life_cycle_cost object with a category of Construction was associated with #{final_construction.name}. Cost was only adjusted for one of the life_cycle_cost objects.")
            else
              const_lcc.set_cost(const_lcc.cost + material_cost_increase_si)
            end
            updated_cost_si += const_lcc.cost
          end
        end

        if cost_added
          runner.register_info("Adjusting material and installation cost for #{final_construction.name} to #{neat_numbers(unit_helper(updated_cost_si, '1/m^2', '1/ft^2'))} ($/ft^2).")
        end

        # add construction object if it didnt exist to start with and a cost increase was requested
        if (const_lcc_cat_const == false) && (material_cost_increase_si != 0)
          lcc_for_uncosted_const = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_increase_insulation', final_construction, material_cost_increase_si, 'cost_per_area', 'Construction', 20, 0).get
          runner.register_info("No material or installation costs existed for #{final_construction.name}. Created a new life_cycle_cost object with a material and installation cost of #{neat_numbers(unit_helper(lcc_for_uncosted_const.cost, '1/m^2', '1/ft^2'))} ($/ft^2). Assumed capitol cost in first year, an expected life of 20 years, and no O & M costs.")
        end

        # add one time cost if requested
        if one_time_retrofit_cost_ip > 0
          one_time_retrofit_cost_si = unit_helper(one_time_retrofit_cost_ip, '1/ft^2', '1/m^2')
          lcc_retrofit_specific = open_studio::Model::Life_cycle_cost.create_life_cycle_cost('lcc_retrofit_specific', final_construction, one_time_retrofit_cost_si, 'cost_per_area', 'Construction', 0, years_until_retrofit_cost).get # using 0 for repeat period since one time cost.
          runner.register_info("Adding one time cost of #{neat_numbers(unit_helper(lcc_retrofit_specific.cost, '1/m^2', '1/ft^2'))} ($/ft^2) related to retrofit of wall insulation.")
        end

        # push to hashes
        constructions_hash_old_new[exterior_surface_construction.name.to_s] = final_construction
        constructions_hash_new_old[final_construction] = exterior_surface_construction # push the object to hash key vs. name

        # find already cloned insulation material and link to construction
        target_material = max_thermal_resistance_material
        found_material = false
        materials_hash.each do |orig, new|
          if target_material.name.to_s == orig
            new_material = new
            materials_hash[max_thermal_resistance_material.name.to_s] = new_material
            final_construction.erase_layer(max_thermal_resistance_material_index)
            final_construction.insert_layer(max_thermal_resistance_material_index, new_material)
            found_material = true
          end
        end

        # clone and edit insulation material and link to construction
        if found_material == false
          new_material = max_thermal_resistance_material.clone(model)
          new_material = new_material.to_opaque_material.get
          new_material.set_name("#{max_thermal_resistance_material.name}_r-value #{r_value} (ft^2*h*R/Btu)")
          materials_hash[max_thermal_resistance_material.name.to_s] = new_material
          final_construction.erase_layer(max_thermal_resistance_material_index)
          final_construction.insert_layer(max_thermal_resistance_material_index, new_material)
          runner.register_info("For construction'#{final_construction.name}', material'#{new_material.name}' was altered.")

          # edit insulation material
          new_material_matt = new_material.to_material
          if !new_material_matt.empty?
            starting_thickness = new_material_matt.get.thickness
            target_thickness = starting_thickness * r_value_si / thermal_resistance_values.max
            final_thickness = new_material_matt.get.set_thickness(target_thickness)
          end
          new_material_massless = new_material.to_massless_opaque_material
          if !new_material_massless.empty?
            final_thermal_resistance = new_material_massless.get.set_thermal_resistance(r_value_si)
          end
          new_material_airgap = new_material.to_air_gap
          if !new_material_airgap.empty?
            final_thermal_resistance = new_material_airgap.get.set_thermal_resistance(r_value_si)
          end
        end
      end
    end

    # loop through construction sets used in the model
    default_construction_sets = model.get_default_construction_sets
    default_construction_sets.each do |default_construction_set|
      if default_construction_set.direct_use_count > 0
        default_surface_const_set = default_construction_set.default_exterior_surface_constructions
        if !default_surface_const_set.empty?
          starting_construction = default_surface_const_set.get.wall_construction

          # creating new default construction set
          new_default_construction_set = default_construction_set.clone(model)
          new_default_construction_set = new_default_construction_set.to_default_construction_set.get
          new_default_construction_set.set_name("#{default_construction_set.name} adj ext wall insulation")

          # create new surface set and link to construction set
          new_default_surface_const_set = default_surface_const_set.get.clone(model)
          new_default_surface_const_set = new_default_surface_const_set.to_default_surface_constructions.get
          new_default_surface_const_set.set_name("#{default_surface_const_set.get.name} adj ext wall insulation")
          new_default_construction_set.set_default_exterior_surface_constructions(new_default_surface_const_set)

          # use the hash to find the proper construction and link to new_default_surface_const_set
          target_const = new_default_surface_const_set.wall_construction
          if !target_const.empty?
            target_const = target_const.get.name.to_s
            found_const_flag = false
            constructions_hash_old_new.each do |orig, new|
              if target_const == orig
                final_construction = new
                new_default_surface_const_set.set_wall_construction(final_construction)
                found_const_flag = true
              end
            end
            if found_const_flag == false # this should never happen but is just an extra test in case something goes wrong with the measure code
              runner.register_warning("Measure couldn't find the construction named '#{target_const}' in the exterior surface hash.")
            end
          end

          # swap all uses of the old construction set for the new
          construction_set_sources = default_construction_set.sources
          construction_set_sources.each do |construction_set_source|
            building_source = construction_set_source.to_building
            # if statement for each type of object than can use a default_construction_set
            if !building_source.empty?
              building_source = building_source.get
              building_source.set_default_construction_set(new_default_construction_set)
            end
            building_story_source = construction_set_source.to_building_story
            if !building_story_source.empty?
              building_story_source = building_story_source.get
              building_story_source.set_default_construction_set(new_default_construction_set)
            end
            space_type_source = construction_set_source.to_space_type
            if !space_type_source.empty?
              space_type_source = space_type_source.get
              space_type_source.set_default_construction_set(new_default_construction_set)
            end
            space_source = construction_set_source.to_space
            if !space_source.empty?
              space_source = space_source.get
              space_source.set_default_construction_set(new_default_construction_set)
            end
          end

        end
      end
    end

    # link cloned and edited constructions for surfaces with hard assigned constructions
    exterior_surfaces.each do |exterior_surface|
      if !exterior_surface.is_construction_defaulted && !exterior_surface.construction.empty?

        # use the hash to find the proper construction and link to surface
        target_const = exterior_surface.construction
        if !target_const.empty?
          target_const = target_const.get.name.to_s
          constructions_hash_old_new.each do |orig, new|
            if target_const == orig
              final_construction = new
              exterior_surface.set_construction(final_construction)
            end
          end
        end

      end
    end

    # report strings for final condition
    final_string = [] # not all exterior wall constructions, but only new ones made. If wall didn't have insulation and was not altered we don't want to show it
    affected_area_si = 0
    total_cost_of_affected_area = 0
    yr0_capital_total_costs = 0
    final_constructions_array.each do |final_construction|
      # unit conversion of wall insulation from si units (M^2*K/W) to ip units (ft^2*h*R/Btu)
      final_conductance_ip = unit_helper(1 / final_construction.thermal_conductance.to_f, 'm^2*K/W', 'ft^2*h*R/Btu')
      final_string << "#{final_construction.name} (R-#{format '%.1f', final_conductance_ip})"
      affected_area_si += final_construction.get_net_area

      # loop through lifecycle costs getting total costs under "Construction" or "Salvage" category and add to counter if occurs during year 0
      const_lc_cs = final_construction.life_cycle_costs
      const_lc_cs.each do |const_lcc|
        if ((const_lcc.category == 'Construction') || (const_lcc.category == 'Salvage')) && (const_lcc.years_from_start == 0)
          yr0_capital_total_costs += const_lcc.total_cost
        end
      end
    end

    # add not applicable test if there were exterior roof constructions but non of them were altered (already enough insulation or doesn't look like insulated wall)
    if affected_area_si == 0
      runner.register_as_not_applicable('No exterior walls were altered.')
      return true
      # affected_area_ip = affected_area_si
    else
      # ip construction area for reporting
      affected_area_ip = unit_helper(affected_area_si, 'm^2', 'ft^2')
    end

    # report final condition
    runner.register_final_condition("The existing insulation for exterior walls was set to R-#{r_value}. This was accomplished for an initial cost of #{one_time_retrofit_cost_ip} ($/sf) and an increase of #{material_cost_increase_ip} ($/sf) for construction. This was applied to #{neat_numbers(affected_area_ip, 0)} (ft^2) across #{final_string.size} exterior wall constructions: #{final_string.sort.join(', ')}.")

    return true
  end
end

# this allows the measure to be used by the application
Increase_insulation_r_value_for_exterior_walls.new.register_with_application
