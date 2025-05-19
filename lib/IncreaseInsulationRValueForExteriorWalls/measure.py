import openstudio

class IncreaseWallInsulationWithMaterialChoice(openstudio.measure.ModelMeasure):
    def name(self):
        return "Increase Wall Insulation Using Selected Material"

    def description(self):
        return "Raises exterior wall insulation R-value to a user-defined target using selected insulation material."

    def modeler_description(self):
        return ("This measure identifies insulation layers in exterior wall constructions, compares existing "
                "R-values to a user-specified target, and if needed, adds additional insulation using the selected "
                "material. It also calculates the required thickness and volume of insulation.")

    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        # User input for desired R-value (in IP units)
        r_value = openstudio.measure.OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Target R-value (ft²·h·°F/Btu)")
        r_value.setDefaultValue(13.0)
        args.append(r_value)

        # Dropdown list of available insulation materials
        material_choices = ["Fiberglass batt", "Blown-in cellulose", "Blown-in fiberglass", "Spray foam", "Mineral wool"]
        retrofit_material = openstudio.measure.OSArgument.makeChoiceArgument("retrofit_material", material_choices, True)
        retrofit_material.setDisplayName("Chosen Retrofit Material")
        retrofit_material.setDefaultValue("Fiberglass batt")
        args.append(retrofit_material)

        # Boolean to allow decreasing R-value if current insulation is better
        allow_reduction = openstudio.measure.OSArgument.makeBoolArgument("allow_reduction", True)
        allow_reduction.setDisplayName("Allow reduction in R-value if current value is higher?")
        allow_reduction.setDefaultValue(False)
        args.append(allow_reduction)

        return args

    def run(self, model, runner, user_arguments):
        # Validate that all user arguments are present and correct
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Retrieve user inputs
        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        material_name = runner.getStringArgumentValue("retrofit_material", user_arguments)
        allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)

        # Validate R-value input
        if r_value_ip <= 0:
            runner.registerError("Target R-value must be greater than 0.")
            return False

        # Convert R-value from IP to SI units (m²·K/W)
        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()

        # Define typical thermal conductivity (k) values in W/m-K for each material
        material_k_dict = {
            "Fiberglass batt": 0.045,
            "Blown-in cellulose": 0.042,
            "Blown-in fiberglass": 0.053,
            "Spray foam": 0.025,
            "Mineral wool": 0.040
        }

        # Lookup selected material's thermal conductivity
        selected_k = material_k_dict[material_name]

        # Store exterior wall surfaces and constructions to be modified
        ext_surfaces = []
        constructions = {}

        # Iterate through all surfaces in the model
        for surface in model.getSurfaces():
            # Filter to exterior walls only
            if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
                ext_surfaces.append(surface)
                # Get associated construction, if present
                if surface.construction().is_initialized():
                    construction = surface.construction().get()
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

            # Skip update if construction already meets or exceeds target R-value (and no reduction is allowed)
            if max_r >= r_value_si and not allow_reduction:
                runner.registerInfo(f"'{name}' already meets or exceeds the R-value target.")
                continue

            # Calculate additional R-value needed
            delta_r = max(0, r_value_si - max_r)

            # Calculate additional thickness required (R = d/k => d = R * k)
            required_thickness = delta_r * selected_k

            # Calculate total area of walls using this construction
            area_m2 = sum([s.grossArea() for s in ext_surfaces if s.construction().get().nameString() == name])

            # Volume = thickness * area
            volume_m3 = area_m2 * required_thickness

            # Report to user
            runner.registerInfo(f"'{material_name}' selected. Required added thickness: {required_thickness:.4f} m. Total volume needed: {volume_m3:.2f} m³.")

            # Clone the original construction for modification
            new_construction = construction.clone(model).to_Construction().get()

            # Create new insulation material with the needed R-value
            new_insul = openstudio.model.MasslessOpaqueMaterial(model)
            new_insul.setName(f"{material_name}_Added")
            new_insul.setThermalResistance(delta_r)

            # Insert new insulation layer after the existing insulation
            layer_list = new_construction.layers()
            layer_list.insert(insul_index + 1, new_insul)
            new_construction.setLayers(layer_list)

            # Replace the construction on each surface using the original one
            for surface in ext_surfaces:
                if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
                    surface.setConstruction(new_construction)

            modified_constructions.append(new_construction)

        # Final summary message
        runner.registerFinalCondition(f"Modified {len(modified_constructions)} constructions using '{material_name}' to reach target R-value of {r_value_ip}.")

        return True


# Register the measure with OpenStudio
IncreaseWallInsulationWithMaterialChoice().registerWithApplication()
