import io
import math
import traceback

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from PIL import Image, ImageOps
import vtracer

app = FastAPI(title="ZGrafic Vectorize API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de segmentación (IA) cargado una sola vez al arrancar el servidor.
_REMBG_SESSION = None


def get_rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session
        # u2netp: ~4.7MB, pensado para correr con poca RAM (planes gratuitos tipo Koyeb).
        # Si tu servidor tiene mas memoria (>=1.5GB), podes cambiar a "u2net" o
        # "isnet-general-use" para mejor calidad de recorte.
        _REMBG_SESSION = new_session("u2netp")
    return _REMBG_SESSION


def ai_remove_background(img: Image.Image) -> Image.Image:
    """Recorta el fondo usando un modelo de segmentación por IA (rembg / u2net)."""
    from rembg import remove
    session = get_rembg_session()
    return remove(img.convert("RGBA"), session=session)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def map_range(v, in_min, in_max, out_min, out_max):
    t = (v - in_min) / (in_max - in_min)
    return out_min + t * (out_max - out_min)


@app.get("/")
def root():
    return {"status": "ok", "service": "zgrafic-vectorize-api"}


@app.post("/vectorize")
async def vectorize(
    file: UploadFile = File(...),
    mode: str = Form("illustration"),      # illustration | photo | sketch | outline
    colors: int = Form(8),
    detail: int = Form(6),                 # 1-10
    noise: int = Form(8),                  # 0-30
    curve: str = Form("sharp"),            # sharp | curvy
    remove_bg: str = Form("false"),
):
    raw = await file.read()

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")

        # Limite de resolucion mas conservador: instancias gratuitas (512MB RAM) se quedan
        # sin memoria con imagenes grandes. Subi esto si tu servidor tiene mas RAM.
        MAX_DIM = 1000
        if max(img.size) > MAX_DIM:
            ratio = MAX_DIM / max(img.size)
            img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)

        remove_bg_flag = remove_bg.lower() == "true"

        color_precision = int(clamp(round(math.log2(max(colors, 2))), 2, 8))
        filter_speckle = int(clamp(noise, 0, 16))
        corner_threshold = int(clamp(map_range(detail, 1, 10, 80, 20), 15, 90))
        path_mode = "polygon" if curve == "sharp" else "spline"

        if mode == "outline":
            cutout = ai_remove_background(img)
            alpha = cutout.split()[-1]
            bw = alpha.point(lambda a: 255 if a > 128 else 0)
            black = Image.new("RGBA", img.size, (10, 10, 10, 255))
            transparent = Image.new("RGBA", img.size, (0, 0, 0, 0))
            work = Image.composite(black, transparent, bw)
            colormode = "binary"
            hierarchical = "stacked"
        else:
            work = img
            if mode == "sketch":
                work = ImageOps.grayscale(work).convert("RGB")
                color_precision = int(clamp(color_precision, 2, 4))

            if remove_bg_flag:
                work = ai_remove_background(work)
                hierarchical = "cutout"
            else:
                work = work.convert("RGBA")
                hierarchical = "stacked"
            colormode = "color"

        buf = io.BytesIO()
        work.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        svg_str = vtracer.convert_raw_image_to_svg(
            png_bytes,
            img_format="png",
            colormode=colormode,
            hierarchical=hierarchical,
            mode=path_mode,
            filter_speckle=filter_speckle,
            color_precision=color_precision,
            corner_threshold=corner_threshold,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
    except Exception as e:
        # Log completo en los logs de Render/HF para poder diagnosticar,
        # y una respuesta de error clara para el frontend (nunca un 200 vacio).
        print("ERROR en /vectorize:", repr(e))
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

    return Response(content=svg_str, media_type="image/svg+xml")
