#!/usr/bin/env python3
"""
convert_simple_glazing_to_layered.py

Physically-consistent conversion of SimpleGlazing → Layered window construction.

Physics model (simplified 1-D steady-state):
  U = 1/(R_ext + R_g1 + R_gap + R_g2 + R_int)  [double pane]
  U = 1/(R_ext + R_g1 + R_int)                  [single pane]

  R_ext        = 1/h_ext = 1/25   = 0.040   m²·K/W  (ASHRAE exterior film, 15 mph wind)
  R_int        = 1/h_int = 1/8.0  = 0.125   m²·K/W  (ASHRAE interior film, still air)
  R_glass      = t/k     = 0.003/0.9 = 0.00333 m²·K/W  (single 3 mm glass pane, k=0.9 W/m·K)
  R_fixed      = R_ext + 2·R_glass + R_int = 0.172 m²·K/W

  Air-gap effective conductance (room-temperature, vertical glazing):
    h_gap  = h_conv + h_rad
    h_conv ≈ k_air / d_gap  (pure-conduction lower bound; valid for d < ~5 mm)
    h_rad  ≈ 3.7 W/m²·K    (both surfaces clear glass, ε = 0.84, T_mean ≈ 283 K)

  Reverse-calculate air-gap thickness:
    R_gap_target = 1/U - R_fixed
    d_gap        = k_air / (1/R_gap_target - h_rad_clear)
    Clamped to [D_GAP_MIN, D_GAP_MAX].

  If R_gap_target ≤ 0 (U too high for any double-pane assembly) → single pane.

Low-E coating rule:
  d_gap >= 4 mm  →  inner-surface emissivity = 0.10 (soft-coat low-E)
  d_gap <  4 mm  →  inner-surface emissivity = 0.84 (clear, thin gap)
"""

import os

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_R_EXT        = 0.040          # m²·K/W — ASHRAE exterior surface film
_R_INT        = 0.125          # m²·K/W — ASHRAE interior surface film
_T_GLASS      = 0.003          # m      — nominal glass pane thickness
_K_GLASS      = 0.9            # W/m·K  — soda-lime glass conductivity
_R_GLASS      = _T_GLASS / _K_GLASS  # m²·K/W ≈ 0.00333
_R_FIXED      = _R_EXT + 2.0 * _R_GLASS + _R_INT  # 0.172 m²·K/W

_H_RAD_CLEAR  = 3.7            # W/m²·K — radiation between two clear surfaces (ε=0.84)
_K_AIR        = 0.026          # W/m·K  — air thermal conductivity at ~10 °C

_D_GAP_MIN    = 0.001          # m — minimum gap (1 mm), EnergyPlus lower limit
_D_GAP_MAX    = 0.020          # m — maximum gap modelled here (20 mm)
_LOW_E_THRESH = 0.004          # m — gaps ≥ 4 mm get low-E coating


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_air_gap_thickness(u_factor):
    """
    Reverse-calculate air-gap thickness [m] for a target assembly U-factor.
    Returns None when the U-factor is too high for a double-pane assembly.
    """
    r_gap_target = 1.0 / u_factor - _R_FIXED
    if r_gap_target <= 0.0:
        return None  # → single pane

    h_gap_required  = 1.0 / r_gap_target
    h_conv_required = h_gap_required - _H_RAD_CLEAR

    if h_conv_required <= 0.0:
        # Radiation alone overshoots R_gap; use maximum gap and accept lower U
        return _D_GAP_MAX

    d = _K_AIR / h_conv_required
    return max(_D_GAP_MIN, min(_D_GAP_MAX, d))


