# Atlas per-batch sign-agreement oracle (run atlas-oracle-20260930-01)

- cells=98927 genes=18080 targets=50 batches=48
- batches lacking NTC: 0
- eligible batches/target (>= 20 cells): median 34, targets with >= 3: 41/50
- scored (target,gene) pairs: 731917
- Spearman(agree_frac, |pooled delta|) all targets: 0.6304
- Spearman restricted to 2026-panel targets: 0.5991

| agree_frac bin | n pairs | mean|pooled| | split-half sign agree | split-half cosine |
|---|---|---|---|---|
| [0.00,0.55) | 339232 | 0.0062 | 0.5009 | -0.0954 |
| [0.55,0.70) | 251276 | 0.0188 | 0.7182 | 0.4885 |
| [0.70,0.85) | 90989 | 0.0413 | 0.8337 | 0.8282 |
| [0.85,0.95) | 24444 | 0.0613 | 0.8491 | 0.9389 |
| [0.95,1.00) | 25976 | 0.1564 | 0.9333 | 0.9909 |
