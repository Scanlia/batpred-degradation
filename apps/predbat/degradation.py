# -----------------------------------------------------------------------------
# Predbat Home Battery System
# Copyright Trefor Southwell 2025-2026 - All Rights Reserved
# This application maybe used for personal use only and not for commercial use
# -----------------------------------------------------------------------------
# fmt off
# pylint: disable=consider-using-f-string
# pylint: disable=line-too-long
# pylint: disable=attribute-defined-outside-init


"""Semi-empirical battery degradation model for LFP and other chemistries.

Implements a Schmalstieg/Naumann semi-empirical ageing model that computes
marginal fractional capacity loss per time step from calendar ageing (time + SoC
stress + temperature) and cycle ageing (throughput + C-rate + temperature +
charge/discharge asymmetry).  The model translates physical wear into a
dimensionless multiplier that scales the base cycle cost, so the optimiser can
compare plans with and without degradation awareness without invasive changes to
the cost function.

Chemistry support is pluggable via CHEMISTRY_PARAMETERS – see the registry
dictionary for model constants tuned to each battery type.  Adding a new
chemistry only requires a new entry in that registry.
"""

import math


# ---------------------------------------------------------------------------
# Chemistry parameter registry
# ---------------------------------------------------------------------------
# Each entry maps a chemistry key to a dict of model hyper-parameters.
# Units:
#   Ea_*   : J/mol          (activation energy)
#   A_*    : dimensionless  (pre-exponential rate constant)
#   z_*    : dimensionless  (kinetic exponent, 0 < z <= 1)
#   gamma  : dimensionless  (C-rate penalty exponent)
#
# Adding a new chemistry: add a new key + dict to this registry.  No other
# code changes are required – DegradationModel reads all values at init time.
# ---------------------------------------------------------------------------

CHEMISTRY_PARAMETERS = {
    "LFP": {
        "label": "Lithium Iron Phosphate",
        "R": 8.314,
        "A_cal": 1.5e5,
        "Ea_cal": 24000.0,
        "z_cal": 0.5,
        "A_cyc_discharge": 3.0e4,
        "A_cyc_charge": 3.5e4,
        "Ea_cyc_normal": 31700.0,
        "Ea_cyc_plating": -15000.0,
        "plating_threshold_k": 283.15,  # 10 C — plating onset for LFP
        "z_cyc": 0.8,
        "gamma_c_rate": 0.9,
        "nominal_c_rate": 0.15,  # reference C-rate where the cycle multiplier == 1.0
        "soc_stress_steepness": 5.0,
        "soc_stress_steepness_low": 3.0,
        "soc_stress_threshold": 0.8,
    },
    "NMC": {
        "label": "Nickel Manganese Cobalt",
        "R": 8.314,
        "A_cal": 2.5e5,
        "Ea_cal": 28000.0,
        "z_cal": 0.55,
        "A_cyc_discharge": 2.5e4,
        "A_cyc_charge": 4.0e4,
        "Ea_cyc_normal": 34000.0,
        "Ea_cyc_plating": -12000.0,
        "plating_threshold_k": 298.15,
        "z_cyc": 0.75,
        "gamma_c_rate": 1.1,
        "nominal_c_rate": 0.3,
        "soc_stress_steepness": 6.0,
        "soc_stress_steepness_low": 6.0,
        "soc_stress_threshold": 0.7,
    },
    "SODIUM_ION": {
        "label": "Sodium-Ion",
        "R": 8.314,
        "A_cal": 1.2e5,
        "Ea_cal": 20000.0,
        "z_cal": 0.5,
        "A_cyc_discharge": 2.5e4,
        "A_cyc_charge": 2.5e4,
        "Ea_cyc_normal": 29000.0,
        "Ea_cyc_plating": -3000.0,
        "plating_threshold_k": 283.15,
        "z_cyc": 0.85,
        "gamma_c_rate": 0.8,
        "nominal_c_rate": 0.2,
        "soc_stress_steepness": 5.0,
        "soc_stress_steepness_low": 3.5,
        "soc_stress_threshold": 0.8,
    },
    "NCA": {
        "label": "Nickel Cobalt Aluminium",
        "R": 8.314,
        "A_cal": 2.0e5,
        "Ea_cal": 30000.0,
        "z_cal": 0.6,
        "A_cyc_discharge": 3.0e4,
        "A_cyc_charge": 5.0e4,
        "Ea_cyc_normal": 35000.0,
        "Ea_cyc_plating": -10000.0,
        "plating_threshold_k": 298.15,
        "z_cyc": 0.7,
        "gamma_c_rate": 1.3,
        "nominal_c_rate": 0.3,
        "soc_stress_steepness": 7.0,
        "soc_stress_steepness_low": 7.0,
        "soc_stress_threshold": 0.65,
    },
    "LEAD_ACID": {
        "label": "Lead-Acid (AGM / Gel / SLA)",
        "R": 8.314,
        "A_cal": 0.2e5,
        "Ea_cal": 15000.0,
        "z_cal": 0.5,
        "A_cyc_discharge": 5.0e4,
        "A_cyc_charge": 6.0e4,
        "Ea_cyc_normal": 25000.0,
        "Ea_cyc_plating": 0.0,
        "plating_threshold_k": 263.15,
        "z_cyc": 0.6,
        "gamma_c_rate": 1.5,
        "nominal_c_rate": 0.1,
        "soc_stress_steepness": 8.0,
        "soc_stress_steepness_low": 8.0,
        "soc_stress_threshold": 0.5,
    },
    "FLOW": {
        "label": "Flow Battery (Vanadium / Zinc-Bromide)",
        "R": 8.314,
        "A_cal": 0.0,
        "Ea_cal": 0.0,
        "z_cal": 0.5,
        "A_cyc_discharge": 0.0,
        "A_cyc_charge": 0.0,
        "Ea_cyc_normal": 0.0,
        "Ea_cyc_plating": 0.0,
        "plating_threshold_k": 0.0,
        "z_cyc": 0.8,
        "gamma_c_rate": 0.0,
        "nominal_c_rate": 0.2,
        "soc_stress_steepness": 0.0,
        "soc_stress_steepness_low": 0.0,
        "soc_stress_threshold": 1.0,
    },
}


