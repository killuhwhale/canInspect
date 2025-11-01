pip install python-can  udsoncan
pip install git+https://github.com/pylessard/python-can-isotp.git

# Example SocketCAN bring-up (adjust device path/speed for your adapter)
sudo slcand -o -c -s6 /dev/ttyACM0 can0    # -s6 = 500 kbit/s

sudo ip link set can0 up type can bitrate 500000
sudo ip -details link show can0
sudo ifconfig can0 up



