#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Este instalador deve ser executado no Raspberry Pi." >&2
  exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
  echo "Execute como usuário normal; o script solicitará sudo quando necessário." >&2
  exit 1
fi

DASHBOARD_USER_NAME="$(id -un)"
SUDO=(sudo)

if [[ ! "${DASHBOARD_USER_NAME}" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "Nome de usuário incompatível com o instalador: ${DASHBOARD_USER_NAME}" >&2
  exit 1
fi

DASHBOARD_HOME_DIR="$(getent passwd "${DASHBOARD_USER_NAME}" | awk -F: '{print $6}')"
if [[ -z "${DASHBOARD_HOME_DIR}" || ! -d "${DASHBOARD_HOME_DIR}" ]]; then
  echo "Não foi possível localizar a home de ${DASHBOARD_USER_NAME}." >&2
  exit 1
fi

VENV_DIR="${DASHBOARD_HOME_DIR}/st7789-env"
STATE_DIR="${DASHBOARD_HOME_DIR}/.config/raspberrypi-st7789-dashboard"
SERVICE_DIR="/etc/systemd/system"

echo "==> Instalando dependências do sistema"
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y \
  python3-venv python3-pip libopenblas0 fonts-dejavu-core usbutils \
  iproute2 iputils-ping iw curl ca-certificates

echo "==> Preparando ambiente Python em ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_DIR}/requirements.txt"

echo "==> Executando testes sem hardware"
cd "${PROJECT_DIR}"
"${VENV_DIR}/bin/python" -m unittest discover -s tests -v

echo "==> Preparando estado local"
PRIMARY_GROUP="$(id -gn "${DASHBOARD_USER_NAME}")"
"${SUDO[@]}" install -d -m 0700 -o "${DASHBOARD_USER_NAME}" -g "${PRIMARY_GROUP}" "${STATE_DIR}"

for DEVICE_GROUP in spi gpio; do
  if getent group "${DEVICE_GROUP}" >/dev/null; then
    "${SUDO[@]}" usermod -aG "${DEVICE_GROUP}" "${DASHBOARD_USER_NAME}"
  fi
done

render_service() {
  local source_file="$1"
  local destination_file="$2"

  sed \
    -e "s|^User=pi$|User=${DASHBOARD_USER_NAME}|" \
    -e "s|/home/pi/raspberrypi-st7789-dashboard|${PROJECT_DIR}|g" \
    -e "s|/home/pi/st7789-env|${VENV_DIR}|g" \
    -e "s|/home/pi/.config/raspberrypi-st7789-dashboard|${STATE_DIR}|g" \
    "${source_file}" | "${SUDO[@]}" tee "${destination_file}" >/dev/null
  "${SUDO[@]}" chmod 0644 "${destination_file}"
}

echo "==> Instalando serviços systemd"
render_service \
  "${PROJECT_DIR}/systemd/bench-display.service" \
  "${SERVICE_DIR}/bench-display.service"
render_service \
  "${PROJECT_DIR}/systemd/bench-display-web.service" \
  "${SERVICE_DIR}/bench-display-web.service"

"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable bench-display.service bench-display-web.service
"${SUDO[@]}" systemctl restart bench-display.service bench-display-web.service

echo
echo "Instalação concluída."
echo "Painel local: http://$(hostname -I | awk '{print $1}'):8080"
echo "Validação: ${PROJECT_DIR}/scripts/validate_install.sh"
