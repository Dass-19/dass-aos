# Contribuir a DASS-AOS

Principios, estructura y comandos: [README.md](README.md). Diseño interno: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Entorno

```bash
git clone https://github.com/Dass-19/dass-aos.git && cd dass-aos
python -m venv .venv            # activar: source .venv/bin/activate | .venv\Scripts\Activate.ps1
pip install -e ".[scan,rag,tui]" ruff
```

## Reglas del código

- El núcleo usa solo la biblioteca estándar y soporta **Python 3.8–3.12**. Las dependencias van como extra opcional (`[scan]`, `[rag]`, `[tui]`) con import perezoso.
- Los tests que usan un extra se saltan si no está instalado (`unittest.skipUnless`); CI instala solo `pip install -e .`.
- Tests en `tests/test_<modulo>.py`, como `unittest.TestCase`: CI usa `unittest discover`, que no ejecuta funciones sueltas.
- Cambio transversal → ADR en `.aos/decisions/` (plantilla `ADR-001-plantilla.md`). Trampa encontrada → `.aos/knowledge/gotchas/`.
- `CLAUDE.md`, `AGENTS.md` y `GEMINI.md` se generan: cambia la plantilla en `dass_aos/sync.py` y ejecuta `aos sync`.

## Ramas y commits

- Rama desde `main`: `feat/`, `fix/`, `refactor/`, `docs/`.
- [Conventional Commits](https://www.conventionalcommits.org/) (`feat(tui): …`, `fix(compat): …`).
- `git add <archivos>` explícito; nunca `git add -A` / `git add .`.

## Antes del PR

```bash
ruff check .
python -m unittest discover -b -s tests -p "test_*.py"
aos doctor          # 0 errores
```

## Release

1. Subir la versión en `pyproject.toml` (`version`) y `dass_aos/constants.py` (`VERSION`).
2. Commit, tag y push:
   ```bash
   git commit -m "chore(release): vX.Y.Z" pyproject.toml dass_aos/constants.py
   git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin main --tags
   ```
3. El tag `v*` dispara `.github/workflows/release.yml`: tests, sdist + wheel y GitHub Release.
