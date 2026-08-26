# Look-ahead Bias Detection Report

**Status: PASS**

PASS: same-bar perfect foresight earns far more than the delayed T+1 path. Enforcing shift_for_execution removes look-ahead alpha.

## Setup

- Perfect signal: long iff next close > current close (future function).
- **Leaky path**: apply that signal with `shift(0)` and fill on the same bar's close.
- **Safe path**: `shift(1)` so T-close foresight only becomes actionable on T+1 close.
- Both paths use `fill_on=next_close`; only the signal delay differs.

## Leaky engine metrics (should look 'too good')

```
{'initial_capital': 100000.0, 'final_equity': 711600552.2464838, 'total_return': 7115.005522464838, 'annual_return': 2.3389116755038066, 'annual_volatility': 0.13394304221872147, 'sharpe': 9.083284348042264, 'max_drawdown': 0.0, 'n_trades': 948, 'n_bars': 1855}
```

## Safe engine metrics (mandatory T+1 delay)

```
{'initial_capital': 100000.0, 'final_equity': 130593.62811909772, 'total_return': 0.30593628119097716, 'annual_return': 0.03694658734597711, 'annual_volatility': 0.15141666970166576, 'sharpe': 0.31481503621487966, 'max_drawdown': -0.36446179211486573, 'n_trades': 948, 'n_bars': 1855}
```

## Details

```
{'leaky_total_return': 7115.005522464838, 'safe_total_return': 0.30593628119097716, 'leaky_sharpe': 9.083284348042264, 'safe_sharpe': 0.31481503621487966, 'return_gap': 7114.699586183647, 'sharpe_gap': 8.768469311827385, 'thresholds': {'sharpe_gap_min': 1.0, 'return_gap_min': 0.2}, 'note': 'Both paths use fill_on=next_close; only signal shift differs.'}
```

## Interpretation

If the safe path still matches leaky same-bar capture (Sharpe / total return
within the failure threshold of the leaky run), signal→fill delay is not
removing look-ahead alpha and the engine pipeline is unsafe to use as-is.
