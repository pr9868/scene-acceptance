"""Saved USD/UV controls; rendering belongs to this caller example, not the harness."""

from pathlib import Path
import argparse
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pxr import Usd, UsdGeom, UsdShade, Sdf
from caller_cpu_renderer import collect, render, look_at


def create(out):
    out.mkdir(parents=True, exist_ok=False)
    for name in ("correct", "mirrored", "occluded"):
        root = out / name
        root.mkdir()
        texture = Image.new("RGB", (768, 320), (255, 230, 60))
        draw = ImageDraw.Draw(texture)
        font = ImageFont.load_default(size=60)
        draw.text((384, 70), "KEEP AISLE CLEAR", font=font, fill="black", anchor="mm")
        draw.line((140, 220, 570, 220), fill="black", width=28)
        draw.polygon([(570, 160), (655, 220), (570, 280)], fill="black")
        texture.save(root / "sign.png")
        s = Usd.Stage.CreateNew(str(root / "scene.usda"))
        w = UsdGeom.Xform.Define(s, "/World")
        s.SetDefaultPrim(w.GetPrim())
        UsdGeom.SetStageUpAxis(s, "Z")
        UsdGeom.SetStageMetersPerUnit(s, 1)
        s.SetStartTimeCode(0)
        s.SetEndTimeCode(0)
        s.SetTimeCodesPerSecond(24)
        mesh = UsdGeom.Mesh.Define(s, "/World/Sign")
        mesh.CreatePointsAttr(
            [(-1.5, 0, -0.6), (1.5, 0, -0.6), (1.5, 0, 0.6), (-1.5, 0, 0.6)]
        )
        mesh.CreateExtentAttr([(-1.5, 0, -0.6), (1.5, 0, 0.6)])
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreateSubdivisionSchemeAttr("none")
        mesh.CreateNormalsAttr([(0, -1, 0)] * 4)
        mesh.SetNormalsInterpolation("vertex")
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        if name == "mirrored":
            uv = [(1 - u, v) for u, v in uv]
        UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex"
        ).Set(uv)
        mat = UsdShade.Material.Define(s, "/World/Looks/Sign")
        shader = UsdShade.Shader.Define(s, "/World/Looks/Sign/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        tex = UsdShade.Shader.Define(s, "/World/Looks/Sign/Texture")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("sign.png"))
        tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
        st = UsdShade.Shader.Define(s, "/World/Looks/Sign/UV")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            st.ConnectableAPI(), "result"
        )
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tex.ConnectableAPI(), "rgb"
        )
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
        if name == "occluded":
            box = UsdGeom.Cube.Define(s, "/World/Occluder")
            box.AddTranslateOp().Set((0, -0.35, 0))
            box.AddScaleOp().Set((1.7, 0.1, 0.75))
            box.CreateDisplayColorAttr([(0.3, 0.3, 0.3)])
        s.GetRootLayer().Save()
        # Re-open saved delivery: no in-memory producer object is the evidence.
        saved = Usd.Stage.Open(str(root / "scene.usda"))
        meshes, skipped = collect(saved, 0)
        eye = np.array((0, -4, 0), float)
        rotation, _ = look_at(eye, (0, 0, 0))
        pixels = render(meshes, rotation, eye, 40, 960, 640, ortho_width=3.8)
        Image.fromarray(pixels).save(root / "front.png")
        (root / "render.json").write_text(
            json.dumps(
                dict(
                    renderer="caller CPU flat-Lambert z-buffer",
                    camera="fixed front",
                    eye_m=eye.tolist(),
                    target_m=[0, 0, 0],
                    ortho_width_m=3.8,
                    time_code=0,
                    unsupported=skipped,
                    limitation="Diagnostic saved-USD rendering; not RTX, photorealism or physical validation",
                ),
                indent=2,
            )
            + "\n"
        )
    (out / "expected.json").write_text(
        json.dumps(
            dict(
                correct="consistent",
                mirrored="concern",
                missing="unknown",
                occluded="unknown",
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    create(parser.parse_args().out)
