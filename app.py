import io
import math
import traceback

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from PIL import Image, ImageFilter
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
        # u2netp: liviano, pensado para correr con poca RAM (planes gratuitos).
        # Si tu servidor tiene mas memoria (>=1.5GB), podes cambiar a "u2net" o
        # "isnet-general-use" para mejor calidad de recorte.
        _REMBG_SESSION = new_session("u2netp")
    return _REMBG_SESSION


def ai_remove_background(img: Image.Image) -> Image.Image:
    """Recorta el fondo usando un modelo de segmentación por IA (rembg)."""
    from rembg import remove
    session = get_rembg_session()
    return remove(img.convert("RGBA"), session=session)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def color_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def analyze_image(img: Image.Image) -> dict:
    """
    La IA decide por si sola como vectorizar la imagen: analiza cuantos colores
    tiene, que tan detallada/texturada es, y si el fondo parece uniforme
    (candidato a recortar con IA) o no. Sin controles manuales del usuario.
    """
    proxy = img.convert("RGB")
    proxy.thumbnail((160, 160))

    # Cantidad de colores dominantes -> ¿ilustración simple o foto compleja?
    colors = proxy.getcolors(maxcolors=256 * 256 * 256)
    unique_colors = len(colors) if colors else 99999

    # Densidad de bordes -> ¿imagen texturada/detallada o de zonas planas?
    edges = proxy.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_pixels = list(edges.getdata())
    edge_mean = sum(edge_pixels) / len(edge_pixels)

    photo_like = unique_colors > 3500 or edge_mean > 16

    # ¿El fondo parece uniforme? Comparamos las 4 esquinas de la imagen original.
    w, h = img.size
    rgb = img.convert("RGB")
    pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    corner_colors = [rgb.getpixel(p) for p in pts]
    max_corner_dist = max(
        color_distance(corner_colors[i], corner_colors[j])
        for i in range(4) for j in range(i + 1, 4)
    )
    flat_background = max_corner_dist < 45

    if photo_like:
        color_precision = 7
        corner_threshold = 58
        filter_speckle = 4
        path_mode = "spline"
    else:
        color_precision = 5
        corner_threshold = 38
        filter_speckle = 8
        path_mode = "polygon" if edge_mean < 9 else "spline"

    return {
        "color_precision": color_precision,
        "corner_threshold": corner_threshold,
        "filter_speckle": filter_speckle,
        "path_mode": path_mode,
        "remove_bg": flat_background,
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "zgrafic-vectorize-api"}


@app.post("/vectorize")
async def vectorize(file: UploadFile = File(...)):
    raw = await file.read()

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")

        # Limite de resolucion conservador: instancias gratuitas (512MB RAM) se quedan
        # sin memoria con imagenes grandes. Subi esto si tu servidor tiene mas RAM.
        MAX_DIM = 1000
        if max(img.size) > MAX_DIM:
            ratio = MAX_DIM / max(img.size)
            img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.LANCZOS)

        settings = analyze_image(img)

        if settings["remove_bg"]:
            work = ai_remove_background(img)
            hierarchical = "cutout"
        else:
            work = img.convert("RGBA")
            hierarchical = "stacked"

        buf = io.BytesIO()
        work.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        svg_str = vtracer.convert_raw_image_to_svg(
            png_bytes,
            img_format="png",
            colormode="color",
            hierarchical=hierarchical,
            mode=settings["path_mode"],
            filter_speckle=settings["filter_speckle"],
            color_precision=settings["color_precision"],
            corner_threshold=settings["corner_threshold"],
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
