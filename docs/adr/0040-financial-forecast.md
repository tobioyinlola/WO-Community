# 0040. The financial forecast: a pure engine and assumptions the founder owns

Status: accepted (toolkit stage T3, forecast)

## Decisions

- **The engine is a pure module.** `forecasts/engine` imports no framework, no database, no
  network and no other toolkit module; import-linter enforces it. It takes a dictionary of
  assumptions and returns 24 months of figures. A model never produces a number that reaches a
  forecast.
- **Money is whole minor units**, rounded half up each month, with the currency stored beside it
  (NGN, KES, GHS, ZAR, EGP, USD; all use two decimals). Rates are percentages as entered. Arithmetic
  runs in `Decimal` at 120 digits and any figure beyond 10^18 is held there and flagged
  (`figures_too_large`) instead of failing.
- **Six templates** (subscription, marketplace, transaction fee, product sales, services,
  licensing) share one cost and cash structure: cost of sales as a percentage of revenue plus any
  direct cost the template has, marketing, salaries by start month and count, fixed costs, tax on
  profit after carried forward losses, and funding events that add cash in their month. There is no
  debt, working capital timing or depreciation; the output is a planning forecast, not accounts.
- **Scenarios are fixed multipliers**, not new inputs: conservative (growth x0.6, churn x1.3, costs
  x1.1), base, optimistic (growth x1.3, churn x0.8, costs x0.95). Sensitivity moves each rate and
  amount 20 percent down and up and ranks the effect on year two revenue and lowest cash.
- **Sanity checks warn, they do not block.** Very high growth, near zero churn, margins over 95
  percent, no operating costs, no revenue, running out of cash and more customers than the
  founder's own market estimate are reported with a plain message.
- **Assumptions are stored, results are not.** The calculation is milliseconds, so results are
  computed on read from the saved assumptions and the version. Every save is a numbered version
  (30 kept) and a stale `base_version` is 409.
- **The model only proposes.** `suggest` offers growth, churn and renewal rates the sourced
  benchmarks support, each tied to a source and validated against the same ranges; prices and
  volumes are never proposed, and nothing is saved until the founder saves it.
- **The spreadsheet keeps its working.** Revenue and cost lines are the engine's figures; every
  derived line (gross profit, operating costs, EBITDA, net income, cash) and the totals are
  formulas, so changing a cost or a funding amount in the file moves cash. Revenue drivers are not
  reconstructed as formulas: doing so would duplicate the engine's rules per template and let the
  two drift apart.
- **Plans read the forecast through `forecasts.selectors.headline`**; a plan section is out of date
  when the forecast version it used has moved.
