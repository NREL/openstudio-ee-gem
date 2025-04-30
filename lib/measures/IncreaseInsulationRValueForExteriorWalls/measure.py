# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import numpy as np
import pprint as pp
import sys
import os
current_dir = os.path.dirname(__file__)
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
sys.path.insert(0, root_dir)
from lib.measures.window_enhancement.resources.EC3_lookup import generate_url
from lib.measures.window_enhancement.resources.EC3_lookup import fetch_epd_data
from lib.measures.window_enhancement.resources.EC3_lookup import parse_product_epd
from lib.measures.window_enhancement.resources.EC3_lookup import parse_industrial_epd
from lib.measures.window_enhancement.resources.EC3_lookup import test_empty_epd

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
        return ["Mineral%20Wool","Cellulose","Fiberglass","EPS","XPS","GPS","Polyisocyanurate","Polyethylene"]
    
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

        allow_reduction = openstudio.measure.OSArgument.makeBoolArgument("allow_reduction", True)
        allow_reduction.setDisplayName("Allow reduction in R-value if current value is higher?")
        allow_reduction.setDefaultValue(False)
        args.append(allow_reduction)

        material_cost = openstudio.measure.OSArgument.makeDoubleArgument("material_cost_increase_ip", True)
        material_cost.setDisplayName("Material and Installation Cost Increase ($/ft²)")
        material_cost.setDefaultValue(0.0)
        args.append(material_cost)

        one_time_cost = openstudio.measure.OSArgument.makeDoubleArgument("one_time_retrofit_cost_ip", True)
        one_time_cost.setDisplayName("One-Time Retrofit Cost ($/ft²)")
        one_time_cost.setDefaultValue(0.0)
        args.append(one_time_cost)

        years_until_cost = openstudio.measure.OSArgument.makeIntegerArgument("years_until_retrofit_cost", True)
        years_until_cost.setDisplayName("Year to Incur One-Time Retrofit Cost")
        years_until_cost.setDefaultValue(0)
        args.append(years_until_cost)

        # WBLCA Parameters
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

        edp_type_chs = openstudio.StringVector()
        for type in self.epd_types():
            edp_type_chs.append(type)
        epd_type = openstudio.measure.OSArgument.makeChoiceArgument("epd_type",edp_type_chs, True)
        epd_type.setDisplayName("EPD Type") 
        epd_type.setDescription("Type of EPD for searching GWP values, Product EPDs refer to specific products from a manufacturer, while industrial EPDs represent average data across an entire industry sector.")
        args.append(epd_type)

        # I02 50mm insulation board
        insulation_material_chs = openstudio.StringVector()
        for option in self.insulation_material_options():
            insulation_material_chs.append(option)
        insulation_material_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_material_type", insulation_material_chs, True)
        insulation_material_type.setDisplayName("Material Type of Insulation for Exterior Wall") 
        args.append(insulation_material_type)

        insulation_application_chs = openstudio.StringVector()
        for option in self.insulation_application_options():
            insulation_application_chs.append(option)
        insulation_application_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_application_type", insulation_application_chs, True)
        insulation_application_type.setDisplayName("Application Type of Insulation for Exterior Wall")
        args.append(insulation_application_type)

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

    def run(self, model, runner, user_arguments):
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)
        material_cost_ip = runner.getDoubleArgumentValue("material_cost_increase_ip", user_arguments)
        one_time_cost_ip = runner.getDoubleArgumentValue("one_time_retrofit_cost_ip", user_arguments)
        years_until_cost = runner.getIntegerArgumentValue("years_until_retrofit_cost", user_arguments)
        # WBLCA parameters:
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        epd_type = runner.getStringArgumentValue("epd_type", user_arguments)
        # Material properties:
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_application_type = runner.getStringArgumentValue("insulation_application_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        precast_concrete_type = runner.getStringArgumentValue("precast_concrete_type", user_arguments)
        precast_concrete_lifetime = runner.getIntegerArgumentValue("precast_concrete_lifetime", user_arguments)
        brick_lifetime = runner.getIntegerArgumentValue("brick_lifetime", user_arguments)
        gypsum_board_type = runner.getStringArgumentValue("gypsum_board_type", user_arguments)
        gypsum_board_fr = runner.getStringArgumentValue("gypsum_board_fr", user_arguments)
        gypsum_board_lifetime = runner.getIntegerArgumentValue("gypsum_board_lifetime", user_arguments)

        # Check if numeric values are reasonable
        if analysis_period <= 0:
            runner.registerError("Choose an integer larger than 0 for analysis period of embodeid carbon calcualtion.")
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

        # r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()
        # material_cost_si = openstudio.convert(material_cost_ip, "1/ft^2", "1/m^2").get()
        # one_time_cost_si = openstudio.convert(one_time_cost_ip, "1/ft^2", "1/m^2").get()

        ext_surfaces = []
        # loop through to collect all the surfaces containing exterior wall constructions
        for surface in model.getSurfaces():
            if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
                ext_surfaces.append(surface)
                runner.registerInfo(f"Processing exterior wall surface: {surface.nameString()}")
            else:
                runner.registerInfo(f"Skipping no exterior wall surface: {surface.nameString()}")
                continue

        #dictionary storing properties of surface containing exterior wall constructions
        surface_dict = {}
        # calculate baseline first, save this for future: modified_constructions = []
        for surface in ext_surfaces:
            surface_name = surface.nameString()
            surface_dict[surface_name] = {}
            surface_dict[surface_name]["Surface object"] = surface
            surface_dict[surface_name]["Window to wall ratio"] = surface.windowToWallRatio() #double
            surface_dict[surface_name]["Net area excluding window (m2)"] = surface.netArea() #double
            # obtain layers for each wall construction
            surface_const = surface.construction().get()
            layered_construction = surface_const.to_LayeredConstruction().get()
            for i in range(layered_construction.numLayers()):
                material = layered_construction.getLayer(i)
                material_name = material.nameString()
                runner.registerInfo(f"Layer {i+1}: {material.nameString()}") 
                surface_dict[surface_name][f"layer {i+1}"] = {}
                surface_dict[surface_name][f"layer {i+1}"]["material name"] = material_name
                # distinguish material type by material name
                if "insulation" in material_name:
                    surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = insulation_material_lifetime
                elif "gypsum" in material_name:
                    surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = gypsum_board_lifetime
                elif "concrete" in material_name:
                    surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = precast_concrete_lifetime
                elif "brick" in material_name:
                    surface_dict[surface_name][f"layer {i+1}"]["lifetime"] = brick_lifetime
                else:
                    runner.registerError(f"Unsupported materail type: {material_name}")
                # if the material layer has thickness assigned
                if material.thickness():
                    surface_dict[surface_name][f"layer {i+1}"]["Thickness (m)"] = material.thickness()
                else: # otherweise, assign zero thickness
                    surface_dict[surface_name][f"layer {i+1}"]["Thickness (m)"] = 0.0
                    runner.registerError(f"The material layer: {i+1} has no thickness assigned.")
                # calculate volume for each layer
                surface_dict[surface_name][f"layer {i+1}"]['Volume (m3)'] = material.thickness() * surface.netArea()

        # get EPD data
        product_epds = []
        industrial_epds = []
        brick_product_url = generate_url(material_name = "Brick", epd_type= "Product", endpoint = "materials")
        concrete_product_url = generate_url(material_name = "PrecastConcrete", epd_type= "Product", endpoint = "materials")
        insulation_product_url = generate_url(material_name = "Insulation", epd_type= "Product", endpoint = "materials")
        gypsum_board_product_url = generate_url(material_name = "Gypsum", epd_type= "Product", endpoint = "materials")
        brick_industry_url = generate_url(material_name = "Brick", epd_type= "Industry", endpoint = "industry_epds")
        concrete_industry_url = generate_url(material_name = "PrecastConcrete", epd_type= "Industry", endpoint = "industry_epds")
        insulation_industry_url = generate_url(material_name = "Insulation", epd_type= "Industry", endpoint = "industry_epds")
        gypsum_board_industry_url = generate_url(material_name = "Gypsum", epd_type= "Industry", endpoint = "industry_epds")
        # fetch both product and industrial EPDs from url 
        product_epds.append(fetch_epd_data(url = brick_product_url, api_token = api_key))
        product_epds.append(fetch_epd_data(url = concrete_product_url, api_token = api_key))
        product_epds.append(fetch_epd_data(url = insulation_product_url, api_token = api_key))
        product_epds.append(fetch_epd_data(url = gypsum_board_product_url, api_token = api_key))
        industrial_epds.append(fetch_epd_data(url = brick_industry_url, api_token = api_key))
        industrial_epds.append(fetch_epd_data(url = concrete_industry_url, api_token = api_key))
        industrial_epds.append(fetch_epd_data(url = insulation_industry_url, api_token = api_key))
        industrial_epds.append(fetch_epd_data(url = gypsum_board_industry_url, api_token = api_key))

        epd_datalist = {} # store non-empty epd ensembles with corresponding epd type
        keys = ["brick", "precast concrete", "insulation", "gypsum board"] # following the appending order above
        for key, prod_epd, ind_epd in zip(keys, product_epds, industrial_epds):
            # initialize dict for each key
            if key not in epd_datalist:
                epd_datalist[key] = {}
            if epd_type == "Product": # if user select to use product epds, handle the scenario when product epds are not available
                if test_empty_epd(prod_epd, ind_epd):
                    epd_datalist[key]["EPDs"] = prod_epd
                    epd_datalist[key]["epd_type"] = "Product"
                elif test_empty_epd(prod_epd, ind_epd) == False:
                    epd_datalist[key]["EPDs"] = ind_epd
                    epd_datalist[key]["epd_type"] = "Industrial"
                    runner.registerInfo(f"Product EPDs are not available, industrial EPDs will be used as replacement.")
                else:
                    runner.registerError(f"Both product and industrial EPDs are not available for {key}")
            elif epd_type == "Industrial":
                if test_empty_epd(ind_epd, prod_epd):
                    epd_datalist[key]["EPDs"] = ind_epd
                    epd_datalist[key]["epd_type"] = "Industrial"
                elif test_empty_epd(ind_epd, prod_epd) == False:
                    epd_datalist[key]["EPDs"] = prod_epd
                    epd_datalist[key]["epd_type"] = "Product"
                    runner.registerInfo(f"Industrial EPDs are not available, Product EPDs will be used as replacement.")
                else:
                    runner.registerError(f"Both product and industrial EPDs are not available for {key}")

        # store gwp values per user selected gwp statistics
        gwp_data = {"brick":{
                "gwp_per_m2": 0.0,
                "gwp_per_kg": 0.0,
                "gwp_per_m3": 0.0}, "precast concrete":{
                "gwp_per_m2": 0.0,
                "gwp_per_kg": 0.0,
                "gwp_per_m3": 0.0}, "insulation":{
                "gwp_per_m2": 0.0,
                "gwp_per_kg": 0.0,
                "gwp_per_m3": 0.0}, "gypsum board":{
                "gwp_per_m2": 0.0,
                "gwp_per_kg": 0.0,
                "gwp_per_m3": 0.0}}
        for key in keys: # loop through epd_datalist to get gwp values per different functional units
            epds = epd_datalist.get(key, {}).get("EPDs", [])
            epd_type = epd_datalist.get(key, {}).get("epd_type", None)
            # collect GWP values per functional unit from all EPDs
            gwp_values = {key:{
                "gwp_per_m2": [],
                "gwp_per_kg": [],
                "gwp_per_m3": []}}
            # loop through epds and parse each EPD 
            for epd in epds:
                # parse json repsonse based on epd_eype
                if epd_type == "Industry":
                    parsed_data = parse_industrial_epd(epd)
                elif epd_type == "Product":
                    parsed_data = parse_product_epd(epd)
                else:
                    runner.registerWarning(f"Unknown epd_type '{epd_type}' for {key}")
                    continue
                # extract values by unit, map keys in gwp_values wiht keys in parsed_data
                mapping = {
                    "gwp_per_m2": "gwp_per_m2 (kg CO2 eq/m2)",
                    "gwp_per_kg": "gwp_per_kg (kg CO2 eq/kg)",
                    "gwp_per_m3": "gwp_per_m3 (kg CO2 eq/m3)"
                }
                for unit_key, json_key in mapping.items():
                    value = parsed_data.get(json_key)
                    if value is not None:
                        gwp_values[key][unit_key].append(float(value))
                # extract gwp statistics  
                for unit_key, list in gwp_values[key].items():
                    if len(list) == 0:
                        runner.registerInfo(f"No GWP values returned from {unit_key}")
                    elif len(list) == 1:
                        gwp_data[key][unit_key] = list[0]
                    elif gwp_statistic == "minimum":
                        gwp_data[key][unit_key] = float(np.min(list))
                    elif gwp_statistic == "maximum":
                        gwp_data[key][unit_key] = float(np.max(list))
                    elif gwp_statistic == "mean":
                        gwp_data[key][unit_key] = float(np.mean(list))
                    elif gwp_statistic == "median":
                        gwp_data[key][unit_key] = float(np.median(list))
                    else:
                        runner.registerError(f"Unsupported gwp_statistic: {gwp_statistic}")
                    
        # assign gwp values to each layer in wall construction based on each layer's material name
        for surface_name, surface_data in surface_dict.items():
            total_embodied_carbon = 0.0
            for layer_key, layer_data in surface_data.items():
                if layer_key.startswith("layer") and isinstance(layer_data, dict):
                    material_name = layer_data.get("material name", "").lower()
                    matched = [k for k in keys if k in material_name]
                    if matched:
                        match_key = matched[0]
                        print(f"{surface_name} - {layer_key}: {material_name} → matched: {matched[0]}")
                        surface_dict[surface_name][layer_key]["GWP values"] = {} 
                        surface_dict[surface_name][layer_key]["GWP values"] = gwp_data[match_key]
                    # calcualte embodied carbon of each wall construction (surface)
                    volume = layer_data.get("Volume (m3)", 0.0)
                    gwp_per_m3 = layer_data.get("GWP values", {}).get("gwp_per_m3", 0.0)
                    embodied_carbon = volume * gwp_per_m3
                    layer_data["embodied carbon"] = embodied_carbon 
                    total_embodied_carbon += embodied_carbon
            surface_data["Wall embodied carbon"] = total_embodied_carbon

            # attach additional properties to openstudio material
            additional_properties = surface_data["Surface object"].additionalProperties()
            additional_properties.setFeature("Subsurface name", surface_name)
            additional_properties.setFeature("Embodied carbon", surface_data["Wall embodied carbon"])

            # if "brick" in key and surface
            #     surface_dict[surface_name]

            #         if analysis_period <= surface_dict[surface_name][f"layer {i+1}"]["Lifetime"]:
            #             embodied_carbon = float(surface_dict[surface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["Volume (m3)"])
            #             subsurface_dict[subsurface_name][material_name]["embodied_carbon"] = embodied_carbon
            #         else:
            #             multiplier = np.ceil(analysis_period/subsurface_dict[subsurface_name][material_name]["Lifetime"])
            #             embodied_carbon = float(subsurface_dict[subsurface_name][material_name]["gwp_per_m3"] * subsurface_dict[subsurface_name][material_name]["Volume (m3)"] * multiplier)
            #             subsurface_dict[subsurface_name][material_name]["embodied_carbon"] = embodied_carbon
                        
        pp.pprint(surface_dict)
        # save the following for future, do baseline calculation first
        # for name, construction in constructions.items():
        #     layers = construction.layers()
        #     #max_r_value = 0
        #     insul_index = -1

        #     for i, mat in enumerate(layers):
        #         opaque_mat = mat.to_OpaqueMaterial()
        #         if opaque_mat.is_initialized():
        #             r_val = opaque_mat.get().thermalResistance()
        #             if r_val > max_r_value:
        #                 max_r_value = r_val
        #                 insul_index = i

        #     if insul_index == -1:
        #         runner.registerInfo(f"No insulation material found in construction: {name}")
        #         continue

        #     if max_r_value >= r_value_si and not allow_reduction:
        #         runner.registerInfo(f"Construction '{name}' already meets or exceeds the target R-value.")
        #         continue

        #     new_construction = construction.clone(model).to_Construction().get()
        #     new_mat = layers[insul_index].clone(model).to_OpaqueMaterial().get()
        #     new_mat.setThermalResistance(r_value_si)
        #     new_construction.setLayer(insul_index, new_mat)
        #     #modified_constructions.append(new_construction)

        #     if material_cost_ip > 0:
        #         openstudio.model.LifeCycleCost.createLifeCycleCost(
        #             "LCC_Material", new_construction, material_cost_si,
        #             "CostPerArea", "Construction", 20, 0
        #         )

        #     if one_time_cost_ip > 0:
        #         openstudio.model.LifeCycleCost.createLifeCycleCost(
        #             "LCC_OneTime", new_construction, one_time_cost_si,
        #             "CostPerArea", "Construction", 0, years_until_cost
        #         )

        #     for surface in ext_surfaces:
        #         if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
        #             surface.setConstruction(new_construction)

        # runner.registerFinalCondition(
        #     f"Modified {len(modified_constructions)} construction(s) to meet target R-value of {r_value_ip} ft²·h·°F/Btu."
        # )
        return True

# Register the measure
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
