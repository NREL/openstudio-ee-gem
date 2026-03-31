# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************


import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import openstudio
import numpy as np
from resources.EC3_lookup import *
import pprint as pp

class IncreaseInsulationRValueForExteriorWalls(openstudio.measure.ModelMeasure):
    def name(self):
        return "Increase R-value of Insulation for Exterior Walls to a Specific Value"

    def description(self):
        return "Increases the R-value of insulation layers in exterior walls to meet a specified target."

    def modeler_description(self):
        return ("This measure modifies insulation materials in exterior wall constructions to reach "
                "a user-defined R-value target by adding supplemental insulation layers. The measure "
                "identifies the existing insulation layer with the highest R-value in each exterior wall "
                "construction and calculates the additional thickness needed to meet the target. "
                "It supports various insulation types including blown materials (cellulose, fiberglass, "
                "mineral wool), foam boards (polyiso, EPS, XPS, GPS), and batts (fiberglass, mineral wool, "
                "pure wool). The measure fetches Environmental Product Declaration (EPD) data from the EC3 "
                "database to calculate embodied carbon (GWP) for the added insulation over a specified "
                "analysis period. Outlier removal using the IQR method is applied to GWP values to improve "
                "accuracy. Results including embodied carbon, material quantities, and GWP metrics are "
                "stored as additional properties on each modified construction for downstream reporting.")

    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]

    @staticmethod
    def insulation_material_types():
        return [
            "Blown Cellulose",
            "Blown Fiberglass",
            "Blown Mineral Wool",
            "Polyiso Insulation Foam Board",
            "Graphite Polystyrene (GPS) Foam Board",
            "Expanded Polystyrene (EPS) Foam Board",
            "Extruded Polystyrene (XPS) Foam Board",
            "Mineral Wool Heavy Density Blanket",
            "Mineral Wool Light Density Blanket",
            "Fiberglass Batts",
            "Pure Wool Batts"
        ]  
    
    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        r_value = openstudio.measure.OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Target Insulation R-value (ft²·h·°F/Btu)")
        r_value.setDefaultValue(13.0)
        args.append(r_value)

        # material_cost = openstudio.measure.OSArgument.makeDoubleArgument("material_cost_increase_ip", True)
        # material_cost.setDisplayName("Material and Installation Cost Increase ($/ft²)")
        # material_cost.setDefaultValue(0.0)
        # args.append(material_cost)

        # one_time_cost = openstudio.measure.OSArgument.makeDoubleArgument("one_time_retrofit_cost_ip", True)
        # one_time_cost.setDisplayName("One-Time Retrofit Cost ($/ft²)")
        # one_time_cost.setDefaultValue(0.0)
        # args.append(one_time_cost)

        # years_until_cost = openstudio.measure.OSArgument.makeIntegerArgument("years_until_retrofit_cost", True)
        # years_until_cost.setDisplayName("Year to Incur One-Time Retrofit Cost")
        # years_until_cost.setDefaultValue(0)
        # args.append(years_until_cost)

        # # WBLCA Parameters
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        gwp_statistics_chs = openstudio.StringVector()
        for gwp_statistic in self.gwp_statistics():
            gwp_statistics_chs.append(gwp_statistic)
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        args.append(gwp_statistic)

        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

        # Dropdown list of available insulation materials
        insulation_materials_types_chs = openstudio.StringVector()
        for option in self.insulation_material_types():
            insulation_materials_types_chs.append(option)
        insulation_material_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_material_type", insulation_materials_types_chs, True)
        insulation_material_type.setDisplayName("Chosen Retrofit Material for Insulation of Exterior Wall")
        insulation_material_type.setDefaultValue("Fiberglass")
        args.append(insulation_material_type)

        insulation_material_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("insulation_material_lifetime",True)
        insulation_material_lifetime.setDisplayName("Product Lifetime of Insulation Material")
        insulation_material_lifetime.setDefaultValue(30)
        args.append(insulation_material_lifetime)

        insulation_thermal_conductivity = openstudio.measure.OSArgument.makeDoubleArgument("insulation_thermal_conductivity", True)
        insulation_thermal_conductivity.setDisplayName("Thermal Conductivity of Insulation Material (W/m·K)")
        insulation_thermal_conductivity.setDescription("Thermal conductivity of the insulation material, if 0.0 is entered, typical conductivity will be used based on material type.")
        insulation_thermal_conductivity.setDefaultValue(0.0) 
        args.append(insulation_thermal_conductivity)

        insulation_material_density = openstudio.measure.OSArgument.makeDoubleArgument("insulation_material_density", True)
        insulation_material_density.setDisplayName("Density of Insulation Material (kg/m³)")
        insulation_material_density.setDescription("Density of the insulation material, if 0.0 is entered, typical density will be used based on material type.")
        insulation_material_density.setDefaultValue(0.0) 
        args.append(insulation_material_density)

        return args

    def generate_url_by_material_type(self, material_type):

        if material_type == "Blown Cellulose":
            return generate_url_byname(category="6fd418c8ff92415c833e6327638d8482", name_like="cellulose")
        elif material_type == "Blown Fiberglass":
            return generate_url_byname(category="6fd418c8ff92415c833e6327638d8482", name_like="fiber glass")
        elif material_type == "Blown Mineral Wool":
            return generate_url_byname(category="6fd418c8ff92415c833e6327638d8482", name_like="mineral wool")
        elif material_type == "Polyiso Insulation Foam Board":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="polyiso roof insulation board")
        elif material_type == "Graphite Polystyrene (GPS) Foam Board":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="Graphite Polystyrene")
        elif material_type == "Expanded Polystyrene (EPS) Foam Board":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="eps insulation")
        elif material_type == "Extruded Polystyrene (XPS) Foam Board":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="xps insulation")
        elif material_type == "Mineral Wool Heavy Density Blanket":
            return generate_url_byname(category="53a5d5bee64545f1bdd60e102a4a6ddf", name_like="mineral wool heavy density")
        elif material_type == "Mineral Wool Light Density Blanket":
            return generate_url_byname(category="53a5d5bee64545f1bdd60e102a4a6ddf", name_like="mineral wool light density")
        elif material_type == "Fiberglass Batts":
            return generate_url_byname(category="53a5d5bee64545f1bdd60e102a4a6ddf", name_like="fiber glass batts")
        elif material_type == "Pure Wool Batts":
            return generate_url_byname(category="53a5d5bee64545f1bdd60e102a4a6ddf", name_like="batts insulation wool")
        
        else:
            return None

    def remove_outliers_iqr(self, data):
        """Remove outliers from a list of numerical values using the IQR method.
        Returns the filtered list without outliers.
        """
        if len(data) < 4:  # Need at least 4 data points for meaningful IQR calculation
            return data
        
        data_array = np.array(data)
        q1 = np.percentile(data_array, 25)
        q3 = np.percentile(data_array, 75)
        iqr = q3 - q1
        
        # Define outlier bounds
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        # Filter out outliers
        filtered_data = [x for x in data if lower_bound <= x <= upper_bound]
        
        return filtered_data

    def run(self, model, runner, user_arguments):
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        # allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)
        # material_cost_ip = runner.getDoubleArgumentValue("material_cost_increase_ip", user_arguments)
        # one_time_cost_ip = runner.getDoubleArgumentValue("one_time_retrofit_cost_ip", user_arguments)
        # years_until_cost = runner.getIntegerArgumentValue("years_until_retrofit_cost", user_arguments)
        # WBLCA parameters:
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        insulation_thermal_conductivity = runner.getDoubleArgumentValue("insulation_thermal_conductivity", user_arguments)
        insulation_material_density = runner.getDoubleArgumentValue("insulation_material_density", user_arguments)

        # Check if numeric values are reasonable
        # if analysis_period <= 0:
        #     runner.registerError("Choose an integer larger than 0 for analysis period of embodeid carbon calcualtion.")
        if insulation_material_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of insulating material.")

        if r_value_ip < 0 or r_value_ip > 500:
            runner.registerError("R-value must be between 0 and 500 ft²·h·°F/Btu.")
            return False

        if insulation_thermal_conductivity < 0:
            runner.registerError("Thermal conductivity of insulation material must be non-negative.")

        if insulation_material_density < 0:
            runner.registerError("Density of insulation material must be non-negative.")

        # Convert R-value from IP to SI units (m²·K/W)
        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()

        # Define typical thermal conductivity (k) values in W/m-K for each material
        material_k_dict = {
            "Blown Cellulose": 0.040, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Blown Fiberglass": 0.033, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Blown Mineral Wool": 0.032, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Polyiso Insulation Foam Board": 0.025, # source: https://www.polyiso.org/
            "Graphite Polystyrene (GPS) Foam Board": 0.030, # source: https://www.epsmolders.org/graphite-enhanced-eps/
            "Expanded Polystyrene (EPS) Foam Board": 0.034, # source: https://www.epsmolders.org/what-is-eps/
            "Extruded Polystyrene (XPS) Foam Board": 0.033, # source: https://www.owenscorning.com/en-us/insulation/foamular
            "Mineral Wool Heavy Density Blanket": 0.032, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Mineral Wool Light Density Blanket": 0.032, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Fiberglass Batts": 0.033, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Pure Wool Batts": 0.040 # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
        }

        # Define typical density (ρ) values in kg/m³ for each material
        material_density_dict = {
            "Blown Cellulose": 50, #source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Blown Fiberglass": 30, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Blown Mineral Wool": 90, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Polyiso Insulation Foam Board": 35, # source: https://www.polyiso.org/
            "Graphite Polystyrene (GPS) Foam Board": 20, # source: https://www.epsmolders.org/graphite-enhanced-eps/
            "Expanded Polystyrene (EPS) Foam Board": 20, # source: https://www.epsmolders.org/what-is-eps/
            "Extruded Polystyrene (XPS) Foam Board": 35, # source: https://www.owenscorning.com/en-us/insulation/foamular
            "Mineral Wool Heavy Density Blanket": 103, # source: OWENS CORNING Thermafiber Light and Heavy Density Mineral Wool Insulation EPD
            "Mineral Wool Light Density Blanket": 48.6, # source: OWENS CORNING Thermafiber Light and Heavy Density Mineral Wool Insulation EPD
            "Fiberglass Batts": 30, # source: https://www.energy.gov/energysaver/weatherize/insulation/types-insulation
            "Pure Wool Batts": 24.98 # source: Havelock Wool Batt and Loose-fill Insulation EPD
        }

        # Lookup selected material's thermal conductivity
        selected_k = None
        if insulation_thermal_conductivity == 0.0:
            selected_k = material_k_dict[insulation_material_type]
        else:
            selected_k = insulation_thermal_conductivity

        if insulation_material_density == 0.0:
            insulation_material_density = material_density_dict[insulation_material_type]

        # Store exterior wall surfaces and constructions to be modified
        ext_surfaces = []
        constructions = {}

        # Iterate through all surfaces in the model
        for surface in model.getSurfaces():
            # Filter to exterior walls only
            if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
                # print(surface.nameString())         
                ext_surfaces.append(surface)
                # Get associated construction, if present
                if surface.construction().is_initialized():
                    construction = surface.construction().get()
                    # print(construction)
                    if construction.nameString() not in constructions:
                        constructions[construction.nameString()] = construction

        # If no applicable surfaces found, exit early
        if not ext_surfaces:
            runner.registerAsNotApplicable("No exterior wall surfaces found.")
            return True
        
        # store constructions require additional insulation layer
        modified_constructions = []

        # Loop through unique constructions found on exterior walls
        for name, construction in constructions.items():
            lc = construction.to_LayeredConstruction()
            if not lc.is_initialized():
                continue

            layers = lc.get().layers()
            max_r = 0
            insul_index = -1

            # Identify the insulation layer with the highest R-value
            for i, mat in enumerate(layers):
                opaque = mat.to_OpaqueMaterial()
                if opaque.is_initialized():
                    r = opaque.get().thermalResistance()
                    if r > max_r:
                        max_r = r
                        insul_index = i

            # If no insulation layer is found, log and skip this construction
            if insul_index == -1:
                runner.registerInfo(f"No suitable insulation found in construction: {name}")
                continue

            # Skip update if construction already meets or exceeds target R-value
            if max_r >= r_value_si:
                runner.registerInfo(f"'{name}' already meets or exceeds the R-value target (current: {openstudio.convert(max_r, 'm^2*K/W', 'ft^2*h*R/Btu').get():.2f}, target: {r_value_ip:.2f}).")
                continue

            # Calculate additional R-value needed
            delta_r = max(0, r_value_si - max_r)

            # Calculate additional thickness required (R = d/k => d = R * k)
            required_thickness = delta_r * selected_k

            # Calculate total area of walls using this construction
            area_m2 = sum(
                s.grossArea()
                for s in ext_surfaces
                if s.construction().get().nameString() == name
            )

            # Volume = thickness * area
            volume_m3 = area_m2 * required_thickness

            # Report to user
            runner.registerInfo(
                f"'{insulation_material_type}' selected. "
                f"Required added thickness: {required_thickness:.4f} m. "
                f"Total volume needed: {volume_m3:.2f} m³."
            )

            # Clone the original construction for modification
            new_construction = construction.clone(model).to_Construction().get()

            # Create new insulation material
            new_insul = openstudio.model.MasslessOpaqueMaterial(model)
            new_insul.setName(f"{insulation_material_type}_Added")
            new_insul.setThermalResistance(delta_r)

            # Insert after existing insulation layer
            import builtins
            layer_list = builtins.list(new_construction.layers())
            layer_list.insert(insul_index + 1, new_insul)
            new_construction.setLayers(layer_list)

            # Replace on each surface
            for surface in ext_surfaces:
                if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
                    surface.setConstruction(new_construction)

            # Store info
            modified_constructions.append({
                "construction": new_construction,
                "total_area_m2": area_m2,
                "added_thickness_m": required_thickness
            })
        
        # print("====== Modified Constructions Summary ======")
        # for item in modified_constructions:
        #     print("+++++++++++++++++")
        #     print(f"Construction: {item['construction'].nameString()}")
        #     print(f"Total Area: {item['total_area_m2']:.2f} m²")
        #     print(f"Added Thickness: {item['added_thickness_m']:.4f} m")

        #######################  EC3 fetch data ###################

        # Pull EC3 data for the chosen insulation type once
        ec3_url = self.generate_url_by_material_type(insulation_material_type)
        # print("Generated EC3 URL:", ec3_url)
        insulation_product_epd = fetch_epd_data(ec3_url, api_key)

        # Extract density and lifetime values from EPD responses
        density_values = []
        lifetime_values = []
        for epd in insulation_product_epd:
            parsed_data = parse_product_epd(epd)
            density_str = parsed_data.get("density")
            if density_str:
                density_value = extract_numeric_value(density_str)
                if density_value > 0.0:
                    density_values.append(density_value)
            
            # Extract reference service life from EPD
            reference_service_life = parsed_data.get("reference_service_life")
            if reference_service_life:
                lifetime_value = extract_numeric_value(reference_service_life)
                if lifetime_value > 0.0:
                    lifetime_values.append(lifetime_value)
        
        # Use EPD density if available, applying the same statistic method as GWP
        if density_values:
            # Remove outliers from density values
            if len(density_values) > 0:
                original_count = len(density_values)
                density_values = self.remove_outliers_iqr(density_values)
                filtered_count = len(density_values)
                if original_count != filtered_count:
                    pass  # Reduced verbosity: runner.registerInfo(f"Removed {original_count - filtered_count} density outliers: {original_count} -> {filtered_count} values")
            
            # Apply statistic based on user selection
            if len(density_values) == 1:
                epd_density = density_values[0]
            elif gwp_statistic == "minimum":
                epd_density = float(np.min(density_values))
            elif gwp_statistic == "maximum":
                epd_density = float(np.max(density_values))
            elif gwp_statistic == "mean":
                epd_density = float(np.mean(density_values))
            elif gwp_statistic == "median":
                epd_density = float(np.median(density_values))
            else:
                epd_density = float(np.mean(density_values))  # default to mean
            
            # Use EPD density if user didn't provide a specific value
            if insulation_material_density == material_density_dict.get(insulation_material_type, 0.0):
                insulation_material_density = epd_density
                # Reduced verbosity
                pass
            else:
                # Reduced verbosity
                pass
        else:
            # Reduced verbosity
            pass

        # Process lifetime values from EPD
        selected_lifetime = insulation_material_lifetime  # Default to user input
        lifetime_source = "user input"
        
        if lifetime_values:
            # Remove outliers from lifetime values
            if len(lifetime_values) > 0:
                original_count = len(lifetime_values)
                lifetime_values = self.remove_outliers_iqr(lifetime_values)
                filtered_count = len(lifetime_values)
                if original_count != filtered_count:
                    pass  # Reduced verbosity: runner.registerInfo(f"Removed {original_count - filtered_count} lifetime outliers: {original_count} -> {filtered_count} values")
            
            # Apply statistic based on user selection
            if len(lifetime_values) == 1:
                epd_lifetime = lifetime_values[0]
            elif gwp_statistic == "minimum":
                epd_lifetime = float(np.min(lifetime_values))
            elif gwp_statistic == "maximum":
                epd_lifetime = float(np.max(lifetime_values))
            elif gwp_statistic == "mean":
                epd_lifetime = float(np.mean(lifetime_values))
            elif gwp_statistic == "median":
                epd_lifetime = float(np.median(lifetime_values))
            else:
                epd_lifetime = float(np.mean(lifetime_values))  # default to mean
            
            # Use EPD lifetime
            selected_lifetime = epd_lifetime
            lifetime_source = "EPD"
            # Reduced verbosity
            pass
        else:
            # Reduced verbosity
            pass

        # Use compute_gwp_data from EC3_lookup to calculate GWP values with outlier removal and statistics
        keys = [insulation_material_type]
        epd_list_by_material = [insulation_product_epd]
        gwp_data = compute_gwp_data(keys, epd_list_by_material, "Product", gwp_statistic)
        
        # Extract GWP values for the selected material
        material_gwp = gwp_data.get(insulation_material_type, {})
        
        # Reduced verbosity - GWP values computed but not logging details
        # runner.registerInfo(f"GWP values computed for {insulation_material_type}:")
        # runner.registerInfo(f"  gwp_per_kg: {material_gwp.get('gwp_per_kg', 0.0):.4f} kg CO2 eq/kg")
        # runner.registerInfo(f"  gwp_per_m2: {material_gwp.get('gwp_per_m2', 0.0):.4f} kg CO2 eq/m2")
        # runner.registerInfo(f"  gwp_per_m3: {material_gwp.get('gwp_per_m3', 0.0):.4f} kg CO2 eq/m3")

        # multipliers for calculating embodied carbon over analysis period
        multiplier = lifetime_multiplier(selected_lifetime, analysis_period)

        # Iterate through all modified constructions to compute embodied carbon
        gwp_summary = []
        for item in modified_constructions:
            total_area_m2 = item["total_area_m2"]
            added_thickness_m = item["added_thickness_m"]

            # Store GWP values from compute_gwp_data results
            item["gwp_per_kg"] = material_gwp.get("gwp_per_kg", 0.0)
            item["gwp_per_m2"] = material_gwp.get("gwp_per_m2", 0.0)
            item["gwp_per_m3"] = material_gwp.get("gwp_per_m3", 0.0)

            # Calculate total GWP for this added insulation
            total_gwp = item['gwp_per_m3'] * (total_area_m2*added_thickness_m) * multiplier
            if (not np.isfinite(total_gwp) or total_gwp == 0.0) and item["gwp_per_kg"] != 0.0:
                total_gwp = item["gwp_per_kg"] * (insulation_material_density * total_area_m2 * added_thickness_m) * multiplier
            if not np.isfinite(total_gwp):
                total_gwp = 0.0

            # Store result in summary table
            gwp_summary.append({
                "gwp_per_kg": item["gwp_per_kg"],
                "gwp_per_m2": item["gwp_per_m2"],
                "gwp_per_m3": item["gwp_per_m3"],
                "insulation_material_type": insulation_material_type,
                "insulation_material_lifetime_years": selected_lifetime,
                "insulation_material_lifetime_source": lifetime_source,
                "insulation_material_density_kg_per_m3": insulation_material_density,
                "insulation_material_thermal_conductivity_W_per_mK": selected_k,
                "construction_name": item["construction"].nameString(),
                "added_total_volume_m3": item["added_thickness_m"] * item["total_area_m2"],
                "added_total_area_m2": total_area_m2,
                "added_thickness_m": added_thickness_m,
                "added_total_mass_kg": insulation_material_density * item["added_thickness_m"] * item["total_area_m2"],
                "total_gwp_kg_co2_eq": total_gwp
            })

        # Debug: Print GWP summary
        # pp.pprint(gwp_summary)

        for idx, item in enumerate(modified_constructions):
            construction = item["construction"]
            total_area_m2 = item["total_area_m2"]
            added_thickness_m = item["added_thickness_m"]
            total_gwp = gwp_summary[idx]["total_gwp_kg_co2_eq"]

            # props = construction.additionalProperties()
            # props.setFeature("construction_name", construction.nameString())
            # props.setFeature("analysis_period_years", analysis_period)
            # props.setFeature("original_insulation_r-value_ip", openstudio.convert(max_r, "m^2*K/W", "ft^2*h*R/Btu").get())
            # props.setFeature("target_insulation_r-value_ip", r_value_ip)
            # props.setFeature("total_embodied_carbon_kgCO2eq", total_gwp) # total embodied carbon for adding insulation layer to all the exterior walls with this construction
            # props.setFeature("insutlation_material_type", insulation_material_type)
            # props.setFeature("total_volume_m3", added_thickness_m * total_area_m2)
            # props.setFeature("renovated_exterior_wall_area_m2", total_area_m2)
            # props.setFeature("added_insulation_layer_thickness_m", added_thickness_m)
            # props.setFeature("added_insulation_layer_mass_kg", insulation_material_density * added_thickness_m * total_area_m2)
            # props.setFeature("insulation_material_density_kg_per_m3", insulation_material_density)
            # props.setFeature("insulation_material_thermal_conductivity_W_per_mK", selected_k)
            # props.setFeature("insulation_material_lifetime_years", selected_lifetime)
            # props.setFeature("insulation_material_lifetime_source", lifetime_source)
            # props.setFeature("insulation_material_gwp_per_kg", item["gwp_per_kg"])
            # props.setFeature("insulation_material_gwp_per_m2", item["gwp_per_m2"])
            # props.setFeature("insulation_material_gwp_per_m3", item["gwp_per_m3"])

            # Reduced verbosity - construction tagging happens silently
            # runner.registerInfo(
            #     f"Tagged '{construction.nameString()}' with embodied carbon: "
            #     f"{total_gwp:.2f} kg CO₂ eq over {total_area_m2:.2f} m²"
            # )
        
        # Calculate building-level totals for summarization
        total_embodied_carbon = sum(gwp_summary[idx]["total_gwp_kg_co2_eq"] for idx in range(len(modified_constructions)))
        total_wall_area = sum(item["total_area_m2"] for item in modified_constructions)
        
        # Store building-level summary in organized AdditionalProperties buckets
        building = model.getBuilding()
        basic_input = building.additionalProperties()
        site = model.getSite()
        reno_detail = site.additionalProperties()
        facility = model.getFacility()
        factors = facility.additionalProperties()
        simcontrol = model.getSimulationControl()
        results = simcontrol.additionalProperties()
        sizingpara = model.getSizingParameters()
        mtrl_prop = sizingpara.additionalProperties()

        # Basic measure inputs
        basic_input.setFeature("measure_name", "Increase Insulation R-Value for Exterior Walls")
        reno_detail.setFeature("wall_target_insulation_r_value_ip", r_value_ip)
        reno_detail.setFeature("wall_insulation_material_type", insulation_material_type)
        basic_input.setFeature("analysis_period_years", analysis_period)
        basic_input.setFeature("gwp_statistic", gwp_statistic)

        # Material properties and lifetime
        mtrl_prop.setFeature("wall_insulation_material_lifetime_years", selected_lifetime)
        # mtrl_prop.setFeature("wall_insulation_material_lifetime_source", lifetime_source)
        mtrl_prop.setFeature("wall_insulation_material_density_kg_per_m3", insulation_material_density)
        mtrl_prop.setFeature("wall_insulation_material_thermal_conductivity_W_per_mK", selected_k)

        # Renovation details / quantities
        reno_detail.setFeature("wall_insulation_renovated_area_m2", total_wall_area)
        reno_detail.setFeature("wall_insulation_added_volume_m3", sum(item["added_thickness_m"] * item["total_area_m2"] for item in modified_constructions))
        # reno_detail.setFeature("wall_insulation_modified_constructions_count", len(modified_constructions))

        # Results (standardized fields)
        results.setFeature("wall_insulation_total_additional_embodied_carbon_kg", total_embodied_carbon)
        results.setFeature("wall_insulation_total_additional_material_cost_$", 0.0)  # Placeholder
        results.setFeature("wall_insulation_total_additional_overhead_profit_cost_$", 0.0)  # Placeholder
        results.setFeature("wall_insulation_total_additional_labour_cost_$", 0.0)  # Placeholder
        results.setFeature("wall_insulation_total_embodied_carbon_kgCO2eq", total_embodied_carbon)

        # Emission factors
        if material_gwp.get("gwp_per_kg", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_kg", material_gwp.get("gwp_per_kg", 0.0))
        if material_gwp.get("gwp_per_m2", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_m2", material_gwp.get("gwp_per_m2", 0.0))
        if material_gwp.get("gwp_per_m3", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_m3", material_gwp.get("gwp_per_m3", 0.0))

        # Construction names for traceability
        construction_names = [item["construction"].nameString() for item in modified_constructions]
        if construction_names:
            basic_input.setFeature("wall_insulation_construction_names", ', '.join(construction_names))

        # # Cross-measure extraction fields on Facility
        # factors.setFeature("name", "Increase_Insulation_R-Value_for_Exterior_Walls")
        # factors.setFeature("total_additional_embodied_carbon_kgCO2", total_embodied_carbon)
        
        runner.registerInfo(
            f"Building-level summary: Total embodied carbon = {total_embodied_carbon:.2f} kg CO2 eq "
            f"across {total_wall_area:.2f} m² of exterior walls"
        )
            
        # Debug: print all additional properties (commented out for production)
        # for prop in model.getAdditionalPropertiess():
        #     print(prop)

        runner.registerFinalCondition(
            f"Modified {len(modified_constructions)} construction(s) to meet target R-value of {r_value_ip} ft²·h·°F/Btu."
        )
        return True

# Register the measure
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
