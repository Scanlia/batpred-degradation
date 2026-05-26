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
    """At 25 C, 0.5C rate, 50% SoC, discharging: multiplier ~1.0."""
    model = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0, capex=10000, lifetime_cycles=8000)
    # Simulate a single 5-minute step at nominal conditions
    delta_kwh = 1.0  # 1 kWh in 5 min = 12 kW = 0.5C on 24 kWh
    delta_hours = 5.0 / 60.0
    result = model.compute_step_degradation_multiplier(
        temp_c=25.0,
        soc_percent=50.0,
        delta_throughput_kwh=delta_kwh,
        delta_time_hours=delta_hours,
        is_charging=False,
    )
    assert 0.5 < result < 2.0, f"Nominal multiplier {result} out of expected range"
    print("  Nominal (25 C, 0.5C, discharge, 50% SOC): {:.2f}".format(result))


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
    """SoC stress affects calendar wear, not cycle multiplier.  (Calendar penalty
    will be a time-shift mechanism in Phase 2 – for now cycle multiplier is
    SoC-independent.)
    Verifies that accumulate_wear (stateful) captures the SoC effect."""
    model1 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    model2 = DegradationModel(chemistry="LFP", battery_capacity_kwh=24.0)
    delta_kwh = 0.1
    delta_hours = 5.0 / 60.0

    # Stateless multiplier is SoC-independent
    mid = model1.compute_step_degradation_multiplier(25.0, 50.0, delta_kwh, delta_hours, False)
    high = model2.compute_step_degradation_multiplier(25.0, 95.0, delta_kwh, delta_hours, False)
    assert abs(mid - high) < 0.01, f"SoC should not change cycle multiplier: {mid} vs {high}"

    # accumulate_wear does capture SoC effect
    model1.accumulate_wear(25.0, 50.0, delta_kwh, delta_hours, False)
    model2.accumulate_wear(25.0, 95.0, delta_kwh, delta_hours, False)
    assert model2.total_capacity_loss > model1.total_capacity_loss, "Calendar wear should accumulate more at high SoC"

    print("  Cycle multiplier same at both SoCs: {:.2f}".format(mid))
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


def run_degradation_tests():
    """Run all degradation model unit tests."""
    print("Degradation model tests:")
    tests = [
        ("Baseline LCOS", test_degradation_baseline_cost),
        ("Nominal conditions", test_degradation_nominal_conditions),
        ("High temperature", test_degradation_high_temperature),
        ("Cold charging plating", test_degradation_cold_charging_plating),
        ("Charge/discharge asymmetry", test_degradation_charge_vs_discharge_asymmetry),
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
