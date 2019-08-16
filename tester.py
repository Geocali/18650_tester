import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM) # GPIO Numbers instead of board numbers

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

import pandas as pd
import time


def close_relay(slot_id, slot_infos):
    # ==== close the relay ====
    RELAY_GPIO = slot_infos[slot_id]["relay_gpio"]
    # GPIO Assign mode
    GPIO.setup(RELAY_GPIO, GPIO.OUT)
    # close the relay
    GPIO.output(RELAY_GPIO, GPIO.LOW)
    slot_infos[slot_id]["relay_open"] = False
    time.sleep(0.5)
    return

def open_relay(slot_id, slot_infos):
    # ==== close the relay ====
    RELAY_GPIO = slot_infos[slot_id]["relay_gpio"]
    # GPIO Assign mode
    GPIO.setup(RELAY_GPIO, GPIO.OUT)
    # close the relay
    GPIO.output(RELAY_GPIO, GPIO.HIGH)
    slot_infos[slot_id]["relay_open"] = True
    time.sleep(0.5)
    return

def read_voltage(slot_id, slot_infos, mcp):
    # create a differential ADC channel between Pin 0 and Pin 1
    pin0 = slot_infos[slot_id]["mcp_pin0"]
    pin1 = slot_infos[slot_id]["mcp_pin1"]
    time.sleep(0.1)
    return AnalogIn(mcp, pin0, pin1).voltage

def read_all_voltages_t(slot_infos, mcp):
    for slot_id in list(slot_infos.keys()):
        close_relay(slot_id, slot_infos)
        time.sleep(0.1)
        voltage = read_voltage(slot_id, slot_infos, mcp)
        open_relay(slot_id, slot_infos)
        print('Voltage batt ' + str(slot_id) + ": " + str(voltage) + 'V')

slot_infos = {
    1: {"relay_gpio":5, "mcp_pin0": MCP.P0, "mcp_pin1": MCP.P1, "relay_open": True, "testing": False},
    2: {"relay_gpio":6, "mcp_pin0": MCP.P2, "mcp_pin1": MCP.P3, "relay_open": True, "testing": False},
    3: {"relay_gpio":13, "mcp_pin0": MCP.P4, "mcp_pin1": MCP.P5, "relay_open": True, "testing": False},
    4: {"relay_gpio":19, "mcp_pin0": MCP.P6, "mcp_pin1": MCP.P7, "relay_open": True, "testing": False}
}

# ==== MCP3008 hardware SPI configuration ====
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
# create the cs (chip select)
cs = digitalio.DigitalInOut(board.CE0)
# create the mcp object (harware option)
mcp = MCP.MCP3008(spi, cs)


# ==== beginning of the capacity measure ====

# voltage under which we consider the battery as discharged
discharged_voltage = 1
# voltage above which we consider the battery as new
min_charged_voltage = 4
# value of the resistor
R = 4 # Ohm

# close all the relays of the slots containing a charged battery
df_slots_history = pd.DataFrame()
for slot_id in list(slot_infos.keys()):
    voltage = read_voltage(slot_id, slot_infos, mcp)
    
    # we record it
    slot_measure = pd.Series(
        data=[datetime.now, slot_id, voltage, slot_infos[slot_id]['relay_open'], False, 0],
        index=['time', 'slot_id', 'voltage', 'relay_open', 'testing', 'testing_session']
    )
    df_slots_history = df_slots_history.append(slot_measure)

    # if the battery is charged, we test it
    if voltage > min_charged_voltage:
        close_relay(slot_id, slot_infos)
    
        # we record it (we read the voltage again, in case the relay is closed)
        voltage = read_voltage(slot_id, slot_infos, mcp)
        slot_measure = pd.Series(
            data=[datetime.now, slot_id, voltage, slot_infos[slot_id]['relay_open'], True, 0],
            index=['time', 'slot_id', 'voltage', 'relay_open', 'testing', 'testing_session']
        )
        df_slots_history = df_slots_history.append(slot_measure)
        

# main loop
i = 0
while i < 3:
    for slot_id in list(slot_infos.keys()):
        # we read the voltage of the battery
        voltage = read_voltage(slot_id, slot_infos, mcp)
        last_measure = df_slots_history[df_slots_history.slot_id == slot_id].tail(1)
        
        # Case 1
        # - the preceding voltage was > discharged_voltage
        # - and current voltage < discharged_voltage
        # - and the battery is under testing
        # we send the conclusions and open the relay
        if (last_measure.voltage > discharged_voltage) and (voltage < discharged_voltage) and last_measure.testing:
            # we calculate the total capacity
            df_testing_session = df_slots_history[
                (df_slots_history.slot_id == slot_id)
                && (df_slots_history.testing_session == last_measure.testing_session)
            ]
            battery_capacity = df_testing_session.voltage.sum() / R / 3600 / 1000
            print('battery ' + str(slot_id) ' tested at ' + str(battery_capacity) + ' mAh')
            
            open_relay(slot_id, slot_infos)
            
            slot_measure = pd.Series(
                data=[datetime.now, slot_id, voltage, slot_infos[slot_id]['relay_open'], False, last_measure.testing_session + 1],
                index=['time', 'slot_id', 'voltage', 'relay_open', 'testing', 'testing_session']
            )
            df_slots_history = df_slots_history.append(slot_measure)
            
        # Case 2
        # if the preceding voltage was < discharged_voltage and now > discharged_voltage
        # this is the case when we open the relay
        # the battery should not be under testing, so we don't do anything
        
        # Case 3
        # if the preceding voltage was > 0(+delta) and now we have 0(+delta)
        # this means that the battery was removed from the slot
        # - the battery was under testing: don't send any conclusion about the capacity, reset
        # - the battery was already tested: reset
        
        # Case 4
        # if the preceding voltage was 0(+delta) and now we have > 0(+delta)
        # this means that a battery was inserted in the slot
        # - the voltage is > min_charged_voltage: the battery is charged, we test it
        # - the voltage is < min_charged_voltage: the battery is not fully charged, we don't test it
        #   a warning shall be sent, only once
        
        slots_history[slot_id]['voltages'].append(voltage)
        print('batt ' + str(slot_id) + ": " + str(voltage))
        
    time.sleep(1)
    i += 1
print(slots_history)

# for each battery
# while the voltage > 3V, record the voltages
# when voltage < 3V, open the relay of this battery, and send the total capacity

# open all the relays
for slot_id in list(slot_infos.keys()):
    open_relay(slot_id, slot_infos)
    time.sleep(0.5)
    
print(df_slots_history)