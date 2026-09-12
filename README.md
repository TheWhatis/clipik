---
title: CLIPIK
---

[![Latest Stable](http://img.shields.io/pypi/v/clipik.svg)](https://pypi.org/project/clipik)
[![Scrutinizer](http://img.shields.io/scrutinizer/g/TheWhatis/clipik.svg)](https://scrutinizer-ci.com/g/TheWhatis/clipik)
[![License](http://img.shields.io/pypi/l/edges/clipik.svg?refresh=true)](https://pypi.org/project/clipik)

CLIPIK - сервис для реализации общего буфера обмена по локальной сети

# Быстрый старт

``` bash
pip install clipik
clipik
```

или

``` bash
git clone https://gitflic.ru/project/kurilka/clipik
cd clipik
uv pip install -e .
clipik
```

# Команды/Работа/Переменные окружения

На данный момент никаких аргументов не принимает, одновременно сервер и
клиент запускается по команде `clipik`,

Имеются только переменные окружения, за счет которых можно менять
свойства:

- `CLIPIK_LOG_LEVEL=INFO` - Уровель логирования: INFO, DEBUG, ERROR,
  CRITICAL …
- `WAYLAND_DISPLAY` - Если оно установлено, будет использовать wayland
  clipboard
- `CLIPIK_PORT=8765` - На каком порту поднять websocket (передача
  буфера)
- `CLIPIK_HANDSHAKE_TIMEOUT=7` - Сколько ждать HANDSHAKE при подключении

# Обязательные утилиты (зависимости)

## Linux

### X11 (xorg)

- `xclip`
- `clipnotify`

### Wayland

- `wl-paste`
- `wl-copy`

## MacOs (пока не поддерживается)

## Windows (пока не поддерживается)

# <span class="todo TODO">TODO</span> 

- [ ] Возможность регестрировать сервисы для подключения к удаленным
  сетями
- [ ] Регистрацию при подключении (ввод pin-кода/разрешенные хосты в
  конфиге)
- [ ] Поддержка всех типов данных, в том числе при копировании из
  файловых менеджеров
- [ ] Поддержка MacOS
- [ ] Поддержка Windows
