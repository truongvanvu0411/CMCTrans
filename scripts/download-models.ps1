param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$modelsRoot = Join-Path $projectRoot "models"

New-Item -ItemType Directory -Force -Path $modelsRoot | Out-Null

$script = @"
from pathlib import Path
from huggingface_hub import snapshot_download

models_root = Path(r"$modelsRoot")
targets = [
    ("quickmt/quickmt-ja-en", "quickmt-ja-en"),
    ("quickmt/quickmt-en-vi", "quickmt-en-vi"),
    ("quickmt/quickmt-vi-en", "quickmt-vi-en"),
    ("quickmt/quickmt-en-ja", "quickmt-en-ja"),
]

for repo_id, local_name in targets:
    target_dir = models_root / local_name
    snapshot_download(repo_id=repo_id, local_dir=str(target_dir))
    print(f"downloaded {repo_id} -> {target_dir}")
"@

& $PythonExe -m pip install huggingface_hub
$script | & $PythonExe -
