"""Bounded image admission and static USD input resolution; no shader execution."""

from pathlib import Path
import warnings
from pxr import Sdf, UsdShade
from .model import ContractError, MissingEvidence


def inspect_visual_reference(path):
    """Admit source images for visual interpretation without changing their pixels.

    Exact pixel comparisons retain their separate, smaller decoder policy. Alpha,
    orientation and colour metadata are preserved, not silently normalised.
    """
    from PIL import Image

    path = Path(path)
    if path.stat().st_size > 8388608:
        raise ContractError("Reference image exceeds 8 MiB")
    from .image_policy import load_image

    try:
        image = load_image(path, modes=("RGB", "RGBA"))
        metadata = dict(
            width=image.width,
            height=image.height,
            mode=image.mode,
            mime="image/png" if image.format == "PNG" else "image/jpeg",
            conversion="none",
            alpha="preserved" if image.mode == "RGBA" else "absent",
            colour_management="none; stored channels and profile metadata preserved",
            orientation="stored pixels; EXIF orientation not applied",
            icc_profile_present=bool(image.info.get("icc_profile")),
        )
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ContractError("Reference image exceeds decoder safety budget") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise ContractError(
            "Reference image cannot be fully decoded: " + str(exc)
        ) from exc

    return metadata


def resolve_asset_input(ctx, attribute):
    """Follow one static UsdShade input chain to an already admitted asset.

    Computed outputs, cycles, multiple sources, missing sources and animated
    values stay unknown. No input connection can add an asset to the closure.
    """
    stage = ctx.artifact.stage
    current = attribute
    chain = []
    while current:
        name = str(current.GetPath())
        if name in chain:
            raise MissingEvidence("Texture input connection cycle")
        if len(chain) >= 64:
            raise MissingEvidence("Texture input chain exceeds 64 attributes")
        chain.append(name)
        if current.GetTypeName() != Sdf.ValueTypeNames.Asset:
            raise MissingEvidence("Texture input source must be asset-valued")
        if current.GetNumTimeSamples():
            raise MissingEvidence("Animated texture input values are not supported")
        connections = current.GetConnections()
        if not connections:
            break
        if len(connections) != 1:
            raise MissingEvidence("Texture input has multiple connected sources")
        source = stage.GetAttributeAtPath(connections[0])
        if not source:
            raise MissingEvidence("Texture input connection source is missing")
        if (
            not UsdShade.Input(current)
            or not UsdShade.Input(source)
            or not UsdShade.ConnectableAPI(source.GetPrim())
        ):
            raise MissingEvidence(
                "Computed shader outputs are outside static texture input resolution"
            )
        current = source
    resolution = dict(input_chain=chain, value_attribute=str(current.GetPath()))
    # Check the shading API agrees with our deliberately bounded input traversal.
    if len(chain) > 1:
        producers = UsdShade.Input(attribute).GetValueProducingAttributes()
        if len(producers) != 1 or producers[0].GetPath() != current.GetPath():
            raise MissingEvidence(
                "Texture input has no unique value-producing attribute"
            )
    asset = current.Get()
    if not asset or not asset.path:
        return None, resolution
    if not asset.resolvedPath:
        raise MissingEvidence("Selected texture file is unresolved")
    path = ctx.bundle.path(asset.resolvedPath)
    if path not in ctx.artifact.assets:
        raise MissingEvidence(
            "Selected texture is outside the admitted dependency closure"
        )
    return ctx.bundle.record(path, missing=True), resolution
