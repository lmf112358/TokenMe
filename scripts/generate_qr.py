"""Development only: pip install -r requirements-dev.txt, then run this file."""
import json
from pathlib import Path
from qrcodegen import QrCode

URL = "https://github.com/lmf112358/TokenMe"
qr = QrCode.encode_text(URL, QrCode.Ecc.QUARTILE)
data = {"url": URL, "matrix": ["".join("1" if qr.get_module(x, y) else "0" for x in range(qr.get_size())) for y in range(qr.get_size())]}
target = Path(__file__).resolve().parents[1] / "token_footprint/share-qr.json"
target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"Generated {qr.get_size()} × {qr.get_size()} modules; fixed public URL only")
