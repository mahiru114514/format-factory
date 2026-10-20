# RapidLaTeXOCR compatibility copy

Source: RapidAI/RapidLaTeXOCR, PyPI wheel `rapid_latex_ocr-0.0.9-py3-none-any.whl`.
SHA-256: `241c51047618c2bf90d94165499f8afcb75b0057dd5623337a833fefa4ea8fb4`.
License: see `RapidLaTeXOCR-LICENSE` (the wheel's original license).

The upstream package declares Python <3.13 and NumPy <2.0. This application uses a local source copy with two explicit compatibility/performance changes: extract the single argmax item using `.item()` for NumPy 2, and limit ONNX intra-op threads to four. Real printed-formula inference is covered by `tests/test_recognition.py`. No files in an installed third-party package are patched.

Runtime receives explicit local model paths. It never uses the upstream automatic downloader. The setup script downloads model assets over HTTPS with timeout, HTTP status checking and a SHA-256 manifest for subsequent verification. Model assets come from the upstream v0.0.0 release.
