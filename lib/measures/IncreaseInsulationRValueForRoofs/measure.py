# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

import openstudio
import numpy as np
import pandas as pd

# EC3 helpers you already use for walls
from resources.EC3_lookup import (
    generate_url_byname,
    fetch_epd_data,
    parse_product_epd,
    lifetime_multiplier
)

class IncreaseInsulationRValueForRoofs(openstudio.measure.ModelMeasure):
    # ---- Metadata ----
    def name(self):
        return "Increase R-value of Insulation for Roofs to a Specific Value"

    def description(self):
        return ("Adjusts insulation layers in roof/ceiling constructions exposed to outdoors "
                "to reach a target R-value, with optional costs and EC3-based embodied carbon tagging.")

    def modeler_description(self):
        return ("Finds the roof insulation layer (preferring massless; else highest R/thickness), "
                "clones the construction, and edits that layer to hit the target R. Adds/adjusts LCCs. "
                "Also computes embodied carbon for *added* insulation using EC3 (EPDs) and saves results "
                "on the construction via additionalProperties.")

    # ---- Static lists ----
    @staticmethod
    def gwp_statistics():
        return ["minimum", "maximum", "mean", "median"]

    @staticmethod
    def insulation_material_types():
        return [
            "Mineral Wool",
            "Cellulose",
            "Fiberglass",
            "Expanded Polystyrene (EPS)",
            "Extruded Polystyrene (XPS)",
            "Graphite Polystyrene (GPS)",
            "Polyiso (ISO)",
            "Expanded Polyethylene",
            "Other"
        ]

    # ---- Helpers ----
    @staticmethod
    def _unit_convert(value, from_u, to_u):
        return openstudio.convert(value, from_u, to_u).get()

    @staticmethod
    def _neat_numbers(number, roundto=2):
        if roundto == 2:
            return f"{number:,.2f}"
        return f"{round(number):,}"

    def _generate_url_by_material_type(self, material_type):
        # Same mapping as your wall measure
        if material_type == "Mineral Wool":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="mineral wool")
        elif material_type == "Cellulose":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="cellulose")
        elif material_type == "Fiberglass":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="fiber glass")
        elif material_type == "Expanded Polystyrene (EPS)":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="eps")
        elif material_type == "Extruded Polystyrene (XPS)":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="xps")
        elif material_type == "Graphite Polystyrene (GPS)":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="Graphite Polystyrene")
        elif material_type == "Polyiso (ISO)":
            return generate_url_byname(category="bf1c8882d7784db4b10d9d5698b8b5cc", name_like="polyiso")
        elif material_type == "Expanded Polyethylene":
            return generate_url_byname(category="56f3c898f94b459eb18feadeb792ab88", name_like="ArmaPET")
        else:
            return None

    # ---- Arguments ----
    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        # R and cost args (parity with your Ruby measure)
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

        # EC3 / WBLCA args (matching your walls measure)
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period", True)
        analysis_period.setDisplayName("Analysis Period (years)")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        gwp_stats = openstudio.StringVector()
        for s in self.gwp_statistics():
            gwp_stats.append(s)
        gwp_stat = openstudio.measure.OSArgument.makeChoiceArgument("gwp_statistic", gwp_stats, True)
        gwp_stat.setDisplayName("GWP Statistic")
        gwp_stat.setDefaultValue("median")
        args.append(gwp_stat)

        api_key = openstudio.measure.OSArgument.makeStringArgument("api_key", True)
        api_key.setDisplayName("API Token (EC3)")
        api_key.setDefaultValue("Obtain the key from EC3 website")
        args.append(api_key)

        mat_types = openstudio.StringVector()
        for opt in self.insulation_material_types():
            mat_types.append(opt)
        insulation_material_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_material_type", mat_types, True)
        insulation_material_type.setDisplayName("Chosen Retrofit Material for Roof Insulation")
        insulation_material_type.setDefaultValue("Polyiso (ISO)")
        args.append(insulation_material_type)

        insulation_material_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("insulation_material_lifetime", True)
        insulation_material_lifetime.setDisplayName("Product Lifetime of Insulation Material (years)")
        insulation_material_lifetime.setDefaultValue(30)
        args.append(insulation_material_lifetime)

        insulation_thermal_conductivity = openstudio.measure.OSArgument.makeDoubleArgument("insulation_thermal_conductivity", True)
        insulation_thermal_conductivity.setDisplayName("Thermal Conductivity of Insulation Material (W/m·K). 0 = Typical")
        insulation_thermal_conductivity.setDefaultValue(0.0)
        args.append(insulation_thermal_conductivity)

        insulation_material_density = openstudio.measure.OSArgument.makeDoubleArgument("insulation_material_density", True)
        insulation_material_density.setDisplayName("Density of Insulation Material (kg/m³). 0 = Typical")
        insulation_material_density.setDefaultValue(0.0)
        args.append(insulation_material_density)

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

        analysis_period = runner.getIntegerArgumentValue("analysis_period", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        insulation_thermal_conductivity = runner.getDoubleArgumentValue("insulation_thermal_conductivity", user_arguments)
        insulation_material_density = runner.getDoubleArgumentValue("insulation_material_density", user_arguments)

        # Reasonableness checks
        if (r_value_ip < 0.0) or (r_value_ip > 500.0):
            runner.registerError("R-value must be between 0 and 500 ft²·h·°F/Btu.")
            return False
        if (years_until_retrofit_cost < 0) or (years_until_retrofit_cost > 100):
            runner.registerError("Year to incur one time retrofit cost should be a non-negative integer ≤ 100.")
            return False
        if insulation_material_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for insulation material lifetime.")
            return False
        if insulation_thermal_conductivity < 0.0:
            runner.registerError("Thermal conductivity of insulation material must be non-negative.")
            return False
        if insulation_material_density < 0.0:
            runner.registerError("Density of insulation material must be non-negative.")
            return False

        # Typical material k and density (same style as your wall measure)
        material_k_dict = {
            "Mineral Wool": 0.032,
            "Cellulose": 0.040,
            "Fiberglass": 0.033,
            "Expanded Polystyrene (EPS)": 0.034,
            "Extruded Polystyrene (XPS)": 0.033,
            "Graphite Polystyrene (GPS)": 0.030,
            "Polyiso (ISO)": 0.025,
            "Expanded Polyethylene": 0.032,
            "Other": 0.030
        }
        material_density_dict = {
            "Mineral Wool": 90,
            "Cellulose": 50,
            "Fiberglass": 30,
            "Expanded Polystyrene (EPS)": 20,
            "Extruded Polystyrene (XPS)": 35,
            "Graphite Polystyrene (GPS)": 20,
            "Polyiso (ISO)": 35,
            "Expanded Polyethylene": 25,
            "Other": 30
        }

        selected_k = insulation_thermal_conductivity if insulation_thermal_conductivity > 0.0 else material_k_dict[insulation_material_type]
        selected_rho = insulation_material_density if insulation_material_density > 0.0 else material_density_dict[insulation_material_type]

        # Conversions
        r_value_si = self._unit_convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W")
        material_cost_increase_si = self._unit_convert(material_cost_increase_ip, "1/ft^2", "1/m^2")

        # Collect roof surfaces + unique constructions
        roof_surfaces = []
        unique_constructions = {}

        for srf in model.getSurfaces():
            if srf.outsideBoundaryCondition() == "Outdoors" and srf.surfaceType() == "RoofCeiling":
                roof_surfaces.append(srf)
                if srf.construction().is_initialized():
                    c = srf.construction().get()
                    c_con = c.to_Construction()
                    if c_con.is_initialized():
                        name = c.nameString()
                        if name not in unique_constructions:
                            unique_constructions[name] = c_con.get()

        if not roof_surfaces:
            runner.registerAsNotApplicable("Model does not have any roofs.")
            return True

        # Initial condition string
        initial_Rs = []
        for cname, c in unique_constructions.items():
            tc = c.thermalConductance()
            if tc.is_initialized():
                R_si = 1.0 / tc.get()
                R_ip = self._unit_convert(R_si, "m^2*K/W", "ft^2*h*R/Btu")
                initial_Rs.append(f"{cname} (R-{R_ip:.1f})")
        initial_Rs.sort()
        if initial_Rs:
            runner.registerInitialCondition(f"The building had {len(initial_Rs)} roof constructions: {', '.join(initial_Rs)}.")
        else:
            runner.registerInitialCondition("The building had roof constructions, but their overall thermal properties could not be determined.")

        # Trackers
        constructions_hash_old_new = {}
        materials_hash = {}
        final_constructions_array = []

        # For EC3 summary (per modified construction)
        modified_constructions = []  # dicts: name, area_m2, added_thickness_m, gwp per FU, total_gwp

        # --- Edit each unique roof construction ---
        for cname, construction in unique_constructions.items():
            layers = list(construction.layers())
            if not layers:
                continue

            # Gather layer info
            mats_info = []
            for i, lyr in enumerate(layers):
                opq = lyr.to_OpaqueMaterial()
                if not opq.is_initialized():
                    continue
                r_val = opq.get().thermalResistance()  # SI m^2*K/W
                is_nomass = lyr.to_MasslessOpaqueMaterial().is_initialized()
                mats_info.append({"index": i, "mat": lyr, "r_value": r_val, "is_nomass": is_nomass})

            if not mats_info:
                runner.registerWarning(f"Construction '{cname}' has no opaque layers with thermal resistance; skipped.")
                continue

            # Select insulation layer
            massless = [m for m in mats_info if m["is_nomass"]]
            used_R_for_ratio = None
            if massless:
                max_R = max(m["r_value"] for m in massless)
                target = [m for m in massless if abs(m["r_value"] - max_R) < 1e-12][0]
                target_index = target["index"]
                target_layer = target["mat"]
                target_R = target["r_value"]
                used_R_for_ratio = max_R
            else:
                best_idx = None
                best_ratio = -1.0
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
                    runner.registerWarning(f"Construction '{cname}' lacks an identifiable insulation layer; skipped.")
                    continue
                target_index = best_idx
                target_layer = layers[target_index]
                target_R = used_R_for_ratio

            # Sanity: minimal insulation
            if target_R <= self._unit_convert(1.0, "ft^2*h*R/Btu", "m^2*K/W"):
                runner.registerWarning(f"Construction '{cname}' does not appear to have an insulation layer and was not altered.")
                continue

            # Respect allow_reduction
            if (target_R >= r_value_si) and (not allow_reduction):
                runner.registerInfo(f"The insulation layer of construction '{cname}' exceeds the requested R-value. It was not altered.")
                continue

            # Clone construction to modify
            new_construction = construction.clone(model).to_Construction().get()
            new_construction.setName(f"{construction.nameString()} adj roof insulation")
            final_constructions_array.append(new_construction)

            # LCC adjustments (Construction category)
            cost_added = False
            had_const_LCC = False
            updated_cost_si = 0.0
            if material_cost_increase_si != 0.0:
                for lcc in new_construction.lifeCycleCosts():
                    if lcc.category() == "Construction":
                        had_const_LCC = True
                        if not cost_added:
                            lcc.setCost(lcc.cost() + material_cost_increase_si)
                            cost_added = True
                        else:
                            runner.registerInfo(f"Multiple 'Construction' LCC on {new_construction.nameString()}; only adjusted one.")
                        updated_cost_si += lcc.cost()
                if not had_const_LCC:
                    openstudio.model.LifeCycleCost.createLifeCycleCost(
                        "LCC_increase_insulation", new_construction, material_cost_increase_si,
                        "CostPerArea", "Construction", 20, 0
                    )

            if one_time_retrofit_cost_ip > 0.0:
                one_time_si = self._unit_convert(one_time_retrofit_cost_ip, "1/ft^2", "1/m^2")
                openstudio.model.LifeCycleCost.createLifeCycleCost(
                    "LCC_retrofit_specific", new_construction, one_time_si,
                    "CostPerArea", "Construction", 0, years_until_retrofit_cost
                )

            # Reuse cloned material if seen before
            reused = False
            for orig_name, new_mat in materials_hash.items():
                if target_layer.nameString() == orig_name:
                    layer_list = list(new_construction.layers())
                    layer_list.pop(target_index)
                    layer_list.insert(target_index, new_mat)
                    new_construction.setLayers(layer_list)
                    reused = True
                    break

            # Compute delta_R for EC3 added thickness/volume
            delta_R = r_value_si - target_R
            if allow_reduction and (delta_R < 0):
                delta_R = 0.0  # no added material for reductions

            # Make/edit material in the construction
            added_thickness_m = 0.0
            if not reused:
                cloned_layer = target_layer.clone(model)
                massless = cloned_layer.to_MasslessOpaqueMaterial()
                airgap = cloned_layer.to_AirGap()
                std_mat = cloned_layer.to_Material()

                new_name_ip = f"{target_layer.nameString()}_R-value {r_value_ip} (ft^2*h*R/Btu)"
                if massless.is_initialized():
                    m = massless.get()
                    m.setName(new_name_ip)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                    # For EC3: if we increased R, infer an equivalent thickness from delta_R via selected_k
                    if delta_R > 0.0:
                        added_thickness_m = delta_R * selected_k
                elif airgap.is_initialized():
                    m = airgap.get()
                    m.setName(new_name_ip)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                    if delta_R > 0.0:
                        added_thickness_m = delta_R * selected_k
                elif std_mat.is_initialized():
                    m = std_mat.get()
                    m.setName(new_name_ip)
                    t_old = m.thickness()
                    # Scale thickness to new target R for this layer
                    # If used_R_for_ratio > 0, t_new = t_old * (R_target / R_current_of_layer)
                    if (used_R_for_ratio is not None) and (used_R_for_ratio > 0.0):
                        t_new = t_old * (r_value_si / used_R_for_ratio)
                    else:
                        # Fallback: scale by target/current
                        t_new = t_old * (r_value_si / max(target_R, 1e-9))
                    m.setThickness(t_new)
                    new_mat_obj = m
                    # Added thickness = max(t_new - t_old, 0)
                    added_thickness_m = max(t_new - t_old, 0.0)
                else:
                    runner.registerWarning(f"Could not manipulate target layer type for '{cname}'; skipping.")
                    # remove the half-done construction from final arrays
                    final_constructions_array.pop()
                    continue

                # Swap in modified layer
                layer_list = list(new_construction.layers())
                layer_list.pop(target_index)
                layer_list.insert(target_index, new_mat_obj)
                new_construction.setLayers(layer_list)

                materials_hash[target_layer.nameString()] = new_mat_obj
                runner.registerInfo(f"For construction '{new_construction.nameString()}', material '{new_mat_obj.nameString()}' was altered.")

            # Map old->new
            constructions_hash_old_new[cname] = new_construction

            # Area that uses this construction
            area_m2 = sum(
                s.grossArea()
                for s in roof_surfaces
                if s.construction().is_initialized()
                and s.construction().get().nameString() == cname
            )

            # Save per-construction EC3 inputs for later aggregation
            modified_constructions.append({
                "construction": new_construction,
                "orig_construction_name": cname,
                "total_area_m2": area_m2,
                "added_thickness_m": added_thickness_m  # (0 if no increase)
            })

        # Swap hard-assigned constructions on surfaces
        for srf in roof_surfaces:
            if srf.construction().is_initialized():
                old_name = srf.construction().get().nameString()
                if old_name in constructions_hash_old_new:
                    srf.setConstruction(constructions_hash_old_new[old_name])

        # Swap default construction sets for roof where applicable
        for dcs in model.getDefaultConstructionSets():
            if dcs.directUseCount() > 0:
                dsc_opt = dcs.defaultExteriorSurfaceConstructions()
                if dsc_opt.is_initialized():
                    dsc = dsc_opt.get()
                    rc_opt = dsc.roofCeilingConstruction()
                    if rc_opt.is_initialized():
                        base_name = rc_opt.get().nameString()
                        if base_name in constructions_hash_old_new:
                            new_dcs = dcs.clone(model).to_DefaultConstructionSet().get()
                            new_dsc = dsc.clone(model).to_DefaultSurfaceConstructions().get()
                            new_dcs.setName(f"{dcs.nameString()} adj roof insulation")
                            new_dsc.setName(f"{dsc.nameString()} adj roof insulation")
                            new_dcs.setDefaultExteriorSurfaceConstructions(new_dsc)
                            new_dsc.setRoofCeilingConstruction(constructions_hash_old_new[base_name])

                            # Replace on sources
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

        # ===================== EC3 embodied carbon =====================
        # 1) Pull EPDs for the selected insulation material type once
        ec3_url = self._generate_url_by_material_type(insulation_material_type)
        gwp_values = {"gwp_per_kg": [], "gwp_per_m3": [], "gwp_per_m2": []}
        if ec3_url:
            try:
                epds = fetch_epd_data(ec3_url, api_key)
                for epd in epds:
                    parsed = parse_product_epd(epd)
                    if parsed.get("gwp_per_kg (kg CO2 eq/kg)", 0.0) != 0.0:
                        gwp_values["gwp_per_kg"].append(float(parsed["gwp_per_kg (kg CO2 eq/kg)"]))
                    if parsed.get("gwp_per_m3 (kg CO2 eq/m3)", 0.0) != 0.0:
                        gwp_values["gwp_per_m3"].append(float(parsed["gwp_per_m3 (kg CO2 eq/m3)"]))
                    if parsed.get("gwp_per_m2 (kg CO2 eq/m2)", 0.0) != 0.0:
                        gwp_values["gwp_per_m2"].append(float(parsed["gwp_per_m2 (kg CO2 eq/m2)"]))
            except Exception as e:
                runner.registerWarning(f"EC3 fetch failed: {e}")
        else:
            runner.registerInfo("No EC3 URL mapping for chosen material; skipping EC3 pull.")

        # 2) Choose a representative GWP value per functional unit by statistic
        def pick_stat(vals):
            if len(vals) == 0:
                return 0.0
            if len(vals) == 1:
                return float(vals[0])
            if gwp_statistic == "minimum":
                return float(np.min(vals))
            if gwp_statistic == "maximum":
                return float(np.max(vals))
            if gwp_statistic == "mean":
                return float(np.mean(vals))
            # default median
            return float(np.median(vals))

        sel_gwp_per_kg = pick_stat(gwp_values["gwp_per_kg"])
        sel_gwp_per_m3 = pick_stat(gwp_values["gwp_per_m3"])
        sel_gwp_per_m2 = pick_stat(gwp_values["gwp_per_m2"])

        # 3) Analysis-period multiplier
        mult = lifetime_multiplier(insulation_material_lifetime, analysis_period)

        # 4) Compute and tag embodied carbon for each modified construction
        gwp_summary_rows = []
        for item in modified_constructions:
            area_m2 = item["total_area_m2"]
            add_t_m = max(item["added_thickness_m"], 0.0)

            # Volume and (fallback) mass for added material only
            added_volume_m3 = area_m2 * add_t_m
            added_mass_kg = selected_rho * added_volume_m3

            # Try per m3 first, fallback to per kg, then per m2 if thickness is zero
            total_gwp = 0.0
            if sel_gwp_per_m3 > 0.0 and added_volume_m3 > 0.0:
                total_gwp = sel_gwp_per_m3 * added_volume_m3 * mult
            elif sel_gwp_per_kg > 0.0 and added_mass_kg > 0.0:
                total_gwp = sel_gwp_per_kg * added_mass_kg * mult
            elif sel_gwp_per_m2 > 0.0 and add_t_m == 0.0:
                # If thickness didn't increase (e.g., massless adjustment), per-m2 EPD if present
                total_gwp = sel_gwp_per_m2 * area_m2 * mult
            else:
                total_gwp = 0.0  # no EC3 data path available

            # Tag onto construction as additionalProperties
            c = item["construction"]
            props = c.additionalProperties()
            props.setFeature("embodied_carbon_kgCO2eq", total_gwp)
            props.setFeature("modified_material", insulation_material_type)
            props.setFeature("total_volume_m3", added_volume_m3)
            props.setFeature("total_area_m2", area_m2)
            props.setFeature("added_thickness_m", add_t_m)
            props.setFeature("insulation_material_density_kg_per_m3", selected_rho)
            props.setFeature("insulation_material_lifetime_years", insulation_material_lifetime)
            props.setFeature("insulation_material_gwp_per_kg", sel_gwp_per_kg)
            props.setFeature("insulation_material_gwp_per_m2", sel_gwp_per_m2)
            props.setFeature("insulation_material_gwp_per_m3", sel_gwp_per_m3)

            gwp_summary_rows.append({
                "construction_name": c.nameString(),
                "orig_construction": item["orig_construction_name"],
                "insulation_material_type": insulation_material_type,
                "added_total_area_m2": area_m2,
                "added_thickness_m": add_t_m,
                "added_total_volume_m3": added_volume_m3,
                "gwp_per_kg": sel_gwp_per_kg,
                "gwp_per_m2": sel_gwp_per_m2,
                "gwp_per_m3": sel_gwp_per_m3,
                "density_kg_per_m3": selected_rho,
                "lifetime_years": insulation_material_lifetime,
                "total_gwp_kg_co2_eq": total_gwp
            })

        if gwp_summary_rows:
            df = pd.DataFrame(gwp_summary_rows)
            runner.registerInfo("\n==== GWP Summary for Modified Roof Constructions ====\n" + df.to_string(index=False))

        # ===================== Final reporting =====================
        if not final_constructions_array:
            runner.registerAsNotApplicable("No roofs were altered.")
            return True

        affected_area_si = 0.0
        finals = []
        for new_c in final_constructions_array:
            tc = new_c.thermalConductance()
            if tc.is_initialized():
                R_ip = self._unit_convert(1.0 / tc.get(), "m^2*K/W", "ft^2*h*R/Btu")
            else:
                R_ip = float("nan")
            finals.append(f"{new_c.nameString()} (R-{R_ip:.1f})")
            affected_area_si += new_c.getNetArea()

        affected_area_ip = self._unit_convert(affected_area_si, "m^2", "ft^2")
        finals.sort()

        runner.registerFinalCondition(
            "The existing insulation for roofs was changed to R-"
            f"{r_value_ip}. This was accomplished for an initial cost of "
            f"{one_time_retrofit_cost_ip} ($/sf) and an increase of {material_cost_increase_ip} "
            f"($/sf) for construction. This was applied to "
            f"{self._neat_numbers(affected_area_ip, 0)} (ft^2) across "
            f"{len(finals)} roof constructions: {', '.join(finals)}."
        )
        return True


# Register the measure
IncreaseInsulationRValueForRoofs().registerWithApplication()
