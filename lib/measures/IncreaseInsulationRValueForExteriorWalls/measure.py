# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio


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
        return ["x","C","F"]

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
        gwp_statistics_chs.append("single_value")
        gwp_statistic = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic",gwp_statistics_chs, True)
        gwp_statistic.setDisplayName("GWP Statistic") 
        gwp_statistic.setDescription("Statistic type (minimum or maximum or mean or single value) of returned GWP value")
        gwp_statistic.setDefaultValue("single_value")
        args.append(gwp_statistic)

        total_embodied_carbon = openstudio.measure.OSArgument.makeDoubleArgument("total_embodied_carbon", True)
        total_embodied_carbon.setDisplayName("Total Embodeid Carbon of Building/Building Assembly")
        total_embodied_carbon.setDescription("Total GWP or embodied carbon intensity of the building (assembly) in kg CO2 eq.")
        total_embodied_carbon.setDefaultValue(0.0)
        args.append(total_embodied_carbon)

        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key",True)
        api_key.setDisplayName("API Token")
        api_key.setDescription("API Token for sending API call to EC3 EPD Database")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

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
        gypsum_board_fr = openstudio.measure.OSArgument.makeChoiceArgument("gypsum_board_fr", gypsum_board_type_chs, True)
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
        total_embodied_carbon = runner.getDoubleArgumentValue("total_embodied_carbon",user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        epd_type = runner.getStringArgumentValue("epd_type", user_arguments)
        # Material properties:
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_application_type = runner.getStringArgumentValue("insulation_application_type", user_arguments)
        insulation_material_lifetime = runner.getStringArgumentValue("insulation_material_lifetime", user_arguments)
        precast_concrete_type = runner.getStringArgumentValue("precast_concrete_type", user_arguments)
        precast_concrete_lifetime = runner.getStringArgumentValue("precast_concrete_lifetime", user_arguments)
        brick_lifetime = runner.getStringArgumentValue("brick_lifetime", user_arguments)
        gypsum_board_type = runner.getStringArgumentValue("gypsum_board_type", user_arguments)
        gypsum_board_fr = runner.getStringArgumentValue("gypsum_board_fr", user_arguments)
        gypsum_board_lifetime = runner.getStringArgumentValue("gypsum_board_lifetime", user_arguments)

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

        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()
        material_cost_si = openstudio.convert(material_cost_ip, "1/ft^2", "1/m^2").get()
        one_time_cost_si = openstudio.convert(one_time_cost_ip, "1/ft^2", "1/m^2").get()

        ext_surfaces = []
        constructions = {}

        for surface in model.getSurfaces():
            if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
                ext_surfaces.append(surface)
                if surface.construction().is_initialized():
                    construction = surface.construction().get()
                    constructions[construction.nameString()] = construction

        if not ext_surfaces:
            runner.registerAsNotApplicable("No exterior wall surfaces found.")
            return True

        modified_constructions = []
        for name, construction in constructions.items():
            layers = construction.layers()
            max_r_value = 0
            insul_index = -1

            for i, mat in enumerate(layers):
                opaque_mat = mat.to_OpaqueMaterial()
                if opaque_mat.is_initialized():
                    r_val = opaque_mat.get().thermalResistance()
                    if r_val > max_r_value:
                        max_r_value = r_val
                        insul_index = i

            if insul_index == -1:
                runner.registerInfo(f"No insulation material found in construction: {name}")
                continue

            if max_r_value >= r_value_si and not allow_reduction:
                runner.registerInfo(f"Construction '{name}' already meets or exceeds the target R-value.")
                continue

            new_construction = construction.clone(model).to_Construction().get()
            new_mat = layers[insul_index].clone(model).to_OpaqueMaterial().get()
            new_mat.setThermalResistance(r_value_si)
            new_construction.setLayer(insul_index, new_mat)
            modified_constructions.append(new_construction)

            if material_cost_ip > 0:
                openstudio.model.LifeCycleCost.createLifeCycleCost(
                    "LCC_Material", new_construction, material_cost_si,
                    "CostPerArea", "Construction", 20, 0
                )

            if one_time_cost_ip > 0:
                openstudio.model.LifeCycleCost.createLifeCycleCost(
                    "LCC_OneTime", new_construction, one_time_cost_si,
                    "CostPerArea", "Construction", 0, years_until_cost
                )

            for surface in ext_surfaces:
                if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
                    surface.setConstruction(new_construction)

        runner.registerFinalCondition(
            f"Modified {len(modified_constructions)} construction(s) to meet target R-value of {r_value_ip} ft²·h·°F/Btu."
        )
        return True


# Register the measure
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
