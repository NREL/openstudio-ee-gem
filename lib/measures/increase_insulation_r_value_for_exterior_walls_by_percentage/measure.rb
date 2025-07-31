# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# start the measure
class temp_class_0 < open_studio::Ruleset::model_user_script
  # define the name that a user will see
  def name
    return 'Increase R-value of Insulation for Exterior Walls By a Specified Percentage'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Ruleset::os_argument_vector.new

    # make an argument insulation R-value
    r_value = open_studio::Ruleset::os_argument.make_double_argument('r_value', true)
    r_value.set_display_name('Percentage Increase of R-value for Exterior Wall Insulation.')
    r_value.set_default_value(30.0)
    args << r_value

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

    # set limit for minimum insulation. This is used to limit input and for inferring insulation layer in construction.
    min_expected_r_value_ip = 1 # ip units

    # check the R-value for reasonableness
    if r_value < -100
      runner.register_error('Percentage increase less than -100% is not valid.')
      return false
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
      counter = 0
      thermal_resistance_values = []

      # loop through construction layers and infer insulation layer/material
      construction_layers.each do |construction_layer|
        construction_layer_r_value = construction_layer.to_opaque_material.get.thermal_resistance
        if !thermal_resistance_values.empty? && (construction_layer_r_value > thermal_resistance_values.max)
          max_thermal_resistance_material = construction_layer
          max_thermal_resistance_material_index = counter
        end
        thermal_resistance_values << construction_layer_r_value
        counter += 1
      end

      if thermal_resistance_values.max <= unit_helper(min_expected_r_value_ip, 'ft^2*h*R/Btu', 'm^2*K/W')
        runner.register_warning("Construction '#{exterior_surface_construction.name}' does not appear to have an insulation layer and was not altered.")
      else
        # clone the construction
        final_construction = exterior_surface_construction.clone(model)
        final_construction = final_construction.to_construction.get
        final_construction.set_name("#{exterior_surface_construction.name} adj exterior wall insulation")
        final_constructions_array << final_construction

        # add construction object if it didnt exist to start with

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
          new_material.set_name("#{max_thermal_resistance_material.name}_r-value #{r_value}% increase")
          materials_hash[max_thermal_resistance_material.name.to_s] = new_material
          final_construction.erase_layer(max_thermal_resistance_material_index)
          final_construction.insert_layer(max_thermal_resistance_material_index, new_material)
          runner.register_info("For construction'#{final_construction.name}', material'#{new_material.name}' was altered.")

          # edit insulation material
          new_material_matt = new_material.to_material
          if !new_material_matt.empty?
            starting_thickness = new_material_matt.get.thickness
            target_thickness = starting_thickness * (1 + (r_value / 100))
            final_thickness = new_material_matt.get.set_thickness(target_thickness)
          end
          new_material_massless = new_material.to_massless_opaque_material
          if !new_material_massless.empty?
            starting_thermal_resistance = new_material_massless.get.thermal_resistance
            final_thermal_resistance = new_material_massless.get.set_thermal_resistance(starting_thermal_resistance * (1 + (r_value / 100)))
          end
          new_material_airgap = new_material.to_air_gap
          if !new_material_airgap.empty?
            starting_thermal_resistance = new_material_airgap.get.thermal_resistance
            final_thermal_resistance = new_material_airgap.get.set_thermal_resistance(starting_thermal_resistance * (1 + (r_value / 100)))
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
          new_default_construction_set.set_name("#{default_construction_set.name} adj exterior wall insulation")

          # create new surface set and link to construction set
          new_default_surface_const_set = default_surface_const_set.get.clone(model)
          new_default_surface_const_set = new_default_surface_const_set.to_default_surface_constructions.get
          new_default_surface_const_set.set_name("#{default_surface_const_set.get.name} adj exterior wall insulation")
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
    final_string = [] # not all exterior surface constructions, but only new ones made. If exterior surface didn't have insulation and was not altered we don't want to show it
    affected_area_si = 0
    final_constructions_array.each do |final_construction|
      # unit conversion of exterior surface insulation from si units (M^2*K/W) to ip units (ft^2*h*R/Btu)
      final_conductance_ip = unit_helper(1 / final_construction.thermal_conductance.to_f, 'm^2*K/W', 'ft^2*h*R/Btu')
      final_string << "#{final_construction.name} (R-#{format '%.1f', final_conductance_ip})"
      affected_area_si += final_construction.get_net_area
    end

    # add not applicable test if there were exterior surface constructions but none of them were altered (already enough insulation or doesn't look like insulated wall)
    if affected_area_si == 0
      runner.register_as_not_applicable('No exterior walls were altered.')
      return true
      # affected_area_ip = affected_area_si
    else
      # ip construction area for reporting
      affected_area_ip = unit_helper(affected_area_si, 'm^2', 'ft^2')
    end

    # report final condition
    runner.register_final_condition("The existing insulation for exterior walls was increased by #{r_value}%. This was applied to #{neat_numbers(affected_area_ip, 0)} (ft^2) across #{final_string.size} exterior wall constructions: #{final_string.sort.join(', ')}.")

    return true
  end
end

# this allows the measure to be used by the application
Increase_insulation_r_value_for_exterior_walls_by_percentage.new.register_with_application
