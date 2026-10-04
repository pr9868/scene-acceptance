# Separately reported denser-motion follow-up

Added after the first two primary results were inspected (rotary simple run 1 and rotary medium run 1). This is **not part of the frozen ten-check primary comparison**, and must never replace it or silently change its pass counts.

The medium producer passed its two supplied endpoints. Its path differed from the later full-target reference at 16 of the 21 primary checkpoints. That observation motivated a further coverage question: can an artifact pass 21 checkpoints while departing from the specified path between them?

Apply the existing `motion.timing.positions` check to 201 equally spaced elapsed-second samples, including endpoints, for all three task families and all 24 slots that deliver a readable scene. Derive positions from the same original analytic curve or piecewise linear knots. Preserve the original 1 mm tolerance, scene files, clocks and checker revision. Report results in a separate table; requirements between checkpoints were supplied only to the detailed producers. Simpler scenes are comparisons to withheld targets.

First check a constructed rotary path with 21 exact circle positions and linear interpolation between them. It should pass the original 21-point check and fail denser samples because a chord deviates from a circle. Check a second constructed control using linearly animated Z rotation and an offset origin, which should pass all 201 points. These are scripted coverage controls, not model errors. They remain separate from the original 33 controls.

A failing sampled position is concrete evidence of noncompliance at that time. Passing all 201 samples still does not prove the whole continuous path, orientation, attachments, collision freedom or physics. The existing review gate for continuous motion stays unresolved. No production repair or extra creation call is added.
