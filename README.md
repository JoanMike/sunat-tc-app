# Tipo de Cambio SUNAT — App de escritorio + CLI

<div align="center">
<img width="852" height="632" alt="python_BHrmoUACDl" src="https://github.com/user-attachments/assets/c8b0c9c7-25b9-4a9e-9c96-dce52c28ba5e" />
</div>

Aplicación en Python (Tkinter) para consultar el **Tipo de Cambio Oficial** publicado por SUNAT.
Tiene **dos modos**:

- **GUI** (default): ventana con tabla, filtros rápidos, copia al portapapeles y exporte a Excel.
- **CLI** (con argumentos): para usar desde la terminal, cron, o pipelines.

Los datos se cachean localmente en SQLite para que las consultas repetidas sean instantáneas.

## Fuente de datos

[apis.net.pe](https://apis.net.pe) — API pública que replica el tipo de cambio oficial de SUNAT.
No requiere clave.

## Estructura del proyecto

```
sunat-tc-app/
├── app.py             # GUI + entry point (despacha a GUI o CLI según argv)
├── cli.py             # Modo línea de comandos (argparse)
├── core/              # Capa de datos (paquete)
│   ├── __init__.py    # Fetching, cache SQLite, persistencia de estado, re-exports
│   ├── errors.py      # FetchError tipado
│   ├── locale.py      # MONTHS_ES / MONTHS_ABBR_ES
│   ├── validators.py  # validate_range / validate_month + constantes MIN_YEAR/MAX_RANGE_DAYS
│   ├── messages.py    # format_fetch_error (mapeador Spanish de FetchError)
│   └── excel.py       # write_xlsx — export Excel compartido (CLI + GUI)
├── tests/             # Suite pytest (84 tests)
├── openspec/          # Workspace SDD (specs + changes)
├── requirements.txt   # requests, openpyxl
├── requirements-dev.txt  # pytest, pytest-mock, requests-mock, ruff
├── pytest.ini
├── run.bat            # Lanzador para Windows
├── LICENSE            # MIT
└── README.md
```

## Requisitos

- Python 3.9+
- Conexión a Internet
- Tkinter (incluido por defecto en Windows; en Linux: `sudo apt install python3-tk`)

## Instalación

```powershell
cd D:\Proyectos\Scripts\sunat-tc-app
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso — GUI

```powershell
# Doble clic en run.bat, o:
python app.py
```

1. Elige modo: **Hoy** / **Rango de días** / **Mes completo**
2. Configura las fechas con los selectores DD/MM/YYYY
3. **O** usa los **filtros rápidos**: Hoy · Ayer · Últ. 7 días · Últ. 30 días · Este mes · Mes pasado
4. Pulsa **Consultar** (o el filtro rápido, que ya consulta automáticamente)
5. Copia al portapapeles (Ctrl+C) o exporta a Excel (Ctrl+E)

**Botones inferiores:**
- Copiar selección · Copiar todo
- **Limpiar caché** — borra la base SQLite local
- Exportar a Excel…

**Indicador de caché** (esquina inferior derecha): muestra cuántas fechas hay cacheadas y el rango. Click para ver detalles.

### ¿Qué se guarda entre sesiones?

Al cerrar la ventana, se persiste en `%APPDATA%\sunat-tc-app\state.json`:
- Posición y tamaño de la ventana
- Modo seleccionado (Hoy / Rango / Mes)
- Fechas del rango o mes/año del mes completo

Al abrir de nuevo, todo se restaura.

## Uso — CLI

```powershell
# Ayuda
python app.py --help

# TC del día actual
python app.py --today

# TC del día anterior
python app.py --yesterday

# Rango de fechas
python app.py --range 2024-01-01:2024-12-31

# Mes completo
python app.py --month 2024-12

# Salida en JSON
python app.py --today --json

# Guardar como CSV
python app.py --range 2024-01-01:2024-12-31 --csv tc_2024.csv

# Guardar como Excel
python app.py --month 2024-12 --xlsx tc_diciembre.xlsx

# Sin caché (forzar API)
python app.py --today --no-cache

# Info del caché
python app.py --cache-info

# Borrar caché
python app.py --clear-cache
```

**Códigos de salida del CLI:**

| Código | Significado |
|---|---|
| 0 | OK (también `--help` y `--version`) |
| 1 | Sin argumentos (ningún flag de consulta) |
| 2 | Argumentos inválidos |
| 3 | No se encontraron datos |
| 4 | Error de API |
| 5 | Error de escritura (CSV/XLSX) |

### Ejemplos de uso avanzado

Pipeline bash para descargar y procesar:

```bash
python app.py --range 2024-01-01:2024-12-31 --json | jq '[.[] | .compra] | add/length'
```

Task Scheduler de Windows para actualizar el Excel cada mañana a las 9am:

```
Programa:    C:\Proyectos\Scripts\sunat-tc-app\run.bat
Argumentos:  --range 2024-01-01:%date:~-4%%date:~3,2%%date:~0,2% --xlsx "D:\Reportes\tc.xlsx"
```

### Codificación de los CSV

Los archivos generados con `--csv` se escriben en **UTF-8 con BOM** (los
primeros tres bytes del archivo son `EF BB BF`). Esto hace que Microsoft
Excel en Windows abra el archivo con la codificación correcta por
defecto, sin pasos manuales de "Datos > Desde texto". La BOM es
**obligatoria** en esta versión; no hay un flag `--csv-bom` para
desactivarla.

La salida con `--json` **no se ve afectada** — sigue siendo UTF-8 puro
apto para `jq`, redirección a `stdin` de otros procesos, o parseo en
cualquier lenguaje.

## Caché local

- **Ubicación:** `%APPDATA%\sunat-tc-app\cache.db` (Windows) / `~/.local/share/sunat-tc-app/cache.db` (Linux/macOS)
- **Qué cachea:** todo (compra, venta, fecha, fuente, timestamp de cuándo se descargó)
- **Cuándo se usa:** para fechas pasadas siempre; para hoy, se re-consulta cada vez (puede cambiar)
- **Cómo limpiarlo:** botón "Limpiar caché" en la GUI, o `python app.py --clear-cache`
- **Velocidad típica:** un mes (~30 días) se consulta a la API en ~1.5s; desde caché en <100ms

## Estado de la ventana

- **Ubicación:** `%APPDATA%\sunat-tc-app\state.json`
- **Qué guarda:** geometría, modo, fechas, mes/año

## Estructura del código

| Archivo | Responsabilidad |
|---|---|
| `core/__init__.py` | Capa de datos: HTTP con reintentos, normalización, cache SQLite, estado JSON. Sin UI. Re-exports públicos. |
| `core/errors.py` | `FetchError` tipado (kinds: network/http_4xx/http_5xx/parse/rate_limit/input). |
| `core/locale.py` | `MONTHS_ES` / `MONTHS_ABBR_ES` para la UI en español. |
| `core/validators.py` | `validate_range` / `validate_month` + constantes `MIN_YEAR` / `MAX_RANGE_DAYS`. |
| `core/messages.py` | `format_fetch_error` — mapeador de `FetchError` a mensajes en español. |
| `core/excel.py` | `write_xlsx` — exportación Excel con formato, compartida por CLI y GUI (openpyxl lazy). |
| `app.py` | GUI: `DateEntry`, `SunatTCApp`, filtros rápidos, exporte Excel. Despacha a CLI si hay argv. |
| `cli.py` | argparse, salida en stdout/JSON/CSV/XLSX, sub-comandos de caché. |

`core/` es la única que toca la red y el disco. Tanto la GUI como el CLI la consumen.

## Notas

- Fines de semana y feriados SUNAT no publica tipo de cambio; la API devuelve la
  última fecha publicada o un set parcial para el mes/rango.
- Para fechas anteriores a 2000 la API no tiene datos.
- La aplicación maneja errores de red reintentando con backoff (3 intentos).
- Los reintentos y errores de red/HTTP se registran en
  `%APPDATA%\sunat-tc-app\app.log` (rotativo, 512 KB × 3 archivos).
