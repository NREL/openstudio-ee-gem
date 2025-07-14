from pathlib import Path

# # Restructured version of the script for running the measure
# def run_measure():
#     import openstudio
#     from measure import IncreaseInsulationRValueForExteriorWalls

#     CURRENT_DIR_PATH = Path(__file__).parent.absolute()
#     model_path = CURRENT_DIR_PATH / "tests/example_model.osm"
#     save_path = CURRENT_DIR_PATH / "tests/output/example_model_with_rvalue_upgrade.osm"

#     # Load the model
#     translator = openstudio.osversion.VersionTranslator()
#     model = translator.loadModel(openstudio.toPath(str(model_path))).get()

#     # Create runner and measure instance
#     osw = openstudio.WorkflowJSON()
#     runner = openstudio.measure.OSRunner(osw)
#     measure = IncreaseInsulationRValueForExteriorWalls()

#     # Setup arguments
#     args = measure.arguments(model)
#     arg_map = openstudio.measure.convertOSArgumentVectorToMap(args)

#     def set_arg(name, value):
#         if name in arg_map:
#             arg = arg_map[name]
#             arg.setValue(value)
#             arg_map[name] = arg

#     # Set required and optional inputs (only those defined in your measure)
#     set_arg("r_value", 60.0)
#     set_arg("api_key", "Obtain the key from EC3 website")  # Example placeholder
#     set_arg("epd_type", "Product")
#     set_arg("insulation_material_type", "Fiberglass batt")
#     set_arg("insulation_material_lifetime", 30)
#     set_arg("precast_concrete_type", "lightweight")
#     set_arg("precast_concrete_lifetime", 30)
#     set_arg("brick_lifetime", 30)
#     set_arg("gypsum_board_type", "moisture_resistant")
#     set_arg("gypsum_board_fr", "X")
#     set_arg("gypsum_board_lifetime", 30)

#     # Run the measure
#     result = measure.run(model, runner, arg_map)

#     # Display results
#     print("RESULT:", runner.result().value().valueName())
#     for info in runner.result().info():
#         print("INFO:", info.logMessage())
#     for warning in runner.result().warnings():
#         print("WARNING:", warning.logMessage())
#     for error in runner.result().errors():
#         print("ERROR:", error.logMessage())

#     # Save modified model
#     model.save(openstudio.toPath(str(save_path)), True)

#     # Clean up
#     del model

# # Uncomment the following to run as a script
# if __name__ == "__main__":
#     run_measure()


####################################################################


from resources.EC3_lookup import *
import urllib3
import pprint as pp
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ["Fiberglass batt", "Blown-in cellulose", "Blown-in fiberglass", "Spray foam", "Mineral wool"]


insulation_data = {
    "Mineral Wool": "Mineral%20Wool",
    "Cellulose": "Cellulose",
    "Fiberglass": "Fiberglass",
    "Expanded Polystyrene (EPS)": "EPS",
    "Extruded Polystyrene (XPS)": "XPS",
    "Graphite Polystyrene (GPS)": "GPS",
    "Polyiso (iso)": "ISO",
    "Expanded Polyethylene": "Expanded%20Polyethylene",
    "Other": "Other"
}


insulation_material_type = list(insulation_data.values())[0]

print('**************************')
print(insulation_material_type)
print('**************************')
# insulation_material_type = "Cellulose" #"Fiberglass batt"
insulation_application_type = "Exterior%20Wall"
api_key = '5fk7wP4cJg6pcmx6ncZN0ftMdoVR8u'
product_epds = []
material_name = "Insulation"


# Collecting parsed industrial EPDs into a list
epd_summary = []


product_url = generate_url(material_name=material_name, endpoint="materials", epd_type="Product", insulation_application=insulation_application_type, insulation_material=insulation_material_type, page_size=100)
industry_url = generate_url(material_name=material_name, endpoint="industry_epds", epd_type="Industry", insulation_application=insulation_application_type, insulation_material=insulation_material_type, page_size=100)


product_epd_data = fetch_epd_data(product_url,API_TOKEN) 
industrial_epd_data = fetch_epd_data(industry_url,API_TOKEN)
# print(f"Number of  product EPDs for {name}: {len(product_epd_data)}")
pp.pprint(product_epd_data)
# print(f"Number of  industrial EPDs for {name}: {len(industrial_epd_data)}")
for idx, epd in enumerate(product_epd_data, start=1):
    parsed_data = parse_product_epd(epd)
    # print(epd)
    # print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

    epd_summary.append({
        "epd_name": parsed_data.get("epd_name"),
        "mass_per_declared_unit": parsed_data.get("mass_per_declared_unit"),
        "gwp_per_m2 (kg CO2 eq/m2)": parsed_data.get("gwp_per_m2 (kg CO2 eq/m2)"),
        "gwp_per_m3 (kg CO2 eq/m3)": parsed_data.get("gwp_per_m3 (kg CO2 eq/m3)"),
        "gwp_per_kg (kg CO2 eq/kg)": parsed_data.get("gwp_per_kg (kg CO2 eq/kg)"),
        "density (kg/m3)": parsed_data.get("density")

    })

