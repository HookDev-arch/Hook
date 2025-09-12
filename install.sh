#!/bin/bash

runin() {
    { "$@" 2>>../Hook-install.log || return $?; } | while read -r line; do
        printf "%s\n" "$line" >>../Hook-install.log
    done
}

runout() {
    { "$@" 2>>Hook-install.log || return $?; } | while read -r line; do
        printf "%s\n" "$line" >>Hook-install.log
    done
}

errorin() { cat ../Hook-install.log; }
errorout() { cat Hook-install.log; }

SUDO_CMD=""
if [ ! x"$SUDO_USER" = x"" ]; then
    if command -v sudo >/dev/null; then
        SUDO_CMD="sudo -u $SUDO_USER "
    fi
fi

clear
clear

printf "\n\n\e[3;34;40m Start Hook Installing (Stable GitHub Version >= 1.0.0)...\e[0m\n\n"

touch Hook-install.log
if [ ! x"$SUDO_USER" = x"" ]; then
    chown "$SUDO_USER:" Hook-install.log
fi

if [ -d "Hook/Hook" ]; then
    cd Hook || { printf "\rError: Install git package and re-run installer"; exit 6; }
    DIR_CHANGED="yes"
fi

if [ -f ".setup_complete" ]; then
    PYVER="3"
    printf "\rExisting installation detected"
    clear
    "python$PYVER" -m hook "$@"
    exit $?
elif [ "$DIR_CHANGED" = "yes" ]; then
    cd ..
fi

echo "Installing..." >Hook-install.log

# Определяем пакетный менеджер
if [ -f '/etc/debian_version' ]; then
    PKGMGR="apt install -y"
    runout dpkg --configure -a
    runout apt update
    PYVER="3"
else
    printf "\r\033[1;31mUnsupported OS.\e[0m Use manual installation: https://github.com/HookDev-arch/Hook"
    exit 1
fi

# Устанавливаем базовые пакеты
printf "\n\r\033[0;34mInstalling linux packages...\e[0m"
runout $SUDO_CMD $PKGMGR python3 python3-pip python3-venv python3-dev git \
    libwebp-dev libz-dev libjpeg-dev libopenjp2-7 libtiff5 \
    ffmpeg imagemagick libffi-dev libcairo2 build-essential

# Устанавливаем pip, если его нет
if ! command -v pip3 >/dev/null 2>&1; then
    runout $SUDO_CMD python3 -m ensurepip --upgrade
    runout $SUDO_CMD python3 -m pip install --upgrade pip
else
    runout $SUDO_CMD python3 -m pip install --upgrade pip
fi

printf "\r\033[K\033[0;32mPackages installed!\e[0m"
printf "\n\r\033[0;34mCloning repo...\e[0m"

# Удаляем старую папку и клонируем репо
${SUDO_CMD}rm -rf Hook
runout ${SUDO_CMD}git clone https://github.com/HookDev-arch/Hook || {
    errorout "Clone failed."
    exit 3
}
cd Hook || { printf "\r\033[0;33mRun: pkg install git и перезапусти установщик"; exit 7; }

printf "\r\033[K\033[0;32mRepo cloned!\e[0m"
printf "\n\r\033[0;34mInstalling python dependencies...\e[0m"

# Устанавливаем зависимости глобально
runin $SUDO_CMD python3 -m pip install --upgrade setuptools wheel
runin $SUDO_CMD python3 -m pip install -r requirements.txt --upgrade --no-warn-script-location --disable-pip-version-check || {
    errorin "Requirements failed!"
    exit 4
}

rm -f ../Hook-install.log
touch .setup_complete

printf "\r\033[K\033[0;32mDependencies installed!\e[0m"
printf "\n\033[0;32mStarting...\e[0m\n\n"

${SUDO_CMD}python3 -m hook --root "$@" || {
    printf "\033[1;31mPython scripts failed\e[0m"
    exit 5
}
