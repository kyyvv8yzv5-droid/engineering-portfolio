# Synthetic checks

This portfolio harness loads two unchanged application modules directly from their reviewed source files. It checks a binary confusion calculation and both Picker hashes using generated data. The harness is portfolio verification code. It does not reproduce an application implementation.

Requirements are Python 3.11 or later and Pillow. From the portfolio root, run python demos/run_synthetic_checks.py after installing Pillow. The checks use no network, API keys, databases, datasets, or model weights.

The wider source collections include context-dependent modules. Passing these checks does not make those collections independently runnable.
