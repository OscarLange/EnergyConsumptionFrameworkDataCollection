from ina219 import INA219, DeviceRangeError
from time import sleep
import socket
from threading import Thread, Lock
import sys

#set mutex
mutex = Lock()

#Acknowledge message 
ack = "Acknowledged"
freq_switch = "Freq Switch"
config_switch = "Config Switch"

#test parameters
cpu_frequencies = [160, 240]
cpu_utilization = [25, 50, 75, 100]
work_files = ["noop_test.csv", "add_test.csv", "sub_test.csv", "mul_test.csv", "div_test.csv", "addf_test.csv", "subf_test.csv", "mulf_test.csv", "divf_test.csv", "linkedlist_test.csv"]

#determines which config is currently running
config_index = 0
cur_freq_index = 0
cur_util_index = 2
cur_work_index = 1
change_work = False

#Resistance of Resistor inside INA219
SHUNT_OHM = 0.1
MAX_CURRENT = 0.4

#ina configurations
ina = INA219(SHUNT_OHM, MAX_CURRENT)
ina.configure(ina.RANGE_16V, ina.GAIN_1_40MV)

stored_values = []

#print current configuration
def print_configuration():
    print("Config:" + str(cpu_frequencies[cur_freq_index]) + "," + str(cpu_utilization[cur_util_index]) + "," + str(work_files[cur_work_index]))

#increase configuration
#function switches through different configuration modes
def inc_configuration():
    global cur_work_index, cur_util_index, cur_freq_index, config_index
    if(config_index < int(sys.argv[1])):
        config_index += 1
        return

    config_index = 0

    if cur_work_index < (len(work_files)-1):
        cur_work_index += 1
        return
    
    cur_work_index = 0
    if cur_util_index < (len(cpu_utilization)-1):
        cur_util_index += 1
        return
    
    cur_util_index = 0
    if cur_freq_index < (len(cpu_frequencies)-1):
        cur_freq_index += 1
        return
    
    cur_freq_index = 0

#sanitize_espoutput
def sanitize_output(input):
    return input.decode();

#average out every collected value
def avg_values(stored_values):
    avg_uges, avg_iges, avg_pges, avg_ushunt = 0,0,0,0
    print(len(stored_values))
    stored_values = stored_values[:-2]
    print(len(stored_values))
    for stored_value in stored_values:
        value_list = stored_value.split(",")
        avg_uges += float(value_list[0])
        avg_iges += float(value_list[1])
        avg_pges += float(value_list[2])
        avg_ushunt += float(value_list[3])
    avg_uges /= len(stored_values)
    avg_iges /= len(stored_values)
    avg_pges /= len(stored_values)
    avg_ushunt /= len(stored_values)
    return str(avg_uges) + "," + str(avg_iges) + "," + str(avg_pges) + "," + str(avg_ushunt)

start_mode = False
#create socket to listen on
sock = socket.socket()
sock.bind(('0.0.0.0', 8090))
sock.listen(0)

print("waiting for coordinating device")
readClient, readAddr = sock.accept();    

config = str(readClient.recv(1024).decode())
print(config)
if(config[0] == 'y'):
    change_work = True
    cur_work_index = 0
    cur_freq_index = int(config.split(",")[1])
    cur_work_index = int(config.split(",")[2])
    cur_util_index = int(config.split(",")[3])

#read ina values and store in file
def read_ina219():
    global stored_values
    while(not mutex.acquire(False)):
        try:
            values = ""
            Uges = ina.voltage() + ina.shunt_voltage()/1000
            values += '{0:0.2f},'.format(Uges)
            values += '{0:0.2f},'.format(ina.current())
            values += '{0:0.2f},'.format(ina.power())
            values += '{0:0.10f};'.format(ina.shunt_voltage())
            stored_values.append(values)
            readClient.send(values.encode())
        except:
            print("Current to high")
            return
    mutex.release()


