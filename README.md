# NFL Predictor

Sistema autónomo de pronósticos de NFL: ingesta datos históricos y del
calendario actual (gratis, sin API key), mantiene un rating Elo por
equipo que se actualiza semana a semana con los resultados reales, y
genera cada lunes el pronóstico de la próxima semana (ganador, marcador
proyectado, total de puntos y una sugerencia de parlay).

## Por qué está armado así

Este proyecto corre en tres capas separadas, cada una con un rol
específico y una razón técnica detrás:

1. **GitHub Actions** (`.github/workflows/weekly_update.yml`) — hace el
   trabajo pesado: descarga datos, actualiza el modelo, escribe en
   BigQuery, y publica el resumen. Corre cada lunes 22:00 hora CDMX
   automáticamente, gratis (el free tier de Actions da 2,000
   minutos/mes en repos privados; esto usa ~2 minutos/semana).
2. **BigQuery** — la base de datos. Se eligió sobre Cloud SQL porque
   Cloud SQL **no** es gratis de forma permanente en GCP (solo un trial
   de $300 USD/90 días); BigQuery sí tiene una capa "Always Free" real
   (10GB de almacenamiento + 1TB de consultas al mes), y este proyecto
   nunca se acerca a esos límites.
3. **Claude** (sesión programada los lunes) — lee el resumen ya
   publicado en `docs/latest.json` de este repo y te lo manda como
   mensaje + reporte. Claude **no habla directamente con BigQuery**:
   el sandbox donde corre Claude tiene una lista blanca de red que no
   incluye `googleapis.com`, así que la única forma confiable de que
   Claude "vea" el resultado semanal es que quede publicado en un lugar
   que sí pueda leer (GitHub sí está permitido).

## Qué tan bueno es el modelo (backtest real)

Corrí un backtest walk-forward (prediciendo cada semana usando solo
información disponible ANTES de esa semana, sin fuga de datos) sobre las
temporadas 2022-2025, 1,139 partidos:

- **Precisión del modelo (Elo + estadísticas): 63.6%** acertando al
  ganador.
- Referencia: elegir siempre al favorito según la casa de apuestas
  (moneyline) acierta 67.5% en el mismo periodo.

Es decir: el modelo es razonable pero todavía no le gana a Vegas —  algo
esperable de un Elo simple sin datos de lesiones, clima o líneas de
apuestas reales. El plan de mejora (ver abajo) es justo cerrar esa
brecha con más señales.

Puedes reproducir el backtest tú mismo:

```bash
pip install -r requirements.txt
python scripts/backtest.py
```

## Uso local (sin GCP, para probar hoy mismo)

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m nfl_predictor.cli run-weekly --backend sqlite
cat docs/latest.md
```

Esto crea `data/nfl_predictor.db` (SQLite) y `docs/latest.md` /
`docs/latest.json` con el pronóstico de la próxima semana disponible.

## Puesta en marcha en GCP + GitHub Actions (para que corra solo cada lunes)

### 1. Crear el proyecto de GCP

1. Entra a https://console.cloud.google.com/projectcreate
2. Nombra el proyecto (p.ej. `nfl-predictor`) y créalo. Anota el
   **Project ID** (no el nombre bonito, el ID real, algo como
   `nfl-predictor-123456`).
3. GCP te va a pedir vincular una cuenta de facturación para poder usar
   BigQuery, aunque te quedes dentro del free tier. Esto es normal y no
   te cobra nada mientras no superes la cuota gratuita. Para tener un
   seguro extra:
   - Ve a **Facturación → Presupuestos y alertas** y crea un
     presupuesto de, por ejemplo, $1 USD con alertas al 50/90/100%.
     Así te enteras por correo si algo se saliera de control, aunque en
     la práctica este proyecto nunca debería generar cargos.

### 2. Habilitar la API de BigQuery

```
https://console.cloud.google.com/apis/library/bigquery.googleapis.com?project=TU_PROJECT_ID
```
Click en "Habilitar" (normalmente ya viene habilitada por default).

### 3. Crear la service account

1. Ve a **IAM y administración → Cuentas de servicio → Crear cuenta de
   servicio**.
2. Nombre sugerido: `nfl-predictor-writer`.
3. Rol a asignar: **BigQuery Data Editor** + **BigQuery Job User**
   (con esos dos alcanza; no le des rol de "Owner" ni "Editor" del
   proyecto completo).
4. Termina de crearla, entra a la cuenta de servicio creada, pestaña
   **Claves → Agregar clave → Crear clave nueva → JSON**. Se descarga
   un archivo `.json` — este es tu único secreto sensible en todo el
   proyecto, no lo subas al repo.

### 4. Crear el dataset y las tablas en BigQuery (una sola vez)

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/ruta/al/archivo-descargado.json
pip install -r requirements.txt
python scripts/setup_bigquery.py --project TU_PROJECT_ID --dataset nfl_predictor
```

### 5. Subir este proyecto a un repo de GitHub (privado)

```bash
cd nfl-predictor
git init
git add .
git commit -m "Setup inicial: NFL Predictor"
gh repo create nfl-predictor --private --source=. --push
# o, sin gh CLI: crea el repo vacío en github.com y luego
# git remote add origin git@github.com:TU_USUARIO/nfl-predictor.git && git push -u origin main
```

### 6. Configurar los secretos del repo (para que Actions se autentique)

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**

- `GCP_PROJECT_ID` → tu Project ID de GCP.
- `GCP_SERVICE_ACCOUNT_KEY` → pega el CONTENIDO completo del archivo
  JSON de la service account (todo el JSON, tal cual).

### 7. Activar GitHub Pages para `docs/` (para que el resumen sea público y Claude pueda leerlo)

**Settings → Pages → Source: Deploy from a branch → Branch: `main` /
`docs`**. Esto publica `docs/latest.json` en una URL pública tipo
`https://TU_USUARIO.github.io/nfl-predictor/latest.json`. No hay datos
sensibles ahí (solo pronósticos, sin tus credenciales ni nada personal),
así que es seguro que sea pública.

### 8. Probar el workflow manualmente

**Actions → Actualización semanal NFL Predictor → Run workflow**. Si
todo salió bien, deberías ver un commit nuevo en `docs/` con el
pronóstico de la próxima semana.

A partir de aquí, corre solo cada lunes a las 22:00 hora CDMX. No
tienes que hacer nada más.

## Roadmap / cómo mejorar la precisión

- **Líneas de apuestas reales (odds API)**: con una API key de un
  proveedor como The Odds API (tiene capa gratuita, ~500 requests/mes)
  se puede comparar la probabilidad del modelo contra la probabilidad
  implícita del mercado, calcular *expected value* real de cada pick, y
  armar parlays con el pago real. Es el siguiente paso más impactante.
- **Datos de jugadores/lesiones**: `nfl_data_py` también expone
  `import_injuries()` y `import_weekly_data()` (estadísticas por
  jugador) — se pueden usar para ajustar el rating de un equipo cuando
  su quarterback titular está lesionado, algo que el Elo puro no ve.
- **Contra el spread (ATS)**: hoy el modelo predice ganador directo y
  total de puntos. Para predecir si el favorito cubre el spread hace
  falta la línea de apuestas real (ver punto de odds API arriba).

## Aviso

Este sistema genera pronósticos analíticos basados en datos históricos
y no garantiza resultados. Ninguna apuesta deportiva está libre de
riesgo. Apuesta solo dinero que puedas permitirte perder.
