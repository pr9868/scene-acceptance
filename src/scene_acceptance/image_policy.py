"""One bounded decoder; callers retain their own comparison and admission policy."""

from pathlib import Path
import io
import warnings

from .model import MissingEvidence, ContractError, sha


def load_image(path, *, max_bytes=8388608, max_pixels=16000000, modes=None):
    from PIL import Image

    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise MissingEvidence("Image exceeds decoding byte budget")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if (
                image.format not in ("PNG", "JPEG")
                or getattr(image, "n_frames", 1) != 1
            ):
                raise MissingEvidence("Only single-frame PNG/JPEG is supported")
            if image.width * image.height > max_pixels:
                raise MissingEvidence("Image exceeds decoding pixel budget")
            if modes is not None and image.mode not in modes:
                raise MissingEvidence(
                    "Image requires "
                    + "/".join(modes)
                    + " channels under the declared policy"
                )
            image.verify()
        with Image.open(path) as image:
            image.load()
            result = image.copy()
            result.format = image.format
            result.info = dict(image.info)
            return result


def linear_pixels(path, space, orientation):
    from PIL import ImageOps, ImageCms

    image = load_image(path, max_bytes=1048576, max_pixels=262144, modes=("RGB",))
    if orientation == "exif":
        image = ImageOps.exif_transpose(image)
    profile = image.info.get("icc_profile")
    if space == "embedded-icc":
        if not profile:
            raise MissingEvidence("Embedded-ICC policy needs an ICC profile")
        try:
            image = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                outputMode="RGB",
            )
        except (OSError, ValueError, ImageCms.PyCMSError) as exc:
            raise MissingEvidence("ICC profile cannot be converted to sRGB") from exc
    elif profile:
        raise MissingEvidence(
            "An embedded profile requires explicit embedded-icc comparison policy"
        )

    def decode(value):
        value = value / 255
        return (
            value
            if space == "linear-rgb8"
            else value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        )

    return image.size, [
        (decode(r), decode(g), decode(b)) for r, g, b in image.get_flattened_data()
    ]


def compare(ctx, params):
    from .image_evidence import resolve_asset_input
    from .packs import Outcome
    from pxr import Sdf

    attribute = ctx.artifact.stage.GetAttributeAtPath(params["asset_attribute"])
    if not attribute or attribute.GetTypeName() != Sdf.ValueTypeNames.Asset:
        return Outcome("FAIL", "Required texture attribute is absent")
    actual, resolution = resolve_asset_input(ctx, attribute)
    if actual is None:
        raise MissingEvidence("Selected texture is empty")
    if params["reference_image"] not in ctx.sources:
        raise ContractError("Reference image must be a declared evidence source")
    reference = ctx.bundle.record(params["reference_image"], missing=True)
    a, pixels_a = linear_pixels(actual, params["actual_space"], params["orientation"])
    b, pixels_b = linear_pixels(
        reference, params["reference_space"], params["orientation"]
    )
    error = (
        max(abs(x - y) for pa, pb in zip(pixels_a, pixels_b) for x, y in zip(pa, pb))
        if a == b
        else None
    )
    return Outcome(
        (
            "PASS"
            if error is not None and error <= params["max_linear_channel_error"]
            else "FAIL"
        ),
        "Compared source images in linear sRGB under explicit orientation and color policies.",
        dict(
            observed_size=list(a),
            expected_size=list(b),
            maximum_linear_channel_error=error,
            max_linear_channel_error=params["max_linear_channel_error"],
            actual_space=params["actual_space"],
            reference_space=params["reference_space"],
            orientation=params["orientation"],
            actual_sha256=sha(actual),
            reference_sha256=sha(reference),
            asset_resolution=resolution,
            coverage="RGB 8-bit source images; ICC conversion uses LittleCMS relative colorimetry. No alpha compositing, HDR, perceptual Delta E, UV or rendered-appearance guarantee.",
        ),
    )


def appearance_pack():
    from .builtin_packs import obj, TEXT
    from .packs import Pack, CheckSpec

    spaces = {"enum": ["srgb", "linear-rgb8", "embedded-icc"]}
    return Pack(
        "textures.appearance",
        "1.0.0",
        "Explicit color and orientation policy for reference comparisons",
        {
            "compare": CheckSpec(
                compare,
                obj(
                    {
                        "asset_attribute": TEXT,
                        "reference_image": TEXT,
                        "actual_space": spaces,
                        "reference_space": spaces,
                        "orientation": {"enum": ["stored", "exif"]},
                        "max_linear_channel_error": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    }
                ),
                "Compare color-managed source pixels",
                "Declared encoding and orientation; all RGB pixels",
                (
                    "Legacy stored-pixel checks retain their original semantics. This is not a render comparison.",
                ),
            ),
        },
        (str(Path(__file__)),),
        ("Pillow", "usd-core"),
    )
