"""Blender client for checking a saved USD delivery through an external harness."""

bl_info = {
    "name": "Scene Acceptance (experimental client)",
    "author": "Pradeep Kaushik",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Acceptance",
    "description": "Check a saved USD or prepare a brief for scope review",
    "category": "3D View",
}

import json
import os
from pathlib import Path
import signal
import subprocess
import uuid
import bpy
from bpy.props import StringProperty, EnumProperty, PointerProperty


class AcceptanceSettings(bpy.types.PropertyGroup):
    executable: StringProperty(
        name="Harness CLI", default="check-3d-isolated", subtype="FILE_PATH"
    )
    bundle: StringProperty(name="Delivery folder", subtype="DIR_PATH")
    candidate: StringProperty(name="Saved USD", subtype="FILE_PATH")
    output_parent: StringProperty(name="Reports folder", subtype="DIR_PATH")
    mode: EnumProperty(
        name="Operation",
        items=[
            ("check", "Checks", "Check the saved USD"),
            ("prepare", "Prepare brief", "Propose a scope for human review"),
        ],
    )
    raw_brief: StringProperty(name="Raw brief manifest", subtype="FILE_PATH")
    interpreter_config: StringProperty(name="Interpreter config", subtype="FILE_PATH")
    latest_report: StringProperty(name="Latest report", subtype="FILE_PATH")
    status: StringProperty(name="Status", default="No delivery checked")


class ACCEPTANCE_OT_check(bpy.types.Operator):
    bl_idname = "acceptance.check_saved_usd"
    bl_label = "Check saved delivery"
    _proc = None
    _timer = None
    _stdout = None
    _stderr = None

    def execute(self, context):
        settings = context.scene.acceptance_settings
        try:
            root = Path(bpy.path.abspath(settings.bundle)).resolve(strict=True)
            scene = Path(bpy.path.abspath(settings.candidate)).resolve(strict=True)
            if not scene.is_relative_to(root):
                raise ValueError("Saved USD must be inside the delivery folder")
            parent = Path(bpy.path.abspath(settings.output_parent)).resolve()
            if parent.is_relative_to(root):
                raise ValueError("Reports folder must be outside the delivery")
            parent.mkdir(parents=True, exist_ok=True)
            run = parent / ("run-" + uuid.uuid4().hex)
            self._log = parent / (run.name + ".json")
            self._error = parent / (run.name + ".log")
            self._run = run
            self._mode = settings.mode
            command = [
                bpy.path.abspath(settings.executable),
                "--wall-seconds",
                "120",
                settings.mode,
                "--bundle-root",
                str(root),
                "--candidate",
                str(scene.relative_to(root)),
                "--out",
                str(run),
            ]
            if settings.mode == "prepare":
                brief = Path(bpy.path.abspath(settings.raw_brief)).resolve(strict=True)
                if not brief.is_relative_to(root):
                    raise ValueError("Raw brief must be inside the delivery folder")
                config = Path(bpy.path.abspath(settings.interpreter_config)).resolve(
                    strict=True
                )
                command += [
                    "--raw-brief",
                    str(brief.relative_to(root)),
                    "--interpreter-config",
                    str(config),
                ]
            self._stdout = self._log.open("wb")
            self._stderr = self._error.open("wb")
            self._proc = subprocess.Popen(
                command,
                stdout=self._stdout,
                stderr=self._stderr,
                start_new_session=True,
            )
        except Exception as exc:
            self._close(context)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.status = (
            "Checking the saved USD…"
            if settings.mode == "check"
            else "Preparing scope; human approval remains required…"
        )
        self._timer = context.window_manager.event_timer_add(
            0.25, window=context.window
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self.cancel(context)
            return {"CANCELLED"}
        if event.type != "TIMER" or self._proc.poll() is None:
            return {"PASS_THROUGH"}
        settings = context.scene.acceptance_settings
        self._close(context)
        try:
            if self._log.stat().st_size > 8388608:
                raise ValueError("Response exceeds client budget")
            result = json.loads(self._log.read_text())
            code = result["exit_code"]
            data = result.get("data") or {}
            settings.status = {
                0: "Completed within the stated scope",
                2: "Repair needed",
                3: "Review or evidence needed",
                4: "Evaluation error",
            }.get(code, "Unknown result")
            if self._mode == "prepare" and code == 0:
                settings.status = "Scope proposed. Review it before approval."
            for path in (
                self._run / "report.html",
                self._run / "report/report.html",
                self._run / "handoff.html",
            ):
                if path.is_file():
                    settings.latest_report = str(path)
                    break
            if result.get("errors"):
                self.report({"WARNING"}, result["errors"][0]["message"])
        except Exception as exc:
            settings.status = "Cannot read harness response"
            self.report({"ERROR"}, str(exc))
        return {"FINISHED"}

    def _close(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        for stream in (self._stdout, self._stderr):
            if stream:
                stream.close()

    def cancel(self, context):
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._close(context)
        context.scene.acceptance_settings.status = "Cancelled; partial records retained"


class ACCEPTANCE_OT_open(bpy.types.Operator):
    bl_idname = "acceptance.open_report"
    bl_label = "Open report"

    def execute(self, context):
        path = Path(context.scene.acceptance_settings.latest_report)
        if not path.is_file():
            self.report({"ERROR"}, "No report yet")
            return {"CANCELLED"}
        bpy.ops.wm.url_open(url=path.resolve().as_uri())
        return {"FINISHED"}


class ACCEPTANCE_PT_panel(bpy.types.Panel):
    bl_label = "Scene Acceptance"
    bl_idname = "ACCEPTANCE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Acceptance"

    def draw(self, context):
        layout = self.layout
        s = context.scene.acceptance_settings
        layout.label(text="Checks the saved USD delivery.")
        for name in ("executable", "bundle", "candidate", "output_parent", "mode"):
            layout.prop(s, name)
        if s.mode == "prepare":
            layout.prop(s, "raw_brief")
            layout.prop(s, "interpreter_config")
            layout.label(text="Sends selected evidence to your model CLI.")
        layout.operator("acceptance.check_saved_usd")
        layout.label(text=s.status)
        layout.operator("acceptance.open_report")


CLASSES = (
    AcceptanceSettings,
    ACCEPTANCE_OT_check,
    ACCEPTANCE_OT_open,
    ACCEPTANCE_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.acceptance_settings = PointerProperty(type=AcceptanceSettings)


def unregister():
    del bpy.types.Scene.acceptance_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
