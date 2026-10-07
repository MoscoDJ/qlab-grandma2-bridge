# Bridge QLab → grandMA2 onPC

QLab manda triggers OSC abstractos (`/lx/go/8`) por Ethernet. El bridge los
traduce al comando de grandMA2 que diga `config.json` y se lo manda a la consola
por **Telnet**, una interfaz nativa de grandMA2.

```
QLab ──OSC/UDP :8000──► ma2_bridge.py ──Telnet/TCP :30000──► grandMA2 onPC ──► Command Wing ──DMX──► AsteraBox ──► Astera
```

No hay MIDI físico, puerto MIDI virtual ni RTP-MIDI. El instalador trae su propio
Python portátil; en desarrollo basta Python 3.8 o superior, sin paquetes extra.

## Instalación rápida (PC de grandMA2)

1. Abre **PowerShell**: tecla Windows, escribe `powershell` y pulsa Enter.
2. Copia este comando con el botón de la esquina del recuadro, pégalo en
   PowerShell y pulsa Enter:

```powershell
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; irm https://raw.githubusercontent.com/MoscoDJ/qlab-grandma2-bridge/main/instalar-web.ps1 | iex
```

3. Acepta el aviso de administrador de Windows y espera a que termine. Al final
   muestra la IP que hay que poner en QLab.

El comando descarga la última versión de este repositorio, instala el bridge en
`C:\ma2_bridge\` con su propio Python portátil (no hace falta tener Python) y lo
deja configurado para arrancar con Windows. Ejecutarlo de nuevo sirve para actualizar:
conserva tu `config.json`.

Con opciones (otra carpeta o sin arranque automático):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/MoscoDJ/qlab-grandma2-bridge/main/instalar-web.ps1))) -Destino D:\ma2_bridge -SinInicioAutomatico
```

**Sin internet en el PC de MA:** en otra computadora, *Code → Download ZIP*.
Descomprime el ZIP en un USB, pásalo al PC y da doble clic en `instalar.bat`. El
paquete ya trae Python. Si Windows SmartScreen avisa, elige *Más información →
Ejecutar de todas formas*.

## 1. grandMA2 onPC (lo hace el iluminador)

1. **Setup → Console → Global Settings → Telnet = `Login Enabled`**.
2. Programar los executors o cues que corresponden a cada LX.
3. Si el usuario o la contraseña no son `administrator` / `admin`, ajustar
   `ma2.user` y `ma2.password` en `config.json`.

Prueba manual opcional desde el mismo PC: `telnet 127.0.0.1 30000`, luego
`Login "administrator" "admin"` y después `Go Executor 1.101`.

## 2. Bridge (en el PC de grandMA2)

### Qué hace el instalador

Da igual cómo lo lances, con el comando de PowerShell o con `instalar.bat`:

- copia el bridge a `C:\ma2_bridge\` con su propio Python 3.12 portátil.
  No toca el Python del sistema ni el PATH. Antes de usar el zip verifica su SHA256;
- conserva el `config.json` de una instalación anterior;
- abre en el firewall el puerto UDP de OSC para todas las redes, porque una red
  de show sin internet suele quedar como "pública";
- crea un icono en el escritorio y el arranque automático con Windows (minimizado);
- hace una autoprueba e indica la IP que hay que poner en QLab.

Opciones: `instalar.bat -Destino D:\ma2_bridge`, `instalar.bat -SinInicioAutomatico`.
Para desinstalar: `desinstalar.bat`, desde el paquete o desde la carpeta instalada.
Requiere Windows 8.1 o superior.

### Configuración y pruebas

1. Editar la tabla `triggers` de `C:\ma2_bridge\config.json`:
   ```json
   "8": { "name": "Final", "command": "Go Executor 1.108" }
   ```
   `command` admite cualquier comando de la línea de comandos de MA:
   `Goto Executor 1.1 Cue 32`, `Macro 15`, `Off Executor 1.101`, etc.
   También se aceptan triggers decimales (`"8.5"`) para cues que se insertan después.
2. Revisar la configuración y si MA responde, sin disparar nada:
   `python\python.exe ma2_bridge.py --check`
3. Disparar un trigger contra MA y salir: `python\python.exe ma2_bridge.py --fire 1 -v`
4. Uso normal: icono **Bridge QLab-MA2** del escritorio. Si el bridge se cae,
   se reinicia solo. Si ya hay otro abierto, el segundo se niega a arrancar,
   para que dos bridges no se repartan los mensajes.

## 3. QLab 5 (Mac)

1. **Workspace Settings → Network → nuevo patch**:
   tipo *OSC*, destino = IP del PC de grandMA2, puerto **8000**.
2. Por cada momento del show, un **Network Cue** con ese patch y el mensaje:
   ```
   /lx/go/8
   ```
   Ponerle de nombre `LX 08 – Final` y agruparlo con el audio o video de esa escena.
3. Comprobar el enlace con un Network Cue `/lx/ping`. El bridge contesta
   `/lx/pong ma2:connected` y deja el ping en el log.

Para probar sin QLab, desde cualquier computadora con Python:
```
python send_osc.py <IP-PC-MA> 8000 /lx/go/3
python send_osc.py <IP-PC-MA> 8000 /lx/ping
```

## Mensajes OSC

| Mensaje | Acción |
|---|---|
| `/lx/go/<n>` | Ejecuta el comando del trigger `n` |
| `/lx/go <n>` | Igual, con `n` como argumento (int, float o string) |
| `/lx/ping` | Responde `/lx/pong` con el estado de la conexión a MA |
| `/lx/cmd "<comando MA>"` | Comando directo. **Desactivado** salvo `allow_raw_commands: true` |

Un trigger que no está en la tabla se ignora y queda una advertencia en el log.
Si prefieres que todo trigger desconocido vaya a una macro, usa
`"default_command": "Macro {n}"`.

## Robustez

- La conexión Telnet es persistente y con keepalive, así que el GO no espera
  a que se abra la conexión. Si MA se reinicia, el bridge reconecta solo cada 2 s.
- Si un envío falla, el bridge reconecta y lo reintenta una vez.
- Antes de cada show: ejecutar el cue `/lx/ping` y mirar la consola del bridge.

## Desarrollo

```
python -m pytest tests     # usa una grandMA2 simulada; no requiere consola
```
