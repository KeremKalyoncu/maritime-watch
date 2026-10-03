#!/data/data/com.termux/files/usr/bin/bash
# Writes GITHUB_DISPATCH_TOKEN into ~/maritime-watch/.env (KARARLAR K26) and tries it once.
# The token is read without echo and only passes through bash builtins and a Python
# process that reads it back from .env, so it never shows on screen, in shell history
# or in another process's argv (ps).
# Usage from the laptop:  ssh -t note4 "bash ~/maritime-watch/scripts/github_token_ekle.sh"
set -euo pipefail

# Replace KEY=... if present, otherwise append; the file stays 600 throughout.
set_key() {
  local key="$1" val="$2" file="$3" tmp
  tmp="$(mktemp "${file}.XXXXXX")"
  chmod 600 "$tmp"
  grep -v "^${key}=" "$file" > "$tmp" || true
  printf '%s=%s\n' "$key" "$val" >> "$tmp"
  mv "$tmp" "$file"
}

main() {
  local env_file="${HOME}/maritime-watch/.env"
  touch "$env_file"
  chmod 600 "$env_file"

  echo
  echo "GitHub token'ini (github_pat_ ile baslar) yapistir ve Enter'a bas."
  echo "(Yapistirinca ekranda hicbir sey gorunmez, bu normal.)"
  local pat=""
  read -rs pat
  echo
  pat="${pat//[[:space:]]/}"
  if [[ "$pat" != github_pat_* ]] || [ "${#pat}" -lt 40 ]; then
    echo "HATA: bu bir fine-grained GitHub token'i gibi gorunmuyor (github_pat_ ile baslamali). Tekrar calistir."
    exit 1
  fi
  set_key GITHUB_DISPATCH_TOKEN "$pat" "$env_file"
  unset pat

  echo "Kaydedildi. GitHub'a bir kez harita guncelleme istegi gonderiliyor..."
  cd "${HOME}/maritime-watch"
  python - <<'PY'
from src.config import load_config
from src.pages_dispatch import PagesDispatch

out = PagesDispatch(load_config()).maybe_dispatch()
print({
    "ok": "TAMAM: GitHub harita guncellemesini baslatti. Claude'a 'yazdim' de.",
    "refused": "HATA: GitHub reddetti. Token yalniz maritime-watch reposunu secmeli ve "
               "'Actions: Read and write' yetkisi olmali.",
    None: "HATA: token .env'den okunamadi. Tekrar calistir.",
}.get(out, "HATA: beklenmeyen cevap (%s). Claude'a soyle." % out))
PY
}

main "$@"
