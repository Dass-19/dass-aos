"""Client generator module from OpenAPI contracts."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .constants import configure_utf8_output


def resolve_npx() -> Optional[str]:
    """Resolve npx command cross-platform (handling Windows .cmd)."""
    return shutil.which("npx") or shutil.which("npx.cmd")


def generate_client(
    contract_path: Path,
    output_dir: Path,
    generator: str = "generic",
    language: Optional[str] = None,
) -> int:
    """Generate typed client from OpenAPI contract."""
    configure_utf8_output()
    contract_path = contract_path.resolve()
    output_dir = output_dir.resolve()

    if not contract_path.exists():
        print(f"[generate-client] ERROR: Contract file not found: {contract_path}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[generate-client] Generating client from '{contract_path.name}' into '{output_dir}'")

    if generator == "openapi-typescript":
        npx_bin = resolve_npx()
        if npx_bin:
            print("[generate-client] Using openapi-typescript...")
            schema_file = output_dir / "schema.d.ts"
            client_file = output_dir / "client.ts"
            cmd = [npx_bin, "--yes", "openapi-typescript", str(contract_path), "-o", str(schema_file)]
            try:
                proc = subprocess.run(cmd, check=False)
                if proc.returncode == 0:
                    if not client_file.exists():
                        client_file.write_text(
                            "// Auto-generated client stub using openapi-typescript\n"
                            "import type { paths } from './schema';\n\n"
                            "// Implement your type-safe fetch or axios wrapper here\n",
                            encoding="utf-8",
                        )
                    print(f"[generate-client] SUCCESS: Generated types at {schema_file}")
                    return 0
                else:
                    print(f"[generate-client] openapi-typescript exited with code {proc.returncode}")
            except Exception as exc:
                print(f"[generate-client] Execution error: {exc}")
        else:
            print("[generate-client] npx not found in PATH. Falling back to generic generator.")
            generator = "generic"

    elif generator == "openapi-generator":
        gen_bin = shutil.which("openapi-generator-cli") or shutil.which("openapi-generator")
        if gen_bin:
            lang = language or "typescript-fetch"
            print(f"[generate-client] Using openapi-generator ({lang})...")
            cmd = [gen_bin, "generate", "-i", str(contract_path), "-g", lang, "-o", str(output_dir)]
            try:
                proc = subprocess.run(cmd, check=False)
                return proc.returncode
            except Exception as exc:
                print(f"[generate-client] Execution error: {exc}")
        else:
            print("[generate-client] openapi-generator-cli not found in PATH. Falling back to generic generator.")
            generator = "generic"

    elif generator == "datamodel-codegen":
        datamodel_bin = shutil.which("datamodel-codegen")
        if datamodel_bin:
            models_file = output_dir / "models.py"
            cmd = [datamodel_bin, "--input", str(contract_path), "--output", str(models_file)]
            try:
                proc = subprocess.run(cmd, check=False)
                return proc.returncode
            except Exception as exc:
                print(f"[generate-client] Execution error: {exc}")
        else:
            print("[generate-client] datamodel-codegen not found. Falling back to generic.")
            generator = "generic"

    # Modo genérico (fallback)
    readme_path = output_dir / "README.md"
    content = (
        f"# Cliente Generado (Marcador de Posición)\n\n"
        f"- **Contrato de Origen**: `{contract_path}`\n"
        f"- **Directorio de Destino**: `{output_dir}`\n\n"
        "Este cliente fue generado en modo genérico porque aún no se ha ejecutado un generador específico.\n"
        "Para generar clientes tipados para tu stack concreto, instala la herramienta deseada y ejecuta:\n\n"
        "```bash\n"
        "# TypeScript:\n"
        f"python aos.py generate-client --contract \"{contract_path}\" --output \"{output_dir}\" --generator openapi-typescript\n\n"
        "# Python (modelos Pydantic):\n"
        f"python aos.py generate-client --contract \"{contract_path}\" --output \"{output_dir}\" --generator datamodel-codegen\n\n"
        "# Java / Go / C# / etc.:\n"
        f"python aos.py generate-client --contract \"{contract_path}\" --output \"{output_dir}\" --generator openapi-generator --language go\n"
        "```\n"
    )
    readme_path.write_text(content, encoding="utf-8")
    print(f"[generate-client] ÉXITO (modo genérico): Instrucciones guardadas en {readme_path}")
    return 0
