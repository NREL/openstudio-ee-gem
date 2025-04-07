# frozen_string_literal: true

# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
from openstudio import Quantity, Unit
from openstudio.measure import ModelMeasure, OSArgument, OSArgumentVector
from openstudio.model import LifeCycleCost, Construction, Material

class IncreaseInsulationRValueForExteriorWalls(ModelMeasure):
    def name(self):
        return "Increase R-value of Insulation for Exterior Walls to a Specific Value"

    def arguments(self, model):
        args = OSArgumentVector()

        r_value = OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Insulation R-value (ft^2*h*R/Btu).")
        r_value.setDefaultValue(13.0)
        args.append(r_value)

        allow_reduction = OSArgument.makeBoolArgument("allow_reduction", True)
        allow_reduction.setDisplayName("Allow both increase and decrease in R-value to reach requested target?")
        allow_reduction.setDefaultValue(False)
        args.append(allow_reduction)

        material_cost = OSArgument.makeDoubleArgument("material_cost_increase_ip", True)
        material_cost.setDisplayName("Increase in Material and Installation Costs ($/ft^2).")
        material_cost.setDefaultValue(0.0)
        args.append(material_cost)

        one_time_cost = OSArgument.makeDoubleArgument("one_time_retrofit_cost_ip", True)
        one_time_cost.setDisplayName("One Time Retrofit Cost ($/ft^2).")
        one_time_cost.setDefaultValue(0.0)
        args.append(one_time_cost)

        years_until_cost = OSArgument.makeIntegerArgument("years_until_retrofit_cost", True)
        years_until_cost.setDisplayName("Year to Incur One Time Retrofit Cost")
        years_until_cost.setDefaultValue(0)
        args.append(years_until_cost)

        return args

    def run(self, model, runner, user_arguments):
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)
        material_cost_ip = runner.getDoubleArgumentValue("material_cost_increase_ip", user_arguments)
        one_time_cost_ip = runner.getDoubleArgumentValue("one_time_retrofit_cost_ip", user_arguments)
        years_until_cost = runner.getIntegerArgumentValue("years_until_retrofit_cost", user_arguments)

        if r_value_ip < 0 or r_value_ip > 500:
            runner.registerError("R-value out of bounds.")
            return False

        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()
        material_cost_si = openstudio.convert(material_cost_ip, "1/ft^2", "1/m^2").get()
        one_time_cost_si = openstudio.convert(one_time_cost_ip, "1/ft^2", "1/m^2").get()

        ext_surfaces = []
        constructions = {}
        for surface in model.getSurfaces():
            if surface.surfaceType() == "Wall" and surface.outsideBoundaryCondition() == "Outdoors":
                ext_surfaces.append(surface)
                construction = surface.construction().get()
                constructions[construction.nameString()] = construction

        if not ext_surfaces:
            runner.registerAsNotApplicable("No exterior walls found.")
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
                runner.registerInfo(f"No valid insulation found in {name}")
                continue

            if max_r_value >= r_value_si and not allow_reduction:
                runner.registerInfo(f"{name} already meets/exceeds R-value.")
                continue

            new_construction = construction.clone(model).to_Construction().get()
            new_mat = layers[insul_index].clone(model).to_OpaqueMaterial().get()
            new_mat.setThermalResistance(r_value_si)
            new_construction.setLayer(insul_index, new_mat)
            modified_constructions.append(new_construction)

            if material_cost_ip > 0:
                LifeCycleCost.createLifeCycleCost("LCC_Material", new_construction, material_cost_si, "CostPerArea", "Construction", 20, 0)

            if one_time_cost_ip > 0:
                LifeCycleCost.createLifeCycleCost("LCC_OneTime", new_construction, one_time_cost_si, "CostPerArea", "Construction", 0, years_until_cost)

            for surface in ext_surfaces:
                if surface.construction().is_initialized() and surface.construction().get().nameString() == name:
                    surface.setConstruction(new_construction)

        runner.registerFinalCondition(f"Modified {len(modified_constructions)} constructions with target R-value of {r_value_ip}.")
        return True


# Register the measure to OpenStudio
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
