# Blender client

This experimental add-on checks a **saved USD delivery** through the same external CLI as other applications. It does not inspect unsaved Blender edits or imply that a `.blend` file has been accepted. Export the delivery first.

Install the harness with its `isolation` extra in a separate Python environment, then install this folder as a Blender add-on. In the Acceptance sidebar, select the full path to `check-3d-isolated`, the delivery folder, saved USD and an output folder outside the delivery. The interface stays responsive while the CLI runs. Open the resulting report to inspect coverage.

“Prepare brief” additionally takes a raw brief manifest and your interpreter configuration. It sends the selected evidence to that configured model and leaves the proposed scope pending human review. The add-on does not approve scope, clear mandatory reviews, edit the scene or render evidence.

Current platform: Blender 4.2+ on macOS/Linux. The client source and transport are checked separately from the harness; a live Blender integration test is still required before treating it as a supported production plug-in. Windows is not claimed because the process-group supervisor is POSIX-only.
