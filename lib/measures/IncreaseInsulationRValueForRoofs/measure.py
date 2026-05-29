# pyright: reportAttributeAccessIssue=false
# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

# Execution flow (see run() for details):
#   Phase 1 - Parse and validate user arguments.
#   Phase 2 - Optional early RSMeans lookup to extract density/conductivity hints.
#   Phase 3 - Model surgery on roof constructions to reach target R-value.
#   Phase 4 - EC3 EPD lookup and embodied-carbon aggregation.
#   Phase 5 - Cost lookup (RSMeans or custom) and AdditionalProperties write-out.
#
# AdditionalProperties buckets:
#   Building          -> basic_input  (high-level measure inputs)
#   Site              -> reno_detail  (renovation target and areas)
#   Facility          -> factors      (cost/emission factors)
#   SimulationControl -> results      (embodied carbon + cost totals)
#   SizingParameters  -> mtrl_prop    (material/lifetime + selected RSMeans id/description)

import importlib.util
import json
import os
import sys
from pathlib import Path

import openstudio
import numpy as np

# Ensure local `resources` package is importable when this measure is loaded dynamically.
measure_dir = os.path.dirname(os.path.abspath(__file__))
if measure_dir not in sys.path:
    sys.path.insert(0, measure_dir)

from resources.EC3_lookup import (
    extract_numeric_value,
    fetch_epd_data,
    generate_url_byname,
    lifetime_multiplier,
    parse_product_epd,
)

