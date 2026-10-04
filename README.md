# Autopublicador de Reels

Subes una carpeta a `cola/` y el repo publica un Reel (vídeo + portada + descripción) 2 veces al día.

## Uso diario

Crea una carpeta en `cola/` con tres archivos exactos:

```
cola/001/
  video.mp4
  portada.jpg        (o .png / .webp)
  descripcion.txt
```

Se publican por orden alfabético: usa `001`, `002`, `003`...
Franjas y demás ajustes: `config.json` (hora de Madrid, formato `HH:MM`).

- Si la cola se vacía, te llega un email de aviso (una vez).
- Si un post falla 3 veces, pasa a `fallido/` y el siguiente sigue su curso.
- Los publicados quedan en `publicado/` (sin el vídeo, para no engordar el repo).

## Configuración inicial (una vez, ~30 min)

### 1. Instagram
Cuenta en modo **Profesional** (Creator o Business): Ajustes → Tipo de cuenta y herramientas.

### 2. App de Meta
1. https://developers.facebook.com → Mis apps → Crear app → caso de uso **Administrar mensajes y contenido en Instagram** (tipo Business).
2. En la app: **Instagram → API setup with Instagram login**.
3. Añade tu cuenta de Instagram (si pide rol de *Instagram Tester*: App roles → Roles → añade tu usuario y acepta la invitación desde la app de Instagram en Ajustes → Permisos del sitio web → Invitaciones de probador).
4. Marca los permisos `instagram_business_basic` e `instagram_business_content_publish`.
5. Pulsa **Generate token** para tu cuenta. Copia:
   - el **token** → será `IG_ACCESS_TOKEN`
   - el **ID de la cuenta de Instagram** → será `IG_USER_ID`

No hace falta pasar la revisión de Meta: para tu propia cuenta basta el modo desarrollo.

### 3. Cloudinary (gratis)
Regístrate en cloudinary.com → Dashboard → *API Keys* → copia la **API environment variable**
(`cloudinary://clave:secreto@nombre`). Será `CLOUDINARY_URL`.

### 4. GitHub
1. Crea un repo **privado** y sube todo el contenido de esta carpeta.
   Si `.github/` no se sube (carpeta oculta), créalo desde la web: *Add file → Create new file* con el nombre
   `.github/workflows/publicar.yml` y pega el contenido; repite con `renovar-token.yml`.
2. Crea un token personal: Settings (tu perfil) → Developer settings → Personal access tokens → **Fine-grained** →
   solo este repo → permiso **Secrets: Read and write**. Será `GH_PAT`.
3. Repo → Settings → Secrets and variables → Actions → New repository secret. Crea estos 4:
   `IG_USER_ID`, `IG_ACCESS_TOKEN`, `CLOUDINARY_URL`, `GH_PAT`.

### 5. Prueba
Pon un post de prueba en `cola/001/` → pestaña **Actions** → *Publicar Reel* → **Run workflow** con `forzar` activado.
Mira el log: debe terminar en "Publicado". A partir de ahí, todo va solo.

## Límites a tener en cuenta
- Vídeo: máx. 100 MB en Cloudinary gratis. Subida desde el navegador de GitHub: 25 MB por archivo (más grande, con git o GitHub Desktop).
- Si el vídeo no es H.264/AAC (p. ej. HEVC del iPhone), el script lo convierte solo.
- La portada se recorta a 9:16 (1080x1920) automáticamente.
- El historial de git conserva los vídeos aunque se borren del árbol: con muchos vídeos grandes el repo crecerá. Si supera ~1-2 GB, hay que limpiar el historial.
- Instagram limita las publicaciones por API a 100 por día; aquí usas 2.
- Si cambian versiones de la Graph API, ajusta `graph_version` en `config.json`.
