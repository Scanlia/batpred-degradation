# Degradation model (fork)

This page documents the physics-based battery **wear model** added by this fork. It is optional: with
the `degradation_*` options off, Predbat behaves exactly like upstream and prices battery use with the
single flat `metric_battery_cycle` cost.

Upstream Predbat charges one flat cost per kWh of throughput, so every cycle costs the same regardless of
charge rate, temperature, or how long the pack sits at a high state of charge. Real LFP cells do not wear
that way. This fork models the two real ageing mechanisms separately, prices each in cents, and lets the
optimiser trade money against genuine degradation.

## The two mechanisms

The model in `apps/predbat/degradation.py` prices each mechanism at its **own nameplate cost** and
**adds them** — there is no capex apportionment splitting one budget between them. Over the life of the
pack the two contributions sum to roughly one capex worth of fade.

### Cycle wear

Driven by energy **throughput**, **C-rate**, and **temperature**.

* Base two-way cost: `capex / (lifetime_cycles · 2 · capacity)` cents per kWh of throughput.
* Multiplied by a per-step factor that rises with **C-rate** (hard/fast charge or discharge wears more)
  and departs from the mild-temperature optimum (cold and hot both wear more).
* A `calendar_contamination` factor (~0.82) is applied so cycle and calendar share one end-of-life fade
  budget rather than double-counting it.

At the current calibration this works out to about **1.0 c/kWh** two-way for a gentle, mild cycle.

### Calendar ageing

Driven by **state of charge**, **temperature (Arrhenius)**, and **time held**.

* Base rate: `capex / (calendar_life_years · 8760 h)` cents per hour.
* Multiplied by an **SoC-stress factor** from a literature-validated 9-point table (Schimpe 2018 /
  Safari 2011), normalised to 1.0 at 50% SoC:

  | SoC | 0% | 12.5% | 25% | 37.5% | 50% | 62.5% | 75% | 87.5% | 100% |
  |-----|----|-------|-----|-------|-----|-------|-----|-------|------|
  | stress | 0.13 | 0.36 | 0.60 | 0.88 | 1.00 | 1.09 | 1.35 | 1.59 | 1.65 |

  Stress is **lowest near empty and rises steeply toward full**, which is why the planner parks the
  battery low when it has nothing better to do with it.
* Multiplied by an **Arrhenius** temperature factor (warmer packs age faster).

For **plan scoring** the calendar term is *marginal*: it prices only the stress **above**
`marginal_baseline_soc`, so two plans of equal duration are compared fairly (the baseline resting SoC
cancels). The **displayed** `Cal c` column uses the full (non-marginal) stress so you see the true
per-slot calendar cost.

## Objective

Plans are scored on:

```text
J = money (import − export) + cycle wear + calendar wear
```

The optimiser will spend a fraction of a cent of energy to avoid a larger chunk of wear, and vice versa.
A single `degradation_calibration_factor` scales the entire model (both mechanisms) so you can tune its
aggressiveness against observed real-world fade without touching the physics.

## Parameters

Set these in `apps.yaml`:

| Option | Meaning | Typical |
|--------|---------|---------|
| `degradation_enable` | Master enable for the model | `true` |
| `degradation_compare_enable` | Build the side-by-side comparison plan | `true` |
| `degradation_cost_enable` | Include modelled wear in the live objective | `true` |
| `degradation_cost_weight` | Weight on the wear term in `J` | `1.0` |
| `degradation_capex` | Pack replacement cost (in the model's cost unit) | e.g. `1000000` |
| `degradation_battery_capacity` | Usable capacity, kWh | your pack |
| `degradation_lifetime_cycles` | Rated full cycles to end-of-life | e.g. `10000` |
| `degradation_nominal_c_rate` | Reference C-rate for the cycle multiplier | e.g. `0.2` |
| `degradation_calendar_life_years` | Rated calendar life (LFP is calendar-robust) | `15`–`20` |
| `degradation_eol_capacity_fade` | Fade defining end of life (e.g. 0.30 = 70% retention) | `0.30` |
| `degradation_calendar_contamination` | Shared-budget factor on cycle cost | `0.82` |
| `degradation_marginal_baseline_soc` | SoC below which calendar is not priced in scoring | `0.10`–`0.30` |
| `degradation_calibration_factor` | Global scale on the whole model | tune to fade |
| `degradation_jit_charge` | Defer charging to reduce high-SoC dwell (validate first) | `false` |

## Recommended companion settings

Because the calendar term pushes SoC **down** when the battery is idle, two native Predbat settings
matter:

* **`combine_charge_slots: true`.** With fine per-slot charge windows the optimiser can manufacture a
  wasteful overnight **charge/discharge sawtooth** — repeatedly topping the pack up and bleeding it down
  around a single SoC to hold charge for a later peak. Each such cycle loses round-trip efficiency plus
  wear for no net storage. Combined windows set one charge target per low-rate block, so the plan holds
  flat (or charges once, just-in-time before the peak) instead. `set_charge_low_power` keeps the combined
  charge gentle, so combining does not cost you slow charging.
* **`metric_battery_value_scaling` near 1.0.** This scales the money value Predbat assigns to charge left
  in the battery at the end of the 48h horizon. Keeping it close to 1.0 stops the calendar term from
  over-dumping the pack simply because the plan window ends.

## Reading the plan

The plan page shows the **ACTIVE** (executing) plan next to the **comparison** plan. The `Wear c` column
is the total modelled wear for the slot. Turn on **Show Debug** to split it into `Wear x` (multiplier),
`C-rate`, `Cyc c` (cycle) and `Cal c` (calendar). In a sawtooth-free plan you should see the battery
coast down to its floor, sit flat while idle, then charge once just before a peak.

> ⚠️ Experimental. This controls a real battery. Start with `degradation_compare_enable` (comparison
> only, does not touch dispatch), watch the plan and the audit pairs, and only then enable execution.
