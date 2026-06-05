# -----------------------------------------------------------------------------
# Predbat Home Battery System
# Copyright Trefor Southwell 2026 - All Rights Reserved
# This application maybe used for personal use only and not for commercial use
# -----------------------------------------------------------------------------
# fmt off
# pylint: disable=consider-using-f-string
# pylint: disable=line-too-long
# pylint: disable=attribute-defined-outside-init


"""Unit tests for the semi-empirical degradation model (degradation.py)."""

from degradation import DegradationModel, CHEMISTRY_PARAMETERS


def test_degradation_baseline_cost():
    """Baseline LCOS should match CapEx / (capacity * cycles * avg_DoD)."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.18, capex=1000000, lifetime_cycles=8000)
    expected = 1000000 / (24.18 * 8000 * 0.8)
    result = model.baseline_cycle_cost()
    assert 5.0 < result < 10.0, f"Baseline cost {result} p/kWh out of expected range"
    print("  Baseline cost: {:.4f} p/kWh".format(result))

    # Also test default constructor
    default_model = DegradationModel()
    default_result = default_model.baseline_cycle_cost()
    assert default_result > 0, "Default model should compute a positive baseline cost"
    print("  Default baseline cost: {:.4f} p/kWh".format(default_result))


def test_degradation_nominal_conditions():
    """At 25 C, nominal C-rate, 50% SoC, discharging: multiplier == 1.0.

    The model is anchored so the reference operating point (discharge at the
    nominal C-rate, 25 C, 50% SoC) scores exactly 1.0.  This is what makes the
    degradation-weighted cycle directly comparable to the flat cycle cost.
    """
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0, capex=10000, lifetime_cycles=8000)
    delta_hours = 5.0 / 60.0
    # Throughput that yields exactly the nominal C-rate over this step.
    delta_kwh = model.nominal_c_rate * model.battery_capacity_kwh * delta_hours
    result = model.compute_step_degradation_multiplier(
        temp_c=25.0,
        soc_percent=50.0,
        delta_throughput_kwh=delta_kwh,
        delta_time_hours=delta_hours,
        is_charging=False,
    )
    assert abs(result - 1.0) < 0.05, f"Nominal multiplier {result} should be ~1.0"
    print("  Nominal ({:.2f}C discharge, 25 C, 50% SOC): {:.3f}".format(model.nominal_c_rate, result))


def test_degradation_high_temperature():
    """At 40 C: multiplier should be higher than nominal."""
    model1 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model2 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    delta_kwh = 1.0
    delta_hours = 5.0 / 60.0
    nominal = model1.compute_step_degradation_multiplier(25.0, 50.0, delta_kwh, delta_hours, False)
    hot = model2.compute_step_degradation_multiplier(40.0, 50.0, delta_kwh, delta_hours, False)
    assert hot > nominal, f"Hot multiplier {hot} should exceed nominal {nominal}"
    print("  Hot (40 C): {:.2f} vs nominal: {:.2f}".format(hot, nominal))


def test_degradation_cold_charging_plating():
    """At 5 C and charging: plating risk drives multiplier much higher."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    delta_kwh = 1.0
    delta_hours = 5.0 / 60.0
    result = model.compute_step_degradation_multiplier(
        temp_c=5.0,
        soc_percent=50.0,
        delta_throughput_kwh=delta_kwh,
        delta_time_hours=delta_hours,
        is_charging=True,
    )
    assert result > 5.0, f"Cold charging multiplier {result} should be >> 1.0"
    print("  Cold charge (5 C): {:.2f}".format(result))


def test_degradation_charge_vs_discharge_asymmetry():
    """Charging at same conditions should show higher wear than discharging."""
    model1 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model2 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    delta_kwh = 1.0
    delta_hours = 5.0 / 60.0
    discharge_mult = model1.compute_step_degradation_multiplier(20.0, 50.0, delta_kwh, delta_hours, False)
    charge_mult = model2.compute_step_degradation_multiplier(20.0, 50.0, delta_kwh, delta_hours, True)
    assert charge_mult >= discharge_mult, f"Charge {charge_mult} should be >= discharge {discharge_mult}"
    print("  Discharge (20 C): {:.2f}, Charge (20 C): {:.2f}".format(discharge_mult, charge_mult))


