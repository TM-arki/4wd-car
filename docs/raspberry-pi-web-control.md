# Raspberry Pi webstyring

Dette setter Raspberry Pi opp som robotens kontrollmaskin:

- Pico kobles til Raspberry Pi med USB.
- Raspberry Pi prøver hjemmenett ved boot og henter siste kode fra GitHub.
- Etter oppdatering starter Raspberry Pi robotens eget Wi-Fi-hotspot.
- Raspberry Pi hoster web-GUI på `http://10.42.0.1:8080`.
- Telefon eller PC kobler seg på robotens Wi-Fi og styrer bilen i nettleseren.

Passord til hjemmenett skal ikke inn i repoet. Det lagres bare lokalt på Raspberry Pi som en NetworkManager-profil.

## 1. Kopier repoet til Raspberry Pi

```bash
cd ~
git clone https://github.com/TM-arki/4wd-car.git
cd 4wd-car
```

Hvis du tester denne PR-branchen før den merges:

```bash
git checkout pi-web-control
```

Etter at branchen er merget til `main`, bruk `main` på Pi.

## 2. Installer webappen

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip network-manager
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

## 3. Sett opp hjemmenett for auto-oppdatering

Opprett en lagret Wi-Fi-profil som heter `HomeWiFi`. Bytt SSID og passord til ditt hjemmenett når du kjører kommandoen på Pi:

```bash
sudo nmcli connection add type wifi ifname wlan0 con-name HomeWiFi ssid "DITT_WIFI_NAVN"
sudo nmcli connection modify HomeWiFi wifi-sec.key-mgmt wpa-psk
sudo nmcli connection modify HomeWiFi wifi-sec.psk "DITT_WIFI_PASSORD"
sudo nmcli connection modify HomeWiFi connection.autoconnect no
sudo nmcli connection up HomeWiFi
```

Test at Pi har nett:

```bash
ping -c 1 github.com
```

Hvis dette virker, vil Pi prøve `HomeWiFi` ved hver boot, hente siste kode, og så bytte til robot-hotspot.

## 4. Sett opp robotens Wi-Fi-hotspot

```bash
sudo nmcli device wifi hotspot ifname wlan0 ssid RobotCar password robot1234
sudo nmcli connection modify Hotspot ipv4.addresses 10.42.0.1/24
sudo nmcli connection modify Hotspot ipv4.method shared
sudo nmcli connection modify Hotspot connection.autoconnect no
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

Bytt hotspot-passord før kjøring ute blant folk.

## 5. Start auto-oppdatering og webappen automatisk

```bash
cd ~/4wd-car/host/pi_web_control
sudo cp systemd/robot-boot-update.service /etc/systemd/system/
sudo cp systemd/robot-web-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable robot-boot-update.service
sudo systemctl enable robot-web-control.service
sudo systemctl start robot-web-control.service
```

`robot-web-control.service` venter på `robot-boot-update.service`. Ved boot skjer dette:

1. Pi prøver å koble til `HomeWiFi`.
2. Hvis den får nett, kjører den `git fetch` og `git reset --hard` til valgt branch.
3. Den oppdaterer Python-avhengigheter fra `requirements.txt`.
4. Den starter `Hotspot`.
5. Webserveren starter.

Standard branch i service-filen er `main`. Hvis du tester PR-branchen før merge, endre dette i `/etc/systemd/system/robot-boot-update.service`:

```text
Environment=ROBOT_GIT_BRANCH=pi-web-control
```

Hvis brukeren på Pi ikke heter `pi`, endre `User=pi` og `/home/pi/...` i begge service-filene.

## 6. Manuell test av boot-update

```bash
sudo systemctl start robot-boot-update.service
journalctl -u robot-boot-update.service -n 100 --no-pager
```

Sjekk webappen:

```bash
sudo systemctl status robot-web-control.service
journalctl -u robot-web-control.service -n 80 --no-pager
```

## 7. Oppstartssjekk

1. Løft bilen slik at hjulene kan spinne fritt første gang.
2. Slå på motorstrøm, men hold fysisk nødstopp tilgjengelig.
3. Start Raspberry Pi.
4. Vent 60-90 sekunder hvis Pi skal rekke å sjekke GitHub først.
5. Koble telefon/PC til `RobotCar`.
6. Åpne `http://10.42.0.1:8080`.
7. Trykk `STOP` først.
8. Test ett hjul av gangen med lav hastighetsgrense.

## Feilsøking

```bash
ls /dev/ttyACM*
nmcli connection show
nmcli device status
sudo systemctl status robot-boot-update.service
sudo systemctl status robot-web-control.service
journalctl -u robot-boot-update.service -n 100 --no-pager
journalctl -u robot-web-control.service -n 80 --no-pager
```

Hvis Pico får en annen port enn `/dev/ttyACM0`, test manuelt med riktig port først. Etterpå kan service-filen oppdateres.

Hvis Pi ikke finner hjemmenett innen ca. 45 sekunder, beholder den koden som allerede ligger lokalt og starter hotspot likevel.