#main loop to wait on incoming msg
while 1:
    #connect to client
    print("waiting for client")
    client, addr = sock.accept();    
    try:
        while 1:
            #wait for msg
            print("waiting for next connection")
            content = client.recv(2048)
            if len(content) == 0:
                break
            else:
                sanitized_content = sanitize_output(content)
                print(sanitized_content)
                #start the collection process
                if("Start collecting" in sanitized_content):
                    start_values = (sanitized_content.split(":")[1]).split(",")
                    start_mode = True
                    mutex.acquire()
                    client.send(ack.encode());
                    #dont collect values while the work is initializing
                    sleep(2)
                    #start another thread that reads the GPIO
                    t = Thread(target = read_ina219, args = ())
                    t.start()
                    #start to collect means connection is closed from other side
                    client.close()
                    break
                elif ("Stop collecting" in sanitized_content):
                    #stop other task
                    mutex.release()
                    #sleep other task as to not cause issues with the writing to compute unit
                    sleep(10)
                    t.join()
                    #if one configuration is done tell client to switch modes
                    if (config_index == int(sys.argv[1])) or change_work:
                        if (cur_work_index == (len(work_files)-1) and cur_util_index == (len(cpu_utilization)-1)) or change_work:
                            change_work = False
                            print("Frequency switch")
                            client.send(freq_switch.encode());
                        else:
                            print("Config switch")
                            client.send(config_switch.encode());
                    else:
                        client.send(ack.encode());
                    inc_configuration()
                    start_mode = False
                elif ("Request config" in sanitized_content):
                    #if client crashed and requests config while the server is collecting data
                    #then restart
                    if(start_mode):
                        mutex.release()
                        t.join()
                        stored_values = []
                        start_mode = False
                    answer = str(cur_work_index) + "," + str(cpu_frequencies[cur_freq_index]) + ";"
                    client.send(answer.encode());
                    #close connection because esp32 needs to restart after resetting config
                    client.close();
                    break;
                elif ("Get work" in sanitized_content):
                    #if client crashed and requests config while the server is collecting data
                    #then restart
                    if(start_mode):
                        mutex.release()
                        t.join()
                        stored_values = []
                        start_mode = False
                    answer = str(cur_work_index) + "," + str(cpu_utilization[cur_util_index]) + ";"
                    client.send(answer.encode());
                elif("Brownout" in sanitized_content):
                    print("BROWNOUT DETECTED")
                else:
                    #if client crashed and requests config while the server is collecting data
                    #then restart
                    if(start_mode):
                        mutex.release()
                        t.join()
                        stored_values = []
                        start_mode = False
                    #split values and reformat to fit into csv file
                    #avg_value = avg_values(stored_values) 
                    got_entry = ""
                    entries = sanitized_content.split(";")
                    needed_values = ["work_task", "main", "IDLE", "IDLE"]
                    needed_values_2 = ["MIN_FREQ", "MAX_FREQ"]
                    appendix = ""
                    for needed_value in needed_values:
                        for entry in entries:
                            print(needed_value + " , " + entry);
                            if needed_value in entry:
                                appendix += "," + entry.split(",")[1] + "," + entry.split(",")[2]
                                #stored_values = [value + appendix for value in stored_values]
                                got_entry = entry
                                entries.remove(got_entry)
                                break
                    
                    for needed_value in needed_values_2:
                        for entry in entries:
                            print(needed_value + " , " + entry);
                            if needed_value in entry:
                                appendix += "," + entry.split(",")[1]
                                #stored_values = [value + appendix for value in stored_values]
                                got_entry = entry
                                entries.remove(got_entry)
                                break
                    
                    appendix = "c" + "," + work_files[cur_work_index] + "," + str(cpu_frequencies[cur_freq_index]) + "," + str(cpu_utilization[cur_util_index]) + appendix + ";"

                    client.send(ack.encode());
                    readClient.send(appendix.encode())
                    stored_values = []
                    config = str(readClient.recv(1024).decode())
                    print(config)
                    if(config[0] == 'y'):
                        change_work = True
                        cur_work_index = 0
                        cur_freq_index = int(config.split(",")[1])
                        cur_work_index = int(config.split(",")[2])
                        cur_util_index = int(config.split(",")[3])


    except KeyboardInterrupt:          
        #program is only stop-able through external cancel
        #so shut down socket to free the port if possible          
        print("Closing connection");
        sock.shutdown(socket.SHUT_RDWR);
        sock.close();