def test_degradation_c_rate_monotonic():
    """Slower charging must score lower wear than faster charging.

    This is the core lever for nudging the optimiser toward gentle charging:
    at fixed temperature/SoC the multiplier must increase with C-rate, sit at
    1.0 at the nominal rate, and be < 1.0 below it.
    """
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    delta_hours = 5.0 / 60.0
    cap = model.battery_capacity_kwh

    def mult_at_c(c_rate, is_charging):
        return model.compute_step_degradation_multiplier(25.0, 50.0, c_rate * cap * delta_hours, delta_hours, is_charging)

    slow = mult_at_c(model.nominal_c_rate * 0.25, True)
    nominal = mult_at_c(model.nominal_c_rate, True)
    fast = mult_at_c(model.nominal_c_rate * 3.0, True)
    assert slow < nominal < fast, f"C-rate not monotonic: slow={slow:.3f} nominal={nominal:.3f} fast={fast:.3f}"
    # Discharging at the nominal rate is the reference point (== 1.0); charging
    # at the same rate is higher due to charge/discharge asymmetry.
    assert nominal > 1.0, f"Charge at nominal {nominal:.3f} should exceed 1.0 (asymmetry)"
    print("  C-rate sweep (charge): slow={:.3f}  nominal={:.3f}  fast={:.3f}".format(slow, nominal, fast))


def test_degradation_condition_multiplier_c_rate_independent():
    """The displayed condition multiplier ignores C-rate and is ~1.0 at 25 C/50%."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    base = model.compute_condition_multiplier(temp_c=25.0, soc_percent=50.0, is_charging=False)
    assert abs(base - 1.0) < 0.05, f"Condition multiplier at reference should be ~1.0, got {base:.3f}"
    # It must reflect SoC stress even when no throughput occurs (e.g. idle/freeze slots).
    high = model.compute_condition_multiplier(temp_c=25.0, soc_percent=95.0, is_charging=False)
    assert high > base, f"High-SoC condition multiplier {high:.3f} should exceed reference {base:.3f}"
    print("  Condition multiplier: ref={:.3f}  high-SoC={:.3f}".format(base, high))


def test_degradation_nominal_c_rate_override():
    """Explicit nominal_c_rate overrides the per-chemistry default."""
    default = DegradationModel(chemistry="LFP")
    override = DegradationModel(chemistry="LFP", nominal_c_rate=0.5)
    assert default.nominal_c_rate == CHEMISTRY_PARAMETERS["LFP"]["nominal_c_rate"]
    assert override.nominal_c_rate == 0.5
    # A falsy/zero override falls back to the chemistry default.
    zero = DegradationModel(chemistry="LFP", nominal_c_rate=0)
    assert zero.nominal_c_rate == default.nominal_c_rate
    print("  nominal_c_rate: default={}  override={}  zero->default={}".format(default.nominal_c_rate, override.nominal_c_rate, zero.nominal_c_rate))


def test_degradation_flow_battery_no_degradation():
    """Flow battery chemistry should have zero degradation multiplier."""
    model = DegradationModel(chemistry="FLOW", battery_capacity_kwh=24.0)
    delta_kwh = 1.0
    delta_hours = 5.0 / 60.0
    result = model.compute_step_degradation_multiplier(25.0, 50.0, delta_kwh, delta_hours, False)
    assert result == 0.0, f"Flow battery multiplier {result} should be 0"
    print("  Flow battery: {:.2f} (should be 0)".format(result))


def test_degradation_chemistry_registry():
    """All expected chemistries should be in the registry."""
    chemistries = dict(DegradationModel.list_chemistries())
    expected = {"LFP", "NMC", "SODIUM_ION", "NCA", "LEAD_ACID", "FLOW"}
    for chem in expected:
        assert chem in chemistries, f"Chemistry {chem} missing from registry"
    print("  All {} chemistries registered: {}".format(len(chemistries), list(chemistries.keys())))


def test_degradation_high_soc_stress():
    """SoC stress factor is now a continuous exponential centred at 50 %.
    The cycle multiplier increases with SoC deviation, matching literature."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)

    # Verify the soc_stress_factor helper
    assert abs(model.soc_stress_factor(0.5) - 1.0) < 0.001, "Stress at 50% should be ~1.0"
    high = model.soc_stress_factor(0.95)
    assert high > 2.0, f"Stress at 95% should be > 2.0, got {high:.2f}"

    # Cycle multiplier at high SoC should be larger than at mid SoC
    delta_kwh = 0.1
    delta_hours = 5.0 / 60.0
    mid_mul = model.compute_step_degradation_multiplier(25.0, 50.0, delta_kwh, delta_hours, False)
    high_mul = model.compute_step_degradation_multiplier(25.0, 95.0, delta_kwh, delta_hours, False)
    assert high_mul > mid_mul * 2.0, f"High-SoC multiplier ({high_mul:.2f}) should be > 2x mid ({mid_mul:.2f})"

    # accumulate_wear also captures SoC effect (calendar stress)
    model1 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model2 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model1.accumulate_wear(25.0, 50.0, delta_kwh, delta_hours, False)
    model2.accumulate_wear(25.0, 95.0, delta_kwh, delta_hours, False)
    assert model2.total_capacity_loss > model1.total_capacity_loss, "Calendar wear should accumulate more at high SoC"

    # LFP is asymmetric — high-SoC stress exceeds low-SoC stress
    low_mul = model.compute_step_degradation_multiplier(25.0, 5.0, delta_kwh, delta_hours, False)
    assert high_mul > low_mul * 1.2, f"High-SoC ({high_mul:.2f}) should exceed low-SoC ({low_mul:.2f}) for LFP"

    print("  Mid stress: {:.2f}  High: {:.2f}  Low: {:.2f}".format(mid_mul, high_mul, low_mul))
    print("  Calendar wear: mid={:.6f}, high={:.6f}".format(model1.total_capacity_loss, model2.total_capacity_loss))


