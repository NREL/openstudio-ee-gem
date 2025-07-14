# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import numpy as np
import pprint as pp
import sys
import os
from resources.EC3_lookup import *
import urllib3
import pprint as pp
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# current_dir = os.path.dirname(__file__)
# root_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
# sys.path.insert(0, root_dir)
# from lib.measures.window_enhancement.resources.EC3_lookup import generate_url
# from lib.measures.window_enhancement.resources.EC3_lookup import fetch_epd_data
# from lib.measures.window_enhancement.resources.EC3_lookup import parse_product_epd
# from lib.measures.window_enhancement.resources.EC3_lookup import parse_industrial_epd
# from lib.measures.window_enhancement.resources.EC3_lookup import test_empty_epd
# from lib.measures.window_enhancement.resources.EC3_lookup import compute_gwp_data

class IncreaseInsulationRValueForExteriorWalls(openstudio.measure.ModelMeasure):
    def name(self):
        return "Increase R-value of Insulation for Exterior Walls to a Specific Value"

    def description(self):
        return "Increases the R-value of insulation layers in exterior walls to meet a specified target."

    def modeler_description(self):
        return ("This measure modifies insulation materials in exterior wall constructions to reach "
                "a user-defined R-value, adjusting thermal resistance and optionally accounting for costs.")

    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]
    
    # for brick layer: filter metrics not working, unable to extract option keywords
    # for insulation layer
    @staticmethod
    def insulation_material_options():
        return [
            "Mineral Wool",
            "Cellulose",
            "Fiberglass",
            "Expanded Polystyrene (EPS)",
            "Extruded Polystyrene (XPS)",
            "Graphite Polystyrene (GPS)",
            "Polyiso (ISO)",
            "Expanded Polyethylene",
            "Other"]  

    @staticmethod
    def insulation_application_options():
        return ["Wall","Exterior%20Wall","Roof","Below%20Grade","Duct"]
    
    # for precast concrete layer
    @staticmethod
    def precast_concrete_options():
        return ["lightweight","grfc","insulated"]
    
    # for gypsum board layer
    @staticmethod
    def gypsum_board_options():
        return ["mold_resistant","moisture_resistant","abuse_resistant"]
    
    @staticmethod
    def gypsum_fire_ratings():
        return ["X","C","F"]

    @staticmethod
    def epd_types():
        return ["Product","Industry"]
    
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
        # analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        # analysis_period.setDisplayName("Analysis Period")
        # analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        # analysis_period.setDefaultValue(30)
        # args.append(analysis_period)

        # gwp_statistics_chs = openstudio.StringVector()
        # for gwp_statistic in self.gwp_statistics():
        #     gwp_statistics_chs.append(gwp_statistic)
        # gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        # gwp_statistic.setDisplayName("GWP Statistic") 
        # gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or median) of returned GWP value")
        # args.append(gwp_statistic)

        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

        edp_type_chs = openstudio.StringVector()
        for type in self.epd_types():
            edp_type_chs.append(type)
        epd_type = openstudio.measure.OSArgument.makeChoiceArgument("epd_type",edp_type_chs, True)
        epd_type.setDisplayName("EPD Type") 
        epd_type.setDescription("Type of EPD for searching GWP values, Product EPDs refer to specific products from a manufacturer, while industrial EPDs represent average data across an entire industry sector.")
        args.append(epd_type)

        # Dropdown list of available insulation materials
        material_choices = ["Mineral Wool", "Cellulose", "Fiberglass", "Expanded Polystyrene (EPS)", "Extruded Polystyrene (XPS)", "Graphite Polystyrene (GPS)", "Polyiso (ISO)", "Expanded Polyethylene", "Other"]
        insulation_material_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_material_type", material_choices, True)
        insulation_material_type.setDisplayName("Chosen Retrofit Material")
        insulation_material_type.setDefaultValue("Fiberglass batt")
        args.append(insulation_material_type)

        # insulation_application_chs = openstudio.StringVector()
        # for option in self.insulation_application_options():
        #     insulation_application_chs.append(option)
        # insulation_application_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_application_type", insulation_application_chs, True)
        # insulation_application_type.setDisplayName("Application Type of Insulation for Exterior Wall")
        # insulation_application_type.setDefaultValue("Exterior%20Wall")
        # args.append(insulation_application_type)

        insulation_material_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("insulation_material_lifetime",True)
        insulation_material_lifetime.setDisplayName("Product Lifetime of Insulation Material")
        insulation_material_lifetime.setDefaultValue(30)
        args.append(insulation_material_lifetime)

        # M15 200mm heavyweight concrete
        precast_concrete_type_chs = openstudio.StringVector()
        for option in self.precast_concrete_options():
            precast_concrete_type_chs.append(option)
        precast_concrete_type = openstudio.measure.OSArgument.makeChoiceArgument("precast_concrete_type", precast_concrete_type_chs, True)
        precast_concrete_type.setDisplayName("Type of Precast Concrete for Exterior Wall") 
        args.append(precast_concrete_type)

        precast_concrete_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("precast_concrete_lifetime",True)
        precast_concrete_lifetime.setDisplayName("Product Lifetime of Precast Concrete")
        precast_concrete_lifetime.setDefaultValue(30)
        args.append(precast_concrete_lifetime)

        # M01 100mm brick
        brick_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("brick_lifetime",True)
        brick_lifetime.setDisplayName("Product Lifetime of Brick")
        brick_lifetime.setDefaultValue(30)
        args.append(brick_lifetime)

        # G01a 19mm gypsum board
        gypsum_board_type_chs = openstudio.StringVector()
        for option in self.gypsum_board_options():
            gypsum_board_type_chs.append(option)
        gypsum_board_type = openstudio.measure.OSArgument.makeChoiceArgument("gypsum_board_type", gypsum_board_type_chs, True)
        gypsum_board_type.setDisplayName("Type of Gypsum Board for Exterior Wall")
        args.append(gypsum_board_type)

        gypsum_board_fr_chs = openstudio.StringVector()
        for option in self.gypsum_fire_ratings():
            gypsum_board_fr_chs.append(option)
        gypsum_board_fr = openstudio.measure.OSArgument.makeChoiceArgument("gypsum_board_fr", gypsum_board_fr_chs, True)
        gypsum_board_fr.setDisplayName("Fire rating of Gypsum Board for Exterior Wall")
        args.append(gypsum_board_fr)

        gypsum_board_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("gypsum_board_lifetime",True)
        gypsum_board_lifetime.setDisplayName("Product Lifetime of Gypsum Board")
        gypsum_board_lifetime.setDefaultValue(30)
        args.append(gypsum_board_lifetime)

        return args

    def calculate_total_gwp_with_density_fallback(self, epd_data, insulated_surface_area_m2, insulated_surface_thickness_m, material_name=None):
        """
        Calculates total embodied carbon (kg CO2 eq) for insulation surface.
        Tries:
          1) Mass-based using EPD density if available
          2) Mass-based using typical density by material if EPD data is missing
          3) Falls back to area × gwp_per_m2 assuming it's for installed thickness
        """

        # Define typical density (ρ) values in kg/m³ for each material
        material_density_dict = {
            "Mineral Wool": 90,                   # range: 60–100 kg/m³ (batts) :https://www.engineeringtoolbox.com/thermal-insulation-d_922.html
            "Cellulose": 50,                      # loose fill: 45–60 kg/m³ :https://www.cellulose.org/HomeOwners/Technical-Information
            "Fiberglass": 30,                     # loose fill: 10–30 kg/m³, batts ~30–40 :https://www.engineeringtoolbox.com/thermal-insulation-d_922.html
            "Expanded Polystyrene (EPS)": 20,     # 15–30 kg/m³ :https://www.epsindustry.org/insulation/eps-insulation-properties
            "Extruded Polystyrene (XPS)": 35,     # 30–45 kg/m³ :https://www.foam-tech.com/theory/foam_properties.htm
            "Graphite Polystyrene (GPS)": 20,     # similar to EPS with graphite ~15–30 kg/m³ :https://www.neopor.basf.com/global/en/performance.html
            "Polyiso (ISO)": 35,                  # polyiso rigid foam board: ~30–40 kg/m³ :https://www.rdh.com/wp-content/uploads/2018/04/Polyisocyanurate-Insulation.pdf
            "Expanded Polyethylene": 25,          # ~25–35 kg/m³ :https://pmc.ncbi.nlm.nih.gov/articles/PMC9658328/
            "Other": 30                           # placeholder generic (phenolic ~35 kg/m³, aerogel 3–100) :https://www.ashrae.org/technical-resources/ashrae-handbook
        }


        gwp_per_m2 = float(epd_data.get("gwp_per_m2", 0) or 0)
        gwp_per_kg = float(epd_data.get("gwp_per_kg", 0) or 0)

        # Try mass-based from EPD density
        density_str = epd_data.get("density")
        if density_str and density_str.lower() != 'none':
            density_kgm3 = float(density_str.split()[0])
            volume_m3 = insulated_surface_area_m2 * insulated_surface_thickness_m
            mass_kg = volume_m3 * density_kgm3
            return mass_kg * gwp_per_kg
        else:
            density_kgm3 = material_density_dict.get(material_name, material_density_dict["Other"])
            volume_m3 = insulated_surface_area_m2 * insulated_surface_thickness_m
            mass_kg = volume_m3 * density_kgm3
            return mass_kg * gwp_per_kg


    def pull_EC3_data(self, insulation_material_type):
        insulation_application_type = "Exterior%20Wall"
        material_name = "Insulation"

        # Collecting parsed industrial & product EPDs
        epd_summary = []

        # Generate URLs
        product_url = generate_url(
            material_name=material_name,
            endpoint="materials",
            epd_type="Product",
            insulation_application=insulation_application_type,
            insulation_material=insulation_material_type,
            page_size=100
        )
        industry_url = generate_url(
            material_name=material_name,
            endpoint="industry_epds",
            epd_type="Industry",
            insulation_application=insulation_application_type,
            insulation_material=insulation_material_type,
            page_size=100
        )

        # Fetch data
        product_epd_data = fetch_epd_data(product_url, API_TOKEN)
        industrial_epd_data = fetch_epd_data(industry_url, API_TOKEN)

        # Parse product EPDs
        for idx, epd in enumerate(product_epd_data, start=1):
            parsed_data = parse_product_epd(epd)
            # print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

            epd_summary.append({
                "epd_name": parsed_data.get("epd_name"),
                "mass_per_declared_unit": parsed_data.get("mass_per_declared_unit"),
                "gwp_per_m2 (kg CO2 eq/m2)": parsed_data.get("gwp_per_m2 (kg CO2 eq/m2)"),
                "gwp_per_m3 (kg CO2 eq/m3)": parsed_data.get("gwp_per_m3 (kg CO2 eq/m3)"),
                "gwp_per_kg (kg CO2 eq/kg)": parsed_data.get("gwp_per_kg (kg CO2 eq/kg)"),
                "density (kg/m3)": parsed_data.get("density")
            })

        # Parse industrial EPDs
        for idx, epd in enumerate(industrial_epd_data, start=1):
            parsed_data = parse_industrial_epd(epd)
            epd_summary.append({
                "epd_name": parsed_data.get("epd_name"),
                "mass_per_declared_unit": parsed_data.get("mass_per_declared_unit"),
                "gwp_per_m2 (kg CO2 eq/m2)": parsed_data.get("gwp_per_m2 (kg CO2 eq/m2)"),
                "gwp_per_m3 (kg CO2 eq/m3)": parsed_data.get("gwp_per_m3 (kg CO2 eq/m3)"),
                "gwp_per_kg (kg CO2 eq/kg)": parsed_data.get("gwp_per_kg (kg CO2 eq/kg)"),
                "density (kg/m3)": parsed_data.get("density")
            })

        # Create and return DataFrame
        df_epd_summary = pd.DataFrame(epd_summary)
        return df_epd_summary

    def run(self, model, runner, user_arguments):
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        # allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)
        # material_cost_ip = runner.getDoubleArgumentValue("material_cost_increase_ip", user_arguments)
        # one_time_cost_ip = runner.getDoubleArgumentValue("one_time_retrofit_cost_ip", user_arguments)
        # years_until_cost = runner.getIntegerArgumentValue("years_until_retrofit_cost", user_arguments)
        # WBLCA parameters:
        # analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        # gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        epd_type = runner.getStringArgumentValue("epd_type", user_arguments)
        # Material properties:
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        # insulation_application_type = runner.getStringArgumentValue("insulation_application_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        precast_concrete_type = runner.getStringArgumentValue("precast_concrete_type", user_arguments)
        precast_concrete_lifetime = runner.getIntegerArgumentValue("precast_concrete_lifetime", user_arguments)
        brick_lifetime = runner.getIntegerArgumentValue("brick_lifetime", user_arguments)
        gypsum_board_type = runner.getStringArgumentValue("gypsum_board_type", user_arguments)
        gypsum_board_fr = runner.getStringArgumentValue("gypsum_board_fr", user_arguments)
        gypsum_board_lifetime = runner.getIntegerArgumentValue("gypsum_board_lifetime", user_arguments)

        # Check if numeric values are reasonable
        # if analysis_period <= 0:
        #     runner.registerError("Choose an integer larger than 0 for analysis period of embodeid carbon calcualtion.")
        if insulation_material_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of insulating material.")
        if precast_concrete_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of precast concrete.")
        if brick_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of brick.")
        if gypsum_board_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of gypsum board.")
        if r_value_ip < 0 or r_value_ip > 500:
            runner.registerError("R-value must be between 0 and 500 ft²·h·°F/Btu.")
            return False

        # Convert R-value from IP to SI units (m²·K/W)
        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()

        # Define typical thermal conductivity (k) values in W/m-K for each material
        material_k_dict = {
            "Mineral Wool": 0.032,                     # range: 0.032–0.044 W/m·K :https://www.buyinsulationonline.co.uk/blog/the-ultimate-guide-to-insulation-values
            "Cellulose": 0.040,                        # range: 0.036–0.042 W/m·K :https://www.engineeringtoolbox.com/thermal-conductivity-d_429.html
            "Fiberglass": 0.033,                       # range: 0.032–0.044 W/m·K :https://www.buyinsulationonline.co.uk/blog/pir-vs-mineral-wool-insulation
            "Expanded Polystyrene (EPS)": 0.034,       # 0.032–0.038 (up to ~0.046) :https://www.engineeringtoolbox.com/thermal-conductivity-d_429.html
            "Extruded Polystyrene (XPS)": 0.033,       # 0.029–0.039 W/m·K :https://en.wikipedia.org/wiki/List_of_thermal_conductivities
            "Graphite Polystyrene (GPS)": 0.030,       # enhanced EPS: ~0.029–0.034 W/m·K :https://www.neopor.basf.com/global/en/performance.html
            "Polyiso (ISO)": 0.025,                    # polyiso/PIR: 0.022–0.028 W/m·K :https://www.buyinsulationonline.co.uk/blog/the-ultimate-guide-to-insulation-values
            "Expanded Polyethylene": 0.032,           # PE foam: 0.032–0.034 W/m·K :https://pmc.ncbi.nlm.nih.gov/articles/PMC9658328/
            "Other": 0.030                             # placeholder (e.g., phenolic, aerogel; 0.018–0.060+ W/m·K) :https://www.ashrae.org/technical-resources/ashrae-handbook
        }

        # Lookup selected material's thermal conductivity
        selected_k = material_k_dict[insulation_material_type]

        ################################################################################
        # This part is old. It is used for checking what is currently in the model.
        ################################################################################
        # ext_surfaces = []
        # # loop through to collect all the surfaces containing exterior wall constructions
        # for surface in model.getSurfaces():
        #     if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
        #         ext_surfaces.append(surface)
        #         runner.registerInfo(f"Processing exterior wall surface: {surface.nameString()}")
        #     else:
        #         runner.registerInfo(f"Skipping no exterior wall surface: {surface.nameString()}")
        #         continue

        # #dictionary storing properties of surface containing exterior wall constructions
        # surface_dict = {}
        # # calculate baseline first, save this for future: modified_constructions = []
        # for surface in ext_surfaces:
        #     surface_name = surface.nameString()
        #     surface_dict[surface_name] = {}
        #     surface_dict[surface_name]["Surface object"] = surface
        #     surface_dict[surface_name]["Window to wall ratio"] = surface.windowToWallRatio() #double
        #     surface_dict[surface_name]["Net area excluding window (m2)"] = surface.netArea() #double
        #     # obtain layers for each wall construction
        #     surface_const = surface.construction().get()
        #     layered_construction = surface_const.to_LayeredConstruction().get()
        #     for i in range(layered_construction.numLayers()):
        #         material = layered_construction.getLayer(i)
        #         material_name = material.nameString()
        #         runner.registerInfo(f"Layer {i+1}: {material.nameString()}") 
        #         surface_dict[surface_name][f"layer {i+1}"] = {}
        #         surface_dict[surface_name][f"layer {i+1}"]["material name"] = material_name
        #         # distinguish material type by material name
        #         if "insulation" in material_name:
        #             surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = insulation_material_lifetime
        #         elif "gypsum" in material_name:
        #             surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = gypsum_board_lifetime
        #         elif "concrete" in material_name:
        #             surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = precast_concrete_lifetime
        #         elif "brick" in material_name:
        #             surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = brick_lifetime
        #         else:
        #             runner.registerError(f"Unsupported materail type: {material_name}")
        #         # if the material layer has thickness assigned
        #         if material.thickness():
        #             surface_dict[surface_name][f"layer {i+1}"]["Thickness (m)"] = material.thickness()
        #         else: # otherweise, assign zero thickness
        #             surface_dict[surface_name][f"layer {i+1}"]["Thickness (m)"] = 0.0
        #             runner.registerError(f"The material layer: {i+1} has no thickness assigned.")
        #         # calculate volume for each layer
        #         surface_dict[surface_name][f"layer {i+1}"]['Volume (m3)'] = material.thickness() * surface.netArea()


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
            if max_r >= r_value_si and not allow_reduction:
                runner.registerInfo(f"'{name}' already meets or exceeds the R-value target.")
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
            layer_list = list(new_construction.layers())
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

        print("====== Modified Constructions Summary ======")
        for item in modified_constructions:
            print("+++++++++++++++++")
            print(f"Construction: {item['construction'].nameString()}")
            print(f"Total Area: {item['total_area_m2']:.2f} m²")
            print(f"Added Thickness: {item['added_thickness_m']:.4f} m")

        #######################  EC3 stuff ###################

        # Pull EC3 data for the chosen insulation type once
        ec3_data = self.pull_EC3_data(insulation_material_type)

        # Create list to store summary rows
        gwp_summary = []

        # Iterate through all modified constructions to compute embodied carbon
        for item in modified_constructions:
            total_area_m2 = item["total_area_m2"]
            added_thickness_m = item["added_thickness_m"]

            # Use the first EPD from your pull_EC3_data dataframe for simplicity
            # (you could also apply median or your own filtering)
            epd_row = ec3_data.iloc[0]
            epd_data = {
                "mass_per_declared_unit": epd_row.get("mass_per_declared_unit"),
                "density": epd_row.get("density (kg/m3)"),
                "gwp_per_m2": epd_row.get("gwp_per_m2 (kg CO2 eq/m2)"),
                "gwp_per_kg": epd_row.get("gwp_per_kg (kg CO2 eq/kg)")
            }

            # Calculate total GWP for this added insulation
            total_gwp_kgco2 = self.calculate_total_gwp_with_density_fallback(
                epd_data,
                insulated_surface_area_m2=total_area_m2,
                insulated_surface_thickness_m=added_thickness_m,
                material_name=insulation_material_type
            )


            # Store result in summary table
            gwp_summary.append({
                "construction_name": item["construction"].nameString(),
                "total_area_m2": total_area_m2,
                "added_thickness_m": added_thickness_m,
                "total_gwp_kgCO2eq": total_gwp_kgco2
            })


        # Convert to DataFrame for reporting
        df_gwp_summary = pd.DataFrame(gwp_summary)

        # Pretty print or save
        print("\n==== GWP Summary for Modified Constructions ====")
        print(df_gwp_summary)

        ##########################################

        for idx, item in enumerate(modified_constructions):
            construction = item["construction"]
            total_area_m2 = item["total_area_m2"]
            added_thickness_m = item["added_thickness_m"]
            total_gwp_kgco2 = gwp_summary[idx]["total_gwp_kgCO2eq"]

            props = construction.additionalProperties()
            props.setFeature("embodied_carbon_kgCO2eq", total_gwp_kgco2)
            props.setFeature("modified_material", insulation_material_type)
            props.setFeature("total_area_m2", total_area_m2)
            props.setFeature("added_thickness_m", added_thickness_m)

            runner.registerInfo(
                f"Tagged '{construction.nameString()}' with embodied carbon: "
                f"{total_gwp_kgco2:.2f} kg CO₂ eq over {total_area_m2:.2f} m²"
            )



        for prop in model.getAdditionalPropertiess():
            print(prop)



        runner.registerFinalCondition(
            f"Modified {len(modified_constructions)} construction(s) to meet target R-value of {r_value_ip} ft²·h·°F/Btu."
        )
        return True

# Register the measure
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
