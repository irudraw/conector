---
title: ZGrafic Vectorize API
emoji: 🧬
colorFrom: purple
colorTo: orange
sdk: docker
app_port: 7860
pinned: false
---

# ZGrafic Vectorize API

Backend de IA para el vectorizador ZG·vector.

- **Recorte de fondo**: modelo de segmentación por IA (`rembg` / u2net), corre en el servidor.
- **Vectorizado**: `vtracer` (Rust), genera SVG de alta calidad a partir de la imagen ya procesada.

## Cómo desplegar

### Opción A — Koyeb (gratis, normalmente sin tarjeta)

Hugging Face empezó a pedir plan pago para el SDK Docker en cuentas nuevas. Koyeb es una alternativa con plan gratis permanente (512 MB RAM, 0.1 vCPU) que generalmente no pide tarjeta.

1. Creá una cuenta en https://app.koyeb.com
2. **Create Service** → **Docker** (podés subir estos archivos a un repo de GitHub y conectarlo, o buildear la imagen vos mismo y subirla a un registro).
3. Si te pide el puerto del contenedor, poné **7860** (coincide con el `Dockerfile`).
4. Elegí la instancia **Free**.
5. Esperá el deploy (~3-5 min la primera vez) y copiá la URL pública (algo como `https://tu-app.koyeb.app`).
6. Pegá esa URL en la constante `SERVER_URL` del `index.html` del frontend.

Nota: con 512 MB de RAM y 0.1 vCPU cada request puede tardar bastante (varios segundos a más de un minuto en imágenes grandes). Por eso este `app.py` ya usa el modelo liviano `u2netp` y limita la resolución de entrada a 1000px — si más adelante movés esto a un servidor con más recursos, podés subir esos valores para mejor calidad.

### Opción B — Hugging Face (si tu cuenta todavía tiene Docker gratis)

1. Creá un nuevo Space en https://huggingface.co/new-space
2. SDK: **Docker**
3. Subí estos 4 archivos (`app.py`, `requirements.txt`, `Dockerfile`, `README.md`) a la raíz del repositorio del Space.
4. Esperá a que build termine (~3-5 min la primera vez, descarga el modelo de IA en el primer request).
5. Copiá la URL pública del Space (algo como `https://TU-USUARIO-zgrafic-vectorize-api.hf.space`) y pegala en la constante `SERVER_URL` del archivo `index.html` del frontend.

### Opción C — Google Cloud Run

Pide tarjeta solo para verificar la cuenta (no cobra dentro del tier gratuito para este uso). Tier gratuito permanente, sin sleep tan agresivo como los anteriores. Avisame si querés que te adapte el Dockerfile para Cloud Run (son 1-2 cambios chicos).

## Endpoint

`POST /vectorize` — `multipart/form-data`

| campo | tipo | valores |
|---|---|---|
| `file` | archivo | imagen jpg/png/webp |
| `mode` | texto | `illustration` \| `photo` \| `sketch` \| `outline` |
| `colors` | número | 2–64 |
| `detail` | número | 1–10 |
| `noise` | número | 0–30 |
| `curve` | texto | `sharp` \| `curvy` |
| `remove_bg` | texto | `true` \| `false` |

Devuelve el SVG como texto plano (`image/svg+xml`).

## Nota sobre el plan gratuito

Los Spaces gratuitos "duermen" tras un rato de inactividad. El primer request tras dormir tarda más (arranca el contenedor + descarga el modelo si es la primera vez). Los siguientes requests son rápidos.
