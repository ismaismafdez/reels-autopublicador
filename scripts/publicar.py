#!/usr/bin/env python3
"""Publica el siguiente Reel de cola/ en Instagram (Instagram Login API + Cloudinary)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
ESTADO_F = RAIZ / "estado.json"
COLA, PUBLICADO, FALLIDO = RAIZ / "cola", RAIZ / "publicado", RAIZ / "fallido"

IG_USER_ID = os.environ["IG_USER_ID"]
IG_TOKEN = os.environ["IG_ACCESS_TOKEN"]
_u = urlparse(os.environ["CLOUDINARY_URL"].replace("CLOUDINARY_URL=", "").strip())
CLD_KEY, CLD_SECRET, CLD_CLOUD = _u.username, _u.password, _u.hostname
GRAPH = f"https://graph.instagram.com/{CFG['graph_version']}"
FORZAR = os.environ.get("FORZAR", "").lower() in ("true", "1")


def log(msg):
    print(msg, flush=True)


def comprobar(r, ctx):
    if not r.ok:
        raise RuntimeError(f"{ctx}: HTTP {r.status_code} {r.text[:500]}")
    return r


# ---------- estado ----------
def cargar_estado():
    est = json.loads(ESTADO_F.read_text(encoding="utf-8")) if ESTADO_F.exists() else {}
    est.setdefault("ultimo_slot", None)
    est.setdefault("intentos", {})
    est.setdefault("avisada_cola_vacia", False)
    return est


def guardar_estado(est):
    ESTADO_F.write_text(json.dumps(est, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- franjas y cola ----------
def franja_actual(ahora):
    for hhmm in CFG["franjas"]:
        h, m = map(int, hhmm.split(":"))
        inicio = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
        if timedelta(0) <= ahora - inicio < timedelta(minutes=CFG["ventana_min"]):
            return inicio.strftime("%Y-%m-%dT%H:%M")
    return None


def buscar_portada(d):
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = d / f"portada.{ext}"
        if p.exists():
            return p
    return None


def siguiente_post():
    carpetas = sorted(
        d for d in COLA.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))
    )
    for d in carpetas:
        if (d / "video.mp4").exists() and buscar_portada(d) and (d / "descripcion.txt").exists():
            return d
        log(f"::warning::{d.name} incompleta (falta video.mp4, portada.* o descripcion.txt); la salto")
    return None


# ---------- vídeo ----------
def asegurar_compatible(video: Path) -> Path:
    """Instagram exige H.264 + AAC + yuv420p. Si no cumple, transcodifica."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout
    streams = json.loads(out)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    ok = (
        v["codec_name"] == "h264"
        and v.get("pix_fmt") == "yuv420p"
        and (a is None or a["codec_name"] == "aac")
    )
    if ok:
        return video
    log("Vídeo no compatible: transcodificando a H.264/AAC...")
    salida = video.with_name("video_ig.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-preset", "fast", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(salida)],
        check=True,
    )
    return salida


# ---------- Cloudinary ----------
def _firmar(params):
    base = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.sha1((base + CLD_SECRET).encode()).hexdigest()


def cld_subir(ruta: Path, tipo: str, public_id: str) -> dict:
    params = {"public_id": public_id, "timestamp": int(time.time())}
    datos = {**params, "api_key": CLD_KEY, "signature": _firmar(params)}
    with open(ruta, "rb") as f:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{CLD_CLOUD}/{tipo}/upload",
            data=datos, files={"file": f}, timeout=900,
        )
    return comprobar(r, f"Cloudinary subir {tipo}").json()


def cld_borrar(tipo: str, public_id: str):
    params = {"public_id": public_id, "timestamp": int(time.time())}
    datos = {**params, "api_key": CLD_KEY, "signature": _firmar(params)}
    try:
        requests.post(
            f"https://api.cloudinary.com/v1_1/{CLD_CLOUD}/{tipo}/destroy", data=datos, timeout=60
        )
    except Exception as e:  # limpieza: nunca debe romper la publicación
        log(f"::warning::No pude borrar {public_id} de Cloudinary: {e}")


