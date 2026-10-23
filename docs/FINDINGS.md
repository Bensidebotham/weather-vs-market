# Findings: why the market wins, and what would have faked a win

The scores are in [RESULTS.md](RESULTS.md), generated from `results/backtest_test.json`.
This note explains them. Every number here comes from a committed results or
parameter file, linked where it is used.

## The result

Out of sample (July 2025 to September 2026), the market's bucket probabilities
were more accurate than the model's at both lead times, on Kalshi and on
Polymarket, by Brier score, ranked probability score and log score. Every 95%
interval excludes zero. The forward record, scored the same way on every day
since the model was frozen, says the same thing so far (it's on the dashboard).

## Does the model know anything the price doesn't?

Losing on its own doesn't rule out the model carrying *some* information the
market misses. A pre-registered blend (protocol v2) pools the two ladders with
weights fit on the training window. In training, the model got a small weight
(about a quarter of the market's) that was clearly above zero. Out of sample it
bought nothing: on Kalshi the blend and the market are indistinguishable, and on
Polymarket the blend was worse, because its weights came from roughly 150 thin
early-2025 New York days that rewarded flattening the market's prices. The
honest reading is that whatever the model knows, the price already has. The
tables are in [RESULTS.md](RESULTS.md).

## Why the model loses

**It sees older information, by design.** To rule out look-ahead, the backtest
only lets the model use forecasts that were already published at each lead
time: runs issued about two days before the target day for the noon-the-day-before
score, and about one day before for the 08:00 score. The market is pricing the
newest runs, local forecasters and the morning's observations. A stale but
honest model against a live crowd is the comparison this project makes on
purpose, and the crowd wins.

**Its confident calls were its worst.** In the calibration chart, buckets the
market called at 60–75% won more often than that; buckets the model called above
50% won far less often. Almost all of those were open-ended tail buckets on days
when GFS and ECMWF disagreed by several degrees. Averaging two models that disagree
and adding a year-round bias produces a confident forecast in between that neither
model supports.

**Coastal stations are hard for a 25 km grid.** The fitted error spread
([`config/det_gauss_v1.params.json`](../config/det_gauss_v1.params.json)) is
1.7–1.8 °F at Miami but 3.6–4.6 °F at Los Angeles and 4.0–5.4 °F at San Francisco,
where the grid point can't see the marine layer. Los Angeles also needs the largest
bias correction (the raw forecast runs 2.6–4.5 °F hot).

## What would have faked a win (and how each was caught)

Each of these was found before the test window was scored; the protocol's
amendments ([PROTOCOL.md](PROTOCOL.md)) record when and why.

- **A failed forecast stored as a confident "no".** An empty ensemble fetch became
  P = 0.0 and was saved as a real prediction. It now raises and is skipped.
- **Stale market prices.** Filtering out wide-spread candles before taking the
  latest one could reach back hours to an older, tighter quote, and stale prices
  flatter the model. The rule is now "latest candle, then the price test".
- **The wrong ground truth.** The model was first fit to the NWS daily climate
  report, but Polymarket settles on station observations, which run lower. Fitting
  Polymarket to the wrong truth would have biased that side.
- **The wrong station.** Kalshi NYC settles on Central Park and Polymarket NYC on
  LaGuardia; Chicago is Midway vs. O'Hare. One station for both would have mixed
  different weather.
- **Hourly readings miss the peak.** The official high runs 0.55–0.86 °F above
  the highest hourly METAR at every station
  ([`config/locked_obs.params.json`](../config/locked_obs.params.json)), so a live
  model that trusted the hourly max undershot every afternoon.
- **Silently incomplete ladders.** A typo in Polymarket's question text ("be tween
  70-71°F") dropped the winning bucket; the event was then scored on the remaining
  buckets after renormalizing. Ladders that don't cover every outcome are now
  dropped and counted.
- **Leads that couldn't exist.** The original 72 h and 48 h lead buckets predate
  the markets themselves (Kalshi ladders open about 39 hours before they close),
  so those rows were later snapshots under the wrong label.

## Data checks

On 1,824 of the 1,825 test days, the NWS daily high fell in the bucket Kalshi
settled as the winner, including after Kalshi switched its settlement source to
The Weather Company in August 2026. Of 1,828 Kalshi and 1,338 Polymarket city-days
in the test window, 117 and 85 (city-day, lead) pairs were dropped for a missing
price and one ladder each for missing buckets (counts in
[RESULTS.md](RESULTS.md)).
