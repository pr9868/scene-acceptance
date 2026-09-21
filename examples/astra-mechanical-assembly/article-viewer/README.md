# Article presentation

This compact viewer was adapted by the coordinating assistant after the producer submission, at Pradeep's request to show multiple animated views inside the article. It adds a Front camera, a compact toolbar, pressed-state accessibility, paused initial playback and pause-on-hide behavior. Perspective, Top and End derive from the original delivered viewer.

It reads the unchanged `../submission/output/crank_slider.glb`, reuses the original locally vendored Three.js modules and plays the saved animation. There is no additional geometry generator or kinematics solver here. The frozen producer workspace, original viewer, original recording, model hashes and 16 minute 7 second task time are unaffected. The new article controls are coordinator work and are not retroactively attributed to that task.

Serve the demonstration directory over HTTP and open `article-viewer/`. In the site source, this presentation is embedded only in private drafts. Public release still needs reviewed asset paths and packaging.