for idx, epd in enumerate(industrial_epd_data, start=1):
    parsed_data = parse_industrial_epd(epd)
    # print(f"Industrial EPD #{idx}: {json.dumps(parsed_data, indent=4)}")

    epd_summary.append({
        "epd_name": parsed_data.get("epd_name"),
        "mass_per_declared_unit": parsed_data.get("mass_per_declared_unit"),
        "gwp_per_m2 (kg CO2 eq/m2)": parsed_data.get("gwp_per_m2 (kg CO2 eq/m2)"),
        "gwp_per_m3 (kg CO2 eq/m3)": parsed_data.get("gwp_per_m3 (kg CO2 eq/m3)"),
        "gwp_per_kg (kg CO2 eq/kg)": parsed_data.get("gwp_per_kg (kg CO2 eq/kg)"),
        "density (kg/m3)": parsed_data.get("density")
    })

# Create DataFrame
df_epd_summary = pd.DataFrame(epd_summary)

# Display DataFrame
# print(df_epd_summary.head(50))






# # Discover available insulating_material values
# # url = generate_url(material_name="Insulation", endpoint="materials", epd_type="Product", insulation_application=None, insulation_material=None)
# url = generate_url(material_name="Insulation", endpoint="materials", epd_type="Product", insulation_application='Exterior%20Wall', insulation_material=None)
# epds = fetch_epd_data(url, api_key)

# for idx, epd in enumerate(epds, start=1):
#     parsed_data = parse_product_epd(epds)
#     print(f"Product EPD #{idx}: {json.dumps(parsed_data, indent=4)}")


# # Print out all unique insulating_material values
# materials = set()
# for epd in epds:
#     mat = epd.get("insulating_material")
#     if mat:
#         materials.add(mat)

# pp.pprint(sorted(materials))





# # Discover available insulating_material values
# # url = generate_url(material_name="Insulation", endpoint="materials", epd_type="Industry", insulation_application=None, insulation_material=None)
# url = generate_url(name, endpoint="industry_epds", epd_type="Industry")

# epds = fetch_epd_data(url, api_key)

# # Print out all unique insulating_material values
# materials = set()
# for epd in epds:
#     mat = epd.get("insulating_material")
#     if mat:
#         materials.add(mat)

# pp.pprint(sorted(materials))



# insulation_product_url = generate_url(material_name = "Insulation", epd_type= "Product", endpoint = "materials", insulation_material = insulation_material_type, insulation_application = insulation_application_type)
# # print(insulation_product_url)

# product_epds.append(fetch_epd_data(url = insulation_product_url, api_token = api_key))








# brick_product_url = generate_url(material_name = "Brick", epd_type= "Product", endpoint = "materials")
# product_epds.append(fetch_epd_data(url = brick_product_url, api_token = api_key))  

# # pp.pprint(fetch_epd_data(url = brick_product_url, api_token = api_key))

# keys = ["brick"] # following the appending order above


# gwp_data_product = compute_gwp_data(keys, product_epds, "Product", "median")
# print(gwp_data_product)


# # get EPD data
# product_epds = []
# industrial_epds = []
# brick_product_url = generate_url(material_name = "Brick", epd_type= "Product", endpoint = "materials")
# concrete_product_url = generate_url(material_name = "PrecastConcrete", epd_type= "Product", endpoint = "materials")
# gypsum_board_product_url = generate_url(material_name = "Gypsum", epd_type= "Product", endpoint = "materials")
# brick_industry_url = generate_url(material_name = "Brick", epd_type= "Industry", endpoint = "industry_epds")
# concrete_industry_url = generate_url(material_name = "PrecastConcrete", epd_type= "Industry", endpoint = "industry_epds")
# insulation_industry_url = generate_url(material_name = "Insulation", epd_type= "Industry", endpoint = "industry_epds", insulation_material = insulation_material_type, insulation_application = insulation_application_type)
# gypsum_board_industry_url = generate_url(material_name = "Gypsum", epd_type= "Industry", endpoint = "industry_epds")

# # fetch both product and industrial EPDs from url 
# product_epds.append(fetch_epd_data(url = brick_product_url, api_token = api_key))
# product_epds.append(fetch_epd_data(url = concrete_product_url, api_token = api_key))
# product_epds.append(fetch_epd_data(url = insulation_product_url, api_token = api_key))
# product_epds.append(fetch_epd_data(url = gypsum_board_product_url, api_token = api_key))
# industrial_epds.append(fetch_epd_data(url = brick_industry_url, api_token = api_key))
# industrial_epds.append(fetch_epd_data(url = concrete_industry_url, api_token = api_key))
# industrial_epds.append(fetch_epd_data(url = insulation_industry_url, api_token = api_key))
# industrial_epds.append(fetch_epd_data(url = gypsum_board_industry_url, api_token = api_key))

