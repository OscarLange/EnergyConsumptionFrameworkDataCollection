import binascii
import sys
from ina219 import INA219, DeviceRangeError
import time

#read ina values and store in file
def read_ina219():
    global stored_values
    values = ""
    Uges = ina.voltage() + ina.shunt_voltage()/1000
    values += '{0:0.2f},'.format(Uges)
    values += '{0:0.2f},'.format(ina.current())
    values += '{0:0.2f},'.format(ina.power())
    values += '{0:0.10f}'.format(ina.shunt_voltage())
    stored_values.append(values)

#Resistance of Resistor inside INA219
SHUNT_OHM = 0.1
MAX_CURRENT = 0.4

#ina configurations
ina = INA219(SHUNT_OHM, MAX_CURRENT)
ina.configure(ina.RANGE_16V, ina.GAIN_1_40MV)

stored_values = []

i = 0
while(i < 20000):
    read_ina219()
    i += 1

file_name = "./test_preproc.csv"

with open(file_name, 'a') as f:
    try:
        for val in stored_values:
            f.write(val + "10,480\n")
    except DeviceRangeError as e:
        print('Current to large!')

