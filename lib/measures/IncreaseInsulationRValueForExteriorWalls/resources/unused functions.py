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

    # def calculate_total_gwp_with_density_fallback(self, epd_data, insulated_surface_area_m2, insulated_surface_thickness_m, material_name=None):
    #     """
    #     Calculates total embodied carbon (kg CO2 eq) for insulation surface.
    #     Tries:
    #       1) Mass-based using EPD density if available
    #       2) Mass-based using typical density by material if EPD data is missing
    #       3) Falls back to area × gwp_per_m2 assuming it's for installed thickness
    #     """

    #     gwp_per_m2 = float(epd_data.get("gwp_per_m2", 0) or 0)
    #     gwp_per_kg = float(epd_data.get("gwp_per_kg", 0) or 0)

    #     # Try mass-based from EPD density
    #     density_str = epd_data.get("density")
    #     if density_str and density_str.lower() != 'none':
    #         density_kgm3 = float(density_str.split()[0])
    #         volume_m3 = insulated_surface_area_m2 * insulated_surface_thickness_m
    #         mass_kg = volume_m3 * density_kgm3
    #         return mass_kg * gwp_per_kg
    #     else:
    #         density_kgm3 = material_density_dict.get(material_name, material_density_dict["Other"])
    #         volume_m3 = insulated_surface_area_m2 * insulated_surface_thickness_m
    #         mass_kg = volume_m3 * density_kgm3
    #         return mass_kg * gwp_per_kg