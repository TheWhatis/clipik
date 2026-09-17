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
clipik server & clipik client
```

или

``` bash
git clone https://gitflic.ru/project/kurilka/clipik
cd clipik
uv pip install -e .
clipik server & clipik client
```

# Использование

При передаче опций, они перезаписывают данные с конфига и переменных
окружения.

- `server` - Запускает сервер с websocket-м на указанном порту (8765) и
  регестрирует сервис в mdns
- `client` - Должен запускаться после иницилизации граф. оболочки,
  мониторит буфер обмена и отправляет его на `server`
- `list`, `first`, `last`, `paste` - Читают бд и записывают данные в
  буфер обмена (по запросу `paste`)

```
$ clipik -h
usage: clipik [-h] [--version] [--config PATH] [--log-level LEVEL] [--log-dir PATH]
              [--size-limit BYTES] [--handshake-timeout SECONDS] [--database PATH]
              COMMAND ...

Synchronize clipboard by network

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --config PATH         Force choice config file
  --log-level LEVEL     Logging level, default [INFO]
  --log-dir PATH        Force choice log directory
  --size-limit BYTES    Max size WS-messages and stdout from wayland/x11 clipboard
  --handshake-timeout SECONDS
                        Timeout for wait to websocket handshake
  --database PATH       Force choice database file

command:
  COMMAND
    server              Run synchronization server
    client              Run synchronization client
    list                Get list clipboard history
    first               Get first clipboard element
    last                Get last clipboard element
    paste               Paste record in clipboard
```

# Конфигурация

## Сервер

По-умолчанию конфигурация находиться по пути
`~/.config/clipik/server.json`, если его не существует, при запуске
**clipik** он создается автоматически, но не все параметры там будут
прописаны.

Конфиг будет иметь вид:

``` json
{
    "interfaces": [],
    "port": 8765,
    "size_limit": 67108864,
    "log_dir": "~/.local/clipik",
    "log_level": "INFO",
    "handshake_timeout": 7
}
```

Со всеми параметрами такой:

``` json
{
    "interfaces": [],
    "port": 8765,
    "size_limit": 67108864,
    "log_dir": "~/.local/clipik",
    "log_level": "INFO",
    "handshake_timeout": 7,
    "database": "~/.local/clipik/clipik.db",
    "allowed_ips": [
        "192.164.0.1/24",
        "100.0.0.1",
        "100.0.0.2"
    ]
}
```

## Клиент

По тому-же пути, только `client.json` - `~/.config/clipik/client.json`,
создается сам если не существует.

Имеет вид:

``` json
{
    "interfaces": [],
    "size_limit": 67108864,
    "log_dir": "~/.local/clipik",
    "log_level": "INFO",
    "handshake_timeout": 7,
}
```

Со всеми параметрами такой;

``` json
{
    "interfaces": [],
    "size_limit": 67108864,
    "log_dir": "~/.local/clipik",
    "log_level": "INFO",
    "handshake_timeout": 7,
    "database": "~/.local/clipik/clipik.db",
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
- `CLIPIK_DATABASE=~/.local/clipik/clipik.db` - Путь до sqlite3 файла c
  БД

# База данных

Сервер работает с sqlite3 БД, вся история буфера по сети именно там, с
помощью `clipik list` можно посмотреть записанную историю, а
`clipik paste <id>` позволяет её вставить в буфер обмена.

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

## Android (пока не поддерживается)

# <span class="todo TODO">TODO</span> \[4/10\]

- [ ] Возможность регистрировать сервисы для подключения к удаленным
  сетями
- [x] Регистрацию при подключении (ввод pin-кода/разрешенные хосты в
  конфиге)
- [ ] Поддержка всех типов данных, в том числе при копировании из
  файловых менеджеров
- [ ] Поддержка MacOS
- [ ] Поддержка Windows
- [ ] Поддержка Android
- [ ] Фоновая загрузка больших файлов с ожиданием вставки (до конца
  загрузки)
- [x] Поддержка передачи данных не только через переменные окружения, но
  и через опции и конфиги
- [x] Одновременная работа на wayland и x11 без переключения
- [x] Переделать архитектуру, сохранять контент в промежуточную историю
  вместо загрузки сразу в буфер обмена
