# *******************************************************************************
# OpenStudio(R), Copyright (c) Alliance for Sustainable Energy, LLC.
# See also https://openstudio.net/license
# *******************************************************************************

# Execution flow (see run() for details):
#   Phase 1 — Argument parsing and validation
#   Phase 2 — Early RSMeans lookup: fetch a material description to extract k and density
#              before the EC3 call, so volume calculations use the best available values.
#   Phase 3 — Model surgery: identify exterior wall constructions, compute added thickness,
#              clone and modify constructions, insert a new insulation layer.
#   Phase 4 — EC3 EPD fetch: query the Building Transparency API for GWP data and
#              calculate embodied carbon over the analysis period.
#   Phase 5 — Cost lookup (RSMeans or custom) and AdditionalProperties write-out.
#              Properties are stored across five model objects per the bucket diagram:
#                Building          → basic_input  (measure name, analysis period, gwp statistic)
#                Site              → reno_detail  (target R-value, material type, renovated area)
#                Facility          → factors      (emission/cost factors: GWP per kg/m2/m3, cost source)
#                SimulationControl → results      (emission/cost results: total carbon, costs, RSMeans detail JSON)
#                SizingParameters  → mtrl_prop    (material properties: k, density, lifetime, RSMeans extracted JSON)
import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import openstudio

measure_dir = os.path.dirname(os.path.abspath(__file__))
if measure_dir not in sys.path:
    sys.path.insert(0, measure_dir)

from resources.EC3_lookup import (
    compute_gwp_data,
    extract_numeric_value,
    fetch_epd_data,
    generate_url_byname,
    lifetime_multiplier,
    parse_product_epd,
)