# ---------- Instagram ----------
def ig(metodo, ruta, **params):
    params["access_token"] = IG_TOKEN
    kw = {"data": params} if metodo == "POST" else {"params": params}
    r = requests.request(metodo, f"{GRAPH}/{ruta}", timeout=120, **kw)
    return comprobar(r, f"Instagram {metodo} {ruta}").json()


def publicar_reel(video_url, cover_url, caption):
    contenedor = ig(
        "POST", f"{IG_USER_ID}/media",
        media_type="REELS", video_url=video_url, cover_url=cover_url,
        caption=caption, share_to_feed="true",
    )["id"]
    log(f"Contenedor creado: {contenedor}")
    limite = time.time() + 20 * 60
    while time.time() < limite:
        s = ig("GET", contenedor, fields="status_code,status")
        codigo = s.get("status_code")
        log(f"Estado del procesado: {codigo}")
        if codigo == "FINISHED":
            break
        if codigo in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram rechazó el vídeo: {s}")
        time.sleep(15)
    else:
        raise TimeoutError("Instagram no terminó de procesar el vídeo en 20 min")
    return ig("POST", f"{IG_USER_ID}/media_publish", creation_id=contenedor)["id"]


# ---------- principal ----------
def main() -> int:
    estado = cargar_estado()
    ahora = datetime.now(ZoneInfo(CFG["zona_horaria"]))

    if FORZAR:
        franja = None
        log("Modo forzado: ignoro franja horaria.")
    else:
        franja = franja_actual(ahora)
        if not franja:
            log(f"Fuera de franja ({ahora:%H:%M} {CFG['zona_horaria']}). Nada que hacer.")
            return 0
        if estado["ultimo_slot"] == franja:
            log(f"Franja {franja} ya publicada. Nada que hacer.")
            return 0

    post = siguiente_post()
    if not post:
        if not estado["avisada_cola_vacia"]:
            estado["avisada_cola_vacia"] = True
            guardar_estado(estado)
            log("::error::La cola está vacía. Sube nuevas carpetas a cola/.")
            return 1  # el fallo dispara el email de aviso (solo una vez)
        log("Cola vacía (ya avisado).")
        return 0
    estado["avisada_cola_vacia"] = False

    nombre = post.name
    n = estado["intentos"].get(nombre, 0) + 1
    estado["intentos"][nombre] = n
    guardar_estado(estado)
    log(f"Publicando '{nombre}' (intento {n}/{CFG['max_intentos']})")

    sello = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    pid_video, pid_portada = f"reels/{sello}_{nombre}_video", f"reels/{sello}_{nombre}_portada"
    subidos = []
    try:
        caption = (post / "descripcion.txt").read_text(encoding="utf-8").strip()[:2200]
        video = asegurar_compatible(post / "video.mp4")

        rv = cld_subir(video, "video", pid_video)
        subidos.append(("video", pid_video))
        cld_subir(buscar_portada(post), "image", pid_portada)
        subidos.append(("image", pid_portada))
        cover_url = (
            f"https://res.cloudinary.com/{CLD_CLOUD}/image/upload/"
            f"c_fill,w_1080,h_1920,f_jpg,q_90/{pid_portada}.jpg"
        )

        media_id = publicar_reel(rv["secure_url"], cover_url, caption)
        log(f"Publicado. media_id={media_id}")
    except Exception as e:
        log(f"::error::Fallo publicando '{nombre}': {e}")
        if n >= CFG["max_intentos"]:
            FALLIDO.mkdir(exist_ok=True)
            shutil.move(str(post), str(FALLIDO / nombre))
            estado["intentos"].pop(nombre, None)
            log(f"::error::'{nombre}' movida a fallido/ tras {n} intentos.")
        guardar_estado(estado)
        for tipo, pid in subidos:
            cld_borrar(tipo, pid)
        return 1

    # Éxito: primero el estado (evita duplicados), luego la limpieza.
    if franja:
        estado["ultimo_slot"] = franja
    estado["intentos"].pop(nombre, None)
    for f in ("video.mp4", "video_ig.mp4"):
        (post / f).unlink(missing_ok=True)
    PUBLICADO.mkdir(exist_ok=True)
    shutil.move(str(post), str(PUBLICADO / f"{ahora:%Y-%m-%d_%H%M}_{nombre}"))
    guardar_estado(estado)
    for tipo, pid in subidos:
        cld_borrar(tipo, pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
