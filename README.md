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
throughput, so every cycle costs the same regardless of charge rate or temperature. Real LFP batteries
don't wear like that: **high C-rate and extreme temperatures accelerate degradation**. This fork models
that and lets the planner exploit it.

The fork compares two plans and picks the cheaper on total cost:

* the **standard plan** (upstream behaviour: full charge rate, money-optimal), and
* the **degradation-aware plan** (gentle, low-power charging that reduces C-rate wear).

What it adds on top of upstream Predbat:

* **Physics-based wear model** (`apps/predbat/degradation.py`): a per-step degradation multiplier `μ`
  driven by **charge/discharge C-rate** and **battery temperature**, calibrated to the cell's rated
  cycle life (LCOS ≈ capex / (capacity · cycles · depth-of-discharge)). Gentle charging at mild
  temperatures wears the pack far less than a hard, cold fast-charge.
* **True economic objective**: plans are scored on `J = money (import minus export) + real μ-weighted
  wear` instead of money plus a flat cycle cost. Wear is priced at its actual modelled cost, so the
  optimiser will spend a fraction of a cent of energy to avoid a larger chunk of battery wear (and
  vice versa).
* **Automatic low-power (gentle) charging, executed live.** Every ~30 min the fork optimises the plan at
  **full charge rate** and at **low (spread) charge rate**, scores both on `J`, and automatically toggles
  Predbat's native `set_charge_low_power` for the live plan **only when gentle charging clearly lowers
  total cost** (a deadband prevents flapping). This reuses Predbat's own battle-tested charge-rate
  dispatch, so what runs is exactly what was scored, and never worse than the standard plan.
* **Side-by-side comparison UI**: the plan page shows the **ACTIVE** (executing) plan next to the
  **comparison** plan, with extra `Wear x` / `Wear c` columns, so you can see the money vs degradation
  trade-off the optimiser is making at a glance.
* **Degradation audit and forecast logging**: optional helpers snapshot each standard vs low-power pair
  to CSV and log forward energy rates and PV forecasts, for offline what-if analysis and validation.
* **Reproducible overlay build**: a **digest-pinned** upstream base image with our modified source files
  layered on top, so upstream can be re-based deliberately without the base silently moving under us.

Enable it with the `degradation_enable` / `degradation_compare_enable` options plus your cell's
`degradation_lifetime_cycles` and `degradation_nominal_c_rate`; leave them off and Predbat behaves
exactly like upstream.

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
