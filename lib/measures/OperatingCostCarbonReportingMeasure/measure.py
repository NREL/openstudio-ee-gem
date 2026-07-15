"""
OpenStudio Measure: Utility Cost and Emissions Report
Calculates annual emissions and utility costs from simulation results.
Reads configuration from CSV files in resources folder.
"""

import openstudio
from typing import Dict, Optional, List, Tuple
import json
from pathlib import Path
import csv


class OperatingCostCarbonReport(openstudio.measure.ReportingMeasure):
    """
    This measure reads hourly electricity and gas consumption from simulation results,
    calculates emissions and utility costs based on CSV configuration files.
    """

    def name(self):
        """Measure name for display in the OpenStudio GUI."""
        return "Operating Cost Carbon Reporting Measure"

    def description(self):
        """Measure description."""
        return (
            "This measure calculates annual emissions and utility costs based on "
            "hourly electricity and gas consumption from EnergyPlus simulations. "
            "Configuration is read from CSV files in the resources folder: "
            "input.csv (main config), emissions.csv (emission factors by Balancing Authority), "
            "eia_gas_price_2024.csv (gas costs by state and building type from EIA 2024 data), "
            "and eia_elec_avg_price_table_4.csv (electricity rates by city and building type from EIA 2024 data)."
        )

    def modeler_description(self):
        """Technical description for modelers."""
        return (
            "Reads 'Electricity:Facility' and 'NaturalGas:Facility' hourly output variables "
            "from the SQL file. Reads configuration from resources/input.csv. "
            "If emission factor is not specified, looks up value from resources/emissions.csv "
            "using Balancing Authority Code. Gas costs are looked up from resources/eia_gas_price_2024.csv "
            "based on the state (mapped from weather file city) and building type category (Residential, "
            "Commercial, or Industrial). If Industrial rate is unavailable, falls back to Commercial. "
            "Electricity rates are looked up from resources/eia_elec_avg_price_table_4.csv based on "
            "the city extracted from the weather file path and building type category. "
            "If no match is found, uses 'United States' national average. "
            "Gas emissions calculated as 50.3 kg CO2/GJ. Demand charge is 20 $/kW times max monthly kW."
        )

    def arguments(self, model=None):
        """Define measure arguments - None needed, reads from CSV files."""
        args = openstudio.measure.OSArgumentVector()
        return args

    def load_input_config(self, runner) -> Optional[Dict]:
        """
        Load configuration from resources/input.csv.
        
        Returns:
            Dictionary with configuration values or None if file not found
        """
        measure_dir = Path(__file__).parent.absolute()
        input_file = measure_dir / "resources" / "input.csv"
        
        if not input_file.exists():
            runner.registerError(f"Configuration file not found: {input_file}")
            return None
        
        config = {}
        try:
            with open(input_file, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
                reader = csv.DictReader(f)
                for row in reader:
                    variable = row.get('Variable', '').strip()
                    value = row.get('Value', '').strip()
                    
                    if variable and value:  # Only add if both variable and value exist
                        config[variable] = value
            
            runner.registerInfo(f"Loaded configuration from {input_file}")
            return config
        except Exception as e:
            runner.registerError(f"Error reading input.csv: {str(e)}")
            return None

    def load_emissions_data(self, runner) -> Optional[Dict]:
        """
        Load emission factors from resources/emissions.csv.
        
        Returns:
            Dictionary mapping Balancing Authority Code to emission rate (lb/MWh)
        """
        measure_dir = Path(__file__).parent.absolute()
        emissions_file = measure_dir / "resources" / "emissions.csv"
        
        if not emissions_file.exists():
            runner.registerWarning(f"Emissions file not found: {emissions_file}")
            return {}
        
        emissions_data = {}
        try:
            with open(emissions_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ba_code = row.get('Balancing Authority Code', '').strip()
                    emission_rate_str = row.get('BA annual CO2 equivalent total output emission rate (lb/MWh)', '0').strip()

                    # Skip shorthand header row and empty rows
                    if not ba_code or ba_code.upper() == 'BACODE':
                        continue

                    # Remove commas from numbers like "1,457.392"
                    emission_rate_str = emission_rate_str.replace(',', '')

                    try:
                        emission_rate = float(emission_rate_str)
                        emissions_data[ba_code] = emission_rate
                    except ValueError:
                        continue
            
            runner.registerInfo(f"Loaded {len(emissions_data)} emission factors from {emissions_file}")
            return emissions_data
        except Exception as e:
            runner.registerError(f"Error reading emissions.csv: {str(e)}")
            return {}

    def load_gas_costs(self, runner) -> Optional[Dict]:
        """
        Load gas costs from resources/gas_cost.csv.
        
        Returns:
            Dictionary mapping State to gas cost ($/1000ft3)
        """
        measure_dir = Path(__file__).parent.absolute()
        gas_file = measure_dir / "resources" / "gas_cost.csv"
        
        if not gas_file.exists():
            runner.registerWarning(f"Gas cost file not found: {gas_file}")
            return {}
        
        gas_costs = {}
        try:
            with open(gas_file, 'r') as f:
                # Skip header row
                next(f)
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        state = row[0].strip()
                        try:
                            cost = float(row[1].strip())
                            gas_costs[state] = cost
                        except ValueError:
                            continue
            
            runner.registerInfo(f"Loaded {len(gas_costs)} gas cost entries from {gas_file}")
            return gas_costs
        except Exception as e:
            runner.registerError(f"Error reading gas_cost.csv: {str(e)}")
            return {}

    def load_eia_gas_prices_2024(self, runner) -> Optional[Dict]:
        """
        Load gas prices from resources/eia_gas_price_2024.csv.
        
        Returns:
            Dictionary mapping (State, building_category) to gas price ($/MMBtu)
        """
        measure_dir = Path(__file__).parent.absolute()
        gas_file = measure_dir / "resources" / "eia_gas_price_2024.csv"
        
        if not gas_file.exists():
            runner.registerWarning(f"Gas price file not found: {gas_file}")
            return {}
        
        gas_prices = {}
        try:
            with open(gas_file, 'r', encoding='latin-1') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    state = row.get('State', '').strip()
                    if not state:
                        continue
                    
                    # Load prices for each building category
                    for category in ['Residential', 'Commercial', 'Industrial']:
                        price_str = row.get(category, '').strip()
                        if price_str and price_str not in ['', '.', '�']:
                            try:
                                price = float(price_str)
                                gas_prices[(state, category)] = price
                            except ValueError:
                                # Skip invalid values
                                continue
                        # If Industrial is empty, leave it out (will fallback to Commercial)
            
            runner.registerInfo(f"Loaded {len(gas_prices)} gas price entries from {gas_file}")
            return gas_prices
        except Exception as e:
            runner.registerError(f"Error reading eia_gas_price_2024.csv: {str(e)}")
            return {}

    def get_state_from_city(self, city: Optional[str]) -> Optional[str]:
        """
        Map city folder name to state name.
        Based on weather files in lib/parametric_run/weather.
        
        Args:
            city: City name from weather file (e.g., 'Atlanta', 'Chicago')
            
        Returns:
            State name or None if city not in mapping
        """
        if not city:
            return None
        
        # Hardcoded mapping based on lib/parametric_run/weather folders
        city_to_state = {
            'Amarillo': 'Texas',
            'Atlanta': 'Georgia',
            'Baltimore': 'Maryland',
            'Buffalo': 'New York',
            'Chicago': 'Illinois',
            'Denver': 'Colorado',
            'Duluth': 'Minnesota',
            'ElPaso': 'Texas',
            'Fairbanks': 'Alaska',
            'Helena': 'Montana',
            'Houston': 'Texas',
            'Miami': 'Florida',
            'Minneapolis': 'Minnesota',
            'Phoenix': 'Arizona',
            'PortAngeles': 'Washington',
            'Portland': 'Oregon',
            'SanFrancisco': 'California',
        }
        
        return city_to_state.get(city)

    def load_electricity_rates(self, runner) -> Optional[Dict]:
        """
        Load electricity rates from resources/eia_elec_avg_price_table_4.csv.
        
        Returns:
            Dictionary mapping (city, building_category) to rate in $/kWh
        """
        measure_dir = Path(__file__).parent.absolute()
        elec_file = measure_dir / "resources" / "eia_elec_avg_price_table_4.csv"
        
        if not elec_file.exists():
            runner.registerWarning(f"Electricity rates file not found: {elec_file}")
            return {}
        
        electricity_rates = {}
        try:
            with open(elec_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    state = row.get('State', '').strip()
                    weather_file = row.get('weather_file', '').strip()
                    
                    # Skip if no weather_file mapping or header rows
                    if not weather_file or not state:
                        continue
                    
                    # Extract rates for each building category (in cents/kWh)
                    for category in ['Residential', 'Commercial', 'Industrial']:
                        rate_str = row.get(category, '').strip()
                        if rate_str and rate_str != '.':
                            try:
                                # Convert from cents/kWh to $/kWh
                                rate_cents = float(rate_str)
                                rate_dollars = rate_cents / 100.0
                                electricity_rates[(weather_file, category)] = rate_dollars
                            except ValueError:
                                continue
            
            runner.registerInfo(f"Loaded {len(electricity_rates)} electricity rate entries from {elec_file}")
            return electricity_rates
        except Exception as e:
            runner.registerError(f"Error reading eia_elec_avg_price_table_4.csv: {str(e)}")
            return {}

    def get_weather_file_city(self, model, runner) -> Optional[str]:
        """
        Extract city name from the weather file path in the model.
        
        Returns:
            City name (e.g., 'Atlanta', 'Chicago') or None if not found
        """
        try:
            weather_file = model.getWeatherFile()
            if weather_file.url().is_initialized():
                url = weather_file.url().get()
                # Extract city from path like '.../weather/Atlanta/USA_GA_Atlanta...'
                path_parts = url.replace('\\', '/').split('/')
                for i, part in enumerate(path_parts):
                    if part == 'weather' and i + 1 < len(path_parts):
                        city = path_parts[i + 1]
                        runner.registerInfo(f"Detected city from weather file: {city}")
                        return city
        except Exception as e:
            runner.registerWarning(f"Could not extract city from weather file: {e}")
        
        return None

    def get_building_type_category(self, model, runner) -> str:
        """
        Map building type to electricity rate category (Residential/Commercial/Industrial).
        
        Returns:
            'Residential', 'Commercial', or 'Industrial'
        """
        try:
            # Try to get building type from model's Building object
            building = model.getBuilding()
            building_type = ""
            
            # Method 1: Check additional properties
            building_props = building.additionalProperties()
            if building_props.hasFeature("building_type"):
                building_type = str(building_props.getFeatureAsString("building_type").get())
                runner.registerInfo(f"Detected building type from AdditionalProperties: {building_type}")
            
            # Method 2: Extract from Building name (DOE prototypes use names like "-Warehouse-ASHRAE...")
            if not building_type:
                building_name = building.name().get() if building.name().is_initialized() else ""
                if building_name:
                    # Extract building type from name pattern: "-BuildingType-Climate..."
                    import re
                    match = re.search(r'-(\w+)-', building_name)
                    if match:
                        building_type = match.group(1)
                        runner.registerInfo(f"Detected building type from Building name: {building_type}")
            
            # Method 3: Try standardsInformation (may not work in all API versions)
            if not building_type:
                try:
                    standards_info = building.standardsInformation()
                    building_type_opt = standards_info.standardsBuildingType()
                    if building_type_opt.is_initialized():
                        building_type = building_type_opt.get()
                        runner.registerInfo(f"Detected building type from standardsInformation: {building_type}")
                except AttributeError:
                    pass  # standardsInformation() not available in this API version
            
            building_type_lower = building_type.lower()
            
            # Map building types to rate categories
            if 'warehouse' in building_type_lower or 'industrial' in building_type_lower:
                return 'Industrial'
            elif 'residential' in building_type_lower or 'apartment' in building_type_lower or 'singlefamily' in building_type_lower or 'multifamily' in building_type_lower:
                return 'Residential'
            else:
                # Default to Commercial for offices, hotels, retail, schools, etc.
                return 'Commercial'
                
        except Exception as e:
            runner.registerWarning(f"Could not determine building type: {e}")
            # Default to Commercial
            return 'Commercial'

    def is_on_peak(self, day_of_week: int, hour: int, 
                   on_peak_start: int, on_peak_end: int) -> bool:
        """
        Determine if a given hour is on-peak.
        Weekends are always off-peak.
        
        Args:
            day_of_week: 1=Sunday, 2=Monday, ..., 7=Saturday
            hour: Hour of day (0-23)
            on_peak_start: On-peak start hour
            on_peak_end: On-peak end hour
            
        Returns:
            True if on-peak, False otherwise
        """
        # Check if weekend (Sunday=1, Saturday=7)
        is_weekend = (day_of_week == 1 or day_of_week == 7)
        
        if is_weekend:
            return False
        
        # Check if hour is in on-peak range
        if on_peak_start < on_peak_end:
            return on_peak_start <= hour < on_peak_end
        else:
            # Handle case where on-peak crosses midnight
            return hour >= on_peak_start or hour < on_peak_end

    def get_timeseries_data(self, sql_file, variable_name: str) -> Optional[List[float]]:
        """
        Extract hourly timeseries data from SQL file.
        
        Args:
            sql_file: OpenStudio SQL file object
            variable_name: Name of the output variable
            
        Returns:
            List of hourly values in J, or None if not found
        """
        # Get the environment period (annual run)
        env_periods = sql_file.availableEnvPeriods()
        if not env_periods or len(env_periods) == 0:
            return None
        
        env_period = env_periods[0]
        
        # Get available timeseries
        timeseries = sql_file.availableTimeSeries()
        
        # Find the specific variable
        ts_name = None
        for ts in timeseries:
            if variable_name.upper() in ts.upper():
                ts_name = ts
                break
        
        if not ts_name:
            return None
        
        # Get reporting frequency key
        reporting_frequencies = sql_file.availableReportingFrequencies(env_period)
        hourly_key = None
        for freq in reporting_frequencies:
            if "Hourly" in freq:
                hourly_key = freq
                break
        
        if not hourly_key:
            return None
        
        # Get the timeseries data
        ts_data = sql_file.timeSeries(env_period, hourly_key, ts_name)
        
        # Check if ts_data is valid (handles both Optional and direct return types)
        if not ts_data:
            return None
        
        # Handle different return types (tuple vs Optional)
        if isinstance(ts_data, tuple):
            if len(ts_data) == 0:
                return None
            ts_obj = ts_data[0]
        elif hasattr(ts_data, 'is_initialized'):
            if not ts_data.is_initialized():
                return None
            ts_obj = ts_data.get()
        else:
            ts_obj = ts_data
        
        # Get values from timeseries
        try:
            ts_values = ts_obj.values()
        except AttributeError:
            # Try alternative method
            try:
                ts_values = ts_obj
            except:
                return None
        
        # Convert to list of floats (values are in J for energy)
        try:
            values = [float(ts_values[i]) for i in range(len(ts_values))]
        except:
            return None
        
        return values
        
        return values

    def get_datetime_info(self, sql_file) -> Optional[List[Tuple[int, int]]]:
        """
        Get day of week and hour for each hourly timestep.
        
        Returns:
            List of tuples (day_of_week, hour) where day_of_week: 1=Sun, 7=Sat
        """
        env_periods = sql_file.availableEnvPeriods()
        if not env_periods or len(env_periods) == 0:
            return None
        
        env_period = env_periods[0]
        
        # Get a timeseries to extract datetime info
        timeseries = sql_file.availableTimeSeries()
        if not timeseries:
            return None
        
        reporting_frequencies = sql_file.availableReportingFrequencies(env_period)
        hourly_key = None
        for freq in reporting_frequencies:
            if "Hourly" in freq:
                hourly_key = freq
                break
        
        if not hourly_key:
            return None
        
        ts_data = sql_file.timeSeries(env_period, hourly_key, timeseries[0])
        
        # Handle different return types
        if not ts_data:
            return None
        
        if isinstance(ts_data, tuple):
            if len(ts_data) == 0:
                return None
            ts = ts_data[0]
        elif hasattr(ts_data, 'is_initialized'):
            if not ts_data.is_initialized():
                return None
            ts = ts_data.get()
        else:
            ts = ts_data
        
        date_times = ts.dateTimes()
        
        datetime_info = []
        for dt in date_times:
            day_of_week = dt.date().dayOfWeek().value()  # 0=Sun, 6=Sat
            hour = dt.time().hours()
            # Convert to 1=Sun, 7=Sat convention
            datetime_info.append((day_of_week + 1, hour))
        
        return datetime_info

    def run(self, runner, user_arguments):
        """Main execution method."""
        super().run(runner, user_arguments)

        # No arguments to validate since we read from CSV files

        # ========================================================================
        # LOAD CONFIGURATION FROM CSV FILES
        # ========================================================================
        config = self.load_input_config(runner)
        if not config:
            runner.registerError("Failed to load configuration or configuration is empty")
            return False
        
        runner.registerInfo(f"Config loaded: {len(config)} entries")
        
        emissions_data = self.load_emissions_data(runner)
        if not emissions_data:
            runner.registerWarning("Could not load emissions data, will use default emission factor")
            emissions_data = {}
        
        runner.registerInfo(f"Emissions data loaded: {len(emissions_data)} entries")
        
        # Load gas prices from EIA 2024 data
        gas_prices = self.load_eia_gas_prices_2024(runner)
        if not gas_prices:
            runner.registerWarning("Could not load gas prices from EIA 2024 data")
            gas_prices = {}
        
        runner.registerInfo(f"Gas prices loaded: {len(gas_prices)} entries")
        
        # Load electricity rates from EIA data
        electricity_rates = self.load_electricity_rates(runner)
        if not electricity_rates:
            runner.registerWarning("Could not load electricity rates, will use default rates from input.csv")
            electricity_rates = {}
        
        runner.registerInfo(f"Electricity rates loaded: {len(electricity_rates)} entries")
        
        # Get model to extract weather file and building type
        model_opt = runner.lastOpenStudioModel()
        if not model_opt.is_initialized():
            runner.registerError("Cannot retrieve OpenStudio model")
            return False
        
        model = model_opt.get()
        
        # Extract city from weather file and building category
        city = self.get_weather_file_city(model, runner)
        building_category = self.get_building_type_category(model, runner)
        
        # Extract configuration values (defaults from input.csv)
        ba_code = config.get('Balancing Authority', 'CISO').strip()
        default_on_peak_rate = float(config.get('Electricity - cost on peak', '0.12'))
        default_off_peak_rate = float(config.get('Electricity - cost off peak', '0.10'))
        on_peak_start = int(config.get('Electricity - peak hour start', '16'))
        on_peak_end = int(config.get('Electricity - peak hour end', '20'))
        state = config.get('State', 'National Average').strip()
        
        # Try to get electricity rate from EIA data based on city and building category
        on_peak_rate = default_on_peak_rate
        off_peak_rate = default_off_peak_rate
        
        if city and building_category and (city, building_category) in electricity_rates:
            avg_rate = electricity_rates[(city, building_category)]
            on_peak_rate = avg_rate
            off_peak_rate = avg_rate
            runner.registerInfo(
                f"Using EIA electricity rate for {city}, {building_category}: ${avg_rate:.4f}/kWh"
            )
        else:
            if city:
                runner.registerWarning(
                    f"No electricity rate found for city='{city}', category='{building_category}'. "
                    f"Using default rates from input.csv"
                )
            else:
                runner.registerWarning(
                    f"Could not determine city from weather file. Using default rates from input.csv"
                )
        
        # Fixed values per requirements
        demand_charge = 20.0  # $/kW
        gas_emission_kg_per_gj = 50.3  # kg CO2/GJ (fixed for natural gas)
        
        # Look up electricity emission factor by Balancing Authority
        elec_emission_lb_per_mwh = emissions_data.get(ba_code, 0.0)
        
        # Convert lb/MWh to kg/kWh
        # 1 lb = 0.453592 kg, 1 MWh = 1000 kWh
        elec_emission = (elec_emission_lb_per_mwh * 0.453592) / 1000.0
        
        if elec_emission == 0.0:
            runner.registerWarning(f"No emission factor found for BA: {ba_code}, using default 0.5 kg/kWh")
            elec_emission = 0.5
        
        # Look up gas price by state and building category
        # First, determine state from city
        gas_state = self.get_state_from_city(city)
        if not gas_state:
            gas_state = 'United States'
            runner.registerInfo(f"City '{city}' not mapped to state, using United States national average")
        
        # Look up gas price with fallback logic
        gas_rate_per_mmbtu = None
        
        # Try (state, building_category)
        if (gas_state, building_category) in gas_prices:
            gas_rate_per_mmbtu = gas_prices[(gas_state, building_category)]
        # If Industrial not found or empty, fallback to Commercial for same state
        elif building_category == 'Industrial' and (gas_state, 'Commercial') in gas_prices:
            gas_rate_per_mmbtu = gas_prices[(gas_state, 'Commercial')]
            runner.registerInfo(f"Industrial gas rate not available for {gas_state}, using Commercial rate")
        # Final fallback to United States
        elif ('United States', building_category) in gas_prices:
            gas_rate_per_mmbtu = gas_prices[('United States', building_category)]
            runner.registerWarning(f"No gas price found for {gas_state}/{building_category}, using US average")
        
        if gas_rate_per_mmbtu is None or gas_rate_per_mmbtu == 0.0:
            runner.registerWarning(f"No gas price found, using default $10/MMBtu")
            gas_rate_per_mmbtu = 10.0
        
        # Convert gas rate from $/MMBtu to $/GJ
        # 1 MMBtu = 1.055056 GJ
        gas_rate_per_gj = gas_rate_per_mmbtu / 1.055056
        
        runner.registerInfo(f"Configuration loaded:")
        runner.registerInfo(f"  Balancing Authority: {ba_code}")
        runner.registerInfo(f"  Electricity emission factor: {elec_emission:.6f} kg CO2e/kWh")
        runner.registerInfo(f"  Gas emission factor: {gas_emission_kg_per_gj} kg CO2e/GJ")
        runner.registerInfo(f"  On-peak rate: ${on_peak_rate:.3f}/kWh ({on_peak_start}:00-{on_peak_end}:00)")
        runner.registerInfo(f"  Off-peak rate: ${off_peak_rate:.3f}/kWh")
        runner.registerInfo(f"  Demand charge: ${demand_charge:.2f}/kW")
        runner.registerInfo(f"  Gas state: {gas_state}, Building category: {building_category}")
        runner.registerInfo(f"  Gas rate: ${gas_rate_per_gj:.3f}/GJ (${gas_rate_per_mmbtu:.2f}/MMBtu)")

        # Get the SQL file
        sql_file = runner.lastEnergyPlusSqlFile()
        if sql_file.empty():
            runner.registerError("Cannot find last EnergyPlus SQL file.")
            return False

        sql_file = sql_file.get()

        # Get hourly electricity consumption (J)
        runner.registerInfo("Retrieving hourly electricity consumption...")
        elec_values = self.get_timeseries_data(sql_file, "Electricity:Facility")
        
        if not elec_values:
            runner.registerWarning("Could not retrieve electricity timeseries data.")
            elec_values = [0.0]

        # Get hourly gas consumption (J)
        runner.registerInfo("Retrieving hourly natural gas consumption...")
        gas_values = self.get_timeseries_data(sql_file, "NaturalGas:Facility")
        
        if not gas_values:
            runner.registerInfo("No natural gas consumption found.")
            gas_values = [0.0] * len(elec_values)

        # Ensure same length
        if len(elec_values) != len(gas_values):
            runner.registerWarning(
                f"Electricity and gas timeseries have different lengths "
                f"({len(elec_values)} vs {len(gas_values)}). Using minimum length."
            )
            min_length = min(len(elec_values), len(gas_values))
            elec_values = elec_values[:min_length]
            gas_values = gas_values[:min_length]

        # Get datetime information
        datetime_info = self.get_datetime_info(sql_file)
        if not datetime_info or len(datetime_info) != len(elec_values):
            runner.registerWarning(
                "Could not retrieve datetime info, assuming all hours are off-peak weekdays."
            )
            datetime_info = [(2, 12)] * len(elec_values)  # Monday noon as default

        # Conversion factors
        J_TO_KWH = 2.77778e-7  # J to kWh
        J_TO_GJ = 1.0e-9  # J to GJ

        # Calculate total consumption
        total_elec_j = sum(elec_values)
        total_gas_j = sum(gas_values)
        
        total_elec_kwh = total_elec_j * J_TO_KWH
        total_gas_gj = total_gas_j * J_TO_GJ

        runner.registerInfo(f"Annual electricity: {total_elec_kwh:.2f} kWh")
        runner.registerInfo(f"Annual natural gas: {total_gas_gj:.2f} GJ")

        # ========================================================================
        # EMISSIONS CALCULATION
        # ========================================================================
        elec_emissions_kg = total_elec_kwh * elec_emission
        gas_emissions_kg = total_gas_gj * gas_emission_kg_per_gj
        total_emissions_kg = elec_emissions_kg + gas_emissions_kg
        total_emissions_mt = total_emissions_kg / 1000.0

        runner.registerInfo(f"Electricity emissions: {elec_emissions_kg:.2f} kg CO2e")
        runner.registerInfo(f"Gas emissions: {gas_emissions_kg:.2f} kg CO2e")
        runner.registerInfo(f"Total emissions: {total_emissions_mt:.2f} metric tons CO2e")

        # ========================================================================
        # ELECTRICITY COST CALCULATION
        # ========================================================================
        on_peak_kwh = 0.0
        off_peak_kwh = 0.0
        monthly_peak_kw = [0.0] * 12  # Track peak demand by month

        for i, (elec_j, (day_of_week, hour)) in enumerate(zip(elec_values, datetime_info)):
            elec_kw = (elec_j * J_TO_KWH)  # Average kW for the hour
            elec_kwh_hour = elec_j * J_TO_KWH
            
            # Determine on-peak vs off-peak (weekends are always off-peak)
            if self.is_on_peak(day_of_week, hour, on_peak_start, on_peak_end):
                on_peak_kwh += elec_kwh_hour
            else:
                off_peak_kwh += elec_kwh_hour
            
            # Update monthly peak demand (simple month estimation based on 8760 hours)
            # This is approximate - for precise monthly tracking, would need actual month from datetime
            estimated_month = min(int(i / 730) + 1, 12)  # ~730 hours per month
            if elec_kw > monthly_peak_kw[estimated_month - 1]:
                monthly_peak_kw[estimated_month - 1] = elec_kw

        # Calculate electricity costs
        on_peak_cost = on_peak_kwh * on_peak_rate
        off_peak_cost = off_peak_kwh * off_peak_rate
        demand_cost = sum(monthly_peak_kw) * demand_charge
        total_elec_cost = on_peak_cost + off_peak_cost + demand_cost

        runner.registerInfo(f"On-peak consumption: {on_peak_kwh:.2f} kWh @ ${on_peak_rate:.3f}/kWh = ${on_peak_cost:.2f}")
        runner.registerInfo(f"Off-peak consumption: {off_peak_kwh:.2f} kWh @ ${off_peak_rate:.3f}/k Wh = ${off_peak_cost:.2f}")
        runner.registerInfo(f"Demand charges: {sum(monthly_peak_kw):.2f} kW @ ${demand_charge:.2f}/kW = ${demand_cost:.2f}")
        runner.registerInfo(f"Total electricity cost: ${total_elec_cost:.2f}")

        # ========================================================================
        # GAS COST CALCULATION
        # ========================================================================
        total_gas_cost = total_gas_gj * gas_rate_per_gj
        runner.registerInfo(f"Natural gas cost: {total_gas_gj:.2f} GJ @ ${gas_rate_per_gj:.3f}/GJ = ${total_gas_cost:.2f}")

        # ========================================================================
        # TOTAL COSTS
        # ========================================================================
        total_utility_cost = total_elec_cost + total_gas_cost

        # ========================================================================
        # REGISTER OUTPUTS
        # ========================================================================
        runner.registerValue("annual_electricity_kwh", total_elec_kwh)
        runner.registerValue("annual_gas_gj", total_gas_gj)
        runner.registerValue("annual_electricity_emissions_kg", elec_emissions_kg)
        runner.registerValue("annual_gas_emissions_kg", gas_emissions_kg)
        runner.registerValue("annual_total_emissions_kg", total_emissions_kg)
        runner.registerValue("annual_total_emissions_mt", total_emissions_mt)
        runner.registerValue("on_peak_electricity_kwh", on_peak_kwh)
        runner.registerValue("off_peak_electricity_kwh", off_peak_kwh)
        runner.registerValue("peak_demand_kw", max(monthly_peak_kw) if monthly_peak_kw else 0.0)
        runner.registerValue("annual_electricity_cost", total_elec_cost)
        runner.registerValue("annual_gas_cost", total_gas_cost)
        runner.registerValue("annual_total_utility_cost", total_utility_cost)

        # ========================================================================
        # ATTACH ADDITIONAL PROPERTIES TO MODEL
        # ========================================================================
        # Get the model from the runner
        model_opt = runner.lastOpenStudioModel()
        if model_opt.is_initialized():
            model = model_opt.get()
            
            # Attach results as additional properties to the Site object
            # (separate from Building AdditionalProperties used by envelope measures)
            site = model.getSite()
            site_props = site.additionalProperties()
            site_props.setFeature("measure_name", self.name())
            site_props.setFeature("annual_electricity_cost_usd", total_elec_cost)
            site_props.setFeature("annual_gas_cost_usd", total_gas_cost)
            site_props.setFeature("annual_electricity_operating_emissions_kg_co2e", elec_emissions_kg)
            site_props.setFeature("annual_gas_operating_emissions_kg_co2e", gas_emissions_kg)
            
            runner.registerInfo("Attached utility cost and emissions data as AdditionalProperties to Site object.")
        else:
            runner.registerWarning("Could not retrieve model to attach AdditionalProperties.")

        runner.registerFinalCondition(
            f"Annual emissions: {total_emissions_mt:.2f} MT CO2e | "
            f"Annual utility cost: ${total_utility_cost:.2f}"
        )

        return True


# Register measure for OpenStudio
OperatingCostCarbonReport().registerWithApplication()