# frozen_string_literal: true

# *******************************************************************************
# open_studio(R), Copyright (c) Alliance for Sustainable Energy, llc.
# See also https://openstudio.net/license
# *******************************************************************************

require 'erb'

# Patch an array sum method into Ruby187
class temp_class_0
  def sum
    sum
  end
end

# start the measure
class temp_class_1 < open_studio::Measure::reporting_measure
  # define the name that a user will see, this method may be deprecated as
  # the display name in pat comes from the name field in measure.xml
  def name
    return 'temp_class_1'
  end

  # define the arguments that the user will input
  def arguments(model = nil)
    args = open_studio::Measure::os_argument_vector.new

    return args
  end

  def energy_plus_output_requests(runner, user_arguments)
    super(runner, user_arguments)

    result = open_studio::Idf_object_vector.new

    # use the built-in error checking
    unless runner.validate_user_arguments(arguments, user_arguments)
      return result
    end

    # note: these variable requests replace the functionality of glhe_pro_setup_export_loadsfor_ground_heat_exchanger_sizing measure

    result << open_studio::Idf_object.load('Output:Variable,,District Heating Water Rate,hourly;').get
    result << open_studio::Idf_object.load('Output:Variable,,District Cooling Water Rate,hourly;').get

    # get the last model
    model = runner.last_open_studio_model
    if model.empty?
      runner.register_error('Cannot find last model.')
      return false
    end
    model = model.get

    # Report the outlet node conditions for each plant loop in the model
    # Rename the outlet node so that it makes sense in the report
    outlet_node_variable_names = []
    outlet_node_variable_names << 'System Node Temperature'
    outlet_node_variable_names << 'System Node Setpoint Temperature'
    outlet_node_variable_names << 'System Node Mass Flow Rate'
    model.get_plant_loops.each do |plant_loop|
      outlet_node = plant_loop.supply_outlet_node
      outlet_node_name = "#{plant_loop.name} Supply Outlet Node"
      outlet_node.set_name(outlet_node_name)
      outlet_node_variable_names.each do |outlet_node_variable_name|
        result << open_studio::Idf_object.load("Output:Variable,#{outlet_node_name},#{outlet_node_variable_name},hourly;").get
      end
    end

    result
  end

  # define what happens when the measure is run
  def run(runner, user_arguments)
    super(runner, user_arguments)

    # use the built-in error checking
    if !runner.validate_user_arguments(arguments, user_arguments)
      return false
    end

    # Get the model and sql file
    model = runner.last_open_studio_model
    if model.empty?
      runner.register_error('Cannot find last model.')
      return false
    end
    model = model.get

    sql = runner.last_energy_plus_sql_file
    if sql.empty?
      runner.register_error('Cannot find last sql file.')
      return false
    end
    sql = sql.get
    model.set_sql_file(sql)

    # Method to translate from open_studio's time formatting
    # to Javascript time formatting
    # open_studio time
    # 2009-May-14 00:10:00   Raw string
    # Javascript time
    # 2009/07/12 12:34:56
    def to_js_time(os_time)
      js_time = os_time.to_s
      # Replace the '-' with '/'
      js_time = js_time.tr('-', '/')
      # Replace month abbreviations with numbers
      js_time = js_time.gsub('Jan', '01')
      js_time = js_time.gsub('Feb', '02')
      js_time = js_time.gsub('Mar', '03')
      js_time = js_time.gsub('Apr', '04')
      js_time = js_time.gsub('May', '05')
      js_time = js_time.gsub('Jun', '06')
      js_time = js_time.gsub('Jul', '07')
      js_time = js_time.gsub('Aug', '08')
      js_time = js_time.gsub('Sep', '09')
      js_time = js_time.gsub('Oct', '10')
      js_time = js_time.gsub('Nov', '11')
      js_time = js_time.gsub('Dec', '12')

      return js_time
    end

    # Get the weather file (as opposed to design day) run period
    ann_env_pd = nil
    sql.available_env_periods.each do |env_pd|
      env_type = sql.environment_type(env_pd)
      if !env_type.empty? && (env_type.get == 'weather_run_period'.to_environment_type)
        ann_env_pd = env_pd
      end
    end

    # Find the names of all plant loops in the model that contain both a
    # district heating and district cooling object
    loop_names = []
    model.get_plant_loops.each do |loop|
      runner.register_info("Checking '#{loop.name}' for district heating and district cooling.")
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
        loop_names << [loop.name.get, dist_htg_name, dist_clg_name]
      end
    end

    # Report any loops that were found that appear to be
    # glhe loops
    if loop_names.empty?
      runner.register_info('No loops found with both district heating and district cooling.')
    else
      runner.register_info("Loops with district heating and district cooling: #{loop_names.join(',')}.")
    end

    # todo: temp workaround to hardcode year
    iann_env_pd = sql.exec_and_return_first_int("select environment_period_index from environment_periods where Environment_name = '#{ann_env_pd}'").get
    start_year = sql.exec_and_return_first_int("select min(year) from Time where Environment_period_index =#{iann_env_pd}").get

    # Define the start and end day for each month
    months = {}
    months[1] = [open_studio::Date.new(open_studio::Month_of_year.new('January'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('January'), 31, start_year)]

    months[2] = [open_studio::Date.new(open_studio::Month_of_year.new('February'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('February'), 28, start_year)]

    months[3] = [open_studio::Date.new(open_studio::Month_of_year.new('March'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('March'), 31, start_year)]

    months[4] = [open_studio::Date.new(open_studio::Month_of_year.new('April'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('April'), 30, start_year)]

    months[5] = [open_studio::Date.new(open_studio::Month_of_year.new('May'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('May'), 31, start_year)]

    months[6] = [open_studio::Date.new(open_studio::Month_of_year.new('June'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('June'), 30, start_year)]

    months[7] = [open_studio::Date.new(open_studio::Month_of_year.new('July'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('July'), 31, start_year)]

    months[8] = [open_studio::Date.new(open_studio::Month_of_year.new('August'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('August'), 31, start_year)]

    months[9] = [open_studio::Date.new(open_studio::Month_of_year.new('September'), 1, start_year),
                 open_studio::Date.new(open_studio::Month_of_year.new('September'), 30, start_year)]

    months[10] = [open_studio::Date.new(open_studio::Month_of_year.new('October'), 1, start_year),
                  open_studio::Date.new(open_studio::Month_of_year.new('October'), 31, start_year)]

    months[11] = [open_studio::Date.new(open_studio::Month_of_year.new('November'), 1, start_year),
                  open_studio::Date.new(open_studio::Month_of_year.new('November'), 30, start_year)]

    months[12] = [open_studio::Date.new(open_studio::Month_of_year.new('December'), 1, start_year),
                  open_studio::Date.new(open_studio::Month_of_year.new('December'), 31, start_year)]

    # Define the start and end time for each day
    start_time = open_studio::Time.new(0, 0, 0, 0)
    end_time = open_studio::Time.new(0, 24, 0, 0)

    # Get the heating and cooling loads for each loop
    # in hourly resolution for reporting, monthly resolution for glhe_pro
    annual_graph_data = []
    monthly_table_data = []
    loop_names.each do |loop_name, dist_htg_name, dist_clg_name|
      runner.register_info("Getting monthly load data for #{loop_name}.")

      # Get the hourly annual heating load in Watts
      ann_hourly_htg_w = sql.time_series(ann_env_pd, 'Hourly', 'District Heating Water Rate', dist_htg_name.upcase)
      if ann_hourly_htg_w.empty?
        runner.register_warning("No hourly heating data found for '#{dist_htg_name}' on '#{loop_name}'")
        next
      else
        ann_hourly_htg_w = ann_hourly_htg_w.get
      end

      # Get the hourly annual cooling load in Watts
      ann_hourly_clg_w = sql.time_series(ann_env_pd, 'Hourly', 'District Cooling Water Rate', dist_clg_name.upcase)
      if ann_hourly_clg_w.empty?
        runner.register_warning("No hourly cooling data found for '#{dist_clg_name}' on '#{loop_name}'")
        next
      else
        ann_hourly_clg_w = ann_hourly_clg_w.get
      end

      # Convert time stamp format to be more readable
      js_date_times = []
      ann_hourly_htg_w.date_times.each do |date_time|
        js_date_times << to_js_time(date_time)
      end

      # Convert the hourly heating load from W to Btu/hr
      ann_hourly_htg_btu_per_hr_vals = []
      ann_hourly_htg_w_vals = ann_hourly_htg_w.values
      for i in 0..(ann_hourly_htg_w_vals.size - 1)
        htg_w = ann_hourly_htg_w_vals[i]
        htg_btu_per_hr = Open_studio.convert(htg_w.to_f, 'W', 'k_btu/hr').get
        ann_hourly_htg_btu_per_hr_vals << htg_btu_per_hr
      end

      # Convert the hourly cooling load from W to Btu/hr
      ann_hourly_clg_btu_per_hr_vals = []
      ann_hourly_clg_w_vals = ann_hourly_clg_w.values
      for i in 0..(ann_hourly_clg_w_vals.size - 1)
        clg_w = ann_hourly_clg_w_vals[i]
        clg_btu_per_hr = Open_studio.convert(clg_w.to_f, 'W', 'k_btu/hr').get
        ann_hourly_clg_btu_per_hr_vals << clg_btu_per_hr
      end

      # Create an array of arrays [timestamp, htg_btu_per_hr, clg_btu_per_hr]
      hourly_vals = js_date_times.zip(ann_hourly_htg_btu_per_hr_vals, ann_hourly_clg_btu_per_hr_vals)

      # Add the hourly load data to json for the report.html
      graph = {}
      graph['title'] = "#{loop_name} - Hourly Heating and Cooling Power"
      graph['xaxislabel'] = 'Time'
      graph['yaxislabel'] = 'Power (k_btu/hr)'
      graph['labels'] = ['Date', 'Heating', 'Cooling']
      graph['colors'] = ['#ff5050', '#0066ff']
      graph['timeseries'] = hourly_vals

      # This measure requires ruby 2.0.0 to create the json for the report graph
      if ruby_version >= '2.0.0'
        annual_graph_data << graph
      end

      # Save out hourly load data to csv
      File.open("./Annual Hourly Loads for #{loop_name}.csv", 'w') do |file|
        file.puts "Annual Hourly Loads for #{loop_name}"
        file.puts 'Date/Time,Heating (k_btu/hr),Cooling (k_btu/hr)'
        hourly_vals.each do |timestamp, htg_btu_per_hr, clg_btu_per_hr|
          file.puts "#{timestamp},#{htg_btu_per_hr},#{clg_btu_per_hr}"
        end
      end

      # Find monthly loads for glhe_pro
      mon_htg_cons = []
      mon_clg_cons = []
      mon_htg_dmd = []
      mon_clg_dmd = []

      # Loop through months and find total heating and cooling energy
      # and peak heating and cooling rate for each month
      # and store in arrays defined above
      (1..12).each do |i|
        # Create the start and end date/time for the month
        start_date = months[i][0]
        end_date = months[i][1]
        start_t = open_studio::Date_time.new(start_date, start_time)
        end_t = open_studio::Date_time.new(end_date, end_time)
        runner.register_info("Month #{i}: #{start_t} to #{end_t}.")

        # Determine the monthly heating information
        mon_hourly_htg_w = ann_hourly_htg_w.values(start_t, end_t)
        # if mon_hourly_htg_w.empty?
        #  runner.register_warning("No heating data for #{start_t} to #{end_t}, check the run period of your simulation.")
        #  next
        # end
        mon_hourly_htg_w_arr = []
        for i in 0..(mon_hourly_htg_w.size - 1)
          mon_hourly_htg_w_arr << mon_hourly_htg_w[i].to_f
        end
        mon_htg_cons_w_hr = mon_hourly_htg_w_arr.sum
        mon_htg_cons_k_btu = Open_studio.convert(mon_htg_cons_w_hr.to_f, 'W*hr', 'k_btu').get
        mon_htg_peak_dmd_w = mon_hourly_htg_w_arr.max
        mon_htg_peak_dmd_btu_hr = Open_studio.convert(mon_htg_peak_dmd_w.to_f, 'W', 'Btu/hr').get

        # Determine the monthly cooling information
        mon_hourly_clg_w = ann_hourly_clg_w.values(start_t, end_t)
        # if mon_hourly_clg_w.empty?
        #  runner.register_warning("No cooling data for #{start_t} to #{end_t}, check the run period of your simulation.")
        #  next
        # end
        mon_hourly_clg_w_arr = []
        for i in 0..(mon_hourly_clg_w.size - 1)
          mon_hourly_clg_w_arr << mon_hourly_clg_w[i].to_f
        end
        mon_clg_cons_w_hr = mon_hourly_clg_w_arr.sum
        mon_clg_cons_k_btu = Open_studio.convert(mon_clg_cons_w_hr.to_f, 'W*hr', 'k_btu').get
        mon_clg_peak_dmd_w = mon_hourly_clg_w_arr.max
        mon_clg_peak_dmd_btu_hr = Open_studio.convert(mon_clg_peak_dmd_w.to_f, 'W', 'Btu/hr').get

        # Report out the monthly values and add to the array
        runner.register_info("htg: #{mon_htg_cons_k_btu} k_btu, clg: #{mon_clg_cons_k_btu} k_btu, htg peak: #{mon_htg_peak_dmd_btu_hr} Btu/hr, clg peak: #{mon_clg_peak_dmd_btu_hr} Btu/hr.")
        mon_htg_cons << Open_studio.to_neat_string(mon_htg_cons_k_btu, 0, false).to_i
        mon_clg_cons << Open_studio.to_neat_string(mon_clg_cons_k_btu, 0, false).to_i
        mon_htg_dmd << Open_studio.to_neat_string(mon_htg_peak_dmd_btu_hr, 0, false).to_i
        mon_clg_dmd << Open_studio.to_neat_string(mon_clg_peak_dmd_btu_hr, 0, false).to_i
      end

      # Log the annual numbers
      ann_htg_cons = mon_htg_cons.sum
      ann_htg_cons = Open_studio.to_neat_string(ann_htg_cons, 0, false).to_i

      ann_clg_cons = mon_clg_cons.sum
      ann_clg_cons = Open_studio.to_neat_string(ann_clg_cons, 0, false).to_i

      ann_htg_dmd = mon_htg_dmd.max
      ann_htg_dmd = Open_studio.to_neat_string(ann_htg_dmd, 0, false).to_i

      ann_clg_dmd = mon_clg_dmd.max
      ann_clg_dmd = Open_studio.to_neat_string(ann_clg_dmd, 0, false).to_i

      runner.register_info('Annual energy and peak demand.')
      runner.register_info("htg: #{ann_clg_cons} k_btu, clg: #{ann_clg_cons} k_btu, htg peak: #{ann_htg_dmd} Btu/hr, clg peak: #{ann_clg_dmd} Btu/hr.")

      # Save the monthly load data for import into glhe_pro (.gt1)
      File.open("./Monthly Loads for #{loop_name}.gt1", 'w') do |file|
        file.puts 'Clg/Htg Consumption (k_btu),' \
                  "#{mon_clg_cons.join(',')}," \
                  "#{ann_clg_cons}," \
                  "#{mon_htg_cons.join(',')}," \
                  "#{ann_htg_cons}"
        file.puts 'Clg/Htg Demand (Btuh),' \
                  "#{mon_clg_dmd.join(',')}," \
                  "#{ann_clg_dmd}," \
                  "#{mon_htg_dmd.join(',')}," \
                  "#{ann_htg_dmd}"
      end

      monthly_table_data = []
    end

    # Convert the graph data to json
    # This measure requires ruby 2.0.0 to create the json for the report graph
    if ruby_version >= '2.0.0'
      require 'json'
      annual_graph_data = annual_graph_data.to_json
    else
      runner.register_info("This Measure needs Ruby 2.0.0 to generate timeseries graphs on the report.  This does not impact the glhe_pro export at all.  You have Ruby #{ruby_version}.  open_studio 1.4.2 and higher user Ruby 2.0.0.")
    end

    # Read in the html report template
    html_in_path = "#{File.dirname(__file__)}/resources/report.html.in"
    if File.exist?(html_in_path)
      html_in_path = html_in_path
    else
      html_in_path = "#{File.dirname(__file__)}/report.html.in"
    end
    html_in = ''
    File.open(html_in_path, 'r') do |file|
      html_in = file.read
    end

    # Configure html template with variable values
    renderer = erb.new(html_in)
    html_out = renderer.result(binding)

    # Write out the html template
    html_out_path = './report.html'
    File.open(html_out_path, 'w') do |file|
      file << html_out
      # Make sure html file is written to the disk one way or the other
      begin
        file.fsync
      rescue standard_error
        file.flush
      end
    end

    # Close the sql file
    sql.close

    return true
  end
end

# this allows the measure to be use by the application
temp_class_1.new.register_with_application
