#!/usr/bin/env bash
# Cria o repositório local e faz o primeiro commit usando a identidade Git do próprio usuário.
set -euo pipefail
if ! git config --global user.name >/dev/null || ! git config --global user.email >/dev/null; then
  echo "Configure sua identidade:"
  echo 'git config --global user.name "SEU NOME"'
  echo 'git config --global user.email "SEU EMAIL DO GITHUB"'
  exit 1
fi
if [[ ! -d .git ]]; then git init -b main; fi
git add .gitignore .env.example requirements.txt pyproject.toml README.md COMANDOS_CLOUD_SHELL.txt src tests scripts docs
if git diff --cached --quiet; then
  echo "Sem alterações para commit."
else
  git commit -m "feat: estrutura inicial do tech challenge GCP"
fi
printf '\nRepositório Git local pronto. Crie o repositório remoto vazio no GitHub e use:\n'
printf 'git remote add origin https://github.com/SEU-USUARIO/fiap-alfabetizacao-gcp.git\n'
printf 'git push -u origin main\n'