def _make_glass_layer(model, name,
                      solar_trans, vis_trans,
                      ir_emissivity_front=0.84, ir_emissivity_back=0.84):
    """
    Create and return an openstudio.model.StandardGlazing layer.

    Solar/visible reflectances are derived from the transmittance values,
    leaving a small absorptance that satisfies T + R ≤ 1.
    """
    import openstudio

    # Keep R small; absorptance = 1 - T - R accounts for the rest
    solar_refl = max(0.0, min(0.09, 1.0 - solar_trans - 0.005))
    vis_refl   = max(0.0, min(0.09, 1.0 - vis_trans   - 0.005))

    glass = openstudio.model.StandardGlazing(model)
    glass.setName(name)
    glass.setOpticalDataType("SpectralAverage")
    glass.setThickness(_T_GLASS)

    glass.setSolarTransmittanceatNormalIncidence(solar_trans)
    glass.setFrontSideSolarReflectanceatNormalIncidence(solar_refl)
    glass.setBackSideSolarReflectanceatNormalIncidence(solar_refl)

    glass.setVisibleTransmittanceatNormalIncidence(vis_trans)
    glass.setFrontSideVisibleReflectanceatNormalIncidence(vis_refl)
    glass.setBackSideVisibleReflectanceatNormalIncidence(vis_refl)

    glass.setInfraredTransmittanceatNormalIncidence(0.0)
    glass.setFrontSideInfraredHemisphericalEmissivity(ir_emissivity_front)
    glass.setBackSideInfraredHemisphericalEmissivity(ir_emissivity_back)

    glass.setConductivity(_K_GLASS)
    glass.setDirtCorrectionFactorforSolarandVisibleTransmittance(1.0)
    glass.setSolarDiffusing(False)
    return glass


def _make_air_gap(model, name, thickness_m):
    """Create and return an openstudio.model.Gas (Air) layer."""
    import openstudio

    gap = openstudio.model.Gas(model)
    gap.setName(name)
    gap.setGasType("Air")
    gap.setThickness(thickness_m)
    return gap


def _map_shgc_to_glass_transmittance(shgc, vt):
    """
    Approximate the glass solar/visible transmittance from SimpleGlazing SHGC/VT.

    For a single pane: SHGC ≈ T_solar + A_solar * N_i
    where A_solar = 1 - T_solar - R_solar (≈ 1 - T_solar - 0.08)
    and   N_i ≈ 0.30 (inward-flowing fraction of absorbed solar).
    Solving: SHGC ≈ T_solar * (1 - 0.30) + 0.30 - 0.30 * R_solar
                  ≈ T_solar * 0.70 + 0.30 * (1 - R_solar) - 0.30 + T_solar*0.30
                  ≈ T_solar + 0.30 * (1 - T_solar - R_solar)
    Simplified: T_solar ≈ SHGC / (1 - 0.30 + 0.30*R_solar) ≈ SHGC / 0.95
    """
    glass_t_sol = max(0.05, min(0.92, shgc / 0.95))
    glass_t_vis = max(0.05, min(0.92, vt   / 0.95))
    return glass_t_sol, glass_t_vis


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all_windows_simple_glazing(model):
    """
    Return True if *every* FixedWindow/OperableWindow/Skylight subsurface in
    *model* resolves to a Construction whose sole layer is a SimpleGlazing.
    Returns False if any window has no construction, a non-layered construction,
    or a layered construction with no SimpleGlazing layer.
    """
    windows = [
        ss for ss in model.getSubSurfaces()
        if ss.subSurfaceType() in ["FixedWindow", "OperableWindow", "Skylight"]
    ]
    if not windows:
        return False

    for ss in windows:
        cons_opt = ss.construction()
        if not cons_opt.is_initialized():
            return False
        cons = cons_opt.get()
        if not cons.to_LayeredConstruction().is_initialized():
            return False
        layered = cons.to_LayeredConstruction().get()
        found_simple = any(
            layered.getLayer(i).to_SimpleGlazing().is_initialized()
            for i in range(layered.numLayers())
        )
        if not found_simple:
            return False

    return True


