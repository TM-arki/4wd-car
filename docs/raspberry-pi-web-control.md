# Raspberry Pi webstyring

Dette setter Raspberry Pi opp som robotens kontrollmaskin:

- Pico kobles til Raspberry Pi med USB.
- Raspberry Pi lager et Wi-Fi-hotspot.
- Raspberry Pi hoster web-GUI på `http://10.42.0.1:8080`.
- Telefon eller PC kobler seg på robotens Wi-Fi og styrer bilen i nettleseren.

## 1. Kopier repoet til Raspberry Pi

```bash
cd ~
git clone https://github.com/TM-arki/4wd-car.git
cd 4wd-car
```

Hvis du tester en egen branch først:

```bash
git checkout pi-web-control
```

## 2. Installer webappen

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip network-manager
cd ~/4wd-car/host/pi_web_control
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Koble Pico til Raspberry Pi med USB. Sjekk port:

```bash
ls /dev/ttyACM*
```

Vanlig port er `/dev/ttyACM0`.

Test webappen manuelt:

```bash
python app.py --serial-port /dev/ttyACM0 --port 8080
```

Åpne fra en annen maskin på samme nett:

```text
http://raspberrypi.local:8080
```

## 3. Sett opp Wi-Fi-hotspot

Dette bruker NetworkManager, som er standard på nyere Raspberry Pi OS.

```bash
sudo nmcli device wifi hotspot ifname wlan0 ssid RobotCar password robot1234
sudo nmcli connection modify Hotspot ipv4.addresses 10.42.0.1/24
sudo nmcli connection modify Hotspot ipv4.method shared
sudo nmcli connection modify Hotspot connection.autoconnect yes
sudo nmcli connection up Hotspot
```

Koble telefon/PC til Wi-Fi-nettet:

```text
SSID: RobotCar
Passord: robot1234
```

Åpne:

```text
http://10.42.0.1:8080
```

Bytt passord før kjøring ute blant folk.

## 4. Start webappen automatisk

```bash
cd ~/4wd-car/host/pi_web_control
sudo cp systemd/robot-web-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now robot-web-control.service
sudo systemctl status robot-web-control.service
```

Hvis brukeren på Pi ikke heter `pi`, endre `User=pi` og `/home/pi/...` i service-filen.

## 5. Oppstartssjekk

1. Løft bilen slik at hjulene kan spinne fritt første gang.
2. Slå på motorstrøm, men hold fysisk nødstopp tilgjengelig.
3. Start Raspberry Pi.
4. Vent 30-60 sekunder.
5. Koble telefon/PC til `RobotCar`.
6. Åpne `http://10.42.0.1:8080`.
7. Trykk `STOP` først.
8. Test ett hjul av gangen med lav hastighetsgrense.

## Feilsøking

```bash
ls /dev/ttyACM*
sudo systemctl status robot-web-control.service
journalctl -u robot-web-control.service -n 80 --no-pager
nmcli connection show
nmcli device status
```

Hvis Pico får en annen port enn `/dev/ttyACM0`, test manuelt med riktig port først. Etterpå kan service-filen oppdateres.