class DegradationModel:
    """Semi-empirical marginal wear model for a single battery.

    Computes a per-step degradation multiplier that indicates how much more (or
    less) damaging the current operating conditions are relative to a nominal
    baseline.  The multiplier is normally >= 1.0 for real operation and can be
    multiplied against the flat cycle cost to obtain a degradation-adjusted
    cycle cost.

    The model tracks cumulative calendar time and cumulative throughput across
    calls so that the derivative of the kinetic power law (t^z, Ah^z) is
    correctly applied.  For Phase 1 the model runs in *overlay* mode – the
    multiplier is recorded alongside the plan but does not influence the
    optimiser's decisions.
    """

    def __init__(self, chemistry="LFP", battery_capacity_kwh=24.0, capex=1000000, lifetime_cycles=8000, nominal_c_rate=None):
        """Initialise the degradation model.

        Args:
            chemistry: Key in CHEMISTRY_PARAMETERS selecting the battery type.
            battery_capacity_kwh: Nominal usable capacity of the battery (kWh).
            capex: Capital cost of the battery system in local currency.
            lifetime_cycles: Manufacturer-rated equivalent full cycles to 80 % SOH.
            nominal_c_rate: Reference C-rate at which the cycle multiplier equals
                1.0 (overrides the per-chemistry default).  Charging/discharging
                slower than this scores < 1.0 (rewarded); faster scores > 1.0
                (penalised).  Pick a value representative of the battery's normal
                operating rate so that typical cycling sits near 1.0.
        """
        params = CHEMISTRY_PARAMETERS.get(chemistry, CHEMISTRY_PARAMETERS["LFP"])
        self.chemistry = chemistry
        self.label = params["label"]

        self.R = params["R"]
        self.A_cal = params["A_cal"]
        self.Ea_cal = params["Ea_cal"]
        self.z_cal = params["z_cal"]
        self.A_cyc_discharge = params["A_cyc_discharge"]
        self.A_cyc_charge = params["A_cyc_charge"]
        self.Ea_cyc_normal = params["Ea_cyc_normal"]
        self.Ea_cyc_plating = params["Ea_cyc_plating"]
        self.plating_threshold_k = params["plating_threshold_k"]
        self.z_cyc = params["z_cyc"]
        self.gamma_c_rate = params["gamma_c_rate"]
        # Reference C-rate where the cycle multiplier == 1.0.  Config override wins,
        # otherwise fall back to the per-chemistry default (0.5 for legacy entries).
        if nominal_c_rate and nominal_c_rate > 0:
            self.nominal_c_rate = nominal_c_rate
        else:
            self.nominal_c_rate = params.get("nominal_c_rate", 0.5)
        # Floor applied to the final multiplier so ultra-gentle cycling never looks
        # essentially free (a battery still wears a little per kWh moved).
        self.min_multiplier = 0.1
        self.soc_stress_steepness = params["soc_stress_steepness"]
        self.soc_stress_steepness_low = params["soc_stress_steepness_low"]
        self.soc_stress_threshold = params["soc_stress_threshold"]

        self.battery_capacity_kwh = battery_capacity_kwh
        self.capex = capex
        self.lifetime_cycles = lifetime_cycles

        # Cumulative state — use 1.0 as initial to avoid the derivative
        # singularity at t=0 (z * t^(z-1) → ∞ as t → 0 for z < 1).
        self.total_time_hours = 1.0
        self.total_throughput_kwh = 1.0

        # Cumulative fractional capacity loss (dimensionless).
        self.total_capacity_loss = 0.0

        # Per-step multipliers recorded for the most recent simulation.
        self.step_multipliers = {}  # minute -> multiplier

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def baseline_cycle_cost(self, average_dod=0.8):
        """Compute the baseline Levelised Cost of Storage (LCOS).

        Returns the cost in the same currency unit as `capex` per kWh of
        throughput under nominal (non-degraded) conditions.

        Args:
            average_dod: Average depth of discharge over the battery lifetime
                (default 0.8, matching typical manufacturer cycle-life ratings
                at 80 % DoD).
        """
        total_lifetime_kwh = self.battery_capacity_kwh * self.lifetime_cycles * average_dod
        if total_lifetime_kwh <= 0:
            return 0.0
        return self.capex / total_lifetime_kwh

    def soc_stress_factor(self, soc_decimal):
        """Continuous SoC stress factor (literature-aligned).

        Uses a Gaussian/exponential form centred at 50 % SoC where stress
        is minimised.  Stress rises smoothly and continuously as SoC
        deviates from the reference — no step-function artefacts.

        Uses separate steepness for high (> 50 %) and low (< 50 %) SoC
        to capture cathode-specific asymmetry (e.g. LFP is more stable at
        low voltage than high).

        Formula:  exp(k × (soc − 0.5)²)
          where k = soc_stress_steepness_low for soc < 0.5
                k = soc_stress_steepness     for soc ≥ 0.5

        Args:
            soc_decimal: State of charge as a fraction (0.0–1.0).

        Returns:
            Stress factor (float ≥ 1.0).  1.0 at exactly 50 % SoC.
        """
        deviation = soc_decimal - 0.5
        if deviation < 0:
            return math.exp(self.soc_stress_steepness_low * deviation * deviation)
        return math.exp(self.soc_stress_steepness * deviation * deviation)

    def compute_step_degradation_multiplier(self, temp_c, soc_percent, delta_throughput_kwh, delta_time_hours, is_charging):
        """Return the degradation multiplier for a single time step.

        Purely stateless – does NOT modify cumulative state.  Safe to call from
        multiple threads / processes simultaneously.

        Multiplier of 1.0 means nominal wear.  Values > 1.0 indicate
        accelerated wear due to unfavourable temperature, SoC, or C-rate.

        Uses *instantaneous rate ratios* rather than cumulative integrals to
        avoid calibration artefacts introduced by the A-pre-exponential
        constants (which are scaled for multi-year integration).

        Args:
            temp_c: Cell temperature in degrees Celsius.
            soc_percent: State of charge as a percentage (0-100).
            delta_throughput_kwh: Energy moved in this step (kWh, always >= 0).
            delta_time_hours: Duration of the step in hours.
            is_charging: True if energy is flowing into the battery.

        Returns:
            degradation_multiplier (float >= 0)
        """
        temp_k = temp_c + 273.15
        T_ref = 298.15  # 25 C reference

        # ---- cycle rate and nominal reference ----
        if delta_throughput_kwh <= 0 or self.z_cyc <= 0:
            return 1.0

        c_rate = (delta_throughput_kwh / max(delta_time_hours, 1e-6)) / self.battery_capacity_kwh
        c_rate = max(c_rate, 0.001)
        c_rate_penalty = c_rate ** self.gamma_c_rate

        soc_decimal = soc_percent / 100.0

        nominal_c_penalty = self.nominal_c_rate ** self.gamma_c_rate
        if not is_charging:
            cyc_rate = self.A_cyc_discharge * c_rate_penalty * math.exp(-self.Ea_cyc_normal / (self.R * temp_k))
            nominal_rate = self.A_cyc_discharge * nominal_c_penalty * math.exp(-self.Ea_cyc_normal / (self.R * T_ref))
        else:
            if self.Ea_cyc_plating < 0:
                plating_frac = 1.0 / (1.0 + math.exp((temp_k - self.plating_threshold_k) / 2.0))
                blended_ea = plating_frac * self.Ea_cyc_plating + (1.0 - plating_frac) * self.Ea_cyc_normal
            else:
                blended_ea = self.Ea_cyc_normal
            cyc_rate = self.A_cyc_charge * c_rate_penalty * math.exp(-blended_ea / (self.R * temp_k))
            # Anchor BOTH directions against the discharge baseline so the reference
            # point (multiplier == 1.0) is "discharge at nominal C-rate / 25 C".
            # Charging at nominal then scores A_cyc_charge / A_cyc_discharge (> 1.0),
            # preserving the charge/discharge asymmetry instead of cancelling it.
            nominal_rate = self.A_cyc_discharge * nominal_c_penalty * math.exp(-self.Ea_cyc_normal / (self.R * T_ref))

        if nominal_rate > 0:
            multiplier = cyc_rate / nominal_rate
        elif cyc_rate <= 0:
            multiplier = 0.0
        else:
            multiplier = 1.0

        multiplier = max(multiplier, 0.0)
        multiplier = min(multiplier, 20.0)

        # A genuinely zero multiplier means the chemistry has no cycle ageing
        # (e.g. flow batteries) — leave it at zero rather than applying the floor.
        if multiplier <= 0.0:
            return 0.0

        multiplier *= self.soc_stress_factor(soc_decimal)

        # Floor so very gentle cycling is rewarded but never treated as free.
        return max(multiplier, self.min_multiplier)

    def compute_condition_multiplier(self, temp_c, soc_percent, is_charging):
        """Return the degradation multiplier for operating conditions, independent of C-rate.

        Evaluates the model at the nominal C-rate so the C-rate term is exactly
        1.0 and the result reflects temperature, SoC, and charge/discharge
        asymmetry only.  Answers: "if I cycled the battery here at a normal rate,
        how damaging would these conditions be relative to the reference?"  This
        is well-defined in every slot (including idle / freeze slots where no
        actual throughput occurs), which is why it is used for the display column.

        Args:
            temp_c: Cell temperature in degrees Celsius.
            soc_percent: State of charge as a percentage (0-100).
            is_charging: True if energy is flowing into the battery.

        Returns:
            condition_multiplier (float >= 0)
        """
        ref_kwh = self.battery_capacity_kwh * self.nominal_c_rate * (5.0 / 60.0)
        return self.compute_step_degradation_multiplier(
            temp_c=temp_c,
            soc_percent=soc_percent,
            delta_throughput_kwh=ref_kwh,
            delta_time_hours=5.0 / 60.0,
            is_charging=is_charging,
        )

    def flush_step_multipliers(self):
        """Clear the per-step multiplier record (call before a new simulation)."""
        self.step_multipliers = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def accumulate_wear(self, temp_c, soc_percent, delta_throughput_kwh, delta_time_hours, is_charging):
        """Accumulate calendar and cycle wear into total_capacity_loss.

        NOT thread-safe – call only from the main (sequential) execution path.
        This is reserved for Phase 2 when cumulative wear tracking is needed.

        Args:
            temp_c: Cell temperature in degrees Celsius.
            soc_percent: State of charge as a percentage (0-100).
            delta_throughput_kwh: Energy moved in this step (kWh, always >= 0).
            delta_time_hours: Duration of the step in hours.
            is_charging: True if energy is flowing into the battery.
        """
        temp_k = temp_c + 273.15
        soc_decimal = soc_percent / 100.0

        # calendar ageing stress factor
        soc_stress = self.soc_stress_factor(soc_decimal)

        cal_rate = self.A_cal * soc_stress * math.exp(-self.Ea_cal / (self.R * temp_k))
        self.total_time_hours += delta_time_hours
        delta_cal_wear = cal_rate * (self.z_cal * (self.total_time_hours ** (self.z_cal - 1.0))) * delta_time_hours

        delta_cyc_wear = 0.0
        if delta_throughput_kwh > 0 and self.z_cyc > 0:
            c_rate = (delta_throughput_kwh / max(delta_time_hours, 1e-6)) / self.battery_capacity_kwh
            c_rate = max(c_rate, 0.001)
            c_rate_penalty = c_rate ** self.gamma_c_rate

            if not is_charging:
                cyc_rate = self.A_cyc_discharge * c_rate_penalty * math.exp(-self.Ea_cyc_normal / (self.R * temp_k))
            else:
                if temp_k < self.plating_threshold_k and self.Ea_cyc_plating < 0:
                    cyc_rate = self.A_cyc_charge * c_rate_penalty * math.exp(-self.Ea_cyc_plating / (self.R * temp_k))
                else:
                    cyc_rate = self.A_cyc_charge * c_rate_penalty * math.exp(-self.Ea_cyc_normal / (self.R * temp_k))

            self.total_throughput_kwh += delta_throughput_kwh
            delta_cyc_wear = cyc_rate * (self.z_cyc * (self.total_throughput_kwh ** (self.z_cyc - 1.0))) * delta_throughput_kwh

        self.total_capacity_loss += delta_cal_wear + delta_cyc_wear

    @staticmethod
    def list_chemistries():
        """Return a list of available chemistry keys and labels."""
        return [(k, v["label"]) for k, v in CHEMISTRY_PARAMETERS.items()]
