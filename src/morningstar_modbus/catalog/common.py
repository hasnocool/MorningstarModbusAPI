# src/morningstar_modbus/catalog/common.py
"""Shared Morningstar state and fault/alarm dictionaries."""

TRISTAR_MPPT_CHARGE_STATES = (
    (0, "START"),
    (1, "NIGHT_CHECK"),
    (2, "DISCONNECT"),
    (3, "NIGHT"),
    (4, "FAULT"),
    (5, "MPPT"),
    (6, "ABSORPTION"),
    (7, "FLOAT"),
    (8, "EQUALIZE"),
    (9, "SLAVE"),
)

PWM_CHARGE_STATES = (
    (0, "START"),
    (1, "NIGHT_CHECK"),
    (2, "DISCONNECT"),
    (3, "NIGHT"),
    (4, "FAULT"),
    (5, "BULK"),
    (6, "ABSORPTION"),
    (7, "FLOAT"),
    (8, "EQUALIZE"),
)

PROSTAR_MPPT_CHARGE_STATES = TRISTAR_MPPT_CHARGE_STATES + ((10, "FIXED"),)

LOAD_STATES = (
    (0, "START"),
    (1, "LOAD_ON"),
    (2, "LVD_WARNING"),
    (3, "LVD"),
    (4, "FAULT"),
    (5, "DISCONNECT"),
)

TRISTAR_MPPT_FAULTS = (
    (0, "overcurrent"),
    (1, "fets_shorted"),
    (2, "software"),
    (3, "battery_hvd"),
    (4, "array_hvd"),
    (5, "settings_switch_changed"),
    (6, "custom_settings_edit"),
    (7, "rts_shorted"),
    (8, "rts_disconnected"),
    (9, "eeprom_retry_limit"),
    (11, "slave_control_timeout"),
)

TRISTAR_MPPT_ALARMS = (
    (0, "rts_open"),
    (1, "rts_shorted"),
    (2, "rts_disconnected"),
    (3, "heatsink_sensor_open"),
    (4, "heatsink_sensor_shorted"),
    (5, "high_temperature_current_limit"),
    (6, "current_limit"),
    (7, "current_offset"),
    (8, "battery_sense_out_of_range"),
    (9, "battery_sense_disconnected"),
    (10, "uncalibrated"),
    (11, "rts_miswire"),
    (12, "hvd"),
    (14, "system_miswire"),
    (15, "mosfet_open"),
    (16, "p12_voltage_off"),
    (17, "high_input_voltage_current_limit"),
    (18, "adc_input_max"),
    (19, "controller_reset"),
)

PROSTAR_ALARMS = (
    (0, "rts_open"),
    (1, "rts_short"),
    (2, "rts_disconnected"),
    (3, "heatsink_sensor_open"),
    (4, "heatsink_sensor_short"),
    (5, "heatsink_hot"),
    (6, "current_limit"),
    (7, "current_offset"),
    (8, "battery_sense_out_of_range"),
    (9, "battery_sense_disconnected"),
    (10, "uncalibrated"),
    (11, "battery_temperature_out_of_range"),
    (12, "fp10_supply"),
    (13, "fet_open"),
    (14, "array_current_offset"),
    (15, "load_current_offset"),
    (16, "3v_supply"),
    (19, "controller_reset"),
    (20, "lvd"),
    (21, "log_timeout"),
    (22, "eeprom_failure"),
)

PROSTAR_MPPT_ARRAY_FAULTS = (
    (0, "overcurrent_phase_1"),
    (1, "fet_shorted"),
    (2, "software"),
    (3, "battery_hvd"),
    (4, "array_hvd"),
    (5, "eeprom_edit"),
    (6, "rts_shorted"),
    (7, "rts_disconnected"),
    (8, "local_temp_sensor_failed"),
    (9, "battery_lvd"),
    (10, "slave_timeout"),
    (11, "dip_changed"),
)

LOAD_FAULTS = (
    (0, "external_short"),
    (1, "overcurrent"),
    (2, "fet_shorted"),
    (3, "software"),
    (4, "hvd"),
    (5, "heatsink_overtemp"),
    (6, "settings_changed"),
)

SUNSAVER_MPPT_ALARMS = (
    (0, "rts_open"),
    (1, "rts_short"),
    (2, "rts_disconnected"),
    (3, "heatsink_sensor_open"),
    (4, "heatsink_sensor_short"),
    (5, "heatsink_hot"),
    (6, "current_limit"),
    (7, "current_offset"),
    (10, "uncalibrated"),
    (11, "rts_miswire"),
    (14, "system_miswire"),
    (15, "fet_open"),
    (16, "p12_voltage_off"),
    (17, "high_array_voltage_current_limit"),
)

SURESINE_CLASSIC_LOAD_STATES = (
    (0, "STARTUP"),
    (1, "LOAD_ON"),
    (2, "LVD_WARNING"),
    (3, "LVD"),
    (4, "FAULT"),
    (5, "LOAD_DISCONNECTED"),
    (6, "LOAD_OFF"),
    (8, "STANDBY"),
)

SURESINE_GEN2_LED_STATES = (
    (0, "ALL_OFF"),
    (1, "OK_OFF"),
    (2, "OK_ON"),
    (3, "OK_STANDBY"),
    (4, "LVD_WARNING"),
    (5, "LVD_OFF"),
    (6, "CRITICAL_FAULT_RESET"),
    (7, "FAULT_OFF"),
)
