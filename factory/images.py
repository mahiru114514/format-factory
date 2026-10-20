from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

from .common import ConversionResult, Options, normalized_format, publish


def register_codecs() -> None:
    import pillow_heif
    pillow_heif.register_heif_opener()


def convert_image(source: Path, target: str, output: Path, options: Options) -> ConversionResult:
    register_codecs()
    target = normalized_format(target)
    formats = {'jpg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP', 'bmp': 'BMP', 'tiff': 'TIFF', 'heic': 'HEIF'}
    if target not in formats:
        raise ValueError('不支持的图片输出格式。')
    if not 1 <= options.quality <= 100 or options.max_size < 0:
        raise ValueError('图片质量应为 1–100，尺寸不能为负数。')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    warnings = []
    with Image.open(source) as original:
        if getattr(original, 'n_frames', 1) > 1:
            warnings.append('多帧图片仅转换第一帧。')
        image = ImageOps.exif_transpose(original)
        if options.max_size:
            image.thumbnail((options.max_size, options.max_size), Image.Resampling.LANCZOS)
        metadata = {}
        if options.keep_metadata:
            if image.getexif():
                metadata['exif'] = image.getexif().tobytes()
            if image.info.get('icc_profile'):
                metadata['icc_profile'] = image.info['icc_profile']
        if target in ('jpg', 'bmp', 'heic'):
            if image.mode in ('RGBA', 'LA', 'P') and ('A' in image.getbands() or 'transparency' in image.info):
                rgba = image.convert('RGBA')
                canvas = Image.new('RGB', rgba.size, 'white')
                canvas.paste(rgba, mask=rgba.getchannel('A'))
                image = canvas
                warnings.append('目标格式不保留透明背景，已填充白色。')
            else:
                image = image.convert('RGB')
        if target in ('jpg', 'webp', 'heic'):
            metadata['quality'] = options.quality
        if target == 'jpg':
            metadata['optimize'] = True
        if not options.keep_metadata:
            # Some encoders inherit EXIF from image.info even without save kwargs.
            # Rebuild pixel data so no private metadata can be inherited implicitly.
            if image.mode == 'P':
                image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
            clean = Image.new(image.mode, image.size)
            clean.paste(image)
            image = clean
        with TemporaryDirectory(prefix='.factory-', dir=output) as temp:
            staged = Path(temp) / ('image.' + target)
            image.save(staged, format=formats[target], **metadata)
            destination = publish(staged, output / f'{Path(source).stem}.{target}')
    return ConversionResult([destination], warnings)