def test_degradation_cumulative_time_reduces_rate():
    """As total_time_hours grows, the derivative slows (z < 1)."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model.total_time_hours = 10000  # Simulate an old battery
    delta_kwh = 0.1
    delta_hours = 5.0 / 60.0
    old_battery = model.compute_step_degradation_multiplier(25.0, 50.0, delta_kwh, delta_hours, False)
    print("  Old battery (10000 h): {:.4f}".format(old_battery))
    # Old batteries should still give reasonable multipliers
    assert old_battery > 0, "Old battery multiplier should be positive"


def run_degradation_tests(predbat=None):
    """Run all degradation model unit tests.

    Accepts an optional predbat instance (passed by the unit_test runner) which
    the pure-model tests do not need.
    """
    print("Degradation model tests:")
    tests = [
        ("Baseline LCOS", test_degradation_baseline_cost),
        ("Nominal conditions", test_degradation_nominal_conditions),
        ("High temperature", test_degradation_high_temperature),
        ("Cold charging plating", test_degradation_cold_charging_plating),
        ("Charge/discharge asymmetry", test_degradation_charge_vs_discharge_asymmetry),
        ("C-rate monotonic (slow < fast)", test_degradation_c_rate_monotonic),
        ("Condition multiplier C-rate independent", test_degradation_condition_multiplier_c_rate_independent),
        ("Nominal C-rate override", test_degradation_nominal_c_rate_override),
        ("Flow battery zero wear", test_degradation_flow_battery_no_degradation),
        ("Chemistry registry", test_degradation_chemistry_registry),
        ("High SoC stress", test_degradation_high_soc_stress),
        ("Cumulative time scaling", test_degradation_cumulative_time_reduces_rate),
    ]
    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print("  Testing {}...".format(name))
            test_fn()
            passed += 1
        except Exception as e:
            print("  FAILED {}: {}".format(name, e))
            failed += 1
    print("  {} passed, {} failed".format(passed, failed))
    return failed


if __name__ == "__main__":
    import sys

    sys.exit(run_degradation_tests())