class IncreaseInsulationRValueForExteriorWalls(openstudio.measure.ModelMeasure):
    def name(self):
        return "Increase R-value of Insulation for Exterior Walls to a Specific Value"

    def description(self):
        return "Increases the R-value of insulation layers in exterior walls to meet a specified target."

    def modeler_description(self):
        return ("This measure modifies insulation materials in exterior wall constructions to reach "
                "a user-defined R-value target by adding supplemental insulation layers. The measure "
                "identifies the existing insulation layer with the highest R-value in each exterior wall "
                "construction and calculates the additional thickness needed to meet the target. "
                "It supports various insulation types including blown materials (cellulose, fiberglass, "
                "mineral wool), foam boards (polyiso, EPS, XPS, GPS), and batts (fiberglass, mineral wool, "
                "pure wool). The measure fetches Environmental Product Declaration (EPD) data from the EC3 "
                "database to calculate embodied carbon (GWP) for the added insulation over a specified "
                "analysis period. Outlier removal using the IQR method is applied to GWP values to improve "
                "accuracy. Results including embodied carbon, material quantities, and GWP metrics are "
                "stored as additional properties on each modified construction for downstream reporting.")

    @staticmethod
    def gwp_statistics():
        return ["minimum","maximum","mean","median"]

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
#            "Pure Wool Batts"
        ]  

    @staticmethod
    def _unit_convert(value, from_u, to_u):
        return openstudio.convert(value, from_u, to_u).get()
    
    def arguments(self, model):
        args = openstudio.measure.OSArgumentVector()

        r_value = openstudio.measure.OSArgument.makeDoubleArgument("r_value", True)
        r_value.setDisplayName("Target Insulation R-value (ft²·h·°F/Btu)")
        r_value.setDefaultValue(13.0)
        args.append(r_value)

        # # WBLCA Parameters
        analysis_period = openstudio.measure.OSArgument.makeIntegerArgument("analysis_period",True)
        analysis_period.setDisplayName("Analysis Period")
        analysis_period.setDescription("Analysis period of embodied carbon of building/building assembly")
        analysis_period.setDefaultValue(30)
        args.append(analysis_period)

        use_lifetime_multiplier = openstudio.measure.OSArgument.makeBoolArgument("use_lifetime_multiplier", True)
        use_lifetime_multiplier.setDisplayName("Apply Lifetime Multiplier to Carbon & Cost")
        use_lifetime_multiplier.setDescription("If true, account for replacement cycles over analysis period; if false, use single-install multiplier of 1.")
        use_lifetime_multiplier.setDefaultValue(False)
        args.append(use_lifetime_multiplier)

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

        # Dropdown list of available insulation materials
        insulation_materials_types_chs = openstudio.StringVector()
        for option in self.insulation_material_types():
            insulation_materials_types_chs.append(option)
        insulation_material_type = openstudio.measure.OSArgument.makeChoiceArgument("insulation_material_type", insulation_materials_types_chs, True)
        insulation_material_type.setDisplayName("Chosen Retrofit Material for Insulation of Exterior Wall")
        insulation_material_type.setDefaultValue("Fiberglass Batts")
        args.append(insulation_material_type)

        insulation_material_lifetime = openstudio.measure.OSArgument.makeIntegerArgument("insulation_material_lifetime",True)
        insulation_material_lifetime.setDisplayName("Product Lifetime of Insulation Material")
        insulation_material_lifetime.setDefaultValue(30)
        args.append(insulation_material_lifetime)

        insulation_thermal_conductivity = openstudio.measure.OSArgument.makeDoubleArgument("insulation_thermal_conductivity", True)
        insulation_thermal_conductivity.setDisplayName("Thermal Conductivity of Insulation Material (W/m·K)")
        insulation_thermal_conductivity.setDescription("Thermal conductivity of the insulation material, if 0.0 is entered, typical conductivity will be used based on material type.")
        insulation_thermal_conductivity.setDefaultValue(0.0) 
        args.append(insulation_thermal_conductivity)

        insulation_material_density = openstudio.measure.OSArgument.makeDoubleArgument("insulation_material_density", True)
        insulation_material_density.setDisplayName("Density of Insulation Material (kg/m³)")
        insulation_material_density.setDescription("Density of the insulation material, if 0.0 is entered, typical density will be used based on material type.")
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

        cost_calc_basis_values = openstudio.StringVector()
        cost_calc_basis_values.append("totalop")
        cost_calc_basis_values.append("bare_material")
        cost_calculation_basis = openstudio.measure.OSArgument.makeChoiceArgument(
            "cost_calculation_basis", cost_calc_basis_values, True
        )
        cost_calculation_basis.setDisplayName("Construction Cost Calculation Basis")
        cost_calculation_basis.setDescription(
            "Choose total installed cost (totalop) or bare material cost (bare_material). "
            "This switch applies to both RSMeans and custom cost paths."
        )
        cost_calculation_basis.setDefaultValue("totalop")
        args.append(cost_calculation_basis)

        use_exact_costline_id = openstudio.measure.OSArgument.makeBoolArgument("use_exact_costline_id", True)
        use_exact_costline_id.setDisplayName("Use Exact RSMeans Costline ID")
        use_exact_costline_id.setDescription("If true, use exact_costline_id for deterministic RSMeans selection.")
        use_exact_costline_id.setDefaultValue(False)
        args.append(use_exact_costline_id)

        exact_costline_id = openstudio.measure.OSArgument.makeStringArgument("exact_costline_id", True)
        exact_costline_id.setDisplayName("Exact RSMeans Costline ID")
        exact_costline_id.setDescription("Optional explicit RSMeans ID, for example 072216101700")
        exact_costline_id.setDefaultValue("")
        args.append(exact_costline_id)

        return args

    def generate_url_by_material_type(self, material_type):

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

    def run(self, model, runner, user_arguments):
        super().run(model, runner, user_arguments)
        if not runner.validateUserArguments(self.arguments(model), user_arguments):
            return False

        r_value_ip = runner.getDoubleArgumentValue("r_value", user_arguments)
        # WBLCA parameters:
        analysis_period = runner.getIntegerArgumentValue("analysis_period",user_arguments)
        use_lifetime_multiplier = runner.getBoolArgumentValue("use_lifetime_multiplier", user_arguments)
        gwp_statistic = runner.getStringArgumentValue("gwp_statistic", user_arguments)
        api_key = runner.getStringArgumentValue("api_key", user_arguments)
        insulation_material_type = runner.getStringArgumentValue("insulation_material_type", user_arguments)
        insulation_material_lifetime = runner.getIntegerArgumentValue("insulation_material_lifetime", user_arguments)
        insulation_thermal_conductivity = runner.getDoubleArgumentValue("insulation_thermal_conductivity", user_arguments)
        insulation_material_density = runner.getDoubleArgumentValue("insulation_material_density", user_arguments)
        if str(insulation_material_type).strip().lower() == "none":
            runner.registerInfo("Insulation material type is 'none'; skipping wall insulation and cost calculation.")
            return True
        use_custom_gwp = runner.getBoolArgumentValue("use_custom_gwp", user_arguments)
        custom_gwp_per_m3 = runner.getDoubleArgumentValue("custom_gwp_per_m3", user_arguments)
        use_custom_costs = runner.getBoolArgumentValue("use_custom_costs", user_arguments)
        custom_cost_per_cf = runner.getDoubleArgumentValue("custom_cost_per_cf", user_arguments)
        labor_cost_multiplier = runner.getDoubleArgumentValue("labor_cost_multiplier", user_arguments)
        overhead_profit_percent = runner.getDoubleArgumentValue("overhead_profit_percent", user_arguments)
        cost_calculation_basis = str(
            runner.getStringArgumentValue("cost_calculation_basis", user_arguments)
        ).strip().lower()
        use_exact_costline_id = runner.getBoolArgumentValue("use_exact_costline_id", user_arguments)
        exact_costline_id = runner.getStringArgumentValue("exact_costline_id", user_arguments).strip()

        if cost_calculation_basis not in ("totalop", "bare_material"):
            runner.registerWarning(
                f"Invalid cost_calculation_basis '{cost_calculation_basis}'. Falling back to 'totalop'."
            )
            cost_calculation_basis = "totalop"

        if use_exact_costline_id and not exact_costline_id:
            runner.registerError("use_exact_costline_id is enabled, but exact_costline_id is empty.")
            return False

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

        # Check if numeric values are reasonable
        if analysis_period <= 0:
            runner.registerError("Analysis period must be greater than 0 years.")
            return False
        if insulation_material_lifetime <= 0:
            runner.registerError("Choose an integer larger than 0 for product lifetime of insulating material.")
            return False

        if r_value_ip < 0 or r_value_ip > 500:
            runner.registerError("R-value must be between 0 and 500 ft²·h·°F/Btu.")
            return False

        if insulation_thermal_conductivity < 0:
            runner.registerError("Thermal conductivity of insulation material must be non-negative.")
            return False

        if insulation_material_density < 0:
            runner.registerError("Density of insulation material must be non-negative.")
            return False
        if use_custom_gwp and custom_gwp_per_m3 < 0:
            runner.registerError("Custom GWP (kgCO2eq/m3) must be non-negative.")
            return False

        # Convert R-value from IP to SI units (m²·K/W)
        r_value_si = openstudio.convert(r_value_ip, "ft^2*h*R/Btu", "m^2*K/W").get()

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
                r'density\s*([\d.]+)\s*(?:pcf|lb/ft³|lb/ft\³)',  # density 1.5 pcf
                r'([\d.]+)\s*(?:pcf|lb/ft³|lb/ft\³)',  # 1.5 pcf
            ]
            for pattern in density_patterns:
                match = re.search(pattern, desc_lower)
                if match:
                    density_pcf = float(match.group(1))
                    # Convert lb/ft³ to kg/m³: 1 lb/ft³ = 16.018 kg/m³
                    density_kg_m3 = density_pcf * 16.018
                    extracted['density_kg_m3'] = density_kg_m3
                    break
            
            # Try to find conductivity or R-value in description
            r_value_patterns = [
                r'r-?([\d.]+)',  # R-5, r-3.5, etc.
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
                        if 0.005 <= parsed_k <= 1.5:
                            extracted['conductivity_W_mK'] = parsed_k
                            extracted['rsmeans_thickness_m_in_description'] = thickness_m
            
            return extracted

        # Define typical thermal conductivity (k) values in W/m-K for each material
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

        # Define typical density (ρ) values in kg/m³ for each material
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

        # Lookup selected material's thermal conductivity
        # Try to get properties from RSMeans first, then fall back to hardcoded
        selected_k = None
        selected_k_source = "hardcoded"
        selected_density_source = "hardcoded"
        rsmeans_extracted_properties = {}
        
        # ── Phase 2: Early RSMeans lookup ─────────────────────────────────────────
        # Query RSMeans once before the EC3 call purely to extract material properties
        # (thermal conductivity k, density) from the matched line-item description.
        # This matters because embodied carbon = GWP × volume, and volume = thickness × area,
        # where thickness = delta_R × k.  If the user left k = 0.0, we try RSMeans first;
        # the hardcoded default is the last resort.
        # A second RSMeans call is made later in Phase 5 to compute actual cost outputs.
        if not use_custom_costs:
            try:
                # Build minimal materials list just for RSMeans property extraction
                mini_rsmeans_materials = [
                    {
                        "name": f"{insulation_material_type} insulation",
                        "description": f"Insulation material: {insulation_material_type}",
                        "quantity": 100.0,
                        "unit": "SF",
                        "division_code": "07",
                    }
                ]
                
                runner.registerInfo("Attempting early RSMeans lookup for material property extraction...")
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
                        write_api_log=False,
                    )
                    
                    if early_rsmeans_lookup and early_rsmeans_lookup.get("status") == "ok":
                        materials_results = early_rsmeans_lookup.get("results", {}).get("materials", [])
                        for mat in materials_results:
                            mat_desc = mat.get("description", "")
                            extracted_props = extract_properties_from_rsmeans_description(mat_desc)
                            if extracted_props:
                                rsmeans_extracted_properties.update(extracted_props)
                                if 'density_kg_m3' in extracted_props:
                                    runner.registerInfo(
                                        f"Extracted density from RSMeans: {extracted_props['density_kg_m3']:.2f} kg/m³"
                                    )
                                if 'conductivity_W_mK' in extracted_props:
                                    runner.registerInfo(
                                        "Extracted conductivity from RSMeans: "
                                        f"{extracted_props['conductivity_W_mK']:.4f} W/m·K"
                                    )
                    else:
                        runner.registerInfo("Early RSMeans property extraction: no match found (will use defaults)")
            except Exception as e:
                runner.registerInfo(f"Early RSMeans property extraction skipped (non-critical): {str(e)[:100]}")
        
        # Use RSMeans-extracted properties if available, otherwise use hardcoded
        if insulation_thermal_conductivity == 0.0:
            if 'conductivity_W_mK' in rsmeans_extracted_properties:
                selected_k = rsmeans_extracted_properties['conductivity_W_mK']
                selected_k_source = "rsmeans_extracted"
            else:
                selected_k = material_k_dict[insulation_material_type]
                selected_k_source = "hardcoded_default"
        else:
            selected_k = insulation_thermal_conductivity
            selected_k_source = "user_provided"

        if insulation_material_density == 0.0:
            if 'density_kg_m3' in rsmeans_extracted_properties:
                insulation_material_density = rsmeans_extracted_properties['density_kg_m3']
                selected_density_source = "rsmeans_extracted"
            else:
                insulation_material_density = material_density_dict[insulation_material_type]
                selected_density_source = "hardcoded_default"
        else:
            selected_density_source = "user_provided"
        
        runner.registerInfo(
            f"Material properties: thermal_conductivity={selected_k:.4f} W/m·K ({selected_k_source}), "
            f"density={insulation_material_density:.2f} kg/m³ ({selected_density_source})"
        )

        # ── Phase 3: Model surgery ────────────────────────────────────────────────
        # Collect every exterior wall surface and its unique construction, then clone
        # and modify each construction to add the required insulation thickness.
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
        
        # store constructions require additional insulation layer
        modified_constructions = []
        skipped_constructions_target_already_met = 0

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
            if max_r >= r_value_si:
                runner.registerInfo(f"'{name}' already meets or exceeds the R-value target (current: {openstudio.convert(max_r, 'm^2*K/W', 'ft^2*h*R/Btu').get():.2f}, target: {r_value_ip:.2f}).")
                skipped_constructions_target_already_met += 1
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
        
        # ── Phase 4: EC3 EPD data fetch and embodied-carbon calculation ──────────
        # Queries the Building Transparency (EC3) API for Environmental Product
        # Declaration (EPD) data for the chosen insulation type.  GWP outliers are
        # removed via IQR before applying the user-selected statistic (min/max/mean/median).
        # Embodied carbon = GWP_per_m³ × volume × lifetime_multiplier.

        # Pull EC3 data for the chosen insulation type once
        carbon_data_unavailable_reasons = []
        if use_custom_gwp:
            runner.registerInfo("Custom GWP mode enabled: skipping EC3 API call for wall insulation carbon calculation.")
            insulation_product_epd = []
        else:
            ec3_url = self.generate_url_by_material_type(insulation_material_type)
            insulation_product_epd = fetch_epd_data(ec3_url, api_key)
            if not isinstance(insulation_product_epd, list):
                insulation_product_epd = []
            if len(insulation_product_epd) == 0:
                carbon_data_unavailable_reasons.append("ec3_epd_fetch_empty")
                runner.registerWarning(
                    f"No EC3 EPD records found for '{insulation_material_type}'. "
                    "Embodied carbon may be reported as 0 due to unavailable carbon data."
                )

        # Extract lifetime values from EPD responses
        lifetime_values = []
        for epd in insulation_product_epd:
            parsed_data = parse_product_epd(epd)

            # Extract reference service life from EPD
            reference_service_life = parsed_data.get("reference_service_life")
            if reference_service_life:
                lifetime_value = extract_numeric_value(reference_service_life)
                if lifetime_value > 0.0:
                    lifetime_values.append(lifetime_value)

        # Process lifetime values from EPD
        selected_lifetime = insulation_material_lifetime  # Default to user input
        lifetime_source = "user input"
        
        if lifetime_values:
            # Remove outliers from lifetime values
            lifetime_values = self.remove_outliers_iqr(lifetime_values)
            
            # Apply statistic based on user selection
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
                epd_lifetime = float(np.mean(lifetime_values))  # default to mean
            
            # Use EPD lifetime
            selected_lifetime = epd_lifetime
            lifetime_source = "EPD"

        # Use compute_gwp_data from EC3_lookup to calculate GWP values with outlier removal and statistics
        if use_custom_gwp:
            gwp_data = {
                insulation_material_type: {
                    "gwp_per_kg": 0.0,
                    "gwp_per_m2": 0.0,
                    "gwp_per_m3": float(custom_gwp_per_m3),
                }
            }
        else:
            keys = [insulation_material_type]
            epd_list_by_material = [insulation_product_epd]
            gwp_data = compute_gwp_data(keys, epd_list_by_material, "Product", gwp_statistic)
        
        # Extract GWP values for the selected material
        material_gwp = gwp_data.get(insulation_material_type, {})
        if not any(material_gwp.get(k, 0.0) > 0.0 for k in ["gwp_per_kg", "gwp_per_m2", "gwp_per_m3"]):
            carbon_data_unavailable_reasons.append("no_valid_gwp_values")
            runner.registerWarning(
                f"No valid GWP values were computed for '{insulation_material_type}'. "
                "Embodied carbon may be reported as 0 due to unavailable carbon data."
            )
        
        # Reduced verbosity - GWP values computed but not logging details
        # runner.registerInfo(f"GWP values computed for {insulation_material_type}:")
        # runner.registerInfo(f"  gwp_per_kg: {material_gwp.get('gwp_per_kg', 0.0):.4f} kg CO2 eq/kg")
        # runner.registerInfo(f"  gwp_per_m2: {material_gwp.get('gwp_per_m2', 0.0):.4f} kg CO2 eq/m2")
        # runner.registerInfo(f"  gwp_per_m3: {material_gwp.get('gwp_per_m3', 0.0):.4f} kg CO2 eq/m3")

        # multipliers for calculating embodied carbon over analysis period
        multiplier = lifetime_multiplier(selected_lifetime, analysis_period) if use_lifetime_multiplier else 1

        # Iterate through all modified constructions to compute embodied carbon
        gwp_summary = []
        for item in modified_constructions:
            total_area_m2 = item["total_area_m2"]
            added_thickness_m = item["added_thickness_m"]

            # Store GWP values from compute_gwp_data results
            item["gwp_per_kg"] = material_gwp.get("gwp_per_kg", 0.0)
            item["gwp_per_m2"] = material_gwp.get("gwp_per_m2", 0.0)
            item["gwp_per_m3"] = material_gwp.get("gwp_per_m3", 0.0)

            # Calculate total GWP for this added insulation
            total_gwp = item['gwp_per_m3'] * (total_area_m2*added_thickness_m) * multiplier
            if (not np.isfinite(total_gwp) or total_gwp == 0.0) and item["gwp_per_kg"] != 0.0:
                total_gwp = item["gwp_per_kg"] * (insulation_material_density * total_area_m2 * added_thickness_m) * multiplier
            if not np.isfinite(total_gwp):
                total_gwp = 0.0

            # Store result in summary table
            gwp_summary.append({
                "gwp_per_kg": item["gwp_per_kg"],
                "gwp_per_m2": item["gwp_per_m2"],
                "gwp_per_m3": item["gwp_per_m3"],
                "insulation_material_type": insulation_material_type,
                "insulation_material_lifetime_years": selected_lifetime,
                "insulation_material_lifetime_source": lifetime_source,
                "insulation_material_density_kg_per_m3": insulation_material_density,
                "insulation_material_thermal_conductivity_W_per_mK": selected_k,
                "construction_name": item["construction"].nameString(),
                "added_total_volume_m3": item["added_thickness_m"] * item["total_area_m2"],
                "added_total_area_m2": total_area_m2,
                "added_thickness_m": added_thickness_m,
                "added_total_mass_kg": insulation_material_density * item["added_thickness_m"] * item["total_area_m2"],
                "total_gwp_kg_co2_eq": total_gwp
            })

        # Calculate building-level totals for summarization
        total_embodied_carbon = sum(gwp_summary[idx]["total_gwp_kg_co2_eq"] for idx in range(len(modified_constructions)))
        total_wall_area = sum(item["total_area_m2"] for item in modified_constructions)
        total_added_volume_m3 = sum(gwp_summary[idx]["added_total_volume_m3"] for idx in range(len(gwp_summary)))
        
        # ── Phase 5: Cost lookup and AdditionalProperties write-out ──────────────
        # Two cost paths:
        #   a) use_custom_costs=True  → user $/CF × added volume (no API call needed)
        #   b) use_custom_costs=False → RSMeans API via search_materials_across_catalogs(),
        #      which tries multiple catalogs and falls back through alternative search terms.
        #
        # Results are written to five model objects matching the bucket diagram
        # (see module header at the top of this file).
        building = model.getBuilding()
        basic_input = building.additionalProperties()       # Basic input bucket
        site = model.getSite()
        reno_detail = site.additionalProperties()           # Renovation details bucket
        facility = model.getFacility()
        factors = facility.additionalProperties()           # Emission/Cost factors bucket
        simcontrol = model.getSimulationControl()
        results = simcontrol.additionalProperties()         # Emission/Cost results bucket
        sizingpara = model.getSizingParameters()
        mtrl_prop = sizingpara.additionalProperties()       # Material properties bucket

        retrofit_materials_json = None
        rsmeans_materials_detail_json = None
        rsmeans_material_id_for_write = None
        rsmeans_material_description_for_write = None

        # ===================== RSMeans cost lookup =====================
        total_material_cost = 0.0
        total_overhead_profit_cost = 0.0
        total_labor_cost = 0.0
        total_equipment_cost = 0.0
        cost_source = "none"
        cost_factor_basis = "not_calculated"
        rsmeans_cost_per_cf_feature_value = "N/A"
        rsmeans_pricing_unit_cost_raw_feature_value = "N/A"
        rsmeans_pricing_unit_uom_raw_feature_value = "N/A"

        rsmeans_materials = []
        if total_wall_area > 0.0:
            total_wall_area_ft2 = self._unit_convert(total_wall_area, "m^2", "ft^2")
            total_added_volume_ft3 = self._unit_convert(total_added_volume_m3, "m^3", "ft^3") if total_added_volume_m3 > 0 else 0.0
            avg_added_thickness_m = (total_added_volume_m3 / total_wall_area) if total_wall_area > 0 else 0.0
            avg_added_thickness_in = self._unit_convert(avg_added_thickness_m, "m", "in") if avg_added_thickness_m > 0 else 0.0
            material_entry = {
                "name": f"{insulation_material_type} insulation",
                "description": f"Added insulation to reach R-{r_value_ip}; avg added thickness {avg_added_thickness_in:.2f} in",
                "quantity": float(total_wall_area_ft2),
                "unit": "SF",
                "quantity_volume": float(total_added_volume_ft3),
                "unit_volume": "CF",
                "rsmeans_thickness_ft": float(avg_added_thickness_m) * 3.28084 if avg_added_thickness_m > 0 else 0.0,
                "costing_mode": "volume_from_area",
                "quantity_si": float(total_wall_area),
                "unit_si": "m2",
                "division_code": "07",
            }
            if use_exact_costline_id:
                material_entry["rsmeans_id"] = exact_costline_id
            rsmeans_materials.append(material_entry)

        if rsmeans_materials:
            try:
                retrofit_materials_json = json.dumps(rsmeans_materials)
            except Exception as e:
                runner.registerWarning(f"Could not serialize RSMeans retrofit materials to JSON: {e}")

        if rsmeans_materials:
            if use_custom_costs:
                if custom_cost_per_cf <= 0.0:
                    runner.registerWarning("Custom cost mode enabled, but custom_cost_per_cf is 0. Skipping cost calculation.")
                else:
                    total_added_volume_cf = float(rsmeans_materials[0].get("quantity_volume", 0.0))
                    if total_added_volume_cf > 0.0:
                        _lc_mult = int(lifetime_multiplier(insulation_material_lifetime, analysis_period)) if use_lifetime_multiplier else 1
                        total_material_cost = custom_cost_per_cf * total_added_volume_cf * _lc_mult
                        if labor_cost_multiplier and labor_cost_multiplier > 1.0:
                            total_labor_cost = total_material_cost * (labor_cost_multiplier - 1.0)
                        total_overhead_profit_cost = (total_material_cost + total_labor_cost) * (overhead_profit_percent / 100.0)
                        cost_source = "custom_input"
                        cost_factor_basis = "custom_cost_per_volume"
                        runner.registerInfo(
                            "Custom cost summary (cost_source=custom_input): "
                            f"material_cost=${total_material_cost:,.2f} (lifetime_multiplier={_lc_mult}), "
                            f"labor_cost=${total_labor_cost:,.2f}, "
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
                        runner.registerInfo("Starting RSMeans lookup for wall insulation...")
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
                            cost_calculation_basis=cost_calculation_basis,
                        )
                        if rsmeans_lookup and rsmeans_lookup.get("status") == "ok":
                            summary = rsmeans_lookup.get("summary", {})
                            # RSMeans summary now provides bare component split:
                            # material/labor/equipment are without OHP; OHP is applied once.
                            _lc_mult = int(lifetime_multiplier(insulation_material_lifetime, analysis_period)) if use_lifetime_multiplier else 1
                            total_material_cost = float(summary.get("total_material_cost", 0.0)) * _lc_mult
                            total_labor_cost = float(summary.get("total_labor_cost", 0.0)) * _lc_mult
                            total_equipment_cost = float(summary.get("total_equipment_cost", 0.0)) * _lc_mult
                            total_overhead_profit_cost = float(summary.get("total_overhead_profit_cost", 0.0)) * _lc_mult
                            cost_source = "rsmeans_api"
                            materials_results = rsmeans_lookup.get("results", {}).get("materials", [])
                            total_added_volume_cf = float(rsmeans_materials[0].get("quantity_volume", 0.0))
                            if materials_results:
                                _selected_mat = materials_results[0]
                                _selected_ids = {
                                    str(m.get("rsmeans_id", "")).strip()
                                    for m in materials_results
                                    if str(m.get("rsmeans_id", "")).strip()
                                }
                                if len(_selected_ids) > 1:
                                    _fallback_costline_id = "072116201320"
                                    _selected_via_fallback = None
                                    for _mat in materials_results:
                                        if str(_mat.get("rsmeans_id", "")).strip() == _fallback_costline_id:
                                            _selected_via_fallback = _mat
                                            break
                                    if _selected_via_fallback is not None:
                                        _selected_mat = _selected_via_fallback
                                        runner.registerWarning(
                                            "Multiple RSMeans lines detected for wall insulation API unit rate; "
                                            f"forcing fallback costline ID {_fallback_costline_id}."
                                        )
                                    else:
                                        runner.registerWarning(
                                            "Multiple RSMeans lines detected for wall insulation API unit rate; "
                                            "fallback ID not found in results, using first matched line."
                                        )

                                _bare_unit = float(_selected_mat.get("bare_material_unit_cost", 0.0) or 0.0)
                                _basis = str(_selected_mat.get("bare_material_unit_basis", _selected_mat.get("unit_cost_basis", _selected_mat.get("unit", "")))).upper().replace(" ", "")
                                _mode = str(_selected_mat.get("costing_mode", "")).strip().lower()
                                _cost_per_cf = 0.0
                                _pricing_eff = float(_selected_mat.get("pricing_unit_cost_effective", 0.0) or 0.0)
                                _pricing_eff_uom = str(_selected_mat.get("pricing_unit_uom_effective", "")).upper().replace(" ", "")
                                _pricing_raw = float(_selected_mat.get("pricing_unit_cost_raw", 0.0) or 0.0)
                                _pricing_raw_uom = str(_selected_mat.get("pricing_unit_uom_raw", "")).upper().replace(" ", "")
                                if _bare_unit > 0.0:
                                    if _basis == "CF":
                                        _cost_per_cf = _bare_unit
                                    elif _basis == "CY":
                                        _cost_per_cf = _bare_unit / 27.0
                                    elif _basis == "SF" and _mode == "volume_from_area":
                                        _thk_ft = float(_selected_mat.get("source_line_thickness_ft", 0.0) or 0.0)
                                        if _thk_ft > 0.0:
                                            _cost_per_cf = _bare_unit / _thk_ft
                                if _cost_per_cf <= 0.0 and _pricing_eff > 0.0:
                                    if _pricing_eff_uom == "CF":
                                        _cost_per_cf = _pricing_eff
                                    elif _pricing_eff_uom == "CY":
                                        _cost_per_cf = _pricing_eff / 27.0
                                if _cost_per_cf > 0.0:
                                    # API cost-per-CF feature is bare material-only
                                    # from selected RSMeans line unit pricing.
                                    rsmeans_cost_per_cf_feature_value = _cost_per_cf
                                else:
                                    runner.registerWarning(
                                        "Could not derive wall API unit rate from RSMeans direct unit fields; "
                                        "AP unit-rate feature will remain N/A instead of using back-calculation."
                                    )
                                if _pricing_raw > 0.0 and _pricing_raw_uom:
                                    rsmeans_pricing_unit_cost_raw_feature_value = _pricing_raw
                                    rsmeans_pricing_unit_uom_raw_feature_value = _pricing_raw_uom
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
                            if mode_values == {"area"}:
                                cost_factor_basis = "cost_per_area"
                            elif mode_values == {"volume_from_area"} or mode_values == {"volume_direct"} or unit_values == {"CF"}:
                                cost_factor_basis = "cost_per_volume"
                            elif len(mode_values) > 1 or len(unit_values) > 1:
                                cost_factor_basis = "mixed"
                            else:
                                cost_factor_basis = "other"
                            if materials_results:
                                runner.registerInfo("RSMeans materials detail:")
                                rsmeans_extracted_properties = {}
                                for mat in materials_results:
                                    mat_name = mat.get("name", "(unknown)")
                                    mat_desc = mat.get("description", "")
                                    mat_qty = mat.get("quantity", 0.0)
                                    mat_unit = mat.get("unit", "")
                                    mat_div = mat.get("division_code", "")
                                    mat_unit_cost = mat.get("unit_cost", 0.0)
                                    mat_total_cost = mat.get("total_cost", 0.0)
                                    mat_unit_basis = mat.get("unit_cost_basis", mat.get("unit", ""))
                                    runner.registerInfo(
                                        f"  - {mat_name} | {mat_desc} | {mat_qty} {mat_unit} | "
                                        f"division {mat_div} | unit=${mat_unit_cost:.2f}/{mat_unit_basis} | total=${mat_total_cost:,.2f}"
                                    )
                                    
                                    # Extract material properties from description
                                    extracted_props = extract_properties_from_rsmeans_description(mat_desc)
                                    if extracted_props:
                                        rsmeans_extracted_properties[mat_name] = extracted_props
                                        if 'density_kg_m3' in extracted_props:
                                            runner.registerInfo(
                                                f"    → Extracted density from description: {extracted_props['density_kg_m3']:.2f} kg/m³"
                                            )
                                        if 'rsmeans_rvalue_ip_in_description' in extracted_props:
                                            runner.registerInfo(
                                                f"    → Found R-value in description: R-{extracted_props['rsmeans_rvalue_ip_in_description']}"
                                            )

                                    # Capture RSMeans id/description; write them later in centralized section.
                                    candidate_id = str(mat.get("rsmeans_id", "")).strip()
                                    if candidate_id and rsmeans_material_id_for_write is None:
                                        rsmeans_material_id_for_write = candidate_id
                                    candidate_desc = str(mat.get("rsmeans_description", "")).strip() or str(mat.get("description", "")).strip()
                                    if candidate_desc and rsmeans_material_description_for_write is None:
                                        rsmeans_material_description_for_write = candidate_desc
                                
                                if rsmeans_extracted_properties:
                                    runner.registerInfo(
                                        f"Extracted material properties from RSMeans descriptions: {list(rsmeans_extracted_properties.keys())}"
                                    )

                                # Store full per-material RSMeans lookup results (id, description, unit,
                                # unit_cost, total_cost, match_type, unit_cost_basis, costing_mode, catalog, etc.)
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
                                            "line_uom": mat.get("line_uom", ""),
                                            "unit_cost_basis": mat.get("unit_cost_basis", mat.get("unit", "")),
                                            "costing_mode": mat.get("costing_mode", ""),
                                            "match_type": mat.get("match_type", ""),
                                            "catalog": mat.get("catalog", ""),
                                            "search_term_used": mat.get("search_term_used", ""),
                                            "source": mat.get("source", ""),
                                        })
                                    rsmeans_materials_detail_json = json.dumps(storable_results)
                                except Exception as e:
                                    runner.registerWarning(f"Could not store RSMeans materials detail: {e}")
                            runner.registerInfo(
                                f"RSMeans cost summary: materials={len(materials_results)}, "
                                f"total_cost=${total_material_cost + total_overhead_profit_cost:,.2f} "
                                f"(Note: RSMeans unit costs include both material and labor)"
                            )
                        else:
                            error_msg = rsmeans_lookup.get("message", "Unknown error") if rsmeans_lookup else "No response"
                            runner.registerWarning(
                                f"RSMeans lookup failed: {error_msg}\n"
                                f"The RSMeans API could not find a cost for this insulation material.\n"
                                f"SOLUTION: Retry the measure with custom cost input:\n"
                                f"  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
                                f"  2. Enter 'Custom Insulation Cost ($/CF)' with your estimated cost\n"
                                f"  (For Pure Wool Batts, consult RS Means or quotes from vendors for typical $/CF rates)"
                            )
                    except Exception as e:
                        runner.registerWarning(
                            f"RSMeans lookup failed: {e}\n"
                            f"SOLUTION: Retry the measure with custom cost input:\n"
                            f"  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
                            f"  2. Enter 'Custom Insulation Cost ($/CF)' with your estimated cost"
                        )
                else:
                    runner.registerWarning(
                        "RSMeans helper not found at resources/call_rsmeans_api.py\n"
                        "SOLUTION: Retry the measure with custom cost input:\n"
                        f"  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true\n"
                        f"  2. Enter 'Custom Insulation Cost ($/CF)' with your estimated cost"
                    )

            if (not use_custom_costs) and cost_source != "rsmeans_api":
                total_added_volume_cf = float(rsmeans_materials[0].get("quantity_volume", 0.0)) if rsmeans_materials else 0.0
                if float(custom_cost_per_cf) > 0.0 and total_added_volume_cf > 0.0:
                    _lc_mult = int(lifetime_multiplier(insulation_material_lifetime, analysis_period)) if use_lifetime_multiplier else 1
                    total_material_cost = custom_cost_per_cf * total_added_volume_cf * _lc_mult
                    total_labor_cost = (
                        total_material_cost * (labor_cost_multiplier - 1.0)
                        if labor_cost_multiplier and labor_cost_multiplier > 1.0 else 0.0
                    )
                    total_equipment_cost = 0.0
                    total_overhead_profit_cost = (total_material_cost + total_labor_cost) * (overhead_profit_percent / 100.0)
                    cost_source = "custom_input_fallback"
                    cost_factor_basis = "custom_cost_per_volume"
                    runner.registerInfo(
                        "Custom cost fallback summary (cost_source=custom_input_fallback): "
                        f"material_cost=${total_material_cost:,.2f} (lifetime_multiplier={_lc_mult}), "
                        f"labor_cost=${total_labor_cost:,.2f}, "
                        f"overhead_profit_cost=${total_overhead_profit_cost:,.2f} "
                        f"(volume={total_added_volume_cf:.2f} CF × rate ${custom_cost_per_cf}/CF, "
                        f"labor_multiplier={labor_cost_multiplier:.2f}, overhead_profit_percent={overhead_profit_percent:.1f}%)"
                    )
                else:
                    runner.registerError(
                        "RSMeans lookup failed/returned no costs AND no custom fallback cost was provided.\n"
                        "SOLUTION: Retry the measure with custom cost input:\n"
                        "  1. Set 'Use Custom Cost Inputs (skip RSMeans)' = true, or keep RSMeans mode with a fallback rate\n"
                        "  2. Enter a non-zero 'Custom Insulation Cost ($/CF)'"
                    )
                    return False

        # ===================== AdditionalProperties write-out (centralized) =====================
        # Per-construction properties for reporting compatibility
        for idx, item in enumerate(modified_constructions):
            construction = item["construction"]
            total_area_m2 = item["total_area_m2"]
            total_gwp = gwp_summary[idx]["total_gwp_kg_co2_eq"]
            props = construction.additionalProperties()
            # Aligned per-construction keys
            props.setFeature("wall_insulation_renovated_exterior_wall_area_m2", total_area_m2)
            props.setFeature("wall_insulation_renovated_embodied_carbon_kgCO2eq", total_gwp)
            props.setFeature("wall_insulation_material_type", insulation_material_type)
            if retrofit_materials_json is not None:
                props.setFeature("wall_insulation_retrofit_materials_json", retrofit_materials_json)
            if rsmeans_materials_detail_json is not None:
                props.setFeature("wall_insulation_rsmeans_materials_detail_json", rsmeans_materials_detail_json)

        # Building bucket: basic inputs
        basic_input.setFeature("wall_insulation_measure_name", "Increase Insulation R-Value for Exterior Walls")
        basic_input.setFeature("wall_insulation_analysis_period_years", analysis_period)
        basic_input.setFeature("wall_insulation_gwp_statistic", gwp_statistic)
        basic_input.setFeature("wall_insulation_gwp_source", "custom_user_inputs" if use_custom_gwp else "ec3")

        # Site bucket: renovation details/quantities
        reno_detail.setFeature("wall_insulation_renovated_area_m2", total_wall_area)
        reno_detail.setFeature("wall_insulation_added_volume_m3", total_added_volume_m3)
        reno_detail.setFeature("wall_insulation_target_r_value_ip", r_value_ip)
        reno_detail.setFeature("wall_insulation_material_type", insulation_material_type)
        reno_detail.setFeature("wall_insulation_modified_constructions_count", len(modified_constructions))
        requested_summary = f"wall insulation upgrade to target R-{r_value_ip:.2f} using '{insulation_material_type}'"
        context_summary = (
            f"modified constructions={len(modified_constructions)}, "
            f"target-already-met skips={skipped_constructions_target_already_met}, "
            f"renovated area={total_wall_area:.3f} m2, added volume={total_added_volume_m3:.3f} m3"
        )

        if len(modified_constructions) == 0 and skipped_constructions_target_already_met > 0:
            wall_summary_notes = (
                "Requested: "
                + requested_summary
                + ". Outcome: Not implemented. "
                + "Reason: All eligible wall constructions already met or exceeded the target R-value. "
                + "Context: "
                + context_summary
                + "."
            )
        elif len(modified_constructions) == 0:
            wall_summary_notes = (
                "Requested: "
                + requested_summary
                + ". Outcome: Not implemented. "
                + "Reason: No eligible exterior wall constructions were found. "
                + "Context: "
                + context_summary
                + "."
            )
        else:
            wall_summary_notes = (
                "Requested: "
                + requested_summary
                + ". Outcome: Implemented. "
                + "Details: Exterior wall insulation layers were updated to meet the target R-value where needed. "
                + "Context: "
                + context_summary
                + "."
            )
        reno_detail.setFeature("wall_insulation_summary_notes", wall_summary_notes)

        # SizingParameters bucket: material properties
        mtrl_prop.setFeature("wall_insulation_material_lifetime_years", selected_lifetime)
        mtrl_prop.setFeature("wall_insulation_material_density_kg_per_m3", insulation_material_density)
        mtrl_prop.setFeature("wall_insulation_material_thermal_conductivity_W_per_mK", selected_k)
        if rsmeans_material_id_for_write:
            mtrl_prop.setFeature("wall_insulation_material_rsmeans_id", rsmeans_material_id_for_write)
        if rsmeans_material_description_for_write:
            mtrl_prop.setFeature("wall_insulation_material_rsmeans_description", rsmeans_material_description_for_write)

        # SimulationControl bucket: results and RSMeans detail JSON
        results.setFeature("wall_insulation_embodied_carbon_kgCO2eq", total_embodied_carbon)
        total_cost_with_overhead_profit = (
            total_material_cost + total_labor_cost + total_equipment_cost + total_overhead_profit_cost
        )
        basis_label = "bare material" if cost_calculation_basis == "bare_material" else "total Op"
        reported_total_construction_cost = (
            total_material_cost if cost_calculation_basis == "bare_material" else total_cost_with_overhead_profit
        )

        results.setFeature("wall_insulation_labor_cost_$", total_labor_cost)
        results.setFeature("wall_insulation_material_cost_$", total_material_cost)
        results.setFeature("wall_insulation_equipment_cost_$", total_equipment_cost)
        results.setFeature("wall_insulation_overhead_profit_cost_$", total_overhead_profit_cost)
        results.setFeature("wall_insulation_total_cost_with_overhead_and_profit_$", reported_total_construction_cost)
        results.setFeature("wall_insulation_cost_calculation_basis", basis_label)
        results.setFeature("wall_insulation_cost_factor_basis", cost_factor_basis)
        
        # Facility bucket: emission/cost factors
        factors.setFeature("wall_insulation_cost_source", cost_source)
        factors.setFeature(
            "wall_insulation_overhead_profit_percent",
            0.0 if cost_source == "rsmeans_api" else overhead_profit_percent,
        )
        factors.setFeature("wall_insulation_cost_calculation_basis", basis_label)
        factors.setFeature("wall_insulation_cost_factor_basis", cost_factor_basis)
        if cost_source in ("custom_input", "custom_input_fallback"):
            factors.setFeature("wall_insulation_custom_labor_cost_multiplier", labor_cost_multiplier)
            factors.setFeature("wall_insulation_custom_cost_per_cf", custom_cost_per_cf)
        if cost_source == "rsmeans_api":
            factors.setFeature("wall_insulation_api_material_cost_per_cf", rsmeans_cost_per_cf_feature_value)
            factors.setFeature("wall_insulation_api_pricing_unit_cost", rsmeans_pricing_unit_cost_raw_feature_value)
            factors.setFeature("wall_insulation_api_pricing_unit_uom", rsmeans_pricing_unit_uom_raw_feature_value)
        if material_gwp.get("gwp_per_kg", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_kg", material_gwp.get("gwp_per_kg", 0.0))
        if material_gwp.get("gwp_per_m2", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_m2", material_gwp.get("gwp_per_m2", 0.0))
        if material_gwp.get("gwp_per_m3", 0.0) > 0.0:
            factors.setFeature("wall_insulation_material_gwp_per_m3", material_gwp.get("gwp_per_m3", 0.0))

        # Construction names for traceability
        construction_names = [item["construction"].nameString() for item in modified_constructions]
        if construction_names:
            basic_input.setFeature("wall_insulation_renovated_construction_names", ', '.join(construction_names))
        
        runner.registerInfo(
            f"Building-level summary: Total embodied carbon = {total_embodied_carbon:.2f} kg CO2 eq "
            f"across {total_wall_area:.2f} m² of exterior walls"
        )

        runner.registerFinalCondition(
            f"Modified {len(modified_constructions)} construction(s) to meet target R-value of {r_value_ip} ft²·h·°F/Btu."
        )
        return True

# Register the measure
IncreaseInsulationRValueForExteriorWalls().registerWithApplication()