# keys = ["brick", "precast concrete", "insulation", "gypsum board"] # following the appending order above
# gwp_data_product = compute_gwp_data(keys, product_epds, "Product", gwp_statistic)
# gwp_data_industrial = compute_gwp_data(keys, industrial_epds, "Industrial", gwp_statistic)

# # dictionary holder for non-zero gwp values
# final_gwp_data = {}
# # recording EPD type actually used
# final_epd_type = {}
# for key in keys:
# prod_val = gwp_data_product[key]["gwp_per_m3"]
# ind_val = gwp_data_industrial[key]["gwp_per_m3"]
# # if user choose product epds
# if epd_type == "Product":
#     if prod_val != 0.0:
#         final_gwp_data[key] = gwp_data_product[key]
#         final_epd_type[key] = "Product"
#     elif ind_val != 0.0:
#         final_gwp_data[key] = gwp_data_industrial[key]
#         final_epd_type[key] = "Industrial"
#         runner.registerInfo(f"{key}: Product gwp_per_m3 is 0.0. Using Industrial EPD instead.")
#     else:
#         final_gwp_data[key] = gwp_data_product[key]  # fallback, both are 0
#         final_epd_type[key] = "Product"
#         runner.registerWarning(f"{key}: Both Product and Industrial gwp_per_m3 are 0.0.")
# # if user choose industrial epds
# elif epd_type == "Industrial":
#     if ind_val != 0.0:
#         final_gwp_data[key] = gwp_data_industrial[key]
#         final_epd_type[key] = "Industrial"
#     elif prod_val != 0.0:
#         final_gwp_data[key] = gwp_data_product[key]
#         final_epd_type[key] = "Product"
#         runner.registerInfo(f"{key}: Industrial gwp_per_m3 is 0.0. Using Product EPD instead.")
#     else:
#         final_gwp_data[key] = gwp_data_industrial[key]  # fallback, both are 0
#         final_epd_type[key] = "Industrial"
#         runner.registerWarning(f"{key}: Both Industrial and Product gwp_per_m3 are 0.0.")

# for surface_name, surface_data in surface_dict.items():
# total_embodied_carbon = 0.0
# for layer_key, layer_data in surface_data.items():
#     if layer_key.startswith("layer") and isinstance(layer_data, dict):
#         material_name = layer_data.get("material name", "").lower()
#         matched = [k for k in keys if k in material_name]
#         if matched:
#             match_key = matched[0]
#             print(f"{surface_name} - {layer_key}: {material_name} → matched: {matched[0]}")
#             surface_dict[surface_name][layer_key]["GWP values"] = {} 
#             surface_dict[surface_name][layer_key]["GWP values"] = final_gwp_data[match_key]
#         # calcualte embodied carbon of each wall construction (surface) (product lifetime is not counted here)
#         volume = layer_data.get("Volume (m3)", 0.0)
#         gwp_per_m3 = layer_data.get("GWP values", {}).get("gwp_per_m3", 0.0)
#         embodied_carbon = volume * gwp_per_m3
#         layer_data["embodied carbon"] = embodied_carbon 
#         total_embodied_carbon += embodied_carbon
# surface_data["Wall embodied carbon"] = total_embodied_carbon

# # attach additional properties to openstudio material
# additional_properties = surface_data["Surface object"].additionalProperties()
# additional_properties.setFeature("Subsurface name", surface_name)
# additional_properties.setFeature("Embodied carbon", surface_data["Wall embodied carbon"])
    
# pp.pprint(surface_dict)
# save the following for future, do baseline calculation first
# for name, construction in constructions.items():
# layers = construction.layers()
# #max_r_value = 0
# insul_index = -1

# for i, mat in enumerate(layers):
#     opaque_mat = mat.to_OpaqueMaterial()
#     if opaque_mat.is_initialized():
#         r_val = opaque_mat.get().thermalResistance()
#         if r_val > max_r_value:
#             max_r_value = r_val
#             insul_index = i

# if insul_index == -1:
#     runner.registerInfo(f"No insulation material found in construction: {name}")
#     continue

# if max_r_value >= r_value_si and not allow_reduction:
#     runner.registerInfo(f"Construction '{name}' already meets or exceeds the target R-value.")
#     continue

# new_construction = construction.clone(model).to_Construction().get()
# new_mat = layers[insul_index].clone(model).to_OpaqueMaterial().get()
# new_mat.setThermalResistance(r_value_si)
# new_construction.setLayer(insul_index, new_mat)
# #modified_constructions.append(new_construction)

# if material_cost_ip > 0:
#     openstudio.model.LifeCycleCost.createLifeCycleCost(
#         "LCC_Material", new_construction, material_cost_si,
#         "CostPerArea", "Construction", 20, 0
#     )

# if one_time_cost_ip > 0:
#     openstudio.model.LifeCycleCost.createLifeCycleCost(
#         "LCC_OneTime", new_construction, one_time_cost_si,
#         "CostPerArea", "Construction", 0, years_until_cost
#     )

# for surface in ext_surfaces:
#     if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
#         surface.setConstruction(new_construction)