def _convert_constructions_in_model(model, conversions_out):
    """
    Scan *model* for Construction objects whose sole layer is a SimpleGlazing.
    Replace each such layer in-place with physically-consistent glass/gap layers,
    keeping the Construction handle (so all subsurface references stay valid).
    Appends one dict per converted construction to *conversions_out*.
    """
    for cons in model.getConstructions():
        if not cons.to_LayeredConstruction().is_initialized():
            continue
        layered = cons.to_LayeredConstruction().get()
        if layered.numLayers() != 1:
            continue
        layer0 = layered.getLayer(0)
        if not layer0.to_SimpleGlazing().is_initialized():
            continue

        sg   = layer0.to_SimpleGlazing().get()
        u    = sg.uFactor()
        shgc = sg.solarHeatGainCoefficient()
        vt_raw = sg.visibleTransmittance()
        if hasattr(vt_raw, "is_initialized"):
            vt = vt_raw.get() if vt_raw.is_initialized() else 0.81
        else:
            vt = vt_raw
        cn   = cons.nameString()

        glass_t_sol, glass_t_vis = _map_shgc_to_glass_transmittance(shgc, vt)
        d_gap = _compute_air_gap_thickness(u)

        # Erase existing layer(s) in-place (keeps Construction handle)
        while layered.numLayers() > 0:
            layered.eraseLayer(0)

        if d_gap is None:
            # --- Single pane ---
            g = _make_glass_layer(model, f"{cn} Glass", glass_t_sol, glass_t_vis)
            layered.insertLayer(0, g)
            pane_type       = "single"
            inner_emissivity = None
        else:
            # --- Double pane ---
            # Outer pane: carries the SHGC/VT of the whole assembly
            g_out = _make_glass_layer(model, f"{cn} OuterGlass",
                                      glass_t_sol, glass_t_vis)
            # Inner pane: near-transparent to solar/visible; low-E if gap large enough
            inner_emissivity = 0.10 if d_gap >= _LOW_E_THRESH else 0.84
            g_in  = _make_glass_layer(model, f"{cn} InnerGlass",
                                      solar_trans=0.92, vis_trans=0.92,
                                      ir_emissivity_front=inner_emissivity,
                                      ir_emissivity_back=0.84)
            gap   = _make_air_gap(model, f"{cn} AirGap", d_gap)

            layered.insertLayer(0, g_out)
            layered.insertLayer(1, gap)
            layered.insertLayer(2, g_in)
            pane_type = "double"

        info = {
            "construction_name": cn,
            "pane_type":         pane_type,
            "u_factor":          round(u,    4),
            "shgc":              round(shgc, 4),
            "vt":                round(vt,   4),
            "gap_mm":            round(d_gap * 1000, 2) if d_gap else None,
            "inner_emissivity":  inner_emissivity,
        }
        conversions_out.append(info)
        gap_str = f"gap={d_gap * 1000:.1f} mm" if d_gap else "no gap"
        low_e_str = f", inner ε={inner_emissivity:.2f}" if inner_emissivity else ""
        print(f"      Converted '{cn}': {pane_type} pane, "
              f"U={u:.3f} W/m²K, SHGC={shgc:.3f}, {gap_str}{low_e_str}")


def convert_all_simple_glazing_to_layered(model_path, output_path):
    """
    Load *model_path*, convert every SimpleGlazing construction in-place to a
    physically-consistent layered construction, and save to *output_path*.

    Returns a dict::

        {
          "success":     bool,
          "conversions": list[dict],   # one entry per converted construction
          "message":     str,
        }
    """
    import openstudio

    translator = openstudio.osversion.VersionTranslator()
    loaded = translator.loadModel(openstudio.toPath(str(model_path)))
    if not loaded.is_initialized():
        return {
            "success":     False,
            "conversions": [],
            "message":     f"Could not load model: {model_path}",
        }

    model = loaded.get()

    if not detect_all_windows_simple_glazing(model):
        del model
        return {
            "success":     False,
            "conversions": [],
            "message":     "Not all windows use SimpleGlazing; conversion skipped.",
        }

    conversions = []
    _convert_constructions_in_model(model, conversions)

    if not conversions:
        del model
        return {
            "success":     False,
            "conversions": [],
            "message":     "No SimpleGlazing constructions found to convert.",
        }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    model.save(openstudio.toPath(str(output_path)), True)
    del model

    return {
        "success":     True,
        "conversions": conversions,
        "message":     f"Converted {len(conversions)} construction(s); saved to {output_path}",
    }


# ---------------------------------------------------------------------------
# CLI entry point (standalone use)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python convert_simple_glazing_to_layered.py <input.osm> <output.osm>")
        sys.exit(1)
    result = convert_all_simple_glazing_to_layered(sys.argv[1], sys.argv[2])
    print(result["message"])
    sys.exit(0 if result["success"] else 1)
