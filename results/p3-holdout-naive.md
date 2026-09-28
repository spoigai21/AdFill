# Sweep: p3-holdout-naive

Worlds: 6 (2018-03-01 seed 1, 2018-03-01 seed 2, 2018-03-01 seed 3, 2018-09-01 seed 1, 2018-09-01 seed 2, 2018-09-01 seed 3)

Revenue lift vs guaranteed-first, and campaigns delivered in full (summed over worlds).

### makegood = 1.0 x contract CPM

| policy | exponent | revenue lift vs GF (mean) | min | max | delivered in full | mean delivery |
|---|---|---|---|---|---|---|
| guaranteed_first | – | +0.0% | +0.0% | +0.0% | 240/240 | 1.000 |
| highest_bid | – | -28.2% | -39.4% | -17.8% | 67/240 | 0.547 |
| adfill | 0.5 | +19.0% | +13.2% | +21.3% | 240/240 | 1.000 |
| adfill | 1.0 | +21.8% | +15.8% | +24.2% | 213/240 | 0.999 |
| adfill | 2.0 | +6.6% | -1.8% | +16.0% | 72/240 | 0.878 |
| adfill | 4.0 | -2.6% | -14.1% | +7.2% | 42/240 | 0.805 |

