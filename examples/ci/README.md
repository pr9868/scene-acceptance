# Check a saved scene in consumer CI

Copy [scene-acceptance.yml](scene-acceptance.yml) into your repository's `.github/workflows/`, then set the saved scene and reviewed contract paths. The template pins the currently published release; select a reviewed immutable commit or release appropriate to your checks. The new state/process packs require the forthcoming release or your reviewed development commit.

The workflow makes no model calls and has no write permissions. A rejection, missing evidence or execution error fails the job, while the report remains an artifact. Require the job in branch protection if it should gate merging. A green job covers only the selected contract.

The caller's contract, references and pack policy are trusted code/configuration. Protect them with review ownership so an untrusted scene change cannot weaken its own acceptance criteria. Configure artifact visibility and retention for the data in your scenes and reports.

The harness runs full reproduction on macOS and Linux. Inspect the actual CI result for the immutable revision you adopt; a workflow definition alone is not passing evidence.
