#!/usr/bin/env bash
set -uo pipefail

FAILURES=0
STATE_DIR="${ST7789_DASHBOARD_STATE_DIR:-${HOME}/.config/raspberrypi-st7789-dashboard}"

pass() {
  printf 'PASS  %s\n' "$1"
}

fail() {
  printf 'FAIL  %s\n' "$1" >&2
  FAILURES=$((FAILURES + 1))
}

check_service() {
  local service="$1"
  if systemctl is-active --quiet "${service}"; then
    pass "${service} ativo"
  else
    fail "${service} inativo"
    systemctl status "${service}" --no-pager --lines=8 || true
  fi
}

echo "ST7789 Dashboard — validação da instalação"
echo

if [[ -e /dev/spidev0.0 ]]; then
  pass "SPI disponível em /dev/spidev0.0"
else
  fail "SPI indisponível; habilite em raspi-config"
fi

check_service bench-display.service
check_service bench-display-web.service

if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8080/api/health; then
  echo
  pass "API web respondeu em localhost:8080"
else
  fail "API web não respondeu em localhost:8080"
fi

DISPLAY_STATE="${STATE_DIR}/display-state.json"
if [[ -s "${DISPLAY_STATE}" ]]; then
  if python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); assert data.get("currentPage") and not data.get("error")' "${DISPLAY_STATE}"; then
    pass "display publicou estado sem erro"
  else
    fail "display publicou estado inválido ou com erro"
    sed -n '1,80p' "${DISPLAY_STATE}"
  fi
else
  fail "display ainda não publicou ${DISPLAY_STATE}"
fi

echo
if [[ "${FAILURES}" -eq 0 ]]; then
  echo "Validação automática aprovada."
  echo "Teste manual restante: pressione GPIO23/GPIO24 e confirme página anterior/próxima."
  exit 0
fi

echo "Validação encontrou ${FAILURES} falha(s)." >&2
exit 1
