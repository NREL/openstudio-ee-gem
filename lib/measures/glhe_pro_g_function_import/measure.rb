# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

# see the url below for information on how to write open_studio measures
# http://openstudio.nrel.gov/openstudio-measure-writing-guide

# see the url below for information on using life cycle cost objects in open_studio
# http://openstudio.nrel.gov/openstudio-life-cycle-examples

# see the url below for access to C++ documentation on model objects (click on "model" in the main window to view model objects)
# http://openstudio.nrel.gov/sites/openstudio.nrel.gov/files/nv_data/cpp_documentation_it/model/html/namespaces.html

# start the measure
class temp_class_0 < open_studio::Measure::model_measure
  # define the name that a user will see, this method may be deprecated as
  # the display name in pat comes from the name field in measure.xml
  def name
    return 'temp_class_0'
  end

  # define the arguments that the user will input
  def arguments(model)
    args = open_studio::Measure::os_argument_vector.new

    # make an argument for location of G Function .idf file
    g_function_path = open_studio::Measure::os_argument.make_string_argument('g_function_path', true)
    g_function_path.set_display_name('G Function File Path (C:/g_function.idf)')
    args << g_function_path

    # Find the names of all plant loops in the model that contain both a
    # district heating and district cooling object
    loop_names = open_studio::String_vector.new
    loop_handles = open_studio::String_vector.new
    model.get_plant_loops.each do |loop|
      dist_htg_name = nil
      dist_clg_name = nil
      loop.supply_components.each do |sc|
        if sc.to_district_heating.is_initialized
          dist_htg_name = sc.name.get
        elsif sc.to_district_cooling.is_initialized
          dist_clg_name = sc.name.get
        end
      end

      if dist_htg_name && dist_clg_name
        loop_names << loop.name.get
        loop_handles << loop.handle.to_s
      end
    end

    # make an argument for plant loops
    object = open_studio::Measure::os_argument.make_choice_argument('object', loop_handles, loop_names, true)
    object.set_display_name('Select plant loop to add glhx to')
    args << object

    return args
  end

  # define what happens when the measure is run
  def run(model, runner, user_arguments)
    super(model, runner, user_arguments)

    # Use the built-in error checking
    if !runner.validate_user_arguments(arguments(model), user_arguments)
      return false
    end

    # Assign the user inputs to variables
    g_function_path = runner.get_string_argument_value('g_function_path', user_arguments)
    object = runner.get_optional_workspace_object_choice_value('object', user_arguments, model)

    # Check to make sure the g function file exists
    if !File.exist?(g_function_path)
      runner.register_error("The G Function file '#{g_function_path}' could not be found.")
      return false
    end

    # Check the loop selection
    loop = nil
    if object.empty?
      handle = runner.get_double_argument_value('object', user_arguments)
      if handle.empty?
        runner.register_error('No loop was chosen.')
      else
        runner.register_error("The selected loop with handle '#{handle}' was not found in the model. It may have been removed by another measure.")
      end
      return false
    else
      if object.get.to_plant_loop.is_initialized
        loop = object.get.to_plant_loop.get
      else
        runner.register_error('Script Error - argument not showing up as loop.')
        return false
      end
    end

    # Check the location of the g_function
    if !File.exist?(g_function_path)
      runner.register_error("Coulnd't find the G Function file.  Check file path and try again: '#{g_function_path}'.")
    end

    # Remove the district heating and district cooling objects from the loop
    loop.supply_components.each do |sc|
      if sc.to_district_heating.is_initialized || sc.to_district_cooling.is_initialized
        sc.remove
        runner.register_info("Removed #{sc.name} from #{loop.name}.")
      end
    end

    # Fix up the idf file (glhe_pro exports slightly malformed idf)
    idf_text = nil
    File.open(g_function_path, 'r') { |f| idf_text = f.read }
    idf_text = idf_text.gsub('ground heat exchanger:vertical,', 'groundheatexchanger:vertical,')
    idf_text = idf_text.gsub(' :,', ',')
    File.open(g_function_path, 'w') { |f2| f2.puts idf_text }

    # Remove the setpointmanager from the supply outlet node
    # todo: this might be necessary?

    # Add a glhx to the loop
    glhx = open_studio::Model::Ground_heat_exchanger_vertical.new(model)
    glhx.set_name("glhx for #{loop.name}")
    loop.add_supply_branch_for_component(glhx)
    runner.register_info("Added glhx to #{loop.name}.")

    # Read the input parameters from the G Function .idf file
    g_function_file = open_studio::Workspace.load(g_function_path).get
    glhx_idf = g_function_file.get_objects_by_type('groundheatexchanger:vertical'.to_idd_object_type)[0]
    max_flow = glhx_idf.get_double(3).get
    num_boreholes = glhx_idf.get_int(4).get
    borehole_length = glhx_idf.get_double(5).get
    borehole_radius = glhx_idf.get_double(6).get
    ground_cond = glhx_idf.get_double(7).get
    ground_ht_cap = glhx_idf.get_double(8).get
    specific_heat = glhx_idf.get_double(9).get
    t_ground = glhx_idf.get_double(10).get
    vol_flowrate = glhx_idf.get_double(11).get
    grout_cond = glhx_idf.get_double(12).get
    pipe_cond = glhx_idf.get_double(13).get
    fluid_cond = glhx_idf.get_double(14).get
    # runner.register_info("fluid_cond = #{fluid_cond}")
    fluid_density = glhx_idf.get_double(15).get
    # runner.register_info("fluid_density = #{fluid_density}")
    fluid_visc = glhx_idf.get_double(16).get
    # runner.register_info("fluid_visc = #{fluid_visc}")
    pipe_diam = glhx_idf.get_double(17).get
    # runner.register_info("pipe_diam = #{pipe_diam}")
    u_tube_sep = glhx_idf.get_double(18).get
    # runner.register_info("u_tube_sep = #{u_tube_sep}")
    pipe_wall_thick = glhx_idf.get_double(19).get
    # runner.register_info("pipe_wall_thick = #{pipe_wall_thick}")
    max_sim = glhx_idf.get_int(20).get
    # runner.register_info("max_sim = #{max_sim}")
    num_data_pairs = glhx_idf.get_int(21).get
    # runner.register_info("num_data_pairs = #{num_data_pairs}")
    reference_ratio = borehole_radius / borehole_length

    # Set the input parameters of the glhe
    glhx.set_maximum_flow_rate(max_flow)
    glhx.set_numberof_bore_holes(num_boreholes)
    glhx.set_bore_hole_length(borehole_length)
    glhx.set_bore_hole_radius(borehole_radius)
    glhx.set_ground_thermal_conductivity(ground_cond)
    glhx.set_ground_thermal_heat_capacity(ground_ht_cap)
    glhx.set_ground_temperature(t_ground)
    glhx.set_design_flow_rate(vol_flowrate)
    glhx.set_grout_thermal_conductivity(grout_cond)
    glhx.set_pipe_thermal_conductivity(pipe_cond)
    glhx.set_pipe_out_diameter(pipe_diam)
    glhx.set_u_tube_distance(u_tube_sep)
    glhx.set_pipe_thickness(pipe_wall_thick)
    glhx.set_maximum_lengthof_simulation(max_sim)
    glhx.set_g_function_reference_ratio(reference_ratio)

    # Add the G Function pairs after removing all old ones
    glhx.remove_all_g_functions
    pair_range = 22..((76 * 2) + 22 - 2) # Pairs start on field 22
    pair_range.step(2) do |i|
      lntts = glhx_idf.get_double(i)
      gfnc = glhx_idf.get_double(i + 1)
      if lntts.empty? || gfnc.empty?
        runner.register_warning("Pair in fields #{i} and #{i + 1} missing.")
        next
      else
        lntts = lntts.get
        gfnc = gfnc.get
      end
      # runner.register_info("G Function pair:  #{lntts} : #{gfnc}")
      glhx.add_g_function(lntts, gfnc)
    end

    return true
  end
end

# this allows the measure to be use by the application
temp_class_0.new.register_with_application
