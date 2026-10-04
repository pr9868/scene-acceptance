# Unified invocation controls

`host_smoke.py` exercises actual Python and Node host integrations against an installed `check-3d`, using a deterministic model adapter. It covers legacy invocation and the three explicit modes, each with and without a mapped brief: 16 host invocations. These are interface tests, not real model opinions.

The package's `tests/test_evaluation_modes.py` checks component isolation, all six mode/brief combinations, unchanged legacy behavior, view provenance and budgets, source mutation, custom rubrics, withheld/script-aware exposure, evidence suitability, model disagreement and preserved partial reports after timeout or malformed responses. It includes the real study's 960×600 view size and rejects images above the separate 16-million-pixel ceiling.

The October 3 final non-editable replay passed 448 software tests without skips, preserving the earlier pack, geometry, timing, supplemental, reporting, content and bounded physics results. Test results apply to the retained runtime digest; they do not certify model judgment or all possible scenes. Real model reviews are a separate study in `../judge-modes-v1/`.
