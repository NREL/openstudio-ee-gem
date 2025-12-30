# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio

class IncreaseInsulationRValueForRoofs(openstudio.measure.ModelMeasure):
    # ---- Metadata ----
    def name(self):
        return "Increase R-value of Insulation for Roofs to a Specific Value"

    def description(self):
        return ("Adjusts insulation layers in roof/ceiling constructions exposed "
                "to outdoors to reach a target R-value. Optionally adds cost data.")

    def modeler_description(self):
        return ("Finds the roof insulation layer (preferring massless materials; "
                "otherwise the layer with highest R per thickness), clones the construction, "
                "and edits that layer to achieve a user-specified R-value. Can optionally "
                "add/adjust LifeCycleCost objects and swap default construction sets.")

    # ---- Helpers ----
    @staticmethod
    def _unit_convert(value, from_u, to_u):
        """Convert units via OpenStudio; returns float."""
        return openstudio.convert(value, from_u, to_u).get()

    @staticmethod
    def _neat_numbers(number, roundto=2):
        """Format with commas and 0/2 decimals."""
        if roundto == 2:
            number = float(f"{number:.2f}")
            s = f"{number:,.2f}"
        else:
            s = f"{round(number):,}"
        return s

    # ---- Arguments ----
    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        r_value = openstudio.measure.OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Insulation R-value (ft^2*h*R/Btu).")
        r_value.setDefaultValue(30.0)
        args.append(r_value)

        allow_reduction = openstudio.measure.OSArgument.makeBoolArgument("allow_reduction", True)
        allow_reduction.setDisplayName("Allow both increase and decrease in R-value to reach requested target?")
        allow_reduction.setDefaultValue(False)
        args.append(allow_reduction)

        material_cost_increase_ip = openstudio.measure.OSArgument.makeDoubleArgument("material_cost_increase_ip", True)
        material_cost_increase_ip.setDisplayName("Increase in Material and Installation Costs for Construction per Area Used ($/ft^2).")
        material_cost_increase_ip.setDefaultValue(0.0)
        args.append(material_cost_increase_ip)

        one_time_retrofit_cost_ip = openstudio.measure.OSArgument.makeDoubleArgument("one_time_retrofit_cost_ip", True)
        one_time_retrofit_cost_ip.setDisplayName("One Time Retrofit Cost to Add Insulation to Construction ($/ft^2).")
        one_time_retrofit_cost_ip.setDefaultValue(0.0)
        args.append(one_time_retrofit_cost_ip)

        years_until_retrofit_cost = openstudio.measure.OSArgument.makeIntegerArgument("years_until_retrofit_cost", True)
        years_until_retrofit_cost.setDisplayName("Year to Incur One Time Retrofit Cost (whole years).")
        years_until_retrofit_cost.setDefaultValue(0)
        args.append(years_until_retrofit_cost)

        return args

    # ---- Core ----
    def run(self, model, runner, user_arguments):
        super(type(self), self).run(model, runner, user_arguments)

        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Inputs
        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        allow_reduction = runner.getBoolArgumentValue("allow_reduction", user_arguments)
        material_cost_increase_ip = runner.getDoubleArgumentValue("material_cost_increase_ip", user_arguments)
        one_time_retrofit_cost_ip = runner.getDoubleArgumentValue("one_time_retrofit_cost_ip", user_arguments)
        years_until_retrofit_cost = runner.getIntegerArgumentValue("years_until_retrofit_cost", user_arguments)

        # Reasonableness checks
        min_expected_r_value_ip = 1.0
        if (r_value_ip < 0.0) or (r_value_ip > 500.0):
            runner.registerError(f"The requested roof insulation R-value of {r_value_ip} ft^2*h*R/Btu was above the measure limit.")
            return False
        elif r_value_ip > 60.0:
            runner.registerWarning(f"The requested roof insulation R-value of {r_value_ip} ft^2*h*R/Btu is abnormally high.")
        elif r_value_ip < min_expected_r_value_ip:
            runner.registerWarning(f"The requested roof insulation R-value of {r_value_ip} ft^2*h*R/Btu is abnormally low.")

        if (years_until_retrofit_cost < 0) or (years_until_retrofit_cost > 100):
            runner.registerError("Year to incur one time retrofit cost should be a non-negative integer less than or equal to 100.")
            return False

        # Conversions
        r_value_si = self._unit_convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W")
        material_cost_increase_si = self._unit_convert(material_cost_increase_ip, "1/ft^2", "1/m^2")

        # Gather exterior roof surfaces and unique constructions
        exterior_surfaces = []
        unique_constructions = {}
        roof_R_overall = []

        for srf in model.getSurfaces():
            if srf.outsideBoundaryCondition() == "Outdoors" and srf.surfaceType() == "RoofCeiling":
                exterior_surfaces.append(srf)
                if srf.construction().is_initialized():
                    c = srf.construction().get()
                    name = c.nameString()
                    if name not in unique_constructions:
                        # ensure basic Construction (layered)
                        c_try = c.to_Construction()
                        if c_try.is_initialized():
                            unique_constructions[name] = c_try.get()
                            # overall construction R (IP) for initial reporting
                            tc = c_try.get().thermalConductance()
                            if tc.is_initialized():
                                R_si = 1.0 / tc.get()
                                R_ip = self._unit_convert(R_si, "m^2*K/W", "ft^2*h*R/Btu")
                                roof_R_overall.append((name, R_ip))

        if not exterior_surfaces:
            runner.registerAsNotApplicable("Model does not have any roofs.")
            return True

        # Initial condition report
        if roof_R_overall:
            initial_string = [f"{name} (R-{R_ip:.1f})" for (name, R_ip) in roof_R_overall]
            initial_string.sort()
            runner.registerInitialCondition(f"The building had {len(roof_R_overall)} roof constructions: {', '.join(initial_string)}.")
        else:
            runner.registerInitialCondition("The building had roof constructions, but their overall thermal properties could not be determined.")

        # Hashes to track original -> new and vice versa, and cloned materials
        constructions_hash_old_new = {}
        constructions_hash_new_old = {}
        materials_hash = {}
        final_constructions_array = []

        # Iterate each unique roof construction and adjust the insulation layer
        for cname, construction in unique_constructions.items():
            layers = list(construction.layers())
            if not layers:
                continue

            # Build material info list
            mats_info = []
            for i, lyr in enumerate(layers):
                opq = lyr.to_OpaqueMaterial()
                if opq.is_initialized():
                    opq = opq.get()
                    r_val = opq.thermalResistance()  # SI m^2*K/W if massless; for Material, OpenStudio computes based on thickness/k
                else:
                    # not an opaque material; skip (rare for roof opaque layers)
                    continue

                nomass = not lyr.to_MasslessOpaqueMaterial().is_initialized() is False  # True if massless exists
                mats_info.append({
                    "index": i,
                    "mat": lyr,
                    "is_nomass": lyr.to_MasslessOpaqueMaterial().is_initialized(),
                    "r_value": r_val
                })

            if not mats_info:
                runner.registerWarning(f"Construction '{cname}' has no opaque layers with thermal resistance; skipped.")
                continue

            # Strategy:
            # 1) If there are massless materials, pick the one with the highest R (SI)
            # 2) Otherwise, pick material with highest (R / thickness)
            massless = [m for m in mats_info if m["is_nomass"]]
            if massless:
                max_R = max(m["r_value"] for m in massless)
                target = [m for m in massless if abs(m["r_value"] - max_R) < 1e-12][0]
                target_index = target["index"]
                target_layer = target["mat"]
                target_R = target["r_value"]
                used_R_for_ratio = max_R
            else:
                # compute R/thickness for opaque materials that have thickness (Material)
                best_idx = None
                best_ratio = -1.0
                used_R_for_ratio = None
                for m in mats_info:
                    as_mat = m["mat"].to_Material()
                    if as_mat.is_initialized():
                        thick = as_mat.get().thickness()
                        if thick > 0.0:
                            ratio = m["r_value"] / thick
                            if ratio > best_ratio:
                                best_ratio = ratio
                                best_idx = m["index"]
                                used_R_for_ratio = m["r_value"]
                if best_idx is None:
                    runner.registerWarning(f"Construction '{cname}' does not appear to have an identifiable insulation layer; skipped.")
                    continue
                target_index = best_idx
                target_layer = layers[target_index]
                target_R = [m["r_value"] for m in mats_info if m["index"] == target_index][0]

            # Check min insulation expectation
            if target_R <= self._unit_convert(1.0, "ft^2*h*R/Btu", "m^2*K/W"):
                runner.registerWarning(f"Construction '{cname}' does not appear to have an insulation layer and was not altered.")
                continue

            # Respect allow_reduction if current exceeds target
            if (target_R >= r_value_si) and (not allow_reduction):
                runner.registerInfo(f"The insulation layer of construction '{cname}' exceeds the requested R-value. It was not altered.")
                continue

            # Clone construction
            new_construction = construction.clone(model).to_Construction().get()
            new_construction.setName(f"{construction.nameString()} adj roof insulation")
            final_constructions_array.append(new_construction)

            # Adjust/attach LifeCycleCost on construction (Construction category)
            cost_added = False
            had_const_LCC = False
            updated_cost_si = 0.0
            for lcc in new_construction.lifeCycleCosts():
                if lcc.category() == "Construction" and material_cost_increase_si != 0.0:
                    had_const_LCC = True
                    if not cost_added:
                        lcc.setCost(lcc.cost() + material_cost_increase_si)
                        cost_added = True
                    else:
                        runner.registerInfo(f"More than one LifeCycleCost with 'Construction' found on {new_construction.nameString()}. Only adjusted one.")
                    updated_cost_si += lcc.cost()

            if cost_added:
                runner.registerInfo(
                    f"Adjusting material/installation cost for {new_construction.nameString()} "
                    f"to {self._neat_numbers(self._unit_convert(updated_cost_si, '1/m^2', '1/ft^2'))} ($/ft^2)."
                )

            if (not had_const_LCC) and (material_cost_increase_si != 0.0):
                lcc = openstudio.model.LifeCycleCost.createLifeCycleCost(
                    "LCC_increase_insulation", new_construction, material_cost_increase_si,
                    "CostPerArea", "Construction", 20, 0
                ).get()
                runner.registerInfo(
                    f"No material/installation costs existed for {new_construction.nameString()}. "
                    f"Created LifeCycleCost at {self._neat_numbers(self._unit_convert(lcc.cost(), '1/m^2', '1/ft^2'))} ($/ft^2). "
                    f"Assumed 20-year life, year 0."
                )

            if one_time_retrofit_cost_ip > 0.0:
                one_time_si = self._unit_convert(one_time_retrofit_cost_ip, "1/ft^2", "1/m^2")
                lcc_once = openstudio.model.LifeCycleCost.createLifeCycleCost(
                    "LCC_retrofit_specific", new_construction, one_time_si,
                    "CostPerArea", "Construction", 0, years_until_retrofit_cost
                ).get()
                runner.registerInfo(
                    f"Adding one-time retrofit cost {self._neat_numbers(self._unit_convert(lcc_once.cost(), '1/m^2', '1/ft^2'))} ($/ft^2)."
                )

            # Reuse cloned materials if we’ve already made one for the same original
            found_material = False
            for orig_name, new_mat in materials_hash.items():
                if target_layer.nameString() == orig_name:
                    # swap the layer to reuse cloned material
                    layer_list = list(new_construction.layers())
                    layer_list.pop(target_index)
                    layer_list.insert(target_index, new_mat)
                    new_construction.setLayers(layer_list)
                    found_material = True
                    break

            if not found_material:
                # Clone target layer and edit to target R
                cloned_layer = target_layer.clone(model)
                # Name + insert
                # If massless or air gap, set thermal resistance directly; otherwise modify thickness proportionally.
                massless = cloned_layer.to_MasslessOpaqueMaterial()
                airgap = cloned_layer.to_AirGap()
                std_mat = cloned_layer.to_Material()

                # Give a readable name (in IP)
                cloned_R_ip = r_value_ip
                cloned_name = f"{target_layer.nameString()}_R-value {cloned_R_ip} (ft^2*h*R/Btu)"
                if massless.is_initialized():
                    m = massless.get()
                    m.setName(cloned_name)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                elif airgap.is_initialized():
                    m = airgap.get()
                    m.setName(cloned_name)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                elif std_mat.is_initialized():
                    m = std_mat.get()
                    m.setName(cloned_name)
                    # Scale thickness to achieve target R: R_target = R_current * (t_new / t_old) -> t_new = t_old * (R_target / R_current)
                    t_old = m.thickness()
                    if used_R_for_ratio and used_R_for_ratio > 0.0:
                        t_new = t_old * (r_value_si / used_R_for_ratio)
                    else:
                        # Fallback if we couldn't compute ratio; scale by target/current directly.
                        current_R = target_R if target_R > 0 else r_value_si
                        t_new = t_old * (r_value_si / current_R)
                    m.setThickness(t_new)
                    new_mat_obj = m
                else:
                    runner.registerWarning(f"Could not convert target layer type for '{cname}'; skipping.")
                    continue

                # Insert swapped layer
                layer_list = list(new_construction.layers())
                layer_list.pop(target_index)
                layer_list.insert(target_index, new_mat_obj)
                new_construction.setLayers(layer_list)

                # Track cloned material mapping for reuse
                materials_hash[target_layer.nameString()] = new_mat_obj

                runner.registerInfo(f"For construction '{new_construction.nameString()}', material '{new_mat_obj.nameString()}' was altered.")

            # Record mapping
            constructions_hash_old_new[cname] = new_construction
            constructions_hash_new_old[new_construction] = construction

        # Swap default construction sets where applicable
        for dcs in model.getDefaultConstructionSets():
            if dcs.directUseCount() > 0:
                dsc_opt = dcs.defaultExteriorSurfaceConstructions()
                if dsc_opt.is_initialized():
                    dsc = dsc_opt.get()
                    roof_c_opt = dsc.roofCeilingConstruction()
                    # Build new default set and swap in the adjusted roof construction
                    new_dcs = dcs.clone(model).to_DefaultConstructionSet().get()
                    new_dcs.setName(f"{dcs.nameString()} adj roof insulation")

                    new_dsc = dsc.clone(model).to_DefaultSurfaceConstructions().get()
                    new_dsc.setName(f"{dsc.nameString()} adj roof insulation")
                    new_dcs.setDefaultExteriorSurfaceConstructions(new_dsc)

                    if roof_c_opt.is_initialized():
                        target_name = roof_c_opt.get().nameString()
                        if target_name in constructions_hash_old_new:
                            new_roof = constructions_hash_old_new[target_name]
                            new_dsc.setRoofCeilingConstruction(new_roof)
                        else:
                            runner.registerWarning(f"Measure couldn't find construction '{target_name}' in mapping; leaving default set as-is.")

                    # Replace on all sources
                    for src in dcs.sources():
                        bldg = src.to_Building()
                        if bldg.is_initialized():
                            bldg.get().setDefaultConstructionSet(new_dcs)
                        story = src.to_BuildingStory()
                        if story.is_initialized():
                            story.get().setDefaultConstructionSet(new_dcs)
                        stype = src.to_SpaceType()
                        if stype.is_initialized():
                            stype.get().setDefaultConstructionSet(new_dcs)
                        sp = src.to_Space()
                        if sp.is_initialized():
                            sp.get().setDefaultConstructionSet(new_dcs)

        # Swap hard-assigned constructions on surfaces
        for srf in exterior_surfaces:
            if (not srf.isConstructionDefaulted()) and srf.construction().is_initialized():
                name = srf.construction().get().nameString()
                if name in constructions_hash_old_new:
                    srf.setConstruction(constructions_hash_old_new[name])

        # Final reporting: list altered constructions, total affected area, year-0 capital costs
        final_constructions = []
        affected_area_si = 0.0
        yr0_capital_totalCosts = 0.0

        for new_c in final_constructions_array:
            tc = new_c.thermalConductance()
            if tc.is_initialized():
                R_si = 1.0 / tc.get()
                R_ip = self._unit_convert(R_si, "m^2*K/W", "ft^2*h*R/Btu")
            else:
                R_ip = float("nan")
            final_constructions.append(f"{new_c.nameString()} (R-{R_ip:.1f})")

            # Net area & costs from the construction it replaced
            affected_area_si += new_c.getNetArea()

            for lcc in new_c.lifeCycleCosts():
                if lcc.category() in ["Construction", "Salvage"]:
                    if lcc.yearsFromStart() == 0:
                        yr0_capital_totalCosts += lcc.totalCost()

        if affected_area_si == 0.0:
            runner.registerAsNotApplicable("No roofs were altered.")
            return True

        affected_area_ip = self._unit_convert(affected_area_si, "m^2", "ft^2")
        final_constructions.sort()

        runner.registerFinalCondition(
            "The existing insulation for roofs was changed to R-"
            f"{r_value_ip}. This was accomplished for an initial cost of "
            f"{one_time_retrofit_cost_ip} ($/sf) and an increase of {material_cost_increase_ip} "
            f"($/sf) for construction. This was applied to "
            f"{self._neat_numbers(affected_area_ip, 0)} (ft^2) across "
            f"{len(final_constructions)} roof constructions: {', '.join(final_constructions)}."
        )

        return True


# Register the measure
IncreaseInsulationRValueForRoofs().registerWithApplication()
