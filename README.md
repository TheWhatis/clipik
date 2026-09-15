---
title: CLIPIK
---

[![Latest Stable](http://img.shields.io/pypi/v/clipik.svg)](https://pypi.org/project/clipik)
[![Scrutinizer](http://img.shields.io/scrutinizer/g/clipik.svg)](https://scrutinizer-ci.com/g/clipik)
[![License](http://img.shields.io/pypi/l/clipik.svg?refresh=true)](https://pypi.org/project/clipik)

CLIPIK - сервис для реализации общего буфера обмена по локальной сети

# Быстрый старт

Тут должен быть установлен `PATH=${HOME}/.local/bin:${PATH}`

``` bash
uv tool install clipik
clipik
```

или

``` bash
git clone https://gitflic.ru/project/kurilka/clipik
cd clipik
uv pip install -e .
clipik
```

# Использование

При передаче опций, они перезаписывают данные с конфига и переменных
окружения.

```
$ clipik -h
usage: clipik [-h] [--version] [--config PATH] [--port PORT] [--size-limit BYTES]
              [--handshake-timeout SECONDS] [--log-level LEVEL]

Synchronize clipboard by network

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --config PATH         Force choice config file
  --port PORT           WebSocket TCP-port
  --size-limit BYTES    Max size WS-messages and stdout from wayland/x11 clipboard
  --handshake-timeout SECONDS
                        Timeout for wait to websocket handshake
  --log-level LEVEL     Logging level, default [INFO]
```

# Конфигурация

По-умолчанию конфигурация находиться по пути
`~/.config/clipik/config.json`, если его не существует, при запуске
**clipik** он создается автоматически, но не все параметры там будут
прописаны.

Конфиг будет иметь вид:

``` json
{
  "port": 8765,
  "size_limit": 67108864,
  "log_level": "INFO",
  "handshake_timeout": 7
}
```

Со всеми параметрами такой:

``` json
{
  "port": 8765,
  "size_limit": 67108864,
  "log_level": "INFO",
  "handshake_timeout": 7,
  "allowed_ips": [
      "192.164.0.1/24",
      "100.0.0.1",
      "100.0.0.2"
  ]
}
```

# Переменные окружения

Имеются только переменные окружения, за счет которых можно менять
свойства:

- `CLIPIK_LOG_LEVEL=INFO` - Уровель логирования: INFO, DEBUG, ERROR,
  CRITICAL …
- `WAYLAND_DISPLAY` - Если оно установлено, будет использовать wayland
  clipboard
- `CLIPIK_PORT=8765` - На каком порту поднять websocket (передача
  буфера)
- `CLIPIK_HANDSHAKE_TIMEOUT=7` - Сколько ждать HANDSHAKE при подключении
- `CLIPIK_SIZE_LIMIT=67108864` - Макс. размер передаваемых данных

# Обязательные утилиты (зависимости)

## Linux

### Общие (всегда работает с xorg)

- `xclip`
- `clipnotify`

### Wayland (опционально, если есть wayland)

- `wl-paste`
- `wl-copy`

## MacOs (пока не поддерживается)

## Windows (пока не поддерживается)

# <span class="todo TODO">TODO</span> \[3/9\]

- [ ] Возможность регистрировать сервисы для подключения к удаленным
  сетями
- [x] Регистрацию при подключении (ввод pin-кода/разрешенные хосты в
  конфиге)
- [ ] Поддержка всех типов данных, в том числе при копировании из
  файловых менеджеров
- [ ] Поддержка MacOS
- [ ] Поддержка Windows
- [ ] Фоновая загрузка больших файлов с ожиданием вставки (до конца
  загрузки)
- [x] Поддержка передачи данных не только через переменные окружения, но
  и через опции и конфиги
- [x] Одновременная работа на wayland и x11 без переключения
- [ ] Переделать архитектуру, сохранять контент в промежуточную историю
  вместо загрузки сразу в буфер обмена