class IncreaseInsulationRValueForRoofs(openstudio.measure.ModelMeasure):
    # ---- Metadata ----
    def name(self):
        return "Increase R-value of Insulation for Roofs to a Specific Value"

    def description(self):
        return ("Adjusts insulation layers in roof/ceiling constructions exposed to outdoors "
                "to reach a target R-value, with embodied carbon tagging.")

    def modeler_description(self):
        return ("This measure modifies insulation layers in roof/ceiling constructions exposed to "
                "outdoors to reach a user-defined target R-value. The measure identifies the existing "
                "insulation layer by preferring massless opaque materials (e.g., R-value only layers) "
                "or selecting the material with the highest R-value to thickness ratio. It clones the "
                "original construction and adjusts the insulation layer properties to meet the target. "
                "Supports various insulation types including blown materials (cellulose, fiberglass, "
                "mineral wool), foam boards (polyiso, EPS, XPS, GPS), and batts (fiberglass, mineral wool, "
                "pure wool). The measure fetches Environmental Product Declaration (EPD) data from the EC3 "
                "database to calculate embodied carbon (GWP) for the added insulation over a specified "
                "analysis period. Outlier removal using the IQR method is applied to GWP values to improve "
                "data accuracy. Results including embodied carbon, material quantities, density, thermal "
                "properties, and GWP metrics are stored as additional properties on each modified "
                "construction for downstream reporting.")

    @staticmethod
    def gwp_statistics():
        return ["minimum", "maximum", "mean", "median"]

    @staticmethod
    def insulation_material_types():
        return [
            "none",
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

    @staticmethod
    def _unit_convert(value, from_u, to_u):
        return openstudio.convert(value, from_u, to_u).get()

    @staticmethod
    def _neat_numbers(number, roundto=2):
        if roundto == 2:
            return f"{number:,.2f}"
        return f"{round(number):,}"

    @staticmethod
    def _collect_unmatched_rsmeans_materials(
        requested_materials,
        matched_materials,
    ):
        matched_names = {
            str(material.get("name", "")).strip()
            for material in matched_materials
            if material.get("name")
        }
        unmatched_names = []
        seen_names = set()

        for material in requested_materials:
            material_name = str(material.get("name", "")).strip()
            if not material_name or material_name in matched_names:
                continue
            if material_name in seen_names:
                continue
            seen_names.add(material_name)
            unmatched_names.append(material_name)

        return unmatched_names

    @staticmethod
    def _register_rsmeans_resolution_error(
        runner,
        unresolved_materials,
        use_exact_costline_id,
        exact_costline_id,
    ):
        materials_text = "; ".join(unresolved_materials)

        if use_exact_costline_id:
            runner.registerError(
                "RSMeans exact-ID mode could not validate the requested "
                f"costline ID '{exact_costline_id}' for: {materials_text}. "
                "Provide a valid `exact_costline_id`, or disable exact-ID "
                "mode and rerun with `use_custom_costs` enabled and a "
                "non-zero `custom_cost_per_cf`."
            )
            return

        runner.registerError(
            "RSMeans did not find a database match for: "
            f"{materials_text}. Provide cost data by rerunning with either "
            "`use_custom_costs` enabled and a non-zero `custom_cost_per_cf`, "
            "or `use_exact_costline_id` enabled with a valid "
            "`exact_costline_id`."
        )

    @staticmethod
    def _detect_rsmeans_ambiguous_candidates(search_log):
        """Scan the RSMeans search log for entries where 2+ candidates
        share the top score, indicating an ambiguous auto-selection.

        Returns a list of dicts, one per ambiguous lookup:
          material          – original material name sent to RSMeans
          matched_rsmeans_id  – the ID that was auto-selected
          matched_description – description of the auto-selected item
          search_term_used  – the search term that produced the match
          tied_candidates   – sorted list of candidate dicts (score, desc)
        """
        ambiguous = []
        for entry in search_log:
            status = entry.get("status", "")
            if "no_match" in status or "error" in status:
                continue
            candidates = entry.get("candidate_scores", [])
            if len(candidates) < 2:
                continue
            sorted_cands = sorted(
                candidates, key=lambda c: -c.get("score", 0.0)
            )
            top_score = sorted_cands[0].get("score", 0.0)
            tied = [
                c for c in sorted_cands
                if c.get("score", 0.0) == top_score
            ]
            if len(tied) > 1:
                ambiguous.append({
                    "material": entry.get("material", ""),
                    "matched_rsmeans_id": entry.get("rsmeans_id", ""),
                    "matched_description": entry.get(
                        "rsmeans_description", ""
                    ),
                    "search_term_used": entry.get("search_term", ""),
                    "tied_candidates": tied,
                })
        return ambiguous

    def _generate_url_by_material_type(self, material_type):
        # Same mapping as your wall measure
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

    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        # R and cost args 
        r_value = openstudio.measure.OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Insulation R-value (ft^2*h*R/Btu).")
        r_value.setDefaultValue(30.0)
        args.append(r_value)

        # EC3 / WBLCA args 
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
        insulation_material_type.setDefaultValue("Fiberglass Batts")
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

        use_custom_gwp = openstudio.measure.OSArgument.makeBoolArgument("use_custom_gwp", True)
        use_custom_gwp.setDisplayName("Use Custom GWP Inputs (skip EC3)")
        use_custom_gwp.setDefaultValue(False)
        args.append(use_custom_gwp)

        custom_gwp_per_m3 = openstudio.measure.OSArgument.makeDoubleArgument("custom_gwp_per_m3", True)
        custom_gwp_per_m3.setDisplayName("Custom Insulation GWP (kgCO2eq/m3)")
        custom_gwp_per_m3.setDescription("Used only when 'Use Custom GWP Inputs (skip EC3)' is true.")
        custom_gwp_per_m3.setDefaultValue(0.0)
        args.append(custom_gwp_per_m3)

        # Cost / RSMeans args
        use_custom_costs = openstudio.measure.OSArgument.makeBoolArgument("use_custom_costs", True)
        use_custom_costs.setDisplayName("Use Custom Cost Inputs (skip RSMeans)")
        use_custom_costs.setDefaultValue(False)
        args.append(use_custom_costs)

        use_exact_costline_id = openstudio.measure.OSArgument.makeBoolArgument("use_exact_costline_id", True)
        use_exact_costline_id.setDisplayName("Use Exact RSMeans Costline ID")
        use_exact_costline_id.setDefaultValue(False)
        args.append(use_exact_costline_id)

        exact_costline_id = openstudio.measure.OSArgument.makeStringArgument("exact_costline_id", True)
        exact_costline_id.setDisplayName("Exact RSMeans Costline ID (used when exact-ID mode is enabled)")
        exact_costline_id.setDefaultValue("")
        args.append(exact_costline_id)

        custom_cost_per_cf = openstudio.measure.OSArgument.makeDoubleArgument("custom_cost_per_cf", True)
        custom_cost_per_cf.setDisplayName("Custom Insulation Cost ($/CF)")
        custom_cost_per_cf.setDefaultValue(0.0)
        args.append(custom_cost_per_cf)

        labor_cost_multiplier = openstudio.measure.OSArgument.makeDoubleArgument("labor_cost_multiplier", True)
        labor_cost_multiplier.setDisplayName("Labor Cost Multiplier (applies to custom material cost)")
        labor_cost_multiplier.setDefaultValue(1.0)
        args.append(labor_cost_multiplier)

        overhead_profit_percent = openstudio.measure.OSArgument.makeDoubleArgument("overhead_profit_percent", True)
        overhead_profit_percent.setDisplayName("Overhead + Profit Percent (RSMeans only)")
        overhead_profit_percent.setDefaultValue(10.0)
        args.append(overhead_profit_percent)

        return args

    def run(self, model, runner, user_arguments):
        super().run(model, runner, user_arguments)
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        # Inputs
        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        analysis_period = runner.getIntegerArgumentValue("analysis_period", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        insulation_thermal_conductivity = runner.getDoubleArgumentValue("insulation_thermal_conductivity", user_arguments)
        insulation_material_density = runner.getDoubleArgumentValue("insulation_material_density", user_arguments)
        if str(insulation_material_type).strip().lower() == "none":
            runner.registerInfo("Insulation material type is 'none'; skipping roof insulation and cost calculation.")
            return True
        use_custom_gwp = runner.getBoolArgumentValue("use_custom_gwp", user_arguments)
        custom_gwp_per_m3 = runner.getDoubleArgumentValue("custom_gwp_per_m3", user_arguments)
        use_custom_costs = runner.getBoolArgumentValue("use_custom_costs", user_arguments)
        use_exact_costline_id = runner.getBoolArgumentValue("use_exact_costline_id", user_arguments)
        exact_costline_id = runner.getStringArgumentValue("exact_costline_id", user_arguments)
        custom_cost_per_cf = runner.getDoubleArgumentValue("custom_cost_per_cf", user_arguments)
        labor_cost_multiplier = runner.getDoubleArgumentValue("labor_cost_multiplier", user_arguments)
        overhead_profit_percent = runner.getDoubleArgumentValue("overhead_profit_percent", user_arguments)

        exact_costline_id = (exact_costline_id or "").strip()

        # Pre-flight warning: if RSMeans is the active path and the user has
        # not supplied a fallback custom rate, the measure will hard-error if
        # RSMeans returns nothing. Surface this risk up front.
        if (not use_custom_costs) and float(custom_cost_per_cf) <= 0.0:
            runner.registerWarning(
                "RSMeans cost lookup is the active cost source (use_custom_costs=false) "
                "but no fallback 'custom_cost_per_cf' value has been provided. "
                "If RSMeans returns no match for this insulation material, the measure "
                "will fail. Consider setting a non-zero 'custom_cost_per_cf' as a safety net."
            )
        
        # Track if user provided explicit density value (non-zero means user-specified)
        user_specified_density = insulation_material_density > 0.0

        # Reasonableness checks
        if (r_value_ip < 0.0) or (r_value_ip > 500.0):
            runner.registerError("R-value must be between 0 and 500 ft²·h·°F/Btu.")
            return False
        if analysis_period <= 0:
            runner.registerError("Analysis period must be greater than 0 years.")
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
        if use_custom_gwp and custom_gwp_per_m3 < 0.0:
            runner.registerError("Custom GWP (kgCO2eq/m3) must be non-negative.")
            return False
        if use_custom_costs and use_exact_costline_id:
            runner.registerError("Choose only one cost mode: custom cost OR exact RSMeans costline ID.")
            return False
        if labor_cost_multiplier < 1.0:
            runner.registerError("Labor cost multiplier must be at least 1.0.")
            return False
        if use_exact_costline_id and not exact_costline_id:
            runner.registerError("Exact RSMeans costline ID mode is enabled, but no costline ID was provided.")
            return False

        # Typical material k and density (same style as your wall measure)
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

        # Function to parse RSMeans description for material properties
        def extract_properties_from_rsmeans_description(description: str):
            """
            Parse RSMeans description to extract density and thermal conductivity.
            Returns dict with 'density_kg_m3' and 'conductivity_W_mK' if found, else empty dict.
            """
            extracted = {}
            desc_lower = description.lower()

            def _parse_inches_token(token: str):
                token = str(token).strip()
                if not token:
                    return None
                if "-" in token:
                    whole, frac = token.split("-", 1)
                    try:
                        whole_val = float(whole)
                    except ValueError:
                        return None
                    if "/" in frac:
                        num, den = frac.split("/", 1)
                        try:
                            return whole_val + (float(num) / float(den))
                        except (ValueError, ZeroDivisionError):
                            return None
                    return None
                if "/" in token:
                    num, den = token.split("/", 1)
                    try:
                        return float(num) / float(den)
                    except (ValueError, ZeroDivisionError):
                        return None
                try:
                    return float(token)
                except ValueError:
                    return None

            def _extract_thickness_m_from_description(desc: str):
                thickness_patterns = [
                    r'(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*"',
                    r'(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*(?:in|inch|inches)\b',
                ]
                for pattern in thickness_patterns:
                    match = re.search(pattern, desc, flags=re.IGNORECASE)
                    if not match:
                        continue
                    thickness_in = _parse_inches_token(match.group(1))
                    if thickness_in and thickness_in > 0:
                        return self._unit_convert(thickness_in, "in", "m")
                return None

            # Try to find density in description (e.g., "density 1.5 pcf" or "1.5 lb/ft³")
            import re
            density_patterns = [
                r'density\s*([\d.]+)\s*(?:pcf|lb/ft³|lb/ft\³)',
                r'([\d.]+)\s*(?:pcf|lb/ft³|lb/ft\³)',
            ]
            for pattern in density_patterns:
                match = re.search(pattern, desc_lower)
                if match:
                    density_pcf = float(match.group(1))
                    # Convert lb/ft³ to kg/m³: 1 lb/ft³ = 16.018 kg/m³
                    extracted['density_kg_m3'] = density_pcf * 16.018
                    break

            # Try to find conductivity or R-value in description
            r_value_patterns = [
                r'r-?([\d.]+)',
                r'(?:thermal\s+)?(?:conductivity|resistance)\s*([\d.]+)',
            ]
            for pattern in r_value_patterns:
                match = re.search(pattern, desc_lower)
                if match:
                    r_value_ip_parsed = float(match.group(1))
                    if r_value_ip_parsed > 0:
                        extracted['rsmeans_rvalue_ip_in_description'] = r_value_ip_parsed
                    break

            # Derive thermal conductivity from parsed thickness and R-value when available.
            # R = t / k  =>  k = t / R
            if 'rsmeans_rvalue_ip_in_description' in extracted:
                thickness_m = _extract_thickness_m_from_description(desc_lower)
                if thickness_m and thickness_m > 0:
                    r_value_si_parsed = self._unit_convert(
                        extracted['rsmeans_rvalue_ip_in_description'],
                        "ft^2*h*R/Btu",
                        "m^2*K/W",
                    )
                    if r_value_si_parsed > 0:
                        parsed_k = thickness_m / r_value_si_parsed
                        # Keep only physically plausible insulation conductivity values.
                        if 0.005 <= parsed_k <= 1.5:
                            extracted['conductivity_W_mK'] = parsed_k
                            extracted['rsmeans_thickness_m_in_description'] = thickness_m

            return extracted

        # -- Phase 1: Parse and validate user arguments --
        # (Arguments were already extracted from arg_map above; this comment marks
        # the boundary before any model reads or API calls begin.)

        # Lookup selected material properties.
        # Priority order: RSMeans-extracted text (Phase 2) > user-provided > hardcoded defaults.
        # selected_k and selected_rho are used in Phase 3 for thickness calculations and
        # Phase 4 for embodied-carbon volume-to-mass conversions.
        selected_k = None
        selected_k_source = "hardcoded"
        selected_density_source = "hardcoded"
        rsmeans_extracted_properties = {}

        # -- Phase 2: Early RSMeans property extraction --
        # This pass is only to infer material properties from RSMeans text.
        # Actual costing is done later in the dedicated cost phase.
        if not use_custom_costs:
            try:
                mini_rsmeans_materials = [
                    {
                        "name": f"{insulation_material_type} insulation",
                        "description": f"Insulation material: {insulation_material_type}",
                        "quantity": 100.0,
                        "unit": "SF",
                        "division_code": "07",
                    }
                ]
                if use_exact_costline_id and exact_costline_id:
                    mini_rsmeans_materials[0]["rsmeans_id"] = exact_costline_id

                runner.registerInfo("Attempting early RSMeans lookup for roof material property extraction...")
                rsmeans_module_path = Path(__file__).parent / "resources" / "call_rsmeans_api.py"
                if rsmeans_module_path.exists():
                    spec = importlib.util.spec_from_file_location("call_rsmeans_api_early", rsmeans_module_path)
                    rsmeans_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(rsmeans_module)

                    early_rsmeans_lookup = rsmeans_module.run_rsmeans_cost_lookup(
                        materials=mini_rsmeans_materials,
                        release_id="2024-an",
                        catalogs=["bc-mf", "gb-mf", "rp-mf"],
                        location_id="us-us-national",
                        labor_type="std",
                        measurement_system="imp",
                        use_sandbox=False,
                        overhead_profit_percent=overhead_profit_percent,
                    )

                    if early_rsmeans_lookup and early_rsmeans_lookup.get("status") == "ok":
                        materials_results = early_rsmeans_lookup.get("results", {}).get("materials", [])
                        for mat in materials_results:
                            mat_desc = mat.get("description", "")
                            extracted_props = extract_properties_from_rsmeans_description(mat_desc)
                            if extracted_props:
                                rsmeans_extracted_properties.update(extracted_props)
                                if "density_kg_m3" in extracted_props:
                                    runner.registerInfo(
                                        f"Extracted density from RSMeans: {extracted_props['density_kg_m3']:.2f} kg/m³"
                                    )
                                if "conductivity_W_mK" in extracted_props:
                                    runner.registerInfo(
                                        "Extracted conductivity from RSMeans: "
                                        f"{extracted_props['conductivity_W_mK']:.4f} W/m·K"
                                    )
                    else:
                        runner.registerInfo("Early RSMeans property extraction: no match found (will use defaults)")
            except Exception as e:
                runner.registerInfo(f"Early RSMeans property extraction skipped (non-critical): {str(e)[:100]}")

        if insulation_thermal_conductivity == 0.0:
            if "conductivity_W_mK" in rsmeans_extracted_properties:
                selected_k = rsmeans_extracted_properties["conductivity_W_mK"]
                selected_k_source = "rsmeans_extracted"
            else:
                selected_k = material_k_dict[insulation_material_type]
                selected_k_source = "hardcoded_default"
        else:
            selected_k = insulation_thermal_conductivity
            selected_k_source = "user_provided"

        # Use user-specified density if provided, otherwise use RSMeans-extracted or default
        if insulation_material_density == 0.0:
            if "density_kg_m3" in rsmeans_extracted_properties:
                insulation_material_density = rsmeans_extracted_properties["density_kg_m3"]
                selected_density_source = "rsmeans_extracted"
            else:
                insulation_material_density = material_density_dict[insulation_material_type]
                selected_density_source = "hardcoded_default"
        else:
            selected_density_source = "user_provided"

        # Initialize selected_rho with selected density (may be updated from EPD for hardcoded defaults)
        selected_rho = insulation_material_density
        runner.registerInfo(
            f"Material properties: thermal_conductivity={selected_k:.4f} W/m·K ({selected_k_source}), "
            f"density={insulation_material_density:.2f} kg/m³ ({selected_density_source})"
        )

        # -- Phase 3: Model surgery on roof constructions --
        # Convert user-supplied IP R-value to SI for all internal calculations.
        # OpenStudio model objects use SI throughout.
        r_value_si = self._unit_convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W")

        # Walk all surfaces in the model to collect exterior roof/ceiling surfaces
        # and the unique Construction objects assigned to them.
        # Uniqueness is by name — we only modify each construction once.
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
        skipped_constructions_target_already_met = 0

        # --- Edit each unique roof construction ---
        # For each construction we:
        #   1. Identify the insulation layer (prefer massless layers; fall back to
        #      highest R-per-thickness ratio among standard material layers).
        #   2. Clone the construction and modify only the insulation layer's R-value
        #      or thickness so the whole-assembly target is met.
        #   3. Record how much thickness was added for EC3 volume calculations.
        for cname, construction in unique_constructions.items():
            layers = list(construction.layers())
            if not layers:
                continue

            # Collect thermal data for every opaque layer in this construction.
            # Non-opaque layers (e.g. air films) are skipped — they don't have
            # a thermalResistance method on OpaqueMaterial.
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

            # Select the insulation layer to modify.
            # Strategy A (preferred): pick the massless layer with the highest R-value.
            #   Massless layers in OpenStudio represent pure thermal resistance with no
            #   physical thickness — they are almost always the modelled insulation.
            # Strategy B (fallback): among standard material layers, pick the one with
            #   the highest R-value-per-unit-thickness ratio, which is the best proxy
            #   for a high-performance insulation material.
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
                # No massless layer — find the standard material with the best R/thickness.
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

            # Sanity: minimal insulation - only skip if there's essentially no insulation layer
            if target_R <= self._unit_convert(0.1, "ft^2*h*R/Btu", "m^2*K/W"):
                runner.registerWarning(f"Construction '{cname}' does not appear to have an insulation layer (R < 0.1) and was not altered.")
                continue

            # Skip renovation when requested target does not exceed existing insulation R-value.
            if target_R >= r_value_si:
                current_r_ip = self._unit_convert(target_R, "m^2*K/W", "ft^2*h*R/Btu")
                runner.registerInfo(
                    f"'{cname}' already meets or exceeds the target insulation R-value "
                    f"(current: {current_r_ip:.2f}, target: {r_value_ip:.2f}); skipping renovation."
                )
                skipped_constructions_target_already_met += 1
                continue

            # Clone the whole construction so the original is preserved.
            # We only modify the cloned insulation layer; all other layers are unchanged.
            new_construction = construction.clone(model).to_Construction().get()
            new_construction.setName(f"{construction.nameString()} adj roof insulation")
            final_constructions_array.append(new_construction)

            # If two constructions share the same insulation layer object (same OSM handle),
            # reuse the already-modified clone rather than creating a second identical copy.
            reused = False
            for orig_name, new_mat in materials_hash.items():
                if target_layer.nameString() == orig_name:
                    layer_list = list(new_construction.layers())
                    layer_list.pop(target_index)
                    layer_list.insert(target_index, new_mat)
                    new_construction.setLayers(layer_list)
                    reused = True
                    break

            # delta_R is the thermal resistance that must be added by the new insulation.
            # It is used below to back-calculate how much physical thickness was added,
            # which feeds into the EC3 volume calculation in Phase 4.
            delta_R = r_value_si - target_R

            # Compute added thickness from the original target layer so reused
            # materials still get correct added volume/GWP and downstream costing.
            added_thickness_m = 0.0
            target_massless = target_layer.to_MasslessOpaqueMaterial()
            target_airgap = target_layer.to_AirGap()
            target_std_mat = target_layer.to_Material()
            if delta_R > 0.0:
                if target_massless.is_initialized() or target_airgap.is_initialized():
                    added_thickness_m = delta_R * selected_k
                elif target_std_mat.is_initialized():
                    t_old_target = target_std_mat.get().thickness()
                    if (used_R_for_ratio is not None) and (used_R_for_ratio > 0.0):
                        t_new_target = t_old_target * (r_value_si / used_R_for_ratio)
                    else:
                        t_new_target = t_old_target * (r_value_si / max(target_R, 1e-9))
                    added_thickness_m = max(t_new_target - t_old_target, 0.0)

            # Make/edit material in the construction
            if not reused:
                cloned_layer = target_layer.clone(model)
                massless = cloned_layer.to_MasslessOpaqueMaterial()
                airgap = cloned_layer.to_AirGap()
                std_mat = cloned_layer.to_Material()

                new_name_ip = f"{target_layer.nameString()}_R-value {r_value_ip} (ft^2*h*R/Btu)"
                if massless.is_initialized():
                    # MasslessOpaqueMaterial: pure R-value with no physical thickness.
                    # Simply set the target R directly; derive equivalent thickness
                    # from R = thickness / k  =>  thickness = delta_R * k.
                    m = massless.get()
                    m.setName(new_name_ip)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                    if delta_R > 0.0:
                        added_thickness_m = delta_R * selected_k
                elif airgap.is_initialized():
                    # AirGap: also a pure-R layer; treat identically to massless.
                    m = airgap.get()
                    m.setName(new_name_ip)
                    m.setThermalResistance(r_value_si)
                    new_mat_obj = m
                    if delta_R > 0.0:
                        added_thickness_m = delta_R * selected_k
                elif std_mat.is_initialized():
                    # Standard material with explicit thickness.
                    # Scale thickness proportionally: t_new = t_old * (R_target / R_layer).
                    # This preserves the material's conductivity while achieving the new R.
                    m = std_mat.get()
                    m.setName(new_name_ip)
                    t_old = m.thickness()
                    if (used_R_for_ratio is not None) and (used_R_for_ratio > 0.0):
                        t_new = t_old * (r_value_si / used_R_for_ratio)
                    else:
                        t_new = t_old * (r_value_si / max(target_R, 1e-9))
                    m.setThickness(t_new)
                    new_mat_obj = m
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
                "added_thickness_m": added_thickness_m,  # (0 if no increase)
                "original_r_value_si": target_R,  # Original R-value in SI units
                "target_r_value_si": r_value_si   # Target R-value in SI units
            })

        # Re-assign the upgraded constructions on every roof surface.
        # Surfaces that reference a construction that was not modified are left alone.
        for srf in roof_surfaces:
            if srf.construction().is_initialized():
                old_name = srf.construction().get().nameString()
                if old_name in constructions_hash_old_new:
                    srf.setConstruction(constructions_hash_old_new[old_name])

        # Also update any DefaultConstructionSet objects that point to the old
        # roof construction, so spaces/stories that inherit defaults pick up the
        # upgraded version rather than keeping the original.
        for dcs in model.getDefaultConstructionSets():
            dsc_opt = dcs.defaultExteriorSurfaceConstructions()
            if dsc_opt.is_initialized():
                dsc = dsc_opt.get()
                rc_opt = dsc.roofCeilingConstruction()
                if rc_opt.is_initialized():
                    base_name = rc_opt.get().nameString()
                    if base_name in constructions_hash_old_new:
                        # Clone and configure new construction set
                        new_dcs = dcs.clone(model).to_DefaultConstructionSet().get()
                        new_dsc = dsc.clone(model).to_DefaultSurfaceConstructions().get()
                        new_dcs.setName(f"{dcs.nameString()} adj roof insulation")
                        new_dsc.setName(f"{dsc.nameString()} adj roof insulation")
                        new_dcs.setDefaultExteriorSurfaceConstructions(new_dsc)
                        new_dsc.setRoofCeilingConstruction(constructions_hash_old_new[base_name])

                        # Collect sources BEFORE we modify them
                        sources_to_update = list(dcs.sources())
                        
                        # Replace on sources
                        for src in sources_to_update:
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

        # -- Phase 4: EC3 embodied carbon --
        # Query the EC3 API for Environmental Product Declarations (EPDs) matching
        # the selected insulation material type.  EPDs report Global Warming Potential
        # (GWP) in kg CO₂-equivalent per functional unit (per kg, m², or m³).
        #
        # We collect all matching EPD values into lists and then apply the user's
        # chosen statistic (min/max/mean/median) to select a representative GWP.
        # This guards against outlier EPDs skewing the result.
        carbon_data_unavailable_reasons = []
        if use_custom_gwp:
            runner.registerInfo("Custom GWP mode enabled: skipping EC3 API call for roof insulation carbon calculation.")
            insulation_product_epd = []
        else:
            ec3_url = self._generate_url_by_material_type(insulation_material_type)
            insulation_product_epd = fetch_epd_data(ec3_url, api_key) if ec3_url else []
            if not isinstance(insulation_product_epd, list):
                runner.registerWarning("EC3 lookup returned invalid data; continuing with empty EPD set.")
                insulation_product_epd = []
            if len(insulation_product_epd) == 0:
                carbon_data_unavailable_reasons.append("ec3_epd_fetch_empty")
                runner.registerWarning(
                    f"No EC3 EPD records found for '{insulation_material_type}'. "
                    "Embodied carbon may be reported as 0 due to unavailable carbon data."
                )

        # Accumulate GWP samples from every EPD returned for this material type.
        # Multiple functional-unit bases are kept so we can cross-check and fall back.
        gwp_values = {"gwp_per_kg": [], "gwp_per_m3": [], "gwp_per_m2": []}

        # Density from EPDs (kg/m³) — used to convert between mass- and
        # volume-based GWP values when only one basis is available in the EPD.
        density_values = []

        # Declared service life from EPDs (years) — used as the insulation
        # lifetime unless the user overrides it with insulation_material_lifetime.
        lifetime_values = []

        # loop through each epd
        for idx, epd in enumerate(insulation_product_epd, start = 1):
            try:
                parsed_data  = parse_product_epd(epd)
            except Exception as e:
                runner.registerWarning(f"EPD {idx} could not be parsed and was skipped: {str(e)[:120]}")
                continue
            
            # Extract density if available
            density_str = parsed_data.get("density")
            if density_str:
                density_value = extract_numeric_value(density_str)
                if density_value > 0.0:
                    density_values.append(density_value)
            
            # Extract reference service life
            reference_service_life = parsed_data.get("reference_service_life")
            if reference_service_life is not None:
                if isinstance(reference_service_life, (int, float)):
                    lifetime_values.append(float(reference_service_life))
                elif isinstance(reference_service_life, str):
                    # Extract numeric value from string (e.g., "25 years" -> 25)
                    numeric_value = extract_numeric_value(reference_service_life)
                    if numeric_value is not None and numeric_value > 0:
                        lifetime_values.append(float(numeric_value))
            else:
                runner.registerInfo(f"EPD {idx}: No lifetime data found")
            
            # per mass
            gwp_per_kg = parsed_data.get("gwp_per_kg (kg CO2 eq/kg)", 0.0)
            if gwp_per_kg != 0.0:
                gwp_values["gwp_per_kg"].append(float(gwp_per_kg))
            # per volume
            gwp_per_m3 = parsed_data.get("gwp_per_m3 (kg CO2 eq/m3)", 0.0)
            if gwp_per_m3 != 0.0:
                gwp_values["gwp_per_m3"].append(float(gwp_per_m3))
            # per area
            gwp_per_m2 = parsed_data.get("gwp_per_m2 (kg CO2 eq/m2)", 0.0)
            if gwp_per_m2 != 0.0:
                gwp_values["gwp_per_m2"].append(float(gwp_per_m2))

        if use_custom_gwp:
            gwp_values["gwp_per_kg"] = []
            gwp_values["gwp_per_m2"] = []
            gwp_values["gwp_per_m3"] = [float(custom_gwp_per_m3)]

        # Remove outliers from GWP values using IQR method
        for key in ["gwp_per_kg", "gwp_per_m3", "gwp_per_m2"]:
            if gwp_values[key]:
                gwp_values[key] = self.remove_outliers_iqr(gwp_values[key])
        if not any(len(gwp_values[k]) > 0 for k in ["gwp_per_kg", "gwp_per_m3", "gwp_per_m2"]):
            carbon_data_unavailable_reasons.append("no_valid_gwp_values")
            runner.registerWarning(
                f"No valid GWP values were computed for '{insulation_material_type}'. "
                "Embodied carbon may be reported as 0 due to unavailable carbon data."
            )
        
        # Remove outliers from lifetime values
        if lifetime_values:
            lifetime_values = self.remove_outliers_iqr(lifetime_values)
        
        # Process lifetime from EPD (with fallback to user input)
        user_lifetime = insulation_material_lifetime
        
        if not lifetime_values:
            # No EPD lifetime - use user input
            epd_lifetime = user_lifetime
        else:
            # Apply the same statistic method as GWP values
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
                epd_lifetime = float(np.mean(lifetime_values))  # Default to mean
        
        # Use the EPD-derived or user-specified lifetime for calculations
        selected_lifetime = epd_lifetime
        lifetime_source = "EPD" if epd_lifetime != user_lifetime else "user_input"

        # Use EPD density if available, applying the same statistic method as GWP
        if density_values:
            # Remove outliers from density values
            density_values = self.remove_outliers_iqr(density_values)

            if density_values:
                # Apply statistic based on user selection
                epd_density = 0.0
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

                # Use EPD density only when density came from hardcoded defaults.
                # Preserve user-provided and RSMeans-extracted density values.
                if (not user_specified_density) and (selected_density_source == "hardcoded_default"):
                    selected_rho = epd_density
                else:
                    selected_rho = insulation_material_density
            else:
                selected_rho = insulation_material_density
                runner.registerInfo(
                    f"Density values became empty after outlier filtering. "
                    f"Using {'user-specified' if user_specified_density else 'default'} density: {selected_rho:.2f} kg/m³"
                )
        else:
            selected_rho = insulation_material_density
            runner.registerInfo(f"No density data found in EPDs. Using {'user-specified' if user_specified_density else 'default'} density: {selected_rho:.2f} kg/m³")

        # Analysis-period multiplier (using EPD-derived or user-specified lifetime)
        mult = lifetime_multiplier(selected_lifetime, analysis_period)

        # Compute and tag embodied carbon for each modified construction
        gwp_summary_rows = []
        for item in modified_constructions:
            area_m2 = item["total_area_m2"]
            add_t_m = max(item["added_thickness_m"], 0.0)

            # Volume and (fallback) mass for added material only
            added_volume_m3 = area_m2 * add_t_m
            added_mass_kg = selected_rho * added_volume_m3

            for functional_unit, gwp_list in gwp_values.items():
                gwp = 0.0
                if not gwp_list:
                    gwp = 0.0
                elif len(gwp_list) == 1:
                    gwp = gwp_list[0]
                elif gwp_statistic == "minimum":
                    gwp = float(np.min(gwp_list))
                elif gwp_statistic == "maximum":
                    gwp = float(np.max(gwp_list))
                elif gwp_statistic == "mean":
                    gwp = float(np.mean(gwp_list))
                elif gwp_statistic == "median":
                    gwp = float(np.median(gwp_list))
                if not np.isfinite(gwp):
                    gwp = 0.0
                # store gwp value to modified_constructions dictionary
                item[functional_unit] = gwp

            sel_gwp_per_kg = item.get("gwp_per_kg", 0.0)
            sel_gwp_per_m3 = item.get("gwp_per_m3", 0.0)
            sel_gwp_per_m2 = item.get("gwp_per_m2", 0.0)

            # Calculate total GWP for this added insulation
            total_gwp = item['gwp_per_m3'] * added_volume_m3 * mult
            if (not np.isfinite(total_gwp) or total_gwp == 0.0) and item["gwp_per_kg"] != 0.0:
                total_gwp = item["gwp_per_kg"] * added_mass_kg * mult
            if not np.isfinite(total_gwp):
                total_gwp = 0.0

            gwp_summary_rows.append({
                "construction_name": item["construction"].nameString(),
                "orig_construction": item["orig_construction_name"],
                "insulation_material_type": insulation_material_type,
                "added_total_area_m2": area_m2,
                "added_thickness_m": add_t_m,
                "added_total_volume_m3": added_volume_m3,
                "gwp_per_kg": sel_gwp_per_kg,
                "gwp_per_m2": sel_gwp_per_m2,
                "gwp_per_m3": sel_gwp_per_m3,
                "density_kg_per_m3": selected_rho,
                "lifetime_years": selected_lifetime,
                "lifetime_source": lifetime_source,
                "total_gwp_kg_co2_eq": total_gwp
            })

            # Tag onto construction as additionalProperties
            c = item["construction"]
            
            runner.registerInfo(
                f"Tagged '{c.nameString()}' with embodied carbon: "
                f"{total_gwp:.2f} kg CO₂ eq over {area_m2:.2f} m²"
            )

        # Calculate building-level totals for summarization
        total_embodied_carbon = sum(row["total_gwp_kg_co2_eq"] for row in gwp_summary_rows)
        total_roof_area = sum(row["added_total_area_m2"] for row in gwp_summary_rows)
        
        # -- Phase 5: Cost lookup and AdditionalProperties write-out --
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

        # ===================== RSMeans cost lookup =====================
        # Backward-compatible alias; historically this field name was used
        # even when RSMeans values included both material and labor.
        total_material_cost = 0.0
        total_labor_cost = 0.0
        total_equipment_cost = 0.0
        total_overhead_profit_cost = 0.0
        cost_source = "none"
        cost_factor_basis = "not_calculated"
        rsmeans_cost_per_cf_feature_value = "N/A"
        retrofit_materials_json = None
        rsmeans_materials_detail_json = None
        rsmeans_material_id_for_write = None
        rsmeans_material_description_for_write = None

        # Create per-construction RSMeans material entries with actual thicknesses
        rsmeans_materials = []
        for row in gwp_summary_rows:
            const_name = row.get("orig_construction", "unknown")
            area_m2 = row.get("added_total_area_m2", 0.0)
            thickness_m = row.get("added_thickness_m", 0.0)
            
            area_ft2 = self._unit_convert(area_m2, "m^2", "ft^2")
            thickness_in = self._unit_convert(thickness_m, "m", "in")
            thickness_ft = max(thickness_in / 12.0, 0.0)
            volume_ft3 = area_ft2 * thickness_ft

            if volume_ft3 <= 0.0:
                runner.registerInfo(
                    f"Skipping RSMeans costing entry for '{const_name}' because added insulation volume is 0."
                )
                continue
            
            rsmeans_materials.append({
                "name": f"{insulation_material_type} roof insulation ({const_name})",
                "description": f"Added insulation to reach R-{r_value_ip}; actual added thickness {thickness_in:.2f} in",
                "quantity": float(area_ft2),
                "unit": "SF",
                "quantity_volume": float(volume_ft3),
                "unit_volume": "CF",
                "rsmeans_thickness_ft": float(thickness_ft),
                "costing_mode": "volume_from_area",
                "quantity_si": float(area_m2),
                "unit_si": "m2",
                "division_code": "07",
                "rsmeans_id": exact_costline_id if use_exact_costline_id else None,
            })

        if rsmeans_materials:
            try:
                retrofit_materials_json = json.dumps(rsmeans_materials)
            except Exception:
                runner.registerWarning("Could not serialize RSMeans retrofit materials to JSON.")

        if rsmeans_materials:
            if use_custom_costs:
                if custom_cost_per_cf <= 0.0:
                    runner.registerWarning("Custom cost mode enabled, but custom_cost_per_cf is 0. Skipping cost calculation.")
                else:
                    total_added_volume_cf = sum(float(m.get("quantity_volume", 0.0)) for m in rsmeans_materials)
                    if total_added_volume_cf > 0.0:
                        _lc_mult = int(lifetime_multiplier(insulation_material_lifetime, analysis_period))
                        total_material_cost = custom_cost_per_cf * total_added_volume_cf * _lc_mult
                        if labor_cost_multiplier > 1.0:
                            total_labor_cost = total_material_cost * (labor_cost_multiplier - 1.0)
                        total_overhead_profit_cost = (total_material_cost + total_labor_cost) * (overhead_profit_percent / 100.0)
                        cost_source = "custom_input"
                        cost_factor_basis = "custom_cost_per_volume"
                        runner.registerInfo(
                            "Custom cost summary (cost_source=custom_input): "
                            f"material_cost=${total_material_cost:,.2f} (lifetime_multiplier={_lc_mult}), "
                            f"labor_cost=${total_labor_cost:,.2f} "
                            f"overhead_profit_cost=${total_overhead_profit_cost:,.2f} "
                            f"(volume={total_added_volume_cf:.2f} CF × rate ${custom_cost_per_cf}/CF, "
                            f"labor_multiplier={labor_cost_multiplier:.2f}, overhead_profit_percent={overhead_profit_percent:.1f}%)"
                        )
                    else:
                        runner.registerWarning("Custom cost mode enabled, but added volume is 0. Skipping cost calculation.")
            else:
                rsmeans_module_path = Path(__file__).parent / "resources" / "call_rsmeans_api.py"
                if rsmeans_module_path.exists():
                    try:
                        runner.registerInfo("Starting RSMeans lookup for roof insulation...")
                        spec = importlib.util.spec_from_file_location("call_rsmeans_api", rsmeans_module_path)
                        rsmeans_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(rsmeans_module)
                        rsmeans_lookup = rsmeans_module.run_rsmeans_cost_lookup(
                            materials=rsmeans_materials,
                            release_id="2024-an",
                            catalogs=["bc-mf", "gb-mf", "rp-mf"],
                            location_id="us-us-national",
                            labor_type="std",
                            measurement_system="imp",
                            use_sandbox=False,
                            overhead_profit_percent=overhead_profit_percent,
                            fallback_costline_ids={
                                "keyword:blown cellulose": "072126100020",
                                "keyword:blown fiberglass": "072126101000",
                                "keyword:blown mineral wool": "072123100100",
                                "keyword:polyiso insulation foam board": "072216101700",
                                "keyword:polyiso foam board": "072216101700",
                                # GPS has the same R-value (~R5/inch) as XPS, so XPS is a
                                # closer cost proxy than EPS (R4/inch). RSMeans 2024-an has
                                # no graphite-polystyrene line.
                                "keyword:graphite polystyrene": "072216101910",
                                "keyword:gps foam board": "072216101910",
                                "keyword:expanded polystyrene": "072113130600",
                                "keyword:eps foam board": "072113130600",
                                "keyword:extruded polystyrene": "072216101910",
                                "keyword:xps foam board": "072216101910",
                                "keyword:mineral wool heavy density blanket": "072116201320",
                                "keyword:mineral wool light density blanket": "072116201320",
                                "keyword:fiberglass batts": "072116200620",
                                "__default__": "072116201320",
                            },  # Keyword fallback + default fallback
                        )
                        if rsmeans_lookup and rsmeans_lookup.get("status") == "ok":
                            summary = rsmeans_lookup.get("summary", {})
                            # Bare costs come split into material/labor/equipment
                            # by call_rsmeans_api so we can populate the
                            # AdditionalProperties cost fields independently and
                            # apply the lifetime multiplier uniformly. Overhead
                            # and profit are computed by the helper on the
                            # combined bare cost (single application).
                            _lc_mult = int(lifetime_multiplier(insulation_material_lifetime, analysis_period))
                            total_material_cost = float(summary.get("total_material_cost", 0.0)) * _lc_mult
                            total_labor_cost = float(summary.get("total_labor_cost", 0.0)) * _lc_mult
                            total_equipment_cost = float(summary.get("total_equipment_cost", 0.0)) * _lc_mult
                            total_overhead_profit_cost = float(summary.get("total_overhead_profit_cost", 0.0)) * _lc_mult
                            cost_source = "rsmeans_api"
                            materials_results = rsmeans_lookup.get(
                                "results", {}
                            ).get("materials", [])
                            total_added_volume_cf = sum(float(m.get("quantity_volume", 0.0)) for m in rsmeans_materials)
                            if total_added_volume_cf > 0.0:
                                # Cost-per-CF feature reflects the full installed
                                # bare cost (material + labor + equipment) so it
                                # remains comparable across line types regardless
                                # of how the API splits the components.
                                total_bare_cost = float(summary.get(
                                    "total_bare_cost",
                                    float(summary.get("total_material_cost", 0.0))
                                    + float(summary.get("total_labor_cost", 0.0))
                                    + float(summary.get("total_equipment_cost", 0.0)),
                                ))
                                rsmeans_cost_per_cf_feature_value = total_bare_cost / total_added_volume_cf
                            if materials_results:
                                first_match = materials_results[0]
                                matched_rsmeans_id = first_match.get("rsmeans_id") or rsmeans_materials[0].get("rsmeans_id", "")
                                matched_rsmeans_description = first_match.get("rsmeans_description") or first_match.get("description", "")
                                if matched_rsmeans_id:
                                    rsmeans_material_id_for_write = str(matched_rsmeans_id)
                                if matched_rsmeans_description:
                                    rsmeans_material_description_for_write = str(matched_rsmeans_description)
                            search_log = rsmeans_lookup.get(
                                "results", {}
                            ).get("search_log", [])

                            # Derive a human-readable cost basis from matched results.
                            mode_values = {
                                str(mat.get("costing_mode", "")).strip().lower()
                                for mat in materials_results
                                if str(mat.get("costing_mode", "")).strip()
                            }
                            unit_values = {
                                str(mat.get("unit_cost_basis", "")).strip().upper()
                                for mat in materials_results
                                if str(mat.get("unit_cost_basis", "")).strip()
                            }
                            if mode_values == {"volume_from_area"} or unit_values == {"CF"}:
                                cost_factor_basis = "cost_per_volume"
                            elif mode_values == {"area"} and unit_values == {"SF"}:
                                cost_factor_basis = "cost_per_area"
                            elif len(mode_values) > 1 or len(unit_values) > 1:
                                cost_factor_basis = "mixed"
                            elif mode_values == {"area"}:
                                cost_factor_basis = "cost_per_unit"
                            elif mode_values:
                                cost_factor_basis = "other"
                            else:
                                cost_factor_basis = "other"

                            unmatched_materials = self._collect_unmatched_rsmeans_materials(
                                rsmeans_materials,
                                materials_results,
                            )
                            exact_id_fallbacks = []
                            if use_exact_costline_id:
                                exact_id_fallbacks = sorted({
                                    str(material.get("name", "")).strip()
                                    for material in materials_results
                                    if material.get("match_type") != "exact_id_match"
                                    and material.get("name")
                                })

                            unresolved_materials = []
                            for material_name in unmatched_materials + exact_id_fallbacks:
                                if material_name and material_name not in unresolved_materials:
                                    unresolved_materials.append(material_name)

                            if unresolved_materials:
                                for material_name in unmatched_materials:
                                    runner.registerWarning(
                                        "RSMeans did not find a catalog match for "
                                        f"retrofit material '{material_name}'."
                                    )
                                if use_exact_costline_id:
                                    for material_name in exact_id_fallbacks:
                                        runner.registerWarning(
                                            "RSMeans exact-ID mode did not return "
                                            f"the requested costline ID '{exact_costline_id}' "
                                            f"for '{material_name}'."
                                        )
                                self._register_rsmeans_resolution_error(
                                    runner,
                                    unresolved_materials,
                                    use_exact_costline_id,
                                    exact_costline_id,
                                )
                                return False

                            # Ambiguity warning: when closest-match mode
                            # auto-selected from tied candidates, warn the
                            # user but proceed with the auto-selected result.
                            if not use_exact_costline_id:
                                ambiguous_matches = (
                                    self
                                    ._detect_rsmeans_ambiguous_candidates(
                                        search_log
                                    )
                                )
                                if ambiguous_matches:
                                    for amb in ambiguous_matches:
                                        tied = amb["tied_candidates"]
                                        tied_descs = "; ".join(
                                            f"'{c.get('description','?')}'" for c in tied[:6]
                                        )
                                        auto_id = amb["matched_rsmeans_id"]
                                        auto_desc = amb["matched_description"]
                                        runner.registerWarning(
                                            f"RSMeans found "
                                            f"{len(tied)} equally-scored candidates "
                                            f"for '{amb['material']}' "
                                            f"(search term: "
                                            f"'{amb['search_term_used']}'). "
                                            f"Auto-selected: "
                                            f"'{auto_desc}' "
                                            f"(ID: {auto_id}). "
                                            f"All tied candidates: "
                                            f"{tied_descs}. "
                                            f"To pin a specific entry, rerun with "
                                            f"`use_exact_costline_id=True` and "
                                            f"`exact_costline_id` set to the desired ID, "
                                            f"or set `use_custom_costs=True` with "
                                            f"`custom_cost_per_cf`."
                                        )

                            # Persist compact RSMeans material detail JSON for downstream inspection.
                            try:
                                storable_results = []
                                for mat in materials_results:
                                    storable_results.append({
                                        "name": mat.get("name", ""),
                                        "description": mat.get("description", ""),
                                        "quantity": mat.get("quantity", 0.0),
                                        "unit": mat.get("unit", ""),
                                        "division_code": mat.get("division_code", ""),
                                        "rsmeans_id": mat.get("rsmeans_id", ""),
                                        "rsmeans_description": mat.get("rsmeans_description", ""),
                                        "unit_cost": mat.get("unit_cost", 0.0),
                                        "total_cost": mat.get("total_cost", 0.0),
                                        "bare_material_unit_cost": mat.get("bare_material_unit_cost", 0.0),
                                        "bare_material_total_cost": mat.get("bare_material_total_cost", 0.0),
                                        "bare_total_unit_cost": mat.get("bare_total_unit_cost", 0.0),
                                        "bare_total_total_cost": mat.get("bare_total_total_cost", 0.0),
                                        "line_uom": mat.get("line_uom", ""),
                                        "unit_cost_basis": mat.get("unit_cost_basis", mat.get("unit", "")),
                                        "costing_mode": mat.get("costing_mode", ""),
                                        "match_type": mat.get("match_type", ""),
                                        "catalog": mat.get("catalog", ""),
                                        "search_term_used": mat.get("search_term_used", ""),
                                        "source": mat.get("source", ""),
                                    })
                                rsmeans_materials_detail_json = json.dumps(storable_results)
                            except Exception:
                                runner.registerWarning("Could not serialize RSMeans material detail JSON.")
                            if materials_results:
                                runner.registerInfo("RSMeans materials detail:")
                                for mat in materials_results:
                                    mat_name = mat.get("name", "(unknown)")
                                    mat_desc = mat.get("description", "")
                                    mat_qty = mat.get("quantity", 0.0)
                                    mat_unit = mat.get("unit", "")
                                    mat_div = mat.get("division_code", "")
                                    mat_rsmeans_id = mat.get("rsmeans_id", "N/A")
                                    mat_unit_cost = mat.get("unit_cost", 0.0)
                                    mat_total_cost = mat.get("total_cost", 0.0)
                                    mat_unit_cost_basis = mat.get("unit_cost_basis", mat_unit)
                                    runner.registerInfo(
                                        f"  - {mat_name} | {mat_desc} | {mat_qty} {mat_unit} | "
                                        f"division {mat_div} | "
                                        f"costline_id={mat_rsmeans_id} | "
                                        f"unit=${mat_unit_cost:,.2f}/{mat_unit_cost_basis} | total=${mat_total_cost:,.2f}"
                                    )
                            runner.registerInfo(
                                "RSMeans cost summary: "
                                f"materials={summary.get('materials_count', 0)}, "
                                f"total_cost=${summary.get('total_cost_with_overhead_profit', 0.0):,.2f} "
                                f"(Note: RSMeans unit costs include both material and labor)"
                            )
                        else:
                            runner.registerWarning(
                                f"RSMeans lookup failed: {rsmeans_lookup.get('message', 'unknown error')}"
                            )
                    except Exception as e:
                        runner.registerWarning(f"RSMeans lookup failed: {e}")
                else:
                    runner.registerWarning("RSMeans lookup skipped: call_rsmeans_api.py not found")

        # ===================== AdditionalProperties write-out (centralized) =====================
        # Building bucket: basic inputs
        basic_input.setFeature("roof_insulation_measure_name", "Increase Insulation R-Value for Roofs")
        basic_input.setFeature("roof_insulation_analysis_period_years", analysis_period)
        basic_input.setFeature("roof_insulation_gwp_statistic", gwp_statistic)
        basic_input.setFeature("roof_insulation_gwp_source", "custom_user_inputs" if use_custom_gwp else "ec3")

        # Site bucket: renovation details/quantities
        reno_detail.setFeature("roof_insulation_renovated_area_m2", total_roof_area)
        reno_detail.setFeature("roof_insulation_added_volume_m3", sum(item["added_total_volume_m3"] for item in gwp_summary_rows))
        reno_detail.setFeature("roof_insulation_target_r_value_ip", r_value_ip)
        reno_detail.setFeature("roof_insulation_material_type", insulation_material_type)
        reno_detail.setFeature("roof_insulation_modified_constructions_count", len(modified_constructions))
        if len(modified_constructions) != 0 and skipped_constructions_target_already_met > 0:
            roof_summary_notes = (
                "No roof insulation renovation executed because target R-value is less than or equal to existing roof insulation R-value "
                f"for all eligible constructions (skipped={skipped_constructions_target_already_met}) "
                f"even though insulation material '{insulation_material_type}' was selected."
            )
        elif len(modified_constructions) == 0:
            roof_summary_notes = (
                "No roof insulation renovation executed because no roof constructions were found. "
            )
        else:
            roof_summary_notes = (
                "Roof insulation renovation completed. "
                f"Modified constructions={len(modified_constructions)}, "
                f"target-already-met skips={skipped_constructions_target_already_met}."
            )
        reno_detail.setFeature("roof_insulation_summary_notes", roof_summary_notes)

        # SizingParameters bucket: material properties
        mtrl_prop.setFeature("roof_insulation_material_lifetime_years", selected_lifetime)
        mtrl_prop.setFeature("roof_insulation_material_density_kg_per_m3", selected_rho)
        mtrl_prop.setFeature("roof_insulation_material_thermal_conductivity_W_per_mK", selected_k)
        if rsmeans_material_id_for_write:
            mtrl_prop.setFeature("roof_insulation_material_rsmeans_id", rsmeans_material_id_for_write)
        if rsmeans_material_description_for_write:
            mtrl_prop.setFeature("roof_insulation_material_rsmeans_description", rsmeans_material_description_for_write)

        # Store RSMeans JSON payloads on modified constructions (not model-level buckets).
        for idx, item in enumerate(modified_constructions):
            props = item["construction"].additionalProperties()
            props.setFeature("roof_insulation_renovated_exterior_roof_area_m2", item["total_area_m2"])
            props.setFeature("roof_insulation_renovated_embodied_carbon_kgCO2eq", gwp_summary_rows[idx]["total_gwp_kg_co2_eq"])
            props.setFeature("roof_insulation_material_type", insulation_material_type)
            if retrofit_materials_json is not None:
                props.setFeature("roof_insulation_retrofit_materials_json", retrofit_materials_json)
            if rsmeans_materials_detail_json is not None:
                props.setFeature("roof_insulation_rsmeans_materials_detail_json", rsmeans_materials_detail_json)

        # SimulationControl bucket: results
        results.setFeature("roof_insulation_embodied_carbon_kgCO2eq", total_embodied_carbon)
        results.setFeature("roof_insulation_material_cost_$", total_material_cost)
        results.setFeature("roof_insulation_labor_cost_$", total_labor_cost)
        results.setFeature("roof_insulation_equipment_cost_$", total_equipment_cost)
        results.setFeature("roof_insulation_overhead_profit_cost_$", total_overhead_profit_cost)
        results.setFeature(
            "roof_insulation_total_cost_with_overhead_and_profit_$",
            total_material_cost + total_labor_cost + total_equipment_cost + total_overhead_profit_cost,
        )
        results.setFeature("roof_insulation_cost_factor_basis", cost_factor_basis)
        if use_exact_costline_id and exact_costline_id:
            results.setFeature("roof_insulation_rsmeans_requested_costline_id", exact_costline_id)

        # Facility bucket: emission/cost factors
        factors.setFeature("roof_insulation_cost_source", cost_source)
        factors.setFeature("roof_insulation_overhead_profit_percent", overhead_profit_percent)
        factors.setFeature("roof_insulation_cost_factor_basis", cost_factor_basis)
        factors.setFeature("roof_insulation_custom_labor_cost_multiplier", labor_cost_multiplier)
        if use_custom_costs:
            factors.setFeature("roof_insulation_custom_cost_per_cf", custom_cost_per_cf)
        factors.setFeature("roof_insulation_material_rsmeans_cost_per_cf", rsmeans_cost_per_cf_feature_value)
        

        # Emission factors aggregated from selected statistic lists
        if gwp_values["gwp_per_kg"]:
            factors.setFeature("roof_insulation_material_gwp_per_kg", float(np.mean(gwp_values["gwp_per_kg"])))
        if gwp_values["gwp_per_m2"]:
            factors.setFeature("roof_insulation_material_gwp_per_m2", float(np.mean(gwp_values["gwp_per_m2"])))
        if gwp_values["gwp_per_m3"]:
            factors.setFeature("roof_insulation_material_gwp_per_m3", float(np.mean(gwp_values["gwp_per_m3"])))

        # Construction names for traceability
        construction_names = [item["construction"].nameString() for item in modified_constructions]
        if construction_names:
            basic_input.setFeature("roof_insulation_renovated_construction_names", ', '.join(construction_names))
        
        # Report per-construction areas
        runner.registerInfo("Roof area by construction:")
        for row in gwp_summary_rows:
            const_name = row.get("orig_construction", "unknown")
            area_m2 = row.get("added_total_area_m2", 0.0)
            area_ft2 = self._unit_convert(area_m2, "m^2", "ft^2")
            runner.registerInfo(
                f"  - {const_name}: {area_m2:.2f} m² ({area_ft2:.2f} ft²)"
            )
        
        runner.registerInfo(
            f"Building-level summary: Total embodied carbon = {total_embodied_carbon:.2f} kg CO2 eq "
            f"across {total_roof_area:.2f} m² of roofs"
        )

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
            f"{r_value_ip}. This was applied to "
            f"{self._neat_numbers(affected_area_ip, 0)} (ft^2) across "
            f"{len(finals)} roof constructions: {', '.join(finals)}."
        )
        return True


# Register the measure
IncreaseInsulationRValueForRoofs().registerWithApplication()
