import struct
import unittest
import json

import snap7.util

from app.main_window import parse_config
from app.plc_layout import TESTER_STATUS_BYTE, RESULTS_BYTE, DB_LAYOUT_END
from app.plc_results import encode_station_results
from app.service.plc_bridge_service import PlcService
from app.tcp_messages import encode_station_sn_codes


class PlcLayoutTests(unittest.TestCase):
    def test_sn_message_is_framed_and_preserves_station_order(self):
        data = encode_station_sn_codes(['A', 'B', 'C', 'D'])
        self.assertTrue(data.endswith(b'\n'))
        self.assertEqual(json.loads(data), {'type': 'station_sn_codes', 'sn_codes': ['A', 'B', 'C', 'D']})
        with self.assertRaises(ValueError):
            encode_station_sn_codes(['A'])

    def test_result_encoding_and_offsets(self):
        stations = [dict(station=i, round_id='r', forward='OK', reverse='NG',
                         forward_spl=12.5, reverse_spl=34.5) for i in range(1, 5)]
        data = encode_station_results(stations)
        self.assertEqual((TESTER_STATUS_BYTE, RESULTS_BYTE, DB_LAYOUT_END), (132, 134, 182))
        self.assertEqual(len(data), 48)
        for i in range(4):
            self.assertEqual(struct.unpack_from('>hfhf', data, i * 12), (1, 12.5, 0, 34.5))

    def test_read_four_strings_and_reject_bad_header(self):
        class Client:
            def __init__(self):
                self.data = bytearray(128)
                for i in range(4):
                    field = bytearray(32)
                    snap7.util.set_string(field, 0, f'SN{i + 1}', 30)
                    self.data[i * 32:(i + 1) * 32] = field

            def db_read(self, db, start, size):
                self.args = db, start, size
                return self.data

        service = PlcService('127.0.0.1', 0, 1, 1, 0, 2)
        service.client = Client()
        self.assertEqual(service.read_station_sn_codes(), ['SN1', 'SN2', 'SN3', 'SN4'])
        self.assertEqual(service.client.args, (1, 4, 128))
        service.client.data[0] = 20
        with self.assertRaises(ValueError):
            service.read_station_sn_codes()

    def test_reject_input_address_overlapping_new_layout(self):
        config = dict(plc_ip='127.0.0.1', rack='0', slot='1', db='1', heartbeat_byte='0',
                      command_byte='2', interval='200', a_host='127.0.0.1', a_port='9000')
        parse_config(config)
        config['command_byte'] = '134'
        with self.assertRaises(ValueError):
            parse_config(config)


if __name__ == '__main__':
    unittest.main()
