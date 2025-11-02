pip install --upgrade pip setuptools wheel

pip install python-can  udsoncan
pip install git+https://github.com/pylessard/python-can-isotp.git
https://chatgpt.com/c/68f86af2-f6f8-832c-b6b5-3495b1ee0b72


# Example SocketCAN bring-up (adjust device path/speed for your adapter)
sudo slcand -o -c -s6 /dev/ttyACM0 can0    # -s6 = 500 kbit/s

sudo ip link set can0 up type can bitrate 500000
sudo ip -details link show can0
sudo ifconfig can0 up



## Grab dump from car

sudo ip link set can0 up type can bitrate 500000
sudo ip -details link show can0

candump can0 | tee can0dump.txt


## Graph dump

python3 plot_wheels.py --car g37 --dump can0dump.txt --units kph
python3 plot_wheels.py --car mercedes --dump can0dump.txt --units mph


## Analyze Dump

python3 can_reverse_from_dump_debug.py --dump can0dump.txt --calib 8 --monitor 12 --verbose --id-summary


### Give report to ChatGPT and it can easily tell which id changed for wheel speed.
#### Take dump while rolling the car back and forth...
[INFO] Parsed frames: 52241 (bad/unparsed lines: 0)
[INFO] First frame: ts=None id=0x1B4 dlc=7 data=00 00 e9 06 40 00 e4
[INFO] Last  frame: ts=None id=0x245 dlc=8 data=ff e0 00 18 00 00 ff e0
[INFO] Timestamp present: False; t_min=None, t_max=None
------ ID Summary (top by frame count) ------
002  frames=  3250  first=ef fd 00 07 bf a6 9f 0a  last=f0 fd 00 07 a0 a6 9f 0a
2DE  frames=  3249  first=00 00 82 00 00 00 0a 1b  last=00 00 82 00 00 00 0a 1a
0C1  frames=  3247  first=b0 fd 00 00 08 00 03 79  last=b1 fd 00 00 08 00 01 78
1B4  frames=  3239  first=00 00 e9 06 40 00 e4  last=00 00 e9 06 40 06 ea
2B0  frames=  3239  first=00 0f ff 81 00 8c 00 cd  last=00 0f ff 81 00 8c 60 2d
160  frames=  3172  first=33 c3 1d 00 08 ff e0  last=33 d3 1f 00 08 ff e0
180  frames=  3172  first=14 9b 31 d3 3c 00 2f 10  last=14 69 31 f3 3d 00 22 10
182  frames=  3172  first=00 00 00 00 00 0f 00 cf  last=00 00 00 00 00 02 00 cf
1F9  frames=  3172  first=20 00 14 9b 00 00 00 80  last=20 00 14 69 00 00 00 80
216  frames=  1625  first=42 64  last=42 64
290  frames=  1625  first=40 05 e9 06 e9 06 12 c7  last=40 05 e9 06 e9 06 92 47
285  frames=  1625  first=00 00 00 00 00 00 16 9d  last=00 00 00 00 00 00 6e f5
284  frames=  1625  first=00 00 00 00 00 00 16 9c  last=00 00 00 00 00 00 6e f4
215  frames=  1625  first=ff f0 ff 00 ff ff  last=ff f0 ff 00 ff ff
2A0  frames=  1625  first=ff 7f fe 7f fe fe  last=ff 7f fe 7f fe fe
245  frames=  1625  first=ff e0 00 18 00 00 ff e0  last=ff e0 00 18 00 00 ff e0
280  frames=  1624  first=03 00 80 00 00 00 3a 40  last=03 15 80 00 00 00 46 40
2B3  frames=  1620  first=00 00 00 00 80 52  last=00 00 00 00 80 52
239  frames=  1586  first=00 ff b1 80 57  last=00 ff b1 80 54
355  frames=   812  first=00 00 00 00 00 00 60  last=00 00 00 00 00 00 60
354  frames=   812  first=00 00 00 00 00 10 04 00  last=00 00 00 00 00 08 04 00
385  frames=   325  first=04 00 00 00 00 00 00  last=04 00 00 00 00 00 00
540  frames=   325  first=28 20 00 00 00 00 00 00  last=28 20 00 00 00 00 00 00
541  frames=   325  first=00 00 00 00 00 00 00 80  last=00 00 00 00 00 00 00 80
542  frames=   325  first=00 00 00 00 00 00 00 00  last=00 00 00 00 00 00 00 00
5C5  frames=   325  first=44 02 75 ee 00 0c 00 00  last=44 02 75 ee 00 0c 00 00
60D  frames=   325  first=00 06 00 00 00 00 00 00  last=00 06 00 00 00 00 00 00
625  frames=   325  first=02 00 ff 1d 20 00  last=02 00 ff 1d 20 00
525  frames=   325  first=c0  last=c0
35D  frames=   325  first=80 03 00 00 00 00 00 00  last=80 03 00 00 00 00 00 00
[DBG] id_summary: unique IDs = 38
[INFO] Running calibration for ~8.0s worth of frames (no hard stop without timestamps).
--------- Calibration Start ----------
[DBG] New ID observed: 0x1B4
[DBG] New ID observed: 0x2B0
[DBG] New ID observed: 0x2B3
[DBG] New ID observed: 0x2DE
[DBG] New ID observed: 0x002
[DBG] New ID observed: 0x216
[DBG] New ID observed: 0x160
[DBG] New ID observed: 0x180
[DBG] New ID observed: 0x182
[DBG] New ID observed: 0x0C1
[DBG] New ID observed: 0x1F9
[DBG] New ID observed: 0x239
[DBG] New ID observed: 0x290
[DBG] New ID observed: 0x285
[DBG] New ID observed: 0x284
[DBG] New ID observed: 0x385
[DBG] New ID observed: 0x280
[DBG] New ID observed: 0x215
[DBG] New ID observed: 0x2A0
[DBG] New ID observed: 0x245
[DBG] New ID observed: 0x540
[DBG] New ID observed: 0x541
[DBG] New ID observed: 0x542
[DBG] New ID observed: 0x355
[DBG] New ID observed: 0x5C5
[DBG] New ID observed: 0x60D
[DBG] New ID observed: 0x354
[DBG] New ID observed: 0x625
[DBG] New ID observed: 0x525
[DBG] New ID observed: 0x35D
[DBG] New ID observed: 0x551
[DBG] New ID observed: 0x580
[DBG] New ID observed: 0x6E2
[DBG] New ID observed: 0x358
[DBG] New ID observed: 0x54A
[DBG] New ID observed: 0x54B
[DBG] New ID observed: 0x54C
[DBG] New ID observed: 0x351
[DBG] calib: processed 5000 frames...
[DBG] calib: processed 10000 frames...
[DBG] calib: processed 15000 frames...
[DBG] calib: processed 20000 frames...
[DBG] calib: processed 25000 frames...
[DBG] calib: processed 30000 frames...
[DBG] calib: processed 35000 frames...
[DBG] calib: processed 40000 frames...
[DBG] calib: processed 45000 frames...
[DBG] calib: processed 50000 frames...
[INFO] Calibration processed frames: 52241
--------- Calibration Complete --------
0C1 XX XX 00 00 XX 00 XX XX
160 XX XX XX 00 XX XX XX
180 XX XX XX XX XX 00 XX XX
182 00 00 00 00 00 XX 00 XX
1B4 00 00 XX XX XX XX XX
1F9 XX 00 XX XX 00 00 00 XX
215 XX XX XX 00 XX XX
239 00 XX XX XX XX
245 XX XX 00 XX 00 00 XX XX
280 XX XX XX 00 00 00 XX XX
284 00 XX 00 XX 00 00 XX XX
285 00 XX 00 XX 00 00 XX XX
2B0 00 XX XX XX 00 XX XX XX
2B3 00 00 00 00 XX XX
2DE 00 00 XX 00 00 00 XX XX
351 00 00 00 00 00 XX 00 XX
354 00 00 00 00 00 XX XX 00
355 00 00 00 00 00 00 XX
358 00 00 00 00 XX 00 00 00
35D XX XX 00 00 00 00 00 00
385 XX 00 00 00 00 00 00
525 C0
540 XX XX 00 00 00 00 00 XX
541 00 00 00 00 00 00 00 XX
542 00 00 00 00 00 00 00 XX
54A XX XX XX XX XX XX 00 XX
54B XX XX XX XX XX 00 00 00
54C XX XX XX 00 00 XX XX XX
551 XX XX 00 XX 00 XX XX XX
580 00 XX XX
5C5 XX XX XX XX 00 XX 00 00
60D 00 XX 00 00 00 00 00 00
625 XX 00 XX XX XX 00
[DBG] Calibration summary rows printed: 33
[INFO] Running monitoring for ~12.0s worth of frames (no hard stop without timestamps).
--------- Monitoring Start -----------
[DBG] monitor: processed 5000 frames... changes so far=0
[DBG] monitor: processed 10000 frames... changes so far=0
[DBG] monitor: processed 15000 frames... changes so far=0
[DBG] monitor: processed 20000 frames... changes so far=0
[DBG] monitor: processed 25000 frames... changes so far=0
[DBG] monitor: processed 30000 frames... changes so far=0
[DBG] monitor: processed 35000 frames... changes so far=0
[DBG] monitor: processed 40000 frames... changes so far=0
[DBG] monitor: processed 45000 frames... changes so far=0
[DBG] monitor: processed 50000 frames... changes so far=0
[INFO] Monitoring processed frames: 52241, changes printed: 0
--------- Monitoring Complete --------