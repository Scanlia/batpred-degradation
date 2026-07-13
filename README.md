# Predbat

![image](https://github.com/springfall2008/batpred/actions/workflows/code-quality.yml/badge.svg)
![image](https://github.com/springfall2008/batpred/actions/workflows/publish-docs.yml/badge.svg)
![image](https://github.com/springfall2008/batpred/actions/workflows/pages/pages-build-deployment/badge.svg)

> **⚡ This is a degradation-aware fork of [springfall2008/batpred](https://github.com/springfall2008/batpred).**
> It adds a physics-based battery **wear model** and **automatic gentle (low-power) charging** so the
> planner trades off money **and** real battery degradation, not money alone. Everything upstream still
> works unchanged; see [Degradation fork additions](#-degradation-fork-additions) for what's new.
> Full credit for Predbat itself goes to Trefor Southwell (@springfall2008).

## Introduction

Home battery prediction and automatic charging for Home Assistant supporting multiple inverters, including GivEnergy, Solis, Huawei, SolarEdge, SigEnergy, FoxESS, Sofar, Tesla Powerwall and many more.

Also known by some as Batpred or Batman!

![icon](https://github.com/springfall2008/batpred/assets/48591903/7c207423-1423-4f88-beb2-d1da5cfbfeeb) ![image](https://github.com/springfall2008/batpred/assets/48591903/e98a0720-d2cf-4b71-94ab-97fe09b3cee1)

If you want to buy me a beer, then please use [Paypal](https://paypal.me/predbat?country.x=GB&locale.x=en_GB) or [GitHub sponsor](https://github.com/springfall2008)
![image](https://github.com/springfall2008/batpred/assets/48591903/b3a533ef-0862-4e0b-b272-30e254f58467)

* Use my referral code for Octopus Energy: <https://share.octopus.energy/jolly-eel-176>
* Use my referral code for Axle Energy (UK): <https://vpp.axle.energy/landing/grid?ref=R-VWIICRSA>

If you find Home Assistant and Predbat too difficult to set up yourself, there is now [PredBat Cloud](https://predbat.com/), a paid version of Predbat hosted in the cloud. Please note that while I have given permission for PredBat Cloud to operate under license, PredBat will remain open source for personal use.

## 🔋 Degradation fork additions

Standard Predbat prices battery use with a single flat `metric_battery_cycle` cost per kWh of
throughput, so every cycle costs the same regardless of charge rate, temperature, or how long the pack
sits at high state of charge. Real LFP batteries don't wear like that. This fork replaces the flat cost
with a **physics-based wear model** that prices the two real ageing mechanisms separately, and lets the
planner trade money against genuine degradation. See [Degradation model](docs/degradation.md) for the
full detail; the summary is below.

The fork optimises and compares two plans, then picks the cheaper on **total cost (money + modelled
wear)**:

* the **comparison plan** (upstream-style: money plus a flat cycle cost), and
* the **degradation-aware ACTIVE plan** (money plus real, mechanism-based wear).

### Two ageing mechanisms, priced independently

The model (`apps/predbat/degradation.py`) prices each mechanism at its own nameplate cost and **adds
them** (no capex apportionment between them):

* **Cycle wear** scales with **energy throughput**, **charge/discharge C-rate**, and **temperature**.
  Gentle, warm charging wears the pack far less than a hard, cold fast-charge. Base cost is
  `capex / (lifetime_cycles · 2 · capacity)`, then a per-step multiplier for C-rate and temperature.
* **Calendar ageing** scales with **state of charge**, **temperature (Arrhenius)**, and **time held**.
  Base rate is `capex / (calendar_life_years · 8760 h)`, multiplied by an SoC-stress factor from a
  literature-validated 9-point table (Schimpe 2018 / Safari 2011): stress is **lowest near empty and
  rises steeply toward full**, so the planner naturally parks the battery low when idle. A
  `calendar_contamination` factor (~0.82) keeps the two mechanisms sharing one end-of-life fade budget
  rather than double-counting it.

A single `degradation_calibration_factor` scales the whole model so you can tune its aggressiveness to
observed real-world fade without changing the physics.

### What it adds on top of upstream Predbat

* **True economic objective**: plans are scored on `J = money (import minus export) + real wear`
  instead of money plus a flat cycle cost, so the optimiser will spend a fraction of a cent of energy to
  avoid a larger chunk of battery wear (and vice versa).
* **Automatic low-power (gentle) charging, executed live.** Every ~30 min the fork optimises at **full
  charge rate** and at **low (spread) charge rate**, scores both on `J`, and toggles Predbat's native
  `set_charge_low_power` for the live plan **only when gentle charging clearly lowers total cost** (a
  deadband prevents flapping). This reuses Predbat's own charge-rate dispatch, so what runs is exactly
  what was scored, and never worse than the standard plan.
* **Side-by-side comparison UI**: the plan page shows the **ACTIVE** plan next to the **comparison**
  plan, with a `Wear c` column (and `Wear x` / `C-rate` / `Cyc c` / `Cal c` breakdown under **Show
  Debug**), so you can see the money vs degradation trade-off at a glance.
* **Degradation audit and forecast logging**: optional helpers snapshot each standard vs low-power pair
  to CSV and log forward energy rates and PV forecasts, for offline what-if analysis and validation.
* **Reproducible overlay build**: a **digest-pinned** upstream base image with our modified source files
  layered on top, so upstream can be re-based deliberately without the base silently moving under us.

### Recommended companion settings

Because the calendar term pushes state of charge **down** when the battery is idle, pair it with:

* **`combine_charge_slots: true`** — with fine per-slot charge windows the optimiser can manufacture a
  wasteful overnight **charge/discharge sawtooth** (topping up and bleeding down around one SoC).
  Combined windows set one target per low-rate block and let it hold flat instead. `set_charge_low_power`
  keeps the combined charge gentle, so you don't lose slow charging.
* **`metric_battery_value_scaling` near 1.0** — this values charge still in the battery at the end of the
  planning horizon. Keeping it close to 1.0 stops the calendar term from over-dumping the pack just
  because the plan window ends.

Enable the model with `degradation_enable` / `degradation_compare_enable` / `degradation_cost_enable`,
plus your cell's `degradation_lifetime_cycles`, `degradation_calendar_life_years`, and
`degradation_capex`; leave them off and Predbat behaves exactly like upstream.

> ⚠️ Experimental. This controls a real battery. Start with `degradation_compare_enable` (comparison
> only, does not touch dispatch), watch the audit pairs, and only then enable execution.

## Predbat documentation

You can find the latest Predbat documentation at [https://springfall2008.github.io/batpred/](https://springfall2008.github.io/batpred/) and
how-to videos on my [YouTube channel](https://www.youtube.com/@springfall2008).

The documentation covers how Predbat works and how to get it installed
and configured, video tutorials and FAQs to help you get going.
It also explains how you can contribute to the project.

## Support

For support, please raise a GitHub ticket or use the Facebook Group: [Predbat](https://www.facebook.com/groups/1477599886299106)

Some inverters have their own groups also, e.g.:

* [GivTCP](https://www.facebook.com/groups/615579009972782)
* [Solis](https://www.facebook.com/groups/288045168816481)

## License

Please see [License](https://github.com/springfall2008/batpred/blob/main/License.md)

```text
Copyright (c) Trefor Southwell 2025-2026 - All rights reserved
This software may be used at no cost for personal use only.
No warranty is given, either expressed or implied.
```
